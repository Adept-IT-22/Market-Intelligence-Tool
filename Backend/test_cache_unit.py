from cache_manager import set_cached_response, get_cached_response
import time

query = "TEST_QUERY_" + str(time.time())
response = "This is a long test response that should be cached correctly. It contains more than 100 characters to pass the length check. " * 3

print(f"Setting cache for: {query}")
set_cached_response(query, response)

print("Retrieving from cache...")
cached = get_cached_response(query)

if cached == response:
    print("✅ Cache Logic Working (Exact Match)")
else:
    print(f"❌ Cache Logic Failed! Received: {cached[:50]}...")

# Test Semantic Match
fuzzy_query = query + "?"
print(f"Retrieving for fuzzy query: {fuzzy_query}")
cached_fuzzy = get_cached_response(fuzzy_query)
if cached_fuzzy == response:
    print("✅ Cache Logic Working (Semantic Match)")
else:
    print("❌ Semantic Match Failed.")
