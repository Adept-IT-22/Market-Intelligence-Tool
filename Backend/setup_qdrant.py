import sqlite3
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
EMBEDDING_MODEL = "BAAI/bge-small-en"
QDRANT_HOST = "localhost"
QDRANT_PORT = 7000
COLLECTION_NAME = "adept_database"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../DB/market-intelligence.db")

def setup_qdrant():
    # 1. Initialize Embedding Model
    logger.info("Loading embedding model...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # 2. Connect to Qdrant
    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # 3. Create Collection
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if not exists:
        logger.info(f"Creating collection '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    else:
        logger.info(f"Collection '{COLLECTION_NAME}' already exists.")

    # 4. Fetch Data from SQLite
    logger.info(f"Reading data from {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Adapt this query to your specific schema. 
    # Based on previous exploration, we want to embed the 'Master' table or similar.
    cursor.execute("SELECT table_name, Title, Summary, Sectors FROM Master")
    rows = cursor.fetchall()
    conn.close()

    points = []
    logger.info(f"Found {len(rows)} rows to embed.")

    for idx, row in enumerate(rows):
        table_name, title, summary, sectors = row
        
        # Create a rich text representation for embedding
        text_to_embed = f"Table: {table_name}. Title: {title}. Summary: {summary}. Sectors: {sectors}"
        
        # Generate embedding
        embedding = model.encode(text_to_embed).tolist()
        
        # Create Payload
        payload = {
            "table_name": table_name,
            "Title": title,
            "Summary": summary,
            "Sectors": sectors
        }

        points.append(PointStruct(
            id=idx,
            vector=embedding,
            payload=payload
        ))

    # 5. Upsert to Qdrant
    if points:
        logger.info(f"Upserting {len(points)} points to Qdrant...")
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        logger.info("Upsert complete!")
    else:
        logger.warning("No points to upsert.")

if __name__ == "__main__":
    setup_qdrant()
