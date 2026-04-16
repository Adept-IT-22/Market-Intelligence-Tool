import sqlite3
import os
from qdrant_client import QdrantClient

# Config for your local setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "DB", "market-intelligence.db")
QDRANT_URL = "http://localhost:7000"

def check_health():
    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    try:
        client = QdrantClient(url=QDRANT_URL)
        
        if not os.path.exists(DB_PATH):
            print(f"ERROR: Database not found at {DB_PATH}")
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            master_count = cursor.execute("SELECT COUNT(*) FROM Master").fetchone()[0]
            
        page_index_count = client.count("document_index").count
        data_points_count = client.count("adept_database").count
        
        print(f"\n--- LOCAL HEALTH REPORT ---")
        print(f"Master Records (SQLite): {master_count}")
        print(f"Tier 1 (PageIndex):      {page_index_count} / {master_count}")
        print(f"Tier 2 (Actual Data):    {data_points_count} points")
        
        # Estimate: average doc has ~45 chunks (based on 1000 char semantic chunking)
        expected_min = master_count * 30
        coverage = (data_points_count / expected_min) * 100 if expected_min > 0 else 0
        
        print(f"Estimated Data Coverage: {coverage:.1f}% (Targets ~30,000+ points)")
        
        if coverage < 70:
            print("\n[!] WARNING: Significant data gap detected.")
            print("    Your system only has partial data. Specific queries will fail.")
            print("    Recommendation: Run a full ingestion sweep.")
        else:
            print("\n[+] Health check passed. Data levels look healthy.")

    except Exception as e:
        print(f"Connection Failed: {e}")

if __name__ == "__main__":
    check_health()
