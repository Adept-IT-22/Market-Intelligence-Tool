import requests
import json

BASE_URL = "http://localhost:8000"

def test_query(query):
    print(f"\n--- Testing Query: {query} ---")
    payload = {"query": query}
    try:
        response = requests.post(f"{BASE_URL}/query", json=payload)
        if response.status_code == 200:
            results = response.json()
            answer = results.get("Results", "")
            print(f"Response status: 200")
            print(f"Answer Preview: {answer[:300]}...")
            
            # Check for thought trace
            if "AI Thought Trace" in answer:
                print("[OK] Found AI Thought Trace")
            else:
                print("[FAIL] Missing AI Thought Trace")
                
            # Check for references
            if "References" in answer:
                print("[OK] Found References section")
            else:
                print("[FAIL] Missing References section")
                
            return results
        else:
            print(f"[FAIL] Query failed with status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")
        return None

if __name__ == "__main__":
    # Test 1: General Query
    res1 = test_query("What does the data you have show? in a sentence??")
    
    # Test 2: Specific Query that was failing (should now use multiple sources)
    res2 = test_query("What are Kenya's key economic sectors and their growth trends")
