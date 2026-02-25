import sqlite3
import os
import time
import logging
import uuid
import numpy as np
import threading
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, PointIdsList

# Configure logging
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db"))
CACHE_COLLECTION = "semantic_cache_l2"
CACHE_TTL = 86400  # 24 hours
MAX_QUERY_LENGTH = 1000 # Safety limit

# Global lock for SQLite (thread safety in Flask)
_db_lock = threading.RLock()

# Error phrases that should NEVER be cached
ERROR_PHRASES = [
    "I encountered an error",
    "Error connecting to Gemini",
    "error generating the final response",
    "FATAL ERROR",
    "API limit reached"
]

def _get_qdrant_client():
    """Lazy initialize Qdrant client."""
    from agent_manager import QDRANT_HOST, QDRANT_PORT
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def init_cache_table():
    """Initialize SQLite L1 and Qdrant L2 cache structures."""
    with _db_lock:
        try:
            # Level 1: SQLite Struct
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
            logger.info("SQLite L1 Cache initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite L1 cache: {e}")

    try:
        # Level 2: Qdrant Collection
        client = _get_qdrant_client()
        collections = client.get_collections().collections
        exists = any(c.name == CACHE_COLLECTION for c in collections)
        
        if not exists:
            # Note: We use 384 dimensions for bge-small-en
            from qdrant_client.models import VectorParams, Distance
            client.create_collection(
                collection_name=CACHE_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )
            logger.info(f"Qdrant L2 Cache collection '{CACHE_COLLECTION}' created.")
    except Exception as e:
        logger.warning(f"Qdrant L2 Cache initialization skipped: {e}")

def get_cached_response(query, embeddings_model=None):
    """Hybrid L1/L2 cache retrieval."""
    if len(query) > MAX_QUERY_LENGTH: return None
    
    q_norm = query.lower().strip()

    # --- Level 1: Exact Match (SQLite) ---
    with _db_lock:
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
                    return response
                else:
                    logger.info("L1 Cache EXPIRED: Removing stale entry.")
                    _clear_exact_query(q_norm)
        except Exception as e:
            logger.debug(f"L1 Cache lookup failed: {e}")

    # --- Level 2: Semantic Match (Qdrant) ---
    if embeddings_model:
        try:
            client = _get_qdrant_client()
            vector = embeddings_model.encode(query).tolist()
            
            search_result = client.search(
                collection_name=CACHE_COLLECTION,
                query_vector=vector,
                limit=1,
                score_threshold=0.95 # Higher precision for semantic cache
            )

            if search_result:
                res = search_result[0]
                payload = res.payload or {}
                created_at = payload.get("created_at", 0)
                
                if time.time() - created_at < CACHE_TTL:
                    logger.info(f"L2 Cache HIT: Semantic match (score {res.score:.2f})")
                    return payload.get("response")
                else:
                    logger.info("L2 Cache EXPIRED: Removing stale point.")
                    try:
                        client.delete(
                            collection_name=CACHE_COLLECTION,
                            points_selector=PointIdsList(points=[res.id])
                        )
                    except Exception: pass
        except Exception as e:
            logger.debug(f"L2 Cache lookup skipped: {e}")

    return None

def set_cached_response(query, response, vector=None):
    """Store response in BOTH L1 and L2 caches."""
    if not response or len(str(response)) < 100: return
    if any(p.lower() in str(response).lower() for p in ERROR_PHRASES): return

    q_norm = query.lower().strip()

    # Store L1
    with _db_lock:
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
            logger.warning(f"L1 Cache write failed: {e}")

    # Store L2
    if vector is not None:
        try:
            client = _get_qdrant_client()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, q_norm))
            client.upsert(
                collection_name=CACHE_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector.tolist() if isinstance(vector, np.ndarray) else vector,
                        payload={
                            "query": q_norm,
                            "response": response,
                            "created_at": time.time()
                        }
                    )
                ]
            )
        except Exception as e:
            logger.warning(f"L2 Cache write failed: {e}")

def _clear_exact_query(q_norm):
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM semantic_cache WHERE query = ?", (q_norm,))
            conn.commit()
            conn.close()
        except Exception: pass

def clear_cache():
    """Wipe both L1 and L2 caches."""
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM semantic_cache")
            conn.commit()
            conn.close()
            logger.info("SQLite L1 Cache cleared.")
        except Exception: pass

    try:
        client = _get_qdrant_client()
        client.delete_collection(CACHE_COLLECTION)
        init_cache_table() # Re-create
        logger.info("Qdrant L2 Cache cleared.")
    except Exception: pass
