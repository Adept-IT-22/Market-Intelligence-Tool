import sqlite3
import os
import time
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db"))

# Cache TTL in seconds (24 hours)
CACHE_TTL = 86400

# Responses containing these phrases are errors and should NEVER be cached
ERROR_PHRASES = [
    "I encountered an error",
    "Error connecting to Gemini",
    "error generating the final response",
    "FATAL ERROR",
]

def init_cache_table():
    """Create the query cache table if it doesn't exist."""
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

def get_cached_response(query):
    """Retrieve a cached response for a query (if not expired)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT response, created_at FROM semantic_cache WHERE query = ?", (query.lower().strip(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            response, created_at = row
            # Check TTL
            if time.time() - created_at > CACHE_TTL:
                logger.info("Cache EXPIRED: Clearing stale entry.")
                clear_query_cache(query)
                return None
            return response
        return None
    except Exception:
        return None

def set_cached_response(query, response):
    """Store a response in the cache (only if it's a valid response)."""
    if not response or not isinstance(response, str):
        return
    
    # Never cache error responses
    for phrase in ERROR_PHRASES:
        if phrase.lower() in response.lower():
            logger.warning(f"Cache BLOCKED: Refusing to cache error response.")
            return
    
    # Only cache responses with meaningful content (>100 chars)
    if len(response.strip()) < 100:
        logger.info("Cache SKIP: Response too short to cache.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO semantic_cache (query, response, created_at) VALUES (?, ?, ?)",
            (query.lower().strip(), response, time.time())
        )
        conn.commit()
        conn.close()
        logger.info(f"Cache SET: Stored response ({len(response)} chars).")
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")

def clear_query_cache(query):
    """Clear a specific query from the cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semantic_cache WHERE query = ?", (query.lower().strip(),))
        conn.commit()
        conn.close()
    except Exception:
        pass

def clear_cache():
    """Clear ALL entries from the cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semantic_cache")
        conn.commit()
        conn.close()
        logger.info("Cache CLEARED: All entries removed.")
    except Exception as e:
        logger.warning(f"Cache clear failed: {e}")

# Initialize on import
init_cache_table()
