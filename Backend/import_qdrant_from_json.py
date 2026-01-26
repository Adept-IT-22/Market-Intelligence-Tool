import json
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Config - Server Qdrant
# Inside docker, host is 'qdrant'
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "adept_database"
DEFAULT_INPUT_FILE = "qdrant_dump.json"

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
    
    # Logic to find the file
    possible_paths = [
        DEFAULT_INPUT_FILE,
        f"/app/{DEFAULT_INPUT_FILE}",
        f"Backend/{DEFAULT_INPUT_FILE}"
    ]
    
    found_file = None
    for path in possible_paths:
        if os.path.exists(path):
            found_file = path
            break
            
    if not found_file:
        print(f"Error: {DEFAULT_INPUT_FILE} not found. Searched in: {possible_paths}")
        print("Current Working Directory:", os.getcwd())
        print("Directory Contents:", os.listdir(os.getcwd()))
        return

    print(f"Loading data from {found_file}...")
    with open(found_file, 'r') as f:
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
