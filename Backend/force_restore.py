import os
import time
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Config
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "adept_database"
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots", "market_intelligence_backup.snapshot")

def restore():
    print(f"Connecting to {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")
    
    # Check if snapshot exists
    if not os.path.exists(SNAPSHOT_PATH):
        print(f"Error: Snapshot not found at {SNAPSHOT_PATH}")
        return

    print("Reading snapshot...")
    # There isn't a direct "upload_snapshot" method in high-level client that takes a file path for collection recovery easily 
    # except via the REST API wrapper.
    # However, client.recover_snapshot exists!
    
    try:
        # Note: recover_snapshot takes a location (URL or path on server)
        # But we want to UPLOAD.
        # The Python client doesn't expose the upload-snapshot-to-recover endpoint easily.
        # Let's use the low-level API proxy.
        
        print(f"Uploading and recovering from {SNAPSHOT_PATH}...")
        with open(SNAPSHOT_PATH, "rb") as f:
            client.http.snapshot_api.recover_from_uploaded_snapshot(
                collection_name=COLLECTION_NAME,
                wait=True,
                snapshot=f
            )
        
        print("Success! Snapshot restored.")
        
        # Verify
        count = client.count(COLLECTION_NAME)
        print(f"Collection now has {count.count} points.")
        
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    restore()
