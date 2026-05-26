import os
import sqlite3
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=== DATABASE COMPARISON ===")
    
    # 1. Query SQLite
    db_path = os.getenv("DATABASE_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DB", "market-intelligence.db")
    print(f"SQLite DB Path: {db_path}")
    if os.path.exists(db_path):
        conn_sl = sqlite3.connect(db_path)
        conn_sl.row_factory = sqlite3.Row
        cur_sl = conn_sl.cursor()
        cur_sl.execute("SELECT id, Title, Source, Department, table_name FROM Master")
        rows_sl = cur_sl.fetchall()
        print(f"\nSQLite 'Master' Table ({len(rows_sl)} records):")
        for r in rows_sl[:10]:
            print(f"  - [{r['id']}] {r['Title']} | Source: {r['Source']} | Table: {r['table_name']}")
        if len(rows_sl) > 10:
            print(f"  ... and {len(rows_sl) - 10} more.")
        conn_sl.close()
    else:
        print("SQLite DB file does not exist!")

    # 2. Query PostgreSQL
    try:
        conn_pg = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.environ["POSTGRES_PASSWORD"]
        )
        cur_pg = conn_pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur_pg.execute("SELECT id, title, source, department, table_name, processed_at FROM master")
        rows_pg = cur_pg.fetchall()
        print(f"\nPostgreSQL 'master' Table ({len(rows_pg)} records):")
        for r in rows_pg[:10]:
            print(f"  - [{r['id']}] {r['title']} | Source: {r['source']} | Table: {r['table_name']} | Processed: {r['processed_at']}")
        if len(rows_pg) > 10:
            print(f"  ... and {len(rows_pg) - 10} more.")
            
        cur_pg.execute("SELECT COUNT(*) as count FROM ingestion_history")
        hist_count = cur_pg.fetchone()['count']
        print(f"\nIngestion History count: {hist_count}")
        conn_pg.close()
    except Exception as e:
        print(f"\nPostgreSQL Query failed: {e}")

if __name__ == "__main__":
    main()
