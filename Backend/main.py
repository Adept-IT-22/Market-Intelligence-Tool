from flask import Flask, request
import os
from dotenv import load_dotenv
import logging
from agent_manager import AgentManager
from typing import Dict

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

#========QDRANT CONFIGS=========
load_dotenv()
host = os.getenv("QDRANT_HOST", "localhost")
port = os.getenv("QDRANT_PORT", "8000")
qdrant_url = os.getenv("QDRANT_URL", f"http://{host}:{port}")

print(f"Connecting to Qdrant at {qdrant_url}")


#query="I'm a farmer in Limuru and want to explore selling my excess maize stock. How might I go about doing that and am i in the right location?")

@app.route('/query', methods=["GET", "POST"])
def run_query()->Dict:

    logger.info("Running Query...")

    user_query = request.args.get("q")
    if not user_query:
        logger.error("No query found")
        return {"error": "Missing query"}, 400

    logger.info(f"Running query: {user_query}")
    try:
        manager = AgentManager(query=user_query)
        results = manager.pipeline()

        logger.info("============QUERY RESULTS==========")
        logger.info(results)
        return {"results": results}

    except Exception as e:
        logger.error(f"Couldn't run the query: {str(e)}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    logger.info("App starting...")
    app.run(host="0.0.0.0", port=8000)
    