import os
import logging
import requests
import shutil
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

# Configuration matches your setup
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
COLLECTION_NAME = "adept_database"
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")

# Ensure backup dir exists
os.makedirs(BACKUP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackupQdrant")

def create_and_download_snapshot():
    base_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    
    logger.info(f"Connecting to Qdrant at {base_url}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    try:
        # 1. Create Snapshot
        logger.info(f"Creating snapshot for collection '{COLLECTION_NAME}'...")
        # We can use the REST API directly for easier streaming download logic
        # POST /collections/{name}/snapshots
        response = requests.post(f"{base_url}/collections/{COLLECTION_NAME}/snapshots")
        response.raise_for_status()
        
        snapshot_info = response.json().get('result')
        if not snapshot_info:
            logger.error("Snapshot creation returned no result.")
            return

        snapshot_name = snapshot_info.get('name')
        logger.info(f"Snapshot created on server: {snapshot_name}")
        
        # 2. Download Snapshot
        download_url = f"{base_url}/collections/{COLLECTION_NAME}/snapshots/{snapshot_name}"
        local_filename = os.path.join(BACKUP_DIR, "market_intelligence_backup.snapshot")
        
        logger.info(f"Downloading to {local_filename}...")
        
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
                
        logger.info("✅ Backup successfully created and downloaded!")
        logger.info(f"File location: {local_filename}")
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")

if __name__ == "__main__":
    create_and_download_snapshot()
