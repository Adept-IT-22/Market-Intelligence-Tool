import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

# Should match Docker internal networking if running inside container, 
# or localhost if forwarding ports.
# In docker-compose, qdrant service is named 'qdrant', port 6333
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333)) 
COLLECTION_NAME = "adept_database"
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots", "market_intelligence_backup.snapshot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RestoreQdrant")

def restore_snapshot():
    base_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    logger.info(f"Targeting Qdrant at {base_url}")
    
    if not os.path.exists(SNAPSHOT_PATH):
        logger.error(f"Snapshot file not found at: {SNAPSHOT_PATH}")
        logger.error("Please place the 'market_intelligence_backup.snapshot' file in the 'snapshots' folder.")
        return

    try:
        # Check if collection exists first
        # We might want to recover TO this collection.
        # The recover API usually takes a file upload or a URL.
        # Direct file upload endpoint: POST /collections/{name}/snapshots/upload
        
        logger.info(f"Restoring snapshot from {SNAPSHOT_PATH}...")
        
        with open(SNAPSHOT_PATH, 'rb') as f:
            files = {'snapshot': f}
            # Note: The endpoint /collections/{name}/snapshots/upload recovers the snapshot data 
            # into the specified collection.
            response = requests.post(
                f"{base_url}/collections/{COLLECTION_NAME}/snapshots/upload",
                files=files
            )
            
        if response.status_code == 200:
            logger.info("✅ Snapshot successfully uploaded and restored!")
        else:
            logger.error(f"Failed to restore: Status {response.status_code}")
            logger.error(response.text)

    except Exception as e:
        logger.error(f"Restore process failed: {e}")

if __name__ == "__main__":
    restore_snapshot()
