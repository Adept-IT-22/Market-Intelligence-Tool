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
        logger.info(f"Restoring snapshot from {SNAPSHOT_PATH}...")
        
        # Read the snapshot file
        with open(SNAPSHOT_PATH, 'rb') as f:
            snapshot_data = f.read()
        
        # Use the correct endpoint with priority parameter
        # The snapshot upload endpoint requires the file as raw body or multipart
        response = requests.post(
            f"{base_url}/collections/{COLLECTION_NAME}/snapshots/upload",
            params={"priority": "snapshot"},  # Use snapshot data over existing
            files={"snapshot": ("market_intelligence_backup.snapshot", open(SNAPSHOT_PATH, 'rb'), "application/octet-stream")}
        )
            
        if response.status_code == 200:
            logger.info("✅ Snapshot successfully uploaded and restored!")
            logger.info(response.json())
        else:
            logger.error(f"Failed to restore: Status {response.status_code}")
            logger.error(response.text)
            
            # If collection doesn't exist, try creating it first
            if response.status_code == 404:
                logger.info("Collection doesn't exist. Trying to recover from snapshot...")
                # Try the recover endpoint which creates the collection from snapshot
                response = requests.put(
                    f"{base_url}/collections/{COLLECTION_NAME}/snapshots/recover",
                    json={
                        "location": SNAPSHOT_PATH
                    }
                )
                if response.status_code == 200:
                    logger.info("✅ Collection recovered from snapshot!")
                else:
                    logger.error(f"Recovery failed: {response.status_code}")
                    logger.error(response.text)

    except Exception as e:
        logger.error(f"Restore process failed: {e}")

if __name__ == "__main__":
    restore_snapshot()
