import time
import requests
import json
import os
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

def test_source_url_injection():
    print("=" * 60)
    print(" TESTING SHAREPOINT SOURCE URL INGESTION ")
    print("=" * 60)

    url = "http://localhost:5000/upload"
    mock_sp_url = "https://adepttechnologiesltd.sharepoint.com/sites/Innovations/Shared%20Documents/test_source_url_doc.txt"
    
    # 1. Create a dummy text file content
    dummy_file_content = "This is a verification test to check if the SharePoint source_url is correctly indexed into the RAG vector database."
    content_b64 = base64.b64encode(dummy_file_content.encode('utf-8')).decode('utf-8')
    
    payload = {
        "$content": content_b64,
        "fileName": "test_source_url_doc.txt",
        "source": "Innovations",
        "source_url": mock_sp_url
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    # 2. Trigger Upload API
    print("Sending POST request to /upload...")
    response = requests.post(url, headers=headers, json=payload)
    print(f"API Response Code: {response.status_code}")
    print(f"API Response Body: {response.text}")
    
    if response.status_code != 200:
        print("API upload failed. Check Flask logs.")
        return
        
    res_data = response.json()
    task_id = res_data.get("task_id")
    print(f"Task ID: {task_id}")
    
    # 3. Wait for background worker to process it
    print("Waiting 15 seconds for background worker to process task...")
    time.sleep(15)
    
    # 4. Check PostgreSQL Master table
    print("\nChecking PostgreSQL database...")
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5435"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres_local_secure")
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query Master table by task_id
        cursor.execute("SELECT * FROM master WHERE task_id = %s", (task_id,))
        row = cursor.fetchone()
        if row:
            print(f"PostgreSQL Master Record found:")
            print(f"  ID: {row.get('id')}")
            print(f"  Title: {row.get('title')}")
            print(f"  Source: {row.get('source')}")
            print(f"  table_name: {row.get('table_name')}")
            print(f"  department: {row.get('department')}")
            
            # Check if source matches the SharePoint URL
            if row.get('source') == mock_sp_url:
                print(f"  ✅ SOURCE URL MATCH! Source correctly set to SharePoint URL")
            else:
                print(f"  ❌ SOURCE URL MISMATCH. Expected: {mock_sp_url}")
        else:
            print(f"PostgreSQL Master record not found for task_id: {task_id}")
            # Also try by title
            cursor.execute("SELECT * FROM master WHERE title LIKE '%test_source_url%' ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                print(f"  (Found by title search: ID={row.get('id')}, Source={row.get('source')}, task_id={row.get('task_id')})")
        conn.close()
    except Exception as e:
        print(f"PostgreSQL connection/query failed: {e}")

    # 5. Check Qdrant payload
    print("\nChecking Qdrant vector payload...")
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
            print(f"Qdrant Points found ({len(results)} points):")
            for p in results:
                source_val = p.payload.get('source', '')
                print(f"  Point ID: {p.id}")
                print(f"  Source field in Qdrant: {source_val}")
                print(f"  Text preview: {p.payload.get('text', '')[:80]}...")
                
                if source_val == mock_sp_url:
                    print(f"  ✅ QDRANT SOURCE URL MATCH!")
                else:
                    print(f"  ❌ QDRANT SOURCE URL MISMATCH. Expected: {mock_sp_url}")
        else:
            print(f"No points found in Qdrant for task_id: {task_id}")
    except Exception as e:
        print(f"Qdrant connection/query failed: {e}")

    print("\n" + "=" * 60)
    print(" TEST COMPLETE ")
    print("=" * 60)

if __name__ == "__main__":
    test_source_url_injection()
