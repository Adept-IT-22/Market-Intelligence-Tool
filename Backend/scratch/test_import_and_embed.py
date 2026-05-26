import time
print("Importing SentenceTransformer...")
from sentence_transformers import SentenceTransformer
print("Loading model...")
t0 = time.time()
try:
    embedder = SentenceTransformer("BAAI/bge-small-en")
    print(f"Loaded successfully in {time.time() - t0:.2f}s")
except Exception as e:
    print(f"Failed to load: {e}")
