"""
notion_ingest.py
================
Notion → Qdrant + SQLite ingestion pipeline for Market Intelligence Tool.

What it does:
  1. Reads your Notion database (Data Sources)
  2. For each entry: extracts metadata + page content
  3. Downloads PDFs/XLSX from Recent Link if available
  4. Chunks all text content
  5. Embeds with BAAI/bge-small-en (matches your existing setup)
  6. Upserts vectors into Qdrant (collection: adept_database)
  7. Writes Master + routing table rows into SQLite

Usage:
  python notion_ingest.py
  python notion_ingest.py --dry-run          # Preview without writing
  python notion_ingest.py --source "Annual Economic Survey"  # Single entry
"""

import os
import re
import uuid
import json
import time
import logging
import sqlite3
import argparse
import hashlib
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import requests
import urllib3
urllib3.disable_warnings()
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

# ── Optional PDF / XLSX parsers ───────────────────────────────────────────────
try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import openpyxl
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config (mirrors agent_manager.py exactly) ─────────────────────────────────
QDRANT_HOST       = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT       = int(os.getenv("QDRANT_PORT", 7000))
COLLECTION_NAME   = "adept_database"
EMBEDDING_MODEL   = "BAAI/bge-small-en"
VECTOR_SIZE       = 384          # bge-small-en output dimension

current_dir   = Path(__file__).parent
DATABASE_PATH = os.getenv("DATABASE_PATH") or str(current_dir / "DB" / "market-intelligence.db")

# Notion
NOTION_API_KEY   = os.getenv("NOTION_API_KEY")
NOTION_DB_ID     = os.getenv("NOTION_DATABASE_ID")   # set after setup step below
NOTION_VERSION   = "2022-06-28"
NOTION_BASE_URL  = "https://api.notion.com/v1"

# Chunking
CHUNK_SIZE       = 800    # characters per chunk
CHUNK_OVERLAP    = 100

# ─────────────────────────────────────────────────────────────────────────────
# 1. Embedding model (singleton, same as agent_manager.py)
# ─────────────────────────────────────────────────────────────────────────────
_EMBEDDING_MODEL = None

def get_embedding_model() -> SentenceTransformer:
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL)
    return _EMBEDDING_MODEL


