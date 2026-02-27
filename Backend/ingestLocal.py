"""
ingestLocal.py
================
Local Data (CSV + Markdown) → Qdrant + SQLite ingestion pipeline for Market Intelligence Tool.

What it does:
  1. Reads a CSV export from Notion (Data Sources)
  2. For each row: extracts metadata
  3. Finds the matching Markdown file for page content
  4. Downloads PDFs/XLSX from Recent Link if available
  5. Chunks all text content
  6. Embeds with BAAI/bge-small-en (matches your existing setup)
  7. Upserts vectors into Qdrant (collection: adept_database)
  8. Writes Master + routing table rows into SQLite

Usage:
  python ingestLocal.py --dir "C:/path/to/extracted/export"
  python ingestLocal.py --dir "C:/path/to/extracted/export" --dry-run
"""

import os
import re
import uuid
import csv
import time
import hashlib
import logging
import sqlite3
import argparse
import tempfile
from pathlib import Path
from typing import Optional

import requests
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
            ingested_at TEXT DEFAULT (datetime('now'))
        )
    """)
    try:
        conn.execute("ALTER TABLE Master ADD COLUMN notion_id TEXT")
    except Exception as e:
        logger.warning(f"  Could not add notion_id column (perhaps it already exists): {e}")
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
# 4. Document downloaders
# ─────────────────────────────────────────────────────────────────────────────
def download_file(url: str) -> Optional[bytes]:
    """Download a file from a URL. Returns raw bytes or None on failure."""
    if not url or not url.startswith("http"):
        return None
    try:
        resp = requests.get(url, timeout=60, stream=True)
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
    except Exception as e:
        logger.warning(f"  Failed to parse PDF: {e}")
        return ""
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
    except Exception as e:
        logger.warning(f"  Failed to parse XLSX: {e}")
        return ""
    finally:
        os.unlink(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Text chunker
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
# 6. Local extraction helpers
# ─────────────────────────────────────────────────────────────────────────────
def find_markdown_file(title: str, export_dir: str) -> Optional[str]:
    """Finds a matching markdown file for a given title in the export directory."""
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    
    if not os.path.exists(export_dir):
        return None
        
    for filename in os.listdir(export_dir):
        if filename.endswith(".md"):
            if safe_title.lower() in filename.lower():
                return os.path.join(export_dir, filename)
                
    return None

def extract_markdown_content(md_path: str) -> str:
    """Reads the markdown file and strips the properties section at the top."""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        content_lines = []
        is_content = False
        
        for i, line in enumerate(lines):
            if i == 0 and line.startswith("# "):
                continue # Skip title
                
            if not is_content:
                if ":" in line and len(line.split(":", 1)[0].split()) <= 3:
                    continue
                if line.strip() == "":
                    continue
                    
                is_content = True
                
            if is_content:
                content_lines.append(line)
                
        return "".join(content_lines).strip()
    except Exception as e:
        logger.warning(f"Failed to read markdown {md_path}: {e}")
        return ""


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
    Ingest one entry (metadata + content + optional PDF/XLSX).
    Returns the number of Qdrant points upserted.
    """
    title      = meta["Title"]
    notion_id  = meta["notion_id"]
    link       = meta.get("link", "")
    filetype   = meta.get("filetype", "").upper()
    table_name = meta["table_name"]

    logger.info("── Ingesting: %s", title)

    text_sources: list[tuple[str, str, str]] = []  # (text, source_url, file_type)

    # A) Body content
    if page_content.strip():
        text_sources.append((page_content, f"local://{notion_id}", "markdown"))

    # B) Summary as a standalone searchable chunk
    if meta.get("Summary"):
        summary_text = (
            f"Title: {title}\n"
            f"Summary: {meta['Summary']}\n"
            f"Sectors: {meta.get('Sectors', '')}\n"
            f"Data Type: {meta.get('Datatype', '')}\n"
            f"Source: {meta.get('Source', '')}\n"
        )
        text_sources.append((summary_text, link or f"local://{notion_id}", "metadata"))

    # C) Download and extract PDF / XLSX
    if link and link.startswith("http"):
        file_bytes = download_file(link)
        if file_bytes:
            if "PDF" in filetype or "PDF" in link.upper() or link.lower().endswith(".pdf"):
                extracted = extract_pdf_text(file_bytes)
                if extracted:
                    text_sources.append((extracted, link, "pdf"))
            elif "XLSX" in filetype or "EXCEL" in filetype or "XLS" in link.upper() or link.lower().endswith((".xlsx", ".xls")):
                extracted = extract_xlsx_text(file_bytes)
                if extracted:
                    text_sources.append((extracted, link, "xlsx"))

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
        for batch_start in range(0, len(all_points), 100):
            upsert_points(qdrant, all_points[batch_start:batch_start + 100])
    else:
        logger.info("  [DRY RUN] Would upsert %d chunks for '%s'", len(all_points), title)

    return len(all_points)

