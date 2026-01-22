from flask import Flask, request 
from flask_cors import CORS
import time
import os
from dotenv import load_dotenv
import logging
from agent_manager import AgentManager
from typing import Dict

#Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)
CORS(app)

#========QDRANT CONFIGS=========
load_dotenv()
host = os.getenv("QDRANT_HOST", "localhost")
port = os.getenv("QDRANT_PORT", "8000")

#Just Checking If The Correct URL Is Being Called
qdrant_url = os.getenv("QDRANT_URL", f"http://{host}:{port}")
logger.info(f"Connecting to Qdrant at {qdrant_url}")

#query="I'm a farmer in Limuru and want to explore selling my excess maize stock. How might I go about doing that and am i in the right location?")

@app.route('/query', methods=["POST"])
def run_query()->Dict:
    start_time = time.perf_counter()
    logger.info("Running Query...")

    # Get data from JSON body
    data = request.json
    user_query = data.get("query")

    if not user_query:
        logger.error("No query found")
        return {"error": "Missing 'query' field in JSON body"}, 400

    logger.info(f"Running query: {user_query}")
    
    try:
        manager = AgentManager(query=user_query)
        results = manager.pipeline()

        logger.info("============QUERY RESULTS==========")
        logger.info(results)
        logger.info("====================================")
        
        duration = time.perf_counter() - start_time
        logger.info(f"This task took {duration:.2f} seconds")
        logger.info(f"Type of results['text'] is: {type(results)}")
        return {"Results": str(results), "execution_time": round(duration, 2)}

    except Exception as e:
        logger.error(f"Couldn't run the query: {str(e)}")
        return {"Error": str(e)}, 500

# ============== FILE UPLOAD ENDPOINT ==============
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configuration
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'pptx', 'xlsx', 'xls', 'txt', 'csv', 'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Upload a file for analysis.
    - Max size: 10MB
    - Allowed types: pdf, docx, pptx, xlsx, xls, txt, csv, png, jpg, jpeg
    """
    start_time = time.perf_counter()
    
    if 'file' not in request.files:
        return {"error": "No file part in the request"}, 400
    
    file = request.files['file']
    
    if file.filename == '':
        return {"error": "No file selected"}, 400
    
    # Validate file type
    if not allowed_file(file.filename):
        return {
            "error": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        }, 400
    
    # Validate file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE_BYTES:
        return {
            "error": f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"
        }, 400
    
    # Save the file
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    timestamp = int(time.time())
    unique_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    try:
        file.save(file_path)
        logger.info(f"File uploaded: {unique_filename} ({file_size / 1024:.1f} KB)")
        
        duration = time.perf_counter() - start_time
        return {
            "success": True,
            "filename": unique_filename,
            "original_filename": filename,
            "size_kb": round(file_size / 1024, 1),
            "execution_time": round(duration, 2)
        }, 200
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        return {"error": "Failed to save file"}, 500

@app.route('/upload/limits', methods=['GET'])
def get_upload_limits():
    """Return the current upload limits for the frontend."""
    return {
        "max_size_mb": MAX_FILE_SIZE_MB,
        "allowed_extensions": list(ALLOWED_EXTENSIONS)
    }

if __name__ == "__main__":
    logger.info("App starting...")
    
    app.run(host="0.0.0.0", port=8000)
    