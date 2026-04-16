import json
from qdrant_client import QdrantClient

# Config - Local Qdrant
SOURCE_URL = "http://localhost:7000"
COLLECTION_NAME = "document_index"
OUTPUT_FILE = "index_dump.json"

def dump_data():
    print(f"Connecting to {SOURCE_URL}...")
    client = QdrantClient(url=SOURCE_URL)
    
    # Scroll through all points
    all_points = []
    next_offset = None
    
    print(f"Reading points from {COLLECTION_NAME}...")
    while True:
        records, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            offset=next_offset,
            limit=100,
            with_payload=True,
            with_vectors=True
        )
        all_points.extend(records)
        if not next_offset:
            break
            
    print(f"Read {len(all_points)} points.")
    
    data = []
    for point in all_points:
        data.append({
            "id": point.id,
            "vector": point.vector,
            "payload": point.payload
        })
        
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    dump_data()
