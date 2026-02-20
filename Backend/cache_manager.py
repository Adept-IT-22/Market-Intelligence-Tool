import sqlite3
import os
import json
import time

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db"))

def init_cache_table():
    """Create the query cache table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semantic_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT UNIQUE NOT NULL,
            response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_cached_response(query):
    """Retrieve a cached response for a query."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Simple exact match for now - can be expanded to semantic similarity later
        cursor.execute("SELECT response FROM semantic_cache WHERE query = ?", (query.lower().strip(),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def set_cached_response(query, response):
    """Store a response in the cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO semantic_cache (query, response) VALUES (?, ?)",
            (query.lower().strip(), response)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

# Initialize on import
init_cache_table()
