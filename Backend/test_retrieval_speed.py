import time
import uuid
import logging
from agent_manager import AgentManager

# Silence external loggers for clean output
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

def run_benchmark():
    print("=" * 60)
    print(" TARGETED RETRIEVAL BENCHMARK: PRECISION SCOUT V2 ")
    print("=" * 60)
    
    test_queries = [
        f"What are the quarterly GDP projections for East Africa? {uuid.uuid4()}",
        f"Analyze the impact of global supply chain disruptions on local fertilizer costs. {uuid.uuid4()}",
        f"Summarize the employee turnover rates in the Q3 HR report. {uuid.uuid4()}",
        f"What is the projected ROI for new solar energy investments? {uuid.uuid4()}"
    ]

    total_time = 0

    for idx, query in enumerate(test_queries, 1):
        print(f"\n[Test {idx}/{len(test_queries)}] Query: '{query}'")
        
        manager = AgentManager(query=query)
        
        # We only want to benchmark the Qdrant retrieval, not the LLM generation
        start_time = time.perf_counter()
        
        # This will trigger the two-tier PageIndex search
        results = manager.search_qdrant(top_k=5)
        
        end_time = time.perf_counter()
        elapsed_ms = (end_time - start_time) * 1000
        total_time += elapsed_ms
        
        print(f"   Retrieval Time : {elapsed_ms:.2f} ms")
        print(f"   Chunks Found   : {len(results)}")
        
        if results:
            print(f"   Top Match      : Score {results[0].score:.3f} | Doc #{results[0].payload.get('master_id', 'N/A')} ")
        else:
            print("   No relevant chunks found.")

    print("\n" + "=" * 60)
    print(f" AVERAGE RETRIEVAL LATENCY: {total_time / len(test_queries):.2f} ms")
    print("=" * 60)

if __name__ == "__main__":
    run_benchmark()
