import os
import re
import uuid
import time
import logging
import sqlite3
import argparse
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
import urllib3
urllib3.disable_warnings()
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

# Optional parsers
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

# Setup
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
COLLECTION_NAME = "adept_database"
EMBEDDING_MODEL = "BAAI/bge-small-en"
VECTOR_SIZE = 384

current_dir = Path(__file__).parent
DATABASE_PATH = os.getenv("DATABASE_PATH") or str(current_dir / "DB" / "market-intelligence.db")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# Embedder
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
    if not points: return
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("  → Upserted %d Qdrant point(s).", len(points))

def get_db_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def insert_routing_row(conn: sqlite3.Connection, table_name: str, row: dict):
    # Determine the max existing chunk index to properly append
    cursor = conn.cursor()
    cursor.execute(f'SELECT MAX(chunk_index) FROM "{table_name}"')
    max_idx = cursor.fetchone()[0]
    next_idx = 0 if max_idx is None else max_idx + 1
    
    row["chunk_index"] = next_idx
    
    conn.execute(f"""
        INSERT INTO "{table_name}" (chunk_index, chunk_text, qdrant_point_id, source_url, file_type)
        VALUES (:chunk_index, :chunk_text, :qdrant_point_id, :source_url, :file_type)
    """, row)
    conn.commit()


# Parsers
def download_file(url: str) -> Optional[bytes]:
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
    if not HAS_PDF: return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        pages_text = []
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: pages_text.append(t)
        return "\n".join(pages_text)
    finally:
        os.unlink(tmp_path)

def extract_xlsx_text(data: bytes) -> str:
    if not HAS_XLSX: return ""
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
                if line: rows.append(line)
        return "\n".join(rows)
    finally:
        os.unlink(tmp_path)

def chunk_text(text: str, size: int=CHUNK_SIZE, overlap: int=CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text: return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text): break
        start += size - overlap
    return chunks

def process_table_link(conn, table_name, qdrant, dry_run=False):
    """Processes a single routing table's metadata link to ingest the actual file."""
    try:
        # Get metadata row which usually has file_type='metadata' and contains the original link
        cursor = conn.cursor()
        cursor.execute(f"SELECT source_url FROM '{table_name}' WHERE file_type='metadata' LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            logger.info("  Skipping %s - no metadata link found.", table_name)
            return 0
            
        link = row[0]
        if not link or not link.startswith("http"):
            logger.info("  Skipping %s - solid link not found in DB.", table_name)
            return 0
            
        # Before we download, check if we already parsed this file for this table
        cursor.execute(f"SELECT COUNT(*) FROM '{table_name}' WHERE file_type IN ('pdf', 'xlsx')")
        if cursor.fetchone()[0] > 0:
            logger.info("  Skipping %s - already has ingested chunks.", table_name)
            return 0
            
        logger.info("── Ingesting link from %s: %s", table_name, link)
        
        def fetch_link_bytes(url: str, required_type: str) -> tuple[Optional[bytes], str]:
            b = download_file(url)
            if not b: return None, url
            b_lower = b[:200].lower()
            if b"<!doctype" in b_lower or b"<html" in b_lower:
                logger.info("  Link returned HTML, looking for %s link inside...", required_type)
                try:
                    soup = BeautifulSoup(b, "html.parser")
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
        
        # We don't have explicit Notion filetype here, so we guess based on the URL or attempt both
        file_bytes, final_url = fetch_link_bytes(link, "pdf")
        extracted = extract_pdf_text(file_bytes) if file_bytes else ""
        file_type = "pdf"
        
        # If it wasn't a pdf, try xlsx
        if not extracted:
            file_bytes, final_url = fetch_link_bytes(link, "xlsx")
            extracted = extract_xlsx_text(file_bytes) if file_bytes else ""
            file_type = "xlsx"
            
        if not extracted:
             logger.warning("  Could not extract text or file was not PDF/XLSX: %s", link)
             return 0

        # Get Master info for metadata appending
        cursor.execute(f"SELECT notion_id, Title, Sectors, Datatype FROM Master WHERE table_name=?", (table_name,))
        m_row = cursor.fetchone()
        title = m_row["Title"] if m_row else table_name
        sectors = m_row["Sectors"] if m_row else ""
        data_type = m_row["Datatype"] if m_row else ""
        notion_id = m_row["notion_id"] if m_row else "unknown"

        chunks = chunk_text(extracted)
        logger.info("  Chunked into %d chunks. Embedding...", len(chunks))
        vectors = embed(chunks)
        
        all_points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            payload = {
                "text":          chunk,
                "source":        final_url,
                "title":         title,
                "sectors":       sectors,
                "data_type":     data_type,
                "notion_id":     notion_id,
                "routing_table": table_name,
                "file_type":     file_type,
                "chunk_index":   i,  # Absolute index will be handled by insert_routing_row
            }
            all_points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            
            if not dry_run:
                insert_routing_row(conn, table_name, {
                    "chunk_text":      chunk[:500],
                    "qdrant_point_id": point_id,
                    "source_url":      final_url,
                    "file_type":       file_type,
                })
        
        if not dry_run:
            for batch_start in range(0, len(all_points), 100):
                upsert_points(qdrant, all_points[batch_start:batch_start + 100])
        else:
             logger.info("  [DRY RUN] Would upsert %d chunks for %s", len(all_points), table_name)
             
        return len(all_points)

    except Exception as e:
        logger.error("Error processing table %s: %s", table_name, e)
        return 0

def run_db_ingestion(dry_run=False, table_filter=None):
    logger.info("=" * 60)
    logger.info("SQLite Web Links → Qdrant Ingestion Pipeline")
    logger.info("Qdrant:   %s:%d  |  Collection: %s", QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME)
    logger.info("Database: %s", DATABASE_PATH)
    logger.info("Dry run:  %s", dry_run)
    logger.info("=" * 60)
    
    qdrant = get_qdrant_client()
    if not dry_run:
        ensure_collection(qdrant)
        
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'route_%'")
    tables = [t[0] for t in cursor.fetchall()]
    
    total_upserted = 0
    for t_name in tables:
        if table_filter and table_filter.lower() not in t_name.lower():
            continue
        
        try:
            pts = process_table_link(conn, t_name, qdrant, dry_run=dry_run)
            total_upserted += pts
            if pts > 0:
                 time.sleep(1) # Polite delay after full download/embed sequence
        except Exception as e:
            logger.error("Failed on %s: %s", t_name, e)
            
    conn.close()
    logger.info("=" * 60)
    logger.info("Done. %d new Qdrant points upserted.", total_upserted)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest direct text from URLs currently held in SQLite metadata")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--table", type=str, help="Only ingest specific route_table name or substring")
    args = parser.parse_args()
    
    run_db_ingestion(dry_run=args.dry_run, table_filter=args.table)
