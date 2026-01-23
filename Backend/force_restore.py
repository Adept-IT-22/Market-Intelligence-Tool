import os
import requests

# Config
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "adept_database"
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots", "market_intelligence_backup.snapshot")

def restore():
    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{COLLECTION_NAME}/snapshots/upload"
    print(f"Uploading to {url}...")
    
    if not os.path.exists(SNAPSHOT_PATH):
        print(f"Snapshot file missing at {SNAPSHOT_PATH}!")
        return

    # Open file in binary mode
    with open(SNAPSHOT_PATH, 'rb') as f:
        # The key must be 'snapshot'
        files = {'snapshot': (os.path.basename(SNAPSHOT_PATH), f)}
        
        # Priority=snapshot to force overwrite
        params = {'priority': 'snapshot'}
        
        try:
            response = requests.post(url, files=files, params=params)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code != 200 and 'collection' in response.text and 'exist' in response.text:
                 # If collection missing, create and retry
                 print("Collection missing, attempting to create...")
                 create_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{COLLECTION_NAME}"
                 requests.put(create_url, json={"vectors": {"size": 384, "distance": "Cosine"}})
                 
                 # Retry upload
                 f.seek(0)
                 response = requests.post(url, files=files, params=params)
                 print(f"Retry Status: {response.status_code}")
                 print(f"Retry Response: {response.text}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    restore()
