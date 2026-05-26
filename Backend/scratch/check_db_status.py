import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

def check_status():
    task_id = '341e758a-f91d-454d-9fdd-f72269c22b89'
    print(f"Checking status for task_id: {task_id}")
    
    # Check PostgreSQL
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5435"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres_local_secure")
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM master WHERE task_id = %s", (task_id,))
        row = cursor.fetchone()
        if row:
            print("PostgreSQL master record found:")
            print(dict(row))
        else:
            print("PostgreSQL master record NOT found.")
        conn.close()
    except Exception as e:
        print(f"PostgreSQL query failed: {e}")

    # Check Qdrant
    try:
        client = QdrantClient(host="localhost", port=7000)
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        results = client.scroll(
            collection_name="adept_database",
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="task_id", match=MatchValue(value=task_id))
                ]
            ),
            limit=5
        )[0]
        if results:
            print(f"Qdrant points found: {len(results)}")
            for r in results:
                print(r.payload)
        else:
            print("Qdrant points NOT found.")
    except Exception as e:
        print(f"Qdrant query failed: {e}")

if __name__ == "__main__":
    check_status()