# ─────────────────────────────────────────────────────────────────────────────
# 8. Main runner
# ─────────────────────────────────────────────────────────────────────────────
def run_ingestion(export_dir: str, filter_title: Optional[str] = None, dry_run: bool = False):
    logger.info("=" * 60)
    logger.info("Local Export → Qdrant Ingestion Pipeline")
    logger.info("Export Dir: %s", export_dir)
    logger.info("Qdrant:     %s:%d  |  Collection: %s", QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME)
    logger.info("Database:   %s", DATABASE_PATH)
    logger.info("Dry run:    %s", dry_run)
    logger.info("=" * 60)

    qdrant = get_qdrant_client()
    conn   = get_db_conn()

    if not dry_run:
        ensure_collection(qdrant)
        ensure_master_table(conn)

    # Find the CSV file
    csv_file = None
    for filename in os.listdir(export_dir):
        if filename.endswith(".csv"):
            if "_all.csv" not in filename:
                csv_file = os.path.join(export_dir, filename)
                break
    
    if not csv_file:
        logger.error("No CSV file found in export directory!")
        return

    logger.info("Reading CSV: %s", csv_file)

    total_points   = 0
    skipped_pages  = 0

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("Data", "").strip() or row.get("Name", "").strip() or row.get("Title", "").strip()
            if not title:
                continue

            if filter_title and filter_title.lower() not in title.lower():
                continue

            blockers = row.get("Blockers", "")
            if "redundant" in blockers.lower():
                logger.info("  Skipping '%s' — marked as redundant.", title)
                skipped_pages += 1
                continue

            notion_id = hashlib.md5(title.encode('utf-8')).hexdigest()

            safe_name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
            table_name = f"route_{safe_name}"

            meta = {
                "notion_id":   notion_id,
                "Title":       title,
                "Source":      row.get("Source", ""),
                "Summary":     row.get("Summary", ""),
                "Datatype":    row.get("Data Type", ""),
                "Sectors":     row.get("Relevant Sectors", ""),
                "link":        row.get("Recent Link", ""),
                "filetype":    row.get("API Filetype", ""),
                "blockers":    blockers,
                "table_name":  table_name,
            }

            if not dry_run:
                upsert_master_row(conn, meta)

            page_content = ""
            md_path = find_markdown_file(title, export_dir)
            if md_path:
                page_content = extract_markdown_content(md_path)
            else:
                logger.info("  No markdown file found for '%s'", title)

            n = ingest_page(meta, page_content, qdrant, conn, dry_run=dry_run)
            total_points += n

    logger.info("=" * 60)
    logger.info("Done. %d Qdrant points upserted. %d pages skipped.", total_points, skipped_pages)
    logger.info("=" * 60)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Export → Qdrant ingestion pipeline")
    parser.add_argument("--dir",     type=str, required=True, help="Directory containing the Notion export files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Qdrant or SQLite")
    parser.add_argument("--source",  type=str, default=None, help="Only ingest entries matching this title")
    args = parser.parse_args()

    run_ingestion(export_dir=args.dir, filter_title=args.source, dry_run=args.dry_run)
