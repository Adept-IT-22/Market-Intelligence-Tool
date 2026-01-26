import json
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Config - Server Qdrant
# Inside docker, host is 'qdrant'
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "adept_database"
INPUT_FILE = "qdrant_dump.json"

def import_data():
    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    print(f"Connecting to {url}...")
    client = QdrantClient(url=url)
    
    # Ensure collection exists
    if not client.collection_exists(COLLECTION_NAME):
        print(f"Creating collection {COLLECTION_NAME}...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
        )
    
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    print(f"Loading data from {INPUT_FILE}...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
        
    print(f"Found {len(data)} points. Uploading...")
    
    points = []
    for item in data:
        points.append(models.PointStruct(
            id=item['id'],
            vector=item['vector'],
            payload=item['payload']
        ))
    
    # Upload in batches
    BATCH_SIZE = 100
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )
        print(f"Uploaded batch {i} - {i+len(batch)}")
        
    print("✅ Migration complete!")

if __name__ == "__main__":
    import_data()