def embed(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Qdrant helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection(client: QdrantClient):
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        logger.info("Creating Qdrant collection: %s", COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    else:
        logger.info("Qdrant collection '%s' already exists.", COLLECTION_NAME)


def upsert_points(client: QdrantClient, points: list[PointStruct]):
    if not points:
        return
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("  → Upserted %d Qdrant point(s).", len(points))


# ─────────────────────────────────────────────────────────────────────────────
# 3. SQLite helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_db_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_master_table(conn: sqlite3.Connection):
    """Create the Master table if it doesn't exist (mirrors existing schema)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Master (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            Title       TEXT,
            Source      TEXT,
            Summary     TEXT,
            Datatype    TEXT,
            Sectors     TEXT,
            table_name  TEXT UNIQUE,
            notion_id   TEXT UNIQUE,
            ingested_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def ensure_routing_table(conn: sqlite3.Connection, table_name: str):
    """Create a routing table for a data source if it doesn't exist."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_index     INTEGER,
            chunk_text      TEXT,
            qdrant_point_id TEXT,
            source_url      TEXT,
            file_type       TEXT,
            ingested_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def upsert_master_row(conn: sqlite3.Connection, row: dict) -> int:
    """Insert or update a Master row. Returns the row id."""
    conn.execute("""
        INSERT INTO Master (Title, Source, Summary, Datatype, Sectors, table_name, notion_id)
        VALUES (:Title, :Source, :Summary, :Datatype, :Sectors, :table_name, :notion_id)
        ON CONFLICT(notion_id) DO UPDATE SET
            Title      = excluded.Title,
            Source     = excluded.Source,
            Summary    = excluded.Summary,
            Datatype   = excluded.Datatype,
            Sectors    = excluded.Sectors,
            table_name = excluded.table_name
    """, row)
    conn.commit()
    cur = conn.execute("SELECT id FROM Master WHERE notion_id = ?", (row["notion_id"],))
    return cur.fetchone()[0]


def insert_routing_row(conn: sqlite3.Connection, table_name: str, row: dict):
    conn.execute(f"""
        INSERT INTO "{table_name}" (chunk_index, chunk_text, qdrant_point_id, source_url, file_type)
        VALUES (:chunk_index, :chunk_text, :qdrant_point_id, :source_url, :file_type)
    """, row)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Notion API helpers
# ─────────────────────────────────────────────────────────────────────────────
def _notion_headers() -> dict:
    if not NOTION_API_KEY:
        raise EnvironmentError(
            "NOTION_API_KEY is not set. See setup instructions at the top of this file."
        )
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_notion_database_pages() -> list[dict]:
    """Fetch all pages from the Notion database (handles pagination)."""
    if not NOTION_DB_ID:
        raise EnvironmentError(
            "NOTION_DATABASE_ID is not set. "
            "Run with --setup to get your database ID, or set it in .env"
        )

    pages = []
    url = f"{NOTION_BASE_URL}/databases/{NOTION_DB_ID}/query"
    payload = {"page_size": 100}

    while True:
        resp = requests.post(url, headers=_notion_headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
        time.sleep(0.3)   # gentle rate limiting

    logger.info("Fetched %d pages from Notion.", len(pages))
    return pages


def extract_page_metadata(page: dict) -> dict:
    """
    Parse Notion page properties into a flat dict.
    Adjust property names here if yours differ — these match the screenshots.
    """
    props = page.get("properties", {})

    def _text(prop_name: str) -> str:
        prop = props.get(prop_name, {})
        ptype = prop.get("type", "")
        if ptype == "title":
            return "".join(t["plain_text"] for t in prop.get("title", []))
        if ptype == "rich_text":
            return "".join(t["plain_text"] for t in prop.get("rich_text", []))
        if ptype == "select":
            sel = prop.get("select")
            return sel["name"] if sel else ""
        if ptype == "multi_select":
            return ", ".join(s["name"] for s in prop.get("multi_select", []))
        if ptype == "url":
            return prop.get("url") or ""
        return ""

    title    = _text("Data") or _text("Name") or _text("Title") or "Untitled"
    source   = _text("Source")
    summary  = _text("Summary")
    datatype = _text("Data Type")
    sectors  = _text("Relevant Sectors")
    link     = _text("Recent Link")
    filetype = _text("API Filetype")
    blockers = _text("Blockers")

    # Derive a safe SQLite table name from the title
    safe_name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
    table_name = f"route_{safe_name}"

    return {
        "notion_id":   page["id"],
        "Title":       title,
        "Source":      source,
        "Summary":     summary,
        "Datatype":    datatype,
        "Sectors":     sectors,
        "link":        link,
        "filetype":    filetype,
        "blockers":    blockers,
        "table_name":  table_name,
    }


def fetch_notion_page_blocks(page_id: str) -> str:
    """Recursively fetch all text content from a Notion page's blocks."""
    texts = []
    url = f"{NOTION_BASE_URL}/blocks/{page_id}/children"
    params = {"page_size": 100}

    while True:
        resp = requests.get(url, headers=_notion_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            btype = block.get("type", "")
            content = block.get(btype, {})

            # Extract rich text from common block types
            if "rich_text" in content:
                chunk = "".join(t["plain_text"] for t in content["rich_text"])
                if chunk.strip():
                    texts.append(chunk)

            # Recurse into child blocks (e.g. toggle, columns)
            if block.get("has_children"):
                child_text = fetch_notion_page_blocks(block["id"])
                if child_text:
                    texts.append(child_text)

        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
        time.sleep(0.2)

    return "\n".join(texts)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Document downloaders
# ─────────────────────────────────────────────────────────────────────────────
def download_file(url: str) -> Optional[bytes]:
    """Download a file from a URL. Returns raw bytes or None on failure."""
    if not url or not url.startswith("http"):
        return None
    try:
        resp = requests.get(url, timeout=60, stream=True, verify=False)
        resp.raise_for_status()
        data = b"".join(resp.iter_content(chunk_size=8192))
        logger.info("  Downloaded %d bytes from %s", len(data), url)
        return data
    except Exception as e:
        logger.warning("  Failed to download %s: %s", url, e)
        return None


def extract_pdf_text(data: bytes) -> str:
    """Extract all text from a PDF (bytes)."""
    if not HAS_PDF:
        logger.warning("pdfplumber not installed. Skipping PDF extraction.")
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        pages_text = []
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
        return "\n".join(pages_text)
    finally:
        os.unlink(tmp_path)


def extract_xlsx_text(data: bytes) -> str:
    """Extract all cell values from an XLSX file as plain text."""
    if not HAS_XLSX:
        logger.warning("openpyxl not installed. Skipping XLSX extraction.")
        return ""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        rows = []
        for sheet in wb.worksheets:
            rows.append(f"[Sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                line = "\t".join(cells).strip()
                if line:
                    rows.append(line)
        return "\n".join(rows)
    finally:
        os.unlink(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Text chunker
# ─────────────────────────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# 7. Core ingestion logic per page
# ─────────────────────────────────────────────────────────────────────────────
def ingest_page(
    meta: dict,
    page_content: str,
    qdrant: QdrantClient,
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> int:
    """
    Ingest one Notion page (metadata + content + optional PDF/XLSX).
    Returns the number of Qdrant points upserted.
    """
    title      = meta["Title"]
    notion_id  = meta["notion_id"]
    link       = meta.get("link", "")
    filetype   = meta.get("filetype", "").upper()
    table_name = meta["table_name"]

    logger.info("── Ingesting: %s", title)

    # ── Collect all text to embed ──────────────────────────────────────────
    text_sources: list[tuple[str, str, str]] = []  # (text, source_url, file_type)

    # A) Notion page body content
    if page_content.strip():
        text_sources.append((page_content, f"notion://{notion_id}", "notion"))

    # B) Summary as a standalone searchable chunk
    if meta.get("Summary"):
        summary_text = (
            f"Title: {title}\n"
            f"Summary: {meta['Summary']}\n"
            f"Sectors: {meta.get('Sectors', '')}\n"
            f"Data Type: {meta.get('Datatype', '')}\n"
            f"Source: {meta.get('Source', '')}\n"
        )
        text_sources.append((summary_text, link or f"notion://{notion_id}", "metadata"))

    # C) Download and extract PDF / XLSX
    if link and link.startswith("http"):
        # Helper inline to fetch and resolve if HTML
        def fetch_link_bytes(url: str, required_type: str) -> tuple[Optional[bytes], str]:
            b = download_file(url)
            if not b: return None, url
            # Check if it looks like HTML and it's not explicitly downloading an HTML (though we only extract pdf/xlsx)
            b_lower = b[:200].lower()
            if b"<!doctype" in b_lower or b"<html" in b_lower:
                logger.info("  Link returned HTML, looking for %s link inside...", required_type)
                try:
                    soup = BeautifulSoup(b, "html.parser")
                    # Naively find first link matching extension
                    ext = ".pdf" if required_type == "pdf" else ".xlsx"
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if ext in href.lower() or (".xls" in href.lower() and ext == ".xlsx"):
                            full_url = urljoin(url, href)
                            logger.info("  Found embedded link: %s", full_url)
                            return download_file(full_url), full_url
                except Exception as e:
                    logger.warning("  Failed to parse HTML for links: %s", e)
            return b, url

        if "PDF" in filetype or "PDF" in link.upper() or link.lower().endswith(".pdf"):
            file_bytes, final_url = fetch_link_bytes(link, "pdf")
            if file_bytes:
                extracted = extract_pdf_text(file_bytes)
                if extracted:
                    text_sources.append((extracted, final_url, "pdf"))
        elif "XLS" in filetype or "EXCEL" in filetype or "XLS" in link.upper() or link.lower().endswith((".xlsx", ".xls")):
            file_bytes, final_url = fetch_link_bytes(link, "xlsx")
            if file_bytes:
                extracted = extract_xlsx_text(file_bytes)
                if extracted:
                    text_sources.append((extracted, final_url, "xlsx"))


    if not text_sources:
        logger.warning("  No text content found for '%s'. Skipping.", title)
        return 0

    # ── Chunk → embed → upsert ─────────────────────────────────────────────
    if not dry_run:
        ensure_routing_table(conn, table_name)

    all_points: list[PointStruct] = []
    total_chunks = 0

    for raw_text, source_url, ftype in text_sources:
        chunks = chunk_text(raw_text)
        if not chunks:
            continue

        vectors = embed(chunks)

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())

            payload = {
                "text":          chunk,
                "source":        source_url,
                "title":         title,
                "sectors":       meta.get("Sectors", ""),
                "data_type":     meta.get("Datatype", ""),
                "notion_id":     notion_id,
                "routing_table": table_name,
                "file_type":     ftype,
                "chunk_index":   total_chunks + i,
            }

            all_points.append(PointStruct(id=point_id, vector=vector, payload=payload))

            if not dry_run:
                insert_routing_row(conn, table_name, {
                    "chunk_index":     total_chunks + i,
                    "chunk_text":      chunk[:500],   # preview in DB
                    "qdrant_point_id": point_id,
                    "source_url":      source_url,
                    "file_type":       ftype,
                })

        total_chunks += len(chunks)

    if not dry_run:
        # Batch upsert (max 100 at a time to stay safe)
        for batch_start in range(0, len(all_points), 100):
            upsert_points(qdrant, all_points[batch_start:batch_start + 100])
    else:
        logger.info("  [DRY RUN] Would upsert %d chunks for '%s'", len(all_points), title)

    return len(all_points)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Main runner
# ─────────────────────────────────────────────────────────────────────────────
def run_ingestion(filter_title: Optional[str] = None, dry_run: bool = False):
    logger.info("=" * 60)
    logger.info("Notion → Qdrant Ingestion Pipeline")
    logger.info("Qdrant:   %s:%d  |  Collection: %s", QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME)
    logger.info("Database: %s", DATABASE_PATH)
    logger.info("Dry run:  %s", dry_run)
    logger.info("=" * 60)

    # Setup clients
    qdrant = get_qdrant_client()
    conn   = get_db_conn()

    if not dry_run:
        ensure_collection(qdrant)
        ensure_master_table(conn)

    # Fetch all pages
    pages = fetch_notion_database_pages()

    total_points   = 0
    skipped_pages  = 0

    for page in pages:
        meta = extract_page_metadata(page)

        # Optional single-source filter
        if filter_title and filter_title.lower() not in meta["Title"].lower():
            continue

        # Skip entries marked as redundant (Blockers field)
        if "redundant" in (meta.get("blockers") or "").lower():
            logger.info("  Skipping '%s' — marked as redundant.", meta["Title"])
            skipped_pages += 1
            continue

        # Write Master row
        if not dry_run:
            upsert_master_row(conn, {
                "Title":       meta["Title"],
                "Source":      meta["Source"],
                "Summary":     meta["Summary"],
                "Datatype":    meta["Datatype"],
                "Sectors":     meta["Sectors"],
                "table_name":  meta["table_name"],
                "notion_id":   meta["notion_id"],
            })

        # Fetch Notion page body text
        page_content = ""
        try:
            page_content = fetch_notion_page_blocks(meta["notion_id"])
        except Exception as e:
            logger.warning("  Could not fetch page blocks for '%s': %s", meta["Title"], e)

        # Ingest
        n = ingest_page(meta, page_content, qdrant, conn, dry_run=dry_run)
        total_points += n
        time.sleep(0.3)   # polite rate limiting

    logger.info("=" * 60)
    logger.info("Done. %d Qdrant points upserted. %d pages skipped.", total_points, skipped_pages)
    logger.info("=" * 60)
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Notion setup helper
# ─────────────────────────────────────────────────────────────────────────────
def setup_notion():
    """
    Interactively help the user find their Notion Database ID.
    """
    print("\n" + "=" * 60)
    print("  NOTION INTEGRATION SETUP")
    print("=" * 60)
    print("""
STEP 1 — Create a Notion Integration
──────────────────────────────────────
  1. Go to https://www.notion.so/my-integrations
  2. Click "New integration"
  3. Name it (e.g., "Market Intelligence Ingest")
  4. Select your workspace
  5. Click Submit
  6. Copy the "Internal Integration Secret" (starts with ntn_ or secret_)
  7. Add it to your .env:
       NOTION_API_KEY=ntn_xxxxxxxxxxxx

STEP 2 — Share your Database with the Integration
──────────────────────────────────────────────────
  1. Open your "Data Sources (1)" database in Notion
  2. Click the ••• menu (top right) → Connections → Connect to
  3. Select your integration name
  4. Confirm

STEP 3 — Get your Database ID
──────────────────────────────────────────────────
  Your Notion URL looks like:
    https://www.notion.so/3139c57e888b8090bc8adcd35004832a?v=...
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                           This is your DATABASE ID

  From your screenshots, your Database ID appears to be:
    3139c57e888b8090bc8adcd35004832a

  Add it to your .env:
    NOTION_DATABASE_ID=3139c57e888b8090bc8adcd35004832a

STEP 4 — Install dependencies
──────────────────────────────────────────────────
  pip install notion-client requests pdfplumber openpyxl sentence-transformers qdrant-client python-dotenv

STEP 5 — Run the pipeline
──────────────────────────────────────────────────
  python notion_ingest.py --dry-run     # preview first
  python notion_ingest.py               # full ingestion
""")
    print("=" * 60)  

    if NOTION_API_KEY:
        print(f"✓ NOTION_API_KEY is set ({NOTION_API_KEY[:12]}...)")
    else:
        print("✗ NOTION_API_KEY is NOT set in .env")

    if NOTION_DB_ID:
        print(f"✓ NOTION_DATABASE_ID is set: {NOTION_DB_ID}")
    else:
        print("✗ NOTION_DATABASE_ID is NOT set in .env")

    # Try listing databases to verify connection
    if NOTION_API_KEY:
        print("\nTesting Notion connection...")
        try:
            resp = requests.post(
                f"{NOTION_BASE_URL}/search",
                headers=_notion_headers(),
                json={"filter": {"value": "database", "property": "object"}, "page_size": 10},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                print(f"\nFound {len(results)} accessible database(s):")
                for db in results:
                    title_parts = db.get("title", [])
                    db_title = "".join(t["plain_text"] for t in title_parts) if title_parts else "Untitled"
                    print(f"  • {db_title}  →  ID: {db['id']}")
                print("\nCopy the ID of your 'Data Sources' database into .env as NOTION_DATABASE_ID")
            else:
                print("No databases found. Make sure you've shared the database with your integration (Step 2).")
        except Exception as e:
            print(f"Connection failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notion → Qdrant ingestion pipeline")
    parser.add_argument("--setup",   action="store_true", help="Show Notion setup instructions and test connection")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Qdrant or SQLite")
    parser.add_argument("--source",  type=str, default=None, help="Only ingest entries matching this title")
    args = parser.parse_args()

    if args.setup:
        setup_notion()
    else:
        run_ingestion(filter_title=args.source, dry_run=args.dry_run)