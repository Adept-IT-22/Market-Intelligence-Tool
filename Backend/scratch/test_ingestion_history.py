import time
import requests
import json
import os
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def test_ingestion_history():
    print("=" * 60)
    print(" TESTING INGESTION HISTORY LOGGING SYSTEM ")
    print("=" * 60)

    url = "http://localhost:5000/upload"
    mock_sp_url = "https://adepttechnologiesltd.sharepoint.com/sites/Innovations/Shared%20Documents/test_history_doc.txt"
    
    # 1. Create a dummy text file content
    dummy_file_content = "This is a verification test to check if the Ingestion History logging system captures this run's states."
    content_b64 = base64.b64encode(dummy_file_content.encode('utf-8')).decode('utf-8')
    
    payload = {
        "$content": content_b64,
        "fileName": "test_history_doc.txt",
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
    
    # 3. Query DB immediately to check if status is 'queued' or 'processing'
    print("\nChecking PostgreSQL database for immediately logged history...")
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5435"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres_local_secure")
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM ingestion_history WHERE task_id = %s", (task_id,))
        row = cursor.fetchone()
        if row:
            print("  [OK] Found Ingestion History entry immediately:")
            print(f"  Task ID:           {row['task_id']}")
            print(f"  Original Filename: {row['original_filename']}")
            print(f"  Status:            {row['status']} (Expected 'queued' or 'processing')")
            print(f"  Created At:        {row['created_at']}")
        else:
            print("  [ERROR] Ingestion History entry NOT found immediately!")
            
        conn.close()
    except Exception as e:
        print(f"  Error querying immediately: {e}")

    # 4. Wait for background worker to process it
    print("\nWaiting 35 seconds for background worker to process task...")
    time.sleep(35)
    
    # 5. Check PostgreSQL Ingestion History table again to verify final success state
    print("\nChecking PostgreSQL database again for final state...")
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5435"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres_local_secure")
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM ingestion_history WHERE task_id = %s", (task_id,))
        row = cursor.fetchone()
        if row:
            print("  [OK] Final Ingestion History entry:")
            print(f"  Task ID:           {row['task_id']}")
            print(f"  Filename:          {row['filename']}")
            print(f"  Original Filename: {row['original_filename']}")
            print(f"  File Size KB:      {row['file_size_kb']}")
            print(f"  Department:        {row['department']}")
            print(f"  Source URL:        {row['source_url']}")
            print(f"  Pipeline Type:     {row['pipeline_type']}")
            print(f"  Status:            {row['status']} (Expected 'succeeded')")
            print(f"  Started At:        {row['started_at']}")
            print(f"  Completed At:      {row['completed_at']}")
            print(f"  Duration Seconds:  {row['duration_seconds']}")
            print(f"  Error Message:     {row['error_message']}")
            
            if row['status'] == 'succeeded':
                print("\n  [SUCCESS] Ingestion logging works flawlessly!")
            else:
                print("\n  [FAILED] Final status was not 'succeeded'.")
        else:
            print("  [ERROR] Final Ingestion History entry not found!")
            
        conn.close()
    except Exception as e:
        print(f"  Error querying final state: {e}")

    print("\n" + "=" * 60)
    print(" TEST COMPLETE ")
    print("=" * 60)

if __name__ == "__main__":
    test_ingestion_history()
