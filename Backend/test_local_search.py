from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

def run_test():
    client = QdrantClient("localhost", port=7000)
    model = SentenceTransformer("BAAI/bge-small-en")

    query = "What are the costs for Bitdefender and Sophos licenses for Adept Technologies?"
    vec = model.encode(query).tolist()

    results = client.query_points(
        collection_name="adept_database",
        query=vec,
        limit=5
    ).points

    print(f"\n--- LOCAL SEARCH RESULTS for: '{query}' ---")
    for r in results:
        p = r.payload
        print(f"Score: {r.score:.3f} | Source: {p.get('source', 'unknown')}")
        print(f"Content: {p.get('text', '')[:500]}...")
        print("-" * 50)

if __name__ == "__main__":
    run_test()
