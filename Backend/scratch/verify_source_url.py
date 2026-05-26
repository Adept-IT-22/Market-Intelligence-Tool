import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

load_dotenv()

task_id = 'b902b3d3-fca7-4d4e-8e51-9c7ea334f01a'
mock_sp_url = "https://adepttechnologiesltd.sharepoint.com/sites/Innovations/Shared%20Documents/test_source_url_doc.txt"

print("=" * 60)
print(" VERIFYING SOURCE URL INJECTION RESULTS ")
print("=" * 60)

# 1. Check PostgreSQL
print("\n--- PostgreSQL Master Table ---")
try:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5435"),
        database=os.getenv("POSTGRES_DB", "market_intelligence"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres_local_secure")
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, title, source, department, task_id, table_name FROM master WHERE task_id = %s", (task_id,))
    row = cursor.fetchone()
    if row:
        print(f"  ID:         {row['id']}")
        print(f"  Title:      {row['title']}")
        print(f"  Source:     {row['source']}")
        print(f"  Department: {row['department']}")
        print(f"  Table:      {row['table_name']}")
        if row['source'] == mock_sp_url:
            print(f"  ✅ SOURCE URL MATCH in PostgreSQL!")
        else:
            print(f"  ❌ MISMATCH. Expected: {mock_sp_url}")
    else:
        print(f"  Not found for task_id: {task_id}")
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 2. Check Qdrant
print("\n--- Qdrant Vector Payload ---")
try:
    client = QdrantClient(host="localhost", port=7000)
    results = client.scroll(
        collection_name="adept_database",
        scroll_filter=Filter(
            must=[FieldCondition(key="task_id", match=MatchValue(value=task_id))]
        ),
        limit=5
    )[0]
    if results:
        print(f"  Found {len(results)} point(s)")
        for p in results:
            src = p.payload.get('source', '')
            print(f"  Point ID:   {p.id}")
            print(f"  Source:     {src}")
            print(f"  Department: {p.payload.get('department')}")
            print(f"  Text:      {p.payload.get('text', '')[:100]}...")
            if src == mock_sp_url:
                print(f"  ✅ SOURCE URL MATCH in Qdrant!")
            else:
                print(f"  ❌ MISMATCH. Expected: {mock_sp_url}")
    else:
        print(f"  No points found for task_id: {task_id}")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
