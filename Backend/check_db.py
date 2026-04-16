import sqlite3

db_path = "d:/Projects/ProjectsWork/MIT/Backend/DB/market-intelligence.db"

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    
    # Check agriculture report routing table
    print("=== route_national_agriculture_production_report ===")
    cursor.execute("SELECT file_type, COUNT(*) as cnt, MIN(LENGTH(chunk_text)) as min_len, MAX(LENGTH(chunk_text)) as max_len FROM route_national_agriculture_production_report GROUP BY file_type")
    for row in cursor.fetchall():
        print(f"  file_type={row[0]}, chunks={row[1]}, min_text_len={row[2]}, max_text_len={row[3]}")
    
    # Show a sample chunk from the PDF
    print("\n=== Sample PDF chunk ===")
    cursor.execute("SELECT chunk_text FROM route_national_agriculture_production_report WHERE file_type='pdf' LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(row[0][:300])
    else:
        print("No PDF chunks found!")

# Check Qdrant
from qdrant_client import QdrantClient
client = QdrantClient("localhost", port=7000)
count = client.count("adept_database")
print(f"\n=== Qdrant adept_database total vectors: {count.count} ===")

# Search for agriculture content
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-small-en")
vec = model.encode("maize corn agriculture production Kenya").tolist()
results = client.query_points(collection_name="adept_database", query=vec, limit=3).points
print("\n=== Top 3 Qdrant hits for 'maize corn agriculture production Kenya' ===")
for r in results:
    p = r.payload
    print(f"  score={r.score:.3f} | title={p.get('title','?')[:50]} | file_type={p.get('file_type','?')} | text={p.get('text','')[:150]}")
