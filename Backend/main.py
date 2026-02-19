from flask import Flask, request, g, jsonify
from flask_cors import CORS
import time
import os
from dotenv import load_dotenv
import logging
from agent_manager import AgentManager
from typing import Dict
from models import (
    init_chat_tables, create_user, get_user_by_email, get_user_by_id,
    create_chat_session, get_user_chat_sessions, get_chat_session,
    update_chat_session_title, delete_chat_session,
    add_chat_message, get_chat_messages, update_user_password
)
from auth import hash_password, verify_password, create_token, jwt_required, jwt_optional

#Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)
# Enable CORS for all origins, methods, and headers to support multiple devices on staging
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Initialize chat tables
init_chat_tables()

#========QDRANT CONFIGS=========
load_dotenv()
host = os.getenv("QDRANT_HOST", "localhost")
port = os.getenv("QDRANT_PORT", "8000")

#Just Checking If The Correct URL Is Being Called
qdrant_url = os.getenv("QDRANT_URL", f"http://{host}:{port}")
logger.info(f"Connecting to Qdrant at {qdrant_url}")

#query="I'm a farmer in Limuru and want to explore selling my excess maize stock. How might I go about doing that and am i in the right location?")

@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    display_name = data.get('displayName')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 409

    hashed_pw = hash_password(password)
    user_id = create_user(email, hashed_pw, display_name)
    
    token = create_token(user_id, email)
    return jsonify({
        'token': token,
        'user': {
            'id': user_id,
            'email': email,
            'displayName': display_name
        }
    }), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = create_token(user['id'], user['email'])
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'displayName': user['display_name']
        }
    }), 200

@app.route('/auth/me', methods=['GET'])
@jwt_required
def get_me():
    user = get_user_by_id(g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user': {
        'id': user['id'],
        'email': user['email'],
        'displayName': user['display_name']
    }}), 200

