import os
import sqlite3
import logging
import argparse
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from ingest_data import DataIngester

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "DB", "market-intelligence.db")
COLLECTION_NAME = "adept_database"

def sync_data(source_dir, clean_sync=False):
    logger.info("=== Data Integrity Sync (v2) ===")
    
    if not os.path.exists(source_dir):
        logger.error(f"Source directory {source_dir} not found!")
        return

    # Initialize Qdrant
    # Check if we are in Docker or Local
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = 7000 if qdrant_host == "localhost" else 6333
    client = QdrantClient(host=qdrant_host, port=qdrant_port)
    
    if clean_sync:
        logger.info(f"PERFORMING CLEAN SYNC: Wiping collection '{COLLECTION_NAME}'...")
        client.delete_collection(COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        logger.info("Collection recreated.")

    ingester = DataIngester()
    
    # 1. Build a mapping of filenames to paths in source_dir
    file_map = {}
    logger.info(f"Scanning {source_dir} for documents...")
    for root, _, files in os.walk(source_dir):
        for f in files:
            file_map[f.lower()] = os.path.join(root, f)
    
    logger.info(f"Scan complete. Found {len(file_map)} physical files.")

    # 2. Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, Title, Source, Sectors, Department, table_name FROM Master")
    rows = cursor.fetchall()
    
    logger.info(f"Found {len(rows)} Master entries in database.")

    synced = 0
    skipped = 0

    for row in rows:
        master_id = row['id']
        title = row['Title']
        original_source = row['Source']
        sectors = row['Sectors']
        department = row['Department']
        routing_table_name = row['table_name']
        
        # 3. Find matching file
        filename = original_source.replace('\\', '/').split('/')[-1].lower()
        actual_path = file_map.get(filename)
        
        if not actual_path:
            # logger.warning(f"Skipping #{master_id}: '{title}' — File not found in {source_dir}")
            skipped += 1
            continue
            
        if clean_sync:
            # Drop the table to ensure fresh schema (fixes "no column named Department" errors)
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {routing_table_name}")
                conn.commit()
                # MUST recreate it because the ingester methods assume it exists
                ingester._create_routing_table(routing_table_name)
            except Exception as e:
                logger.warning(f"Could not reset table {routing_table_name}: {e}")

        logger.info(f"Ingesting [{synced + 1}/{len(rows)}]: {title}")
        
        try:
            ext = os.path.splitext(actual_path)[1].lower()
            if ext in ['.xlsx', '.xls']:
                ingester._process_excel(actual_path, master_id, routing_table_name, sectors, department)
            elif ext == '.pdf':
                ingester._process_pdf(actual_path, master_id, routing_table_name, sectors, department)
            elif ext == '.docx':
                ingester._process_docx(actual_path, master_id, routing_table_name, sectors, department)
            elif ext == '.pptx':
                ingester._process_pptx(actual_path, master_id, routing_table_name, sectors, department)
            elif ext == '.md':
                ingester._process_md(actual_path, master_id, routing_table_name, sectors, department)
            elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
                ingester._process_image(actual_path, master_id, routing_table_name, sectors, department)
            
            synced += 1
        except Exception as e:
            logger.error(f"Failed to sync #{master_id}: {e}")
            
    conn.close()
    logger.info(f"=== Sync Complete ===")
    logger.info(f"Synced: {synced} | Skipped: {skipped} | Total Master: {len(rows)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync physical files with the vector database.")
    parser.add_argument("source_dir", help="Local directory containing the documents")
    parser.add_argument("--clean", action="store_true", help="Wipe the existing collection before syncing")
    args = parser.parse_args()
    
    sync_data(args.source_dir, clean_sync=args.clean)
