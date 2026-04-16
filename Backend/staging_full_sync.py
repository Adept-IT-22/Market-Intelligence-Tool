import os
import sqlite3
import logging
import uuid
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from ingest_data import DataIngester

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths - These must match the Docker container paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "DB", "market-intelligence.db"))
# This folder must be mounted in docker-compose.yml
TEMP_UPLOAD_DIR = "/app/temp_upload"
COLLECTION_NAME = "adept_database"

def sync_data():
    logger.info("=== Staging Full Sync (v2) ===")
    
    if not os.path.exists(TEMP_UPLOAD_DIR):
        logger.error(f"Directory {TEMP_UPLOAD_DIR} not found! Did you mount it in docker-compose.yml?")
        return

    ingester = DataIngester()
    
    # Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Get all Master entries
    cursor.execute("SELECT id, Title, Source, Sectors, Department, table_name FROM Master")
    rows = cursor.fetchall()
    
    logger.info(f"Found {len(rows)} Master entries to sync.")
    
    # 2. Build a mapping of filenames to paths in temp_upload
    # This handles Windows -> Linux path shifts
    file_map = {}
    logger.info(f"Scanning {TEMP_UPLOAD_DIR} for documents...")
    for root, _, files in os.walk(TEMP_UPLOAD_DIR):
        for f in files:
            file_map[f.lower()] = os.path.join(root, f)
    
    logger.info(f"Scan complete. Found {len(file_map)} physical files.")

    synced = 0
    skipped = 0

    for row in rows:
        master_id = row['id']
        title = row['Title']
        original_source = row['Source']
        sectors = row['Sectors']
        department = row['Department']
        routing_table_name = row['table_name']
        
        # 3. Find the file on the server
        # Try finding by filename (handles Windows backslashes on Linux)
        filename = original_source.replace('\\', '/').split('/')[-1].lower()
        actual_path = file_map.get(filename)
        
        if not actual_path:
            logger.warning(f"Skipping Document #{master_id}: '{title}' — File not found in temp_upload (expected: {basename})")
            skipped += 1
            continue
            
        logger.info(f"Syncing [{synced + 1}/{len(rows)}]: {title}")
        
        try:
            # 4. Ingest chunks (re-using ingest_data.py logic)
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
    logger.info(f"Synced: {synced} | Skipped: {skipped} | Total: {len(rows)}")

if __name__ == "__main__":
    sync_data()
