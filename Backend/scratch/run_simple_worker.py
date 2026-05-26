import os
import sys
import redis
from dotenv import load_dotenv

# Add parent directory to sys.path to allow importing worker
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from rq import Queue, SimpleWorker
load_dotenv()

def run_worker():
    print("=" * 60)
    print(" STARTING WINDOWS COMPATIBLE RQ SIMPLEWORKER ")
    print("=" * 60)
    
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', '6379')
    print(f"Connecting to Redis at {redis_host}:{redis_port}...")
    
    conn = redis.Redis(host=redis_host, port=int(redis_port))
    queue = Queue('ingestion', connection=conn)
    
    # SimpleWorker runs tasks synchronously in the main thread (doesn't use os.fork)
    worker = SimpleWorker([queue], connection=conn)
    print("Windows SimpleWorker is listening for tasks on the 'ingestion' queue...")
    worker.work()

if __name__ == "__main__":
    run_worker()
