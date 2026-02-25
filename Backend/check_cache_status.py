import sqlite3
import os
from qdrant_client import QdrantClient

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db")
QDRANT_HOST = "localhost"
QDRANT_PORT = 7000
CACHE_COLLECTION = "semantic_cache_storage"

def check_cache():
    print(f"Checking SQLite Cache at {DB_PATH}...")
    if not os.path.exists(DB_PATH):
        print("❌ DB file not found!")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT count(*) FROM semantic_cache")
        count = cursor.fetchone()[0]
        print(f"✅ SQLite entries: {count}")
        if count > 0:
            cursor.execute("SELECT query FROM semantic_cache LIMIT 5")
            print("Recent queries in SQLite:")
            for row in cursor.fetchall():
                print(f" - {row[0]}")
    except Exception as e:
        print(f"❌ Error reading SQLite: {e}")
    finally:
        conn.close()

    print(f"\nChecking Qdrant Cache at {QDRANT_HOST}:{QDRANT_PORT}...")
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        collections = client.get_collections().collections
        exists = any(c.name == CACHE_COLLECTION for c in collections)
        if exists:
            count = client.get_collection(CACHE_COLLECTION).points_count
            print(f"✅ Qdrant points in {CACHE_COLLECTION}: {count}")
        else:
            print(f"❌ Collection {CACHE_COLLECTION} NOT FOUND!")
    except Exception as e:
        print(f"❌ Error connecting to Qdrant: {e}")

if __name__ == "__main__":
    check_cache()
