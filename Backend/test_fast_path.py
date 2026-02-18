import requests
import time

BASE_URL = "http://localhost:8000"

def test_fast_path(query):
    print(f"\n--- Testing Fast Path Query: '{query}' ---")
    start = time.perf_counter()
    payload = {"query": query}
    try:
        response = requests.post(f"{BASE_URL}/query", json=payload)
        duration = time.perf_counter() - start
        if response.status_code == 200:
            results = response.json()
            answer = results.get("Results", "")
            exec_time = results.get("execution_time", 0)
            print(f"Response status: 200")
            print(f"Actual Duration: {duration:.2f}s (Backend reported: {exec_time}s)")
            print(f"Answer: {answer}")
            
            if "Note: Your chat history is not being saved" in answer:
                print("[OK] Found Guest Sign-up encouragement")
            else:
                print("[FAIL] Missing Guest Sign-up encouragement")
                
            return results
        else:
            print(f"[FAIL] Query failed with status {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")

if __name__ == "__main__":
    # Test 1: Greeting (Fast Path)
    test_fast_path("Hi there!")
    
    # Test 2: Another greeting
    test_fast_path("How are you?")
    
    # Test 3: Substantive Query (Should be slow)
    print("\n--- Testing Substantive Query (Should be slower, but optimized) ---")
    test_fast_path("Tell me about the real estate market in Kenya")
