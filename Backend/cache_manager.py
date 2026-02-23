import sqlite3
import os
import time
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct

logger = logging.getLogger(__name__)

# Consolidate paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "DB/market-intelligence.db"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
CACHE_COLLECTION = "semantic_cache_storage"
DEBUG_LOG = os.path.join(BASE_DIR, "cache_debug.log")

# Cache TTL in seconds (24 hours)
CACHE_TTL = 86400

# Responses containing these phrases are errors and should NEVER be cached
ERROR_PHRASES = [
    "I encountered an error",
    "Error connecting to Gemini",
    "error generating the final response",
    "FATAL ERROR",
]

# Re-use the embedding model from agent_manager to save memory/prevent hangs
def get_embedder():
    try:
        from agent_manager import get_embeddings_model
        return get_embeddings_model()
    except ImportError:
        # Fallback if called in isolation
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("BAAI/bge-small-en")

def init_cache_table():
    """Create the query cache table and Qdrant collection if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semantic_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT UNIQUE NOT NULL,
            response TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    
    # Qdrant collection is assumed to be initialized via setup script or first-run logic
    # But we ensure we can connect
    try:
        QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT).get_collections()
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant for caching: {e}")

def get_cached_response(query):
    """Retrieve a cached response for a query (Exact match L1 -> Semantic match L2)."""
    q_norm = query.lower().strip()
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[{time.ctime()}] SEARCHING: '{q_norm}'\n")
    
    # 1. Exact Match (Fastest)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT response, created_at FROM semantic_cache WHERE query = ?", (q_norm,))
        row = cursor.fetchone()
        conn.close()
        if row:
            response, created_at = row
            if time.time() - created_at < CACHE_TTL:
                logger.info("L1 Cache HIT: Exact match.")
                with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"[{time.ctime()}] L1 HIT!\n")
                return response
            else:
                clear_query_cache(query)
        else:
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.ctime()}] L1 MISS.\n")
    except Exception as e:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.ctime()}] L1 ERROR: {e}\n")
        pass

    # 2. Semantic Match (Fuzzy)
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        embedder = get_embedder()
        vector = embedder.encode(query).tolist()
        
        search_result = client.search(
            collection_name=CACHE_COLLECTION,
            query_vector=vector,
            limit=1
        )
        
        if search_result:
            score = search_result[0].score
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.ctime()}] L2 Similarity Score: {score:.4f}\n")
            
            if score > 0.90:
                logger.info(f"L2 Cache HIT: Semantic similarity {score:.2f}")
                with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"[{time.ctime()}] L2 HIT!\n")
                return search_result[0].payload.get("response")
        else:
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.ctime()}] L2 MISS (No results).\n")
    except Exception as e:
        logger.warning(f"Semantic cache search failed: {e}")
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.ctime()}] L2 ERROR: {e}\n")

    return None

def set_cached_response(query, response):
    """Store a response in both L1 (SQLite) and L2 (Qdrant) cache."""
    if not response or not isinstance(response, str):
        return
    
    for phrase in ERROR_PHRASES:
        if phrase.lower() in response.lower():
            return
    
    if len(response.strip()) < 100:
        return

    q_norm = query.lower().strip()
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.ctime()}] STORING: '{q_norm}'\n")

    # 1. Store in SQLite (L1)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO semantic_cache (query, response, created_at) VALUES (?, ?, ?)",
            (q_norm, response, time.time())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"SQLite cache write failed: {e}")

    # 2. Store in Qdrant (L2)
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        embedder = get_embedder()
        vector = embedder.encode(query).tolist()
        
        import uuid
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, query.lower().strip()))
        
        client.upsert(
            collection_name=CACHE_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "query": query.lower().strip(),
                        "response": response,
                        "created_at": time.time()
                    }
                )
            ]
        )
        logger.info(f"Cache SET: L1 & L2 updated ({len(response)} chars).")
    except Exception as e:
        logger.warning(f"Qdrant cache upsert failed: {e}")

def clear_query_cache(query):
    """Clear a specific query from both caches."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semantic_cache WHERE query = ?", (query.lower().strip(),))
        conn.commit()
        conn.close()
        
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        import uuid
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, query.lower().strip()))
        client.delete(collection_name=CACHE_COLLECTION, points_selector=[point_id])
    except Exception: pass

def clear_cache():
    """Clear ALL entries from both caches."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semantic_cache")
        conn.commit()
        conn.close()
        
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        client.delete_collection(CACHE_COLLECTION)
        client.create_collection(
            collection_name=CACHE_COLLECTION,
            vectors_config={"size": 384, "distance": "Cosine"}
        )
        logger.info("Cache CLEARED: All L1 & L2 entries removed.")
    except Exception as e:
        logger.warning(f"Cache clear failed: {e}")

init_cache_table()