@app.route('/auth/change-password', methods=['POST'])
@jwt_required
def change_password():
    """
    Change password for authenticated users.
    Requires current password verification.
    """
    data = request.json
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')

    if not current_password or not new_password:
        return jsonify({'error': 'Current password and new password are required'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400

    # Get user from database
    user = get_user_by_id(g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Verify current password
    if not verify_password(current_password, user['password_hash']):
        return jsonify({'error': 'Current password is incorrect'}), 401

    # Update password
    from models import update_user_password
    success = update_user_password(g.user_id, hash_password(new_password))
    
    if success:
        logger.info(f"Password changed for user {g.user_id}")
        return jsonify({'message': 'Password updated successfully'}), 200
    else:
        return jsonify({'error': 'Failed to update password'}), 500

# ============== CHAT HISTORY ENDPOINTS ==============

@app.route('/chats', methods=['GET'])
@jwt_required
def list_chats():
    sessions = get_user_chat_sessions(g.user_id)
    return jsonify({'sessions': sessions}), 200

@app.route('/chats', methods=['POST'])
@jwt_required
def create_chat():
    data = request.json
    title = data.get('title', 'New Chat')
    session_id = create_chat_session(g.user_id, title)
    return jsonify({'session_id': session_id}), 201

@app.route('/chats/<int:session_id>', methods=['GET'])
@jwt_required
def get_chat(session_id):
    session = get_chat_session(session_id, g.user_id)
    if not session:
        return jsonify({'error': 'Chat session not found'}), 404
    
    messages = get_chat_messages(session_id)
    return jsonify({
        'session': session,
        'messages': messages
    }), 200

@app.route('/chats/<int:session_id>/rename', methods=['PUT'])
@jwt_required
def rename_chat(session_id):
    data = request.json
    title = data.get('title')
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    success = update_chat_session_title(session_id, g.user_id, title)
    if not success:
        return jsonify({'error': 'Failed to rename chat or unauthorized'}), 404
    
    return jsonify({'success': True}), 200

@app.route('/chats/<int:session_id>', methods=['DELETE'])
@jwt_required
def delete_chat(session_id):
    success = delete_chat_session(session_id, g.user_id)
    if not success:
        return jsonify({'error': 'Failed to delete chat or unauthorized'}), 404
    
    return jsonify({'success': True}), 200

# ============== QUERY ENDPOINT (UPDATED) ==============

@app.route('/query', methods=["POST"])
@jwt_optional
def run_query():
    start_time = time.perf_counter()
    logger.info("=== Incoming Query Request ===")

    try:
        # Get data from JSON body
        data = request.json
        if not data:
            logger.error("No JSON data received")
            return jsonify({"error": "No JSON body found"}), 400

        user_query = data.get("query")
        session_id = data.get("session_id")

        if not user_query:
            logger.error("No query found in payload")
            return jsonify({"error": "Missing 'query' field"}), 400

        logger.info(f"Query: {user_query}")
        logger.info(f"Session: {session_id}, User: {getattr(g, 'user_id', 'Guest')}")

        # If session_id is provided and user is logged in, save user message
        user_id = getattr(g, 'user_id', None)
        if session_id and user_id:
            try:
                add_chat_message(session_id, 'user', user_query)
            except Exception as e:
                logger.warning(f"Failed to save user message: {e}")
        else:
            logger.info("Guest user: Skipping chat history persistence.")

        # Fetch chat history for context
        chat_history = []
        if session_id:
            try:
                chat_history = get_chat_messages(session_id)
            except Exception as e:
                logger.warning(f"Failed to fetch chat history: {e}")

        # Initialize Agent and Pipeline
        logger.info("Initializing AgentManager...")
        manager = AgentManager(query=user_query, chat_history=chat_history)
        
        logger.info("Executing Pipeline...")
        results = manager.pipeline()

        logger.info("Synthesis complete. Formatting response...")
        duration = time.perf_counter() - start_time
        response_text = str(results)
        
        # If session_id is provided and user is logged in, save assistant message
        if session_id and user_id:
            try:
                add_chat_message(session_id, 'assistant', response_text, round(duration, 2))
            except Exception as e:
                logger.warning(f"Failed to save assistant message: {e}")

        logger.info(f"Query handled successfully in {duration:.2f}s")
        
        # Append sign-up encouragement for guests
        final_response = response_text
        if not user_id:
            final_response += '<p style="font-size: 10px; color: gray; text-align: center; margin-top: 20px;"><em>Note: Your chat history is not being saved. <a href="/auth/login" style="color: inherit;">Sign up or Log in</a> to keep track of your research sessions.</em></p>'

        return jsonify({"Results": final_response, "execution_time": round(duration, 2)})

    except Exception as e:
        logger.exception("FATAL ERROR in /query endpoint")
        return jsonify({"error": str(e)}), 500

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
    
    # Log incoming request details for debugging
    logger.info(f"Upload request - Content-Type: {request.content_type}, Content-Length: {request.content_length}, Headers: X-File-Name={request.headers.get('X-File-Name', 'MISSING')}")
    
    # Support for Multipart Form (Frontend), Raw Binary, and JSON (Power Automate)
    content = b''
    filename = f"upload_{int(time.time())}.pdf"
    
    try:
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return {"error": "No file selected"}, 400
            filename = file.filename
            content = file.read()
        else:
            # Handle API/Power Automate uploads
            # 1. Get raw data first
            raw_body = request.get_data()
            
            # 2. Try to parse as JSON regardless of Content-Type (Power Automate often sends mismatched headers)
            is_valid_json = False
            try:
                # Only try parsing if it looks like JSON to avoid overhead/errors on large binaries
                if raw_body and raw_body.strip().startswith(b'{'):
                    import json
                    data = json.loads(raw_body)
                    is_valid_json = True
                    
                    logger.info(f"JSON upload - Keys received: {list(data.keys())}")
                    filename = request.headers.get('X-File-Name', data.get('fileName', filename))
                    body = data.get('$content', data.get('content', data.get('body', '')))
                    
                    # Decode base64 if present
                    import base64
                    try:
                        content = base64.b64decode(body) if body else b''
                        logger.info(f"JSON upload - Decoded {len(content)} bytes successfully")
                    except Exception as b64_err:
                        # Fallback: maybe it's not base64 but raw string?
                        logger.warning(f"JSON base64 decode failed, using raw body value: {b64_err}")
                        content = body.encode('utf-8') if isinstance(body, str) else b''
            except Exception as json_err:
                logger.info(f"Not valid JSON (treating as binary): {json_err}")
            
            # 3. If not JSON, treat raw body as the file content
            if not is_valid_json:
                content = raw_body
                filename = request.headers.get('X-File-Name', filename)
                logger.info(f"Binary upload - Content length: {len(content)} bytes")

    except Exception as parse_err:
        logger.error(f"Upload parsing error: {parse_err}")
        return {"error": f"Failed to parse upload: {str(parse_err)}"}, 400
    
    if not content:
        logger.error(f"Upload failed: No content received. Content-Type: {request.content_type}")
        return {"error": "No file content found in request body"}, 400

    # Validate file type (skip for API uploads without proper filename)
    if not allowed_file(filename):
        # If filename has no extension, default to .pdf
        if '.' not in filename:
            filename = filename + '.pdf'
        elif not allowed_file(filename):
            return {
                "error": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            }, 400
    
    # Validate file size
    file_size = len(content)
    if file_size > MAX_FILE_SIZE_BYTES:
        return {
            "error": f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"
        }, 400
    
    # Decode information
    department = "General"
    if 'data' in locals() and isinstance(data, dict):
         # Extract department from JSON (Power Automate)
         department = data.get('source', data.get('dept', data.get('category', 'General')))
    elif request.args.get('source'):
         # Extract from Query Param (if used)
         department = request.args.get('source')

    # Save the file
    from werkzeug.utils import secure_filename
    clean_filename = secure_filename(filename)
    timestamp = int(time.time())
    unique_filename = f"{timestamp}_{clean_filename}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    try:
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"File uploaded: {unique_filename} ({file_size / 1024:.1f} KB) -> Dept: {department}")
        
        # --- Trigger Automatic Ingestion ---
        try:
            from ingest_data import DataIngester
            logger.info(f"Auto-ingesting file: {unique_filename} for {department}")
            ingester = DataIngester()
            
            # Determine type
            ext = clean_filename.rsplit('.', 1)[1].lower() if '.' in clean_filename else 'pdf'
            type_map = {
                'xlsx': 'excel', 'xls': 'excel', 
                'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx',
                'txt': 'pdf', 'csv': 'excel', 'md': 'pdf',
                'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image'
            }
            f_type = type_map.get(ext, 'pdf')
            
            # Process
            ingester.process_input(
                input_path=file_path,
                source_type=f_type,
                title=filename,
                sectors="General", 
                summary="Uploaded via SharePoint Automation",
                department=department
            )
            logger.info("Auto-ingestion successful.")
            
        except Exception as ingest_err:
             logger.error(f"Auto-ingestion failed: {ingest_err}")
             # We don't return 500 here because the file WAS uploaded, just not indexed.
             # You might want to include a warning in the response.

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
    
    app.run(host="0.0.0.0", port=8000, threaded=True)
    