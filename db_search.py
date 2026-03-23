import sqlite3

DB_PATH = r"d:\Projects\ProjectsWork\MIT\Backend\DB\market-intelligence.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]

found_results = []
for table in tables:
    try:
        cursor.execute(f"PRAGMA table_info('{table}')")
        columns = [row[1] for row in cursor.fetchall()]
        
        where_clauses = [f"LOWER(\"{col}\") LIKE '%limuru%' OR LOWER(\"{col}\") LIKE '%maize%'" for col in columns]
        if not where_clauses: continue
        query = f"SELECT * FROM \"{table}\" WHERE " + " OR ".join(where_clauses)
        
        cursor.execute(query)
        rows = cursor.fetchall()
        for r in rows:
            found_results.append((table, r))
    except Exception as e:
        print(f"Error on table {table}: {e}")

if not found_results:
    print("Found NOTHING in the SQLite database matching 'limuru' or 'maize'.")
else:
    print(f"Found {len(found_results)} related rows.")
    for table, row in found_results[:10]:
         print(f"Table: {table}")
         print(f"Row: {row[:5]}")

conn.close()
