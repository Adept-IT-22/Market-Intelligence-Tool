import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../DB/market-intelligence.db")

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)

    # Check Master content
    try:
        cursor.execute("SELECT * FROM Master LIMIT 5")
        rows = cursor.fetchall()
        print("\nMaster Table Sample:")
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading Master table: {e}")

    conn.close()

if __name__ == "__main__":
    check_db()
