"""
PageIndex Builder — Creates a document-level summary index in Qdrant.

This enables two-tier retrieval:
  Tier 1: Search document summaries (fast, narrow) → top N document IDs
  Tier 2: Search chunks only within those documents (precise)

Run this ONCE to index your existing 1,188 Master entries.
After that, new documents are auto-indexed during ingestion.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "DB", "market-intelligence.db"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
EMBEDDING_MODEL = "BAAI/bge-small-en"
INDEX_COLLECTION = "document_index"


def build_index():
    """Read Master table and create document-level embeddings."""
    logger.info("=== PageIndex Builder ===")
    
    # 1. Load embedding model
    logger.info("Loading embedding model...")
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    
    # 2. Connect to Qdrant
    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    # 3. Create/recreate the document_index collection
    existing = [c.name for c in client.get_collections().collections]
    if INDEX_COLLECTION in existing:
        logger.info(f"Dropping existing '{INDEX_COLLECTION}' collection...")
        client.delete_collection(INDEX_COLLECTION)
    
    client.create_collection(
        collection_name=INDEX_COLLECTION,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    logger.info(f"Created collection '{INDEX_COLLECTION}'")
    
    # 4. Read all Master entries
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, Title, Source, Summary, Datatype, Sectors, table_name, Department
        FROM Master
        ORDER BY id
    """)
    rows = cursor.fetchall()
    conn.close()
    
    logger.info(f"Found {len(rows)} documents in Master table")
    
    # 5. Embed and upsert in batches
    batch_size = 50
    points_buffer = []
    indexed = 0
    skipped = 0
    
    for row in rows:
        master_id = row["id"]
        title = row["Title"] or ""
        summary = row["Summary"] or ""
        source = row["Source"] or ""
        sectors = row["Sectors"] or ""
        department = row["Department"] or "General"
        datatype = row["Datatype"] or ""
        table_name = row["table_name"] or ""
        
        # Build the text to embed: Title is weighted heavily
        # by repeating it — this is a proven trick for BGE embeddings
        embed_text = f"{title}. {title}. {summary}. Sectors: {sectors}. Department: {department}"
        
        if not embed_text.strip() or embed_text.strip() == ". . Sectors: . Department: General":
            skipped += 1
            continue
        
        vector = embedder.encode(embed_text).tolist()
        
        point = PointStruct(
            id=int(master_id),  # Qdrant requires int or UUID
            vector=vector,
            payload={
                "master_id": master_id,
                "title": title,
                "summary": summary,
                "source": source,
                "sectors": sectors,
                "department": department,
                "datatype": datatype,
                "table_name": table_name,
                "indexed_at": datetime.now().isoformat()
            }
        )
        points_buffer.append(point)
        
        # Flush batch
        if len(points_buffer) >= batch_size:
            client.upsert(collection_name=INDEX_COLLECTION, points=points_buffer)
            indexed += len(points_buffer)
            logger.info(f"Indexed {indexed}/{len(rows)} documents...")
            points_buffer = []
    
    # Flush remaining
    if points_buffer:
        client.upsert(collection_name=INDEX_COLLECTION, points=points_buffer)
        indexed += len(points_buffer)
    
    logger.info(f"=== PageIndex Complete ===")
    logger.info(f"Indexed: {indexed} | Skipped: {skipped} | Total: {len(rows)}")
    
    # 6. Verify
    info = client.get_collection(INDEX_COLLECTION)
    logger.info(f"Collection '{INDEX_COLLECTION}' has {info.points_count} points")


if __name__ == "__main__":
    build_index()
