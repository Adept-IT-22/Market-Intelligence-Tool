import sqlite3
import os
import time
import logging
import threading
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance, PointIdsList

# Configure logging
logger = logging.getLogger(__name__)

# Thread-safe database lock
_db_lock = threading.Lock()

# Paths & Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "DB/market-intelligence.db"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
CACHE_COLLECTION = "semantic_cache_storage"
DEBUG_LOG = os.path.join(BASE_DIR, "cache_debug.log")

CACHE_TTL = 86400       # 24 hours
MAX_QUERY_LENGTH = 1000  # Prevent excessively long cache keys

# Error phrases that should NEVER be cached
ERROR_PHRASES = [
    "I encountered an error",
    "Error connecting to Gemini",
    "error generating the final response",
    "FATAL ERROR",
    "API limit reached",
    "I am sorry, but I cannot provide",
    "I cannot provide",
    "does not contain",
    "not contain any",
    "could not be found in the provided"
]

# Re-use the embedding model from agent_manager to save memory
def get_embedder():
    try:
        from agent_manager import get_embeddings_model
        return get_embeddings_model()
    except ImportError:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("BAAI/bge-small-en")


def _get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def init_cache_table():
    """Create the SQLite cache table and Qdrant collection if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT UNIQUE NOT NULL,
                    response TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            ''')
            conn.commit()

    # Fix 4: Auto-create Qdrant collection if absent
    try:
        client = _get_qdrant_client()
        existing = [c.name for c in client.get_collections().collections]
        if CACHE_COLLECTION not in existing:
            logger.info(f"Creating Qdrant cache collection '{CACHE_COLLECTION}'...")
            client.create_collection(
                collection_name=CACHE_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),  # Fix 3
            )
            logger.info("Qdrant cache collection created successfully.")
        else:
            logger.info(f"Qdrant cache collection '{CACHE_COLLECTION}' already exists.")
    except Exception as e:
        logger.error(f"Failed to connect to / initialize Qdrant for caching: {e}")


def get_cached_response(query: str):
    """Retrieve a cached response: L1 exact match (SQLite) -> L2 semantic match (Qdrant)."""
    q_norm = query.lower().strip()
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[{time.ctime()}] SEARCHING: '{q_norm}'\n")

    # --- L1: Exact Match ---
    try:
        with _db_lock:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT response, created_at FROM semantic_cache WHERE query = ?", (q_norm,)
                ).fetchone()

        if row:
            response, created_at = row
            if time.time() - created_at < CACHE_TTL:
                logger.info("L1 Cache HIT: Exact match.")
                with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"[{time.ctime()}] L1 HIT!\n")
                return response
            else:
                logger.info("L1 Cache EXPIRED: Clearing stale entry.")
                clear_query_cache(query)
        else:
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{time.ctime()}] L1 MISS.\n")
    except Exception as e:
        logger.error(f"L1 cache lookup failed: {e}")
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.ctime()}] L1 ERROR: {e}\n")

    # --- L2: Semantic Match ---
    try:
        client = _get_qdrant_client()
        embedder = get_embedder()
        vector = embedder.encode(query).tolist()

        _cache_res = client.query_points(
            collection_name=CACHE_COLLECTION,
            query=vector,
            limit=1
        )
        search_result = _cache_res.points
        
        if search_result and search_result[0].score > 0.96:
            res = search_result[0]
            payload = res.payload or {}
            created_at = payload.get("created_at")
            
            # Enforce TTL on L2 semantic hits
            if isinstance(created_at, (int, float)) and (time.time() - created_at < CACHE_TTL):
                logger.info(f"L2 Cache HIT: Semantic similarity {res.score:.2f}")
                return payload.get("response")
            else:
                logger.info("L2 Cache EXPIRED or missing timestamp: Clearing stale entry.")
                clear_query_cache(query)
    except Exception as e:
        logger.warning(f"Semantic cache search failed: {e}")
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.ctime()}] L2 ERROR: {e}\n")

    return None


def set_cached_response(query: str, response: str):
    """Store a response in L1 (SQLite) and L2 (Qdrant) cache."""
    if not response or not isinstance(response, str):
        return
    for phrase in ERROR_PHRASES:
        if phrase.lower() in response.lower():
            logger.info("Skipping cache write: response contains error phrase.")
            return
    if len(response.strip()) < 100:
        logger.info("Skipping cache write: response too short.")
        return
    if len(query) > MAX_QUERY_LENGTH:
        logger.info("Skipping cache write: query too long.")
        return

    q_norm = query.lower().strip()
    now = time.time()
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.ctime()}] STORING: '{q_norm}'\n")

    # L1: SQLite
    try:
        with _db_lock:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO semantic_cache (query, response, created_at) VALUES (?, ?, ?)",
                    (q_norm, response, now)
                )
                conn.commit()
    except Exception as e:
        logger.warning(f"SQLite cache write failed: {e}")

    # L2: Qdrant
    try:
        client = _get_qdrant_client()
        embedder = get_embedder()
        vector = embedder.encode(query).tolist()
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, q_norm))

        client.upsert(
            collection_name=CACHE_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"query": q_norm, "response": response, "created_at": now}
                )
            ]
        )
        logger.info(f"Cache SET: L1 & L2 updated ({len(response)} chars).")
    except Exception as e:
        logger.warning(f"Qdrant cache upsert failed: {e}")


def clear_query_cache(query: str):
    """Clear a specific query from both L1 and L2 caches."""
    try:
        q_norm = query.lower().strip()
        with _db_lock:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM semantic_cache WHERE query = ?", (q_norm,))
                conn.commit()

        # Fix 2: Use PointIdsList for deletion
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, q_norm))
        try:
            _get_qdrant_client().delete(
                collection_name=CACHE_COLLECTION,
                points_selector=PointIdsList(points=[point_id])
            )
        except Exception as e:
            logger.warning(f"Qdrant delete failed for '{q_norm[:50]}': {e}")
    except Exception as e:
        logger.warning(f"Failed to clear cache for query '{query[:50]}': {e}")


def clear_cache():
    """Clear ALL entries from both L1 and L2 caches."""
    try:
        with _db_lock:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM semantic_cache")
                conn.commit()

        client = _get_qdrant_client()
        client.delete_collection(CACHE_COLLECTION)
        # Fix 3: Use VectorParams/Distance instead of raw dict
        client.create_collection(
            collection_name=CACHE_COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("Cache CLEARED: All L1 & L2 entries removed.")
    except Exception as e:
        logger.warning(f"Cache clear failed: {e}")


init_cache_table()
