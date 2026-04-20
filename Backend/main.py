from flask import Flask, request, g, jsonify, Response
import json
from flask_cors import CORS
import time
import os
from datetime import datetime
from dotenv import load_dotenv
import logging
from agent_manager import AgentManager, get_embeddings_model
from cache_manager import get_cached_response, set_cached_response
from typing import Dict
from models import (
    init_chat_tables, create_user, get_user_by_email, get_user_by_id,
    create_chat_session, get_user_chat_sessions, get_chat_session,
    update_chat_session_title, delete_chat_session,
    add_chat_message, get_chat_messages, update_user_password
)
from auth import hash_password, verify_password, create_token, jwt_required, jwt_optional
from cache_manager import get_cached_response, set_cached_response
from report_engine import engine, REPORT_TYPES

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
        data = request.json
        if not data:
            return jsonify({"error": "No JSON body found"}), 400

        user_query = data.get("query")
        session_id = data.get("session_id")
        stream = data.get("stream", False)

        if not user_query:
            return jsonify({"error": "Missing 'query' field"}), 400

        # --- 1. Identity & Context ---
        user_id = getattr(g, 'user_id', None)
        logger.info(f"Query: {user_query} | Session: {session_id} | User: {user_id or 'Guest'}")

        # --- 1. Check Cache ---
        cached = get_cached_response(user_query)
        if cached:
            logger.info("Cache HIT: Returning stored response.")
            # Persist history on cache hit
            if session_id and user_id:
                try:
                    add_chat_message(session_id, 'user', user_query)
                    add_chat_message(session_id, 'assistant', cached, 0.0)
                except Exception as e:
                    logger.warning(f"Failed to save history for cache hit: {e}")

            if not stream:
                return jsonify({"Results": cached, "execution_time": 0.0, "cached": True})
            else:
                def generate_cached():
                    yield f"data: {json.dumps({'chunk': cached})}\n\n"
                    yield f"data: {json.dumps({'done': True, 'execution_time': 0.0, 'cached': True})}\n\n"
                return Response(generate_cached(), mimetype='text/event-stream')

        # --- 2. Build Context ---
        if session_id and user_id:
            try:
                add_chat_message(session_id, 'user', user_query)
            except Exception as e:
                logger.warning(f"Failed to save user message for session {session_id}: {e}")

        chat_history = []
        if session_id:
            try: chat_history = get_chat_messages(session_id)
            except Exception as e:
                logger.warning(f"Failed to fetch chat history for session {session_id}: {e}")

        manager = AgentManager(query=user_query, chat_history=chat_history)
        
        # --- 5. Execute Pipeline ---
        if stream:
            def generate():
                full_response = ""
                for chunk in manager.pipeline_stream():
                    full_response += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                
                duration = time.perf_counter() - start_time
                if session_id and user_id:
                    try: add_chat_message(session_id, 'assistant', full_response, round(duration, 2))
                    except Exception as e:
                        logger.warning(f"Failed to save assistant message to history: {e}")
                set_cached_response(user_query, full_response)
                yield f"data: {json.dumps({'done': True, 'execution_time': round(duration, 2)})}\n\n"

            return Response(generate(), mimetype='text/event-stream')
        else:
            results = manager.pipeline()
            duration = time.perf_counter() - start_time
            if session_id and user_id:
                try: add_chat_message(session_id, 'assistant', results, round(duration, 2))
                except Exception as e:
                    logger.warning(f"Failed to save assistant message to history: {e}")
            set_cached_response(user_query, results)
            return jsonify({"Results": results, "execution_time": round(duration, 2)})

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
        # Extract department from JSON with multiple aliases (Fix 2 & Fix 3)
        department = (
            data.get('department') or
            data.get('Department') or
            data.get('source') or
            data.get('dept') or
            data.get('category') or
            "General"
        )
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
        
        # --- Trigger Automatic Ingestion in Background ---
        def run_ingestion_task(task_file_path, task_f_type, task_filename, task_department):
            try:
                from ingest_data import DataIngester
                logger.info(f"Background Ingestion Started: {task_filename} for {task_department}")
                ingester = DataIngester()
                ingester.process_input(
                    input_path=task_file_path,
                    source_type=task_f_type,
                    title=task_filename,
                    sectors="General",
                    summary="Automated Upload via API/SharePoint",
                    department=task_department
                )
                logger.info(f"Background Ingestion Successful: {task_filename}")
            except Exception as ingest_err:
                logger.error(f"Background Ingestion Failed for {task_filename}: {ingest_err}")

        # Determine type
        ext = clean_filename.rsplit('.', 1)[1].lower() if '.' in clean_filename else 'pdf'
        type_map = {
            'xlsx': 'excel', 'xls': 'excel', 
            'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx',
            'txt': 'pdf', 'csv': 'excel', 'md': 'pdf',
            'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image'
        }
        f_type = type_map.get(ext, 'pdf')

        import threading
        thread = threading.Thread(target=run_ingestion_task, args=(file_path, f_type, filename, department))
        thread.start()
        logger.info(f"Auto-ingestion queued for {unique_filename}")

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

# ============== WORKSPACE ENDPOINTS (v2) ==============
from workspace_manager import (
    create_project, list_projects, get_project, delete_project,
    save_artifact, list_artifacts, get_artifact, get_project_context
)

@app.route('/projects', methods=['GET'])
@jwt_required
def api_list_projects():
    """List all workspace projects."""
    projects = list_projects()
    return jsonify({"projects": projects}), 200

@app.route('/projects', methods=['POST'])
@jwt_required
def api_create_project():
    """Create a new workspace project."""
    data = request.json
    name = data.get("name")
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    project_id = create_project(name, description, user_id=g.user_id)
    return jsonify({"project_id": project_id, "success": True}), 201

@app.route('/projects/<project_id>', methods=['GET'])
@jwt_required
def api_get_project(project_id):
    """Get project details + artifacts."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"project": project}), 200

@app.route('/projects/<project_id>', methods=['DELETE'])
@jwt_required
def api_delete_project(project_id):
    """Delete a workspace project."""
    success = delete_project(project_id)
    if not success:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"success": True}), 200

@app.route('/projects/<project_id>/artifacts', methods=['GET'])
@jwt_required
def api_list_artifacts(project_id):
    """List all artifacts for a project."""
    artifacts = list_artifacts(project_id)
    return jsonify({"artifacts": artifacts}), 200

@app.route('/projects/<project_id>/artifacts/<filename>', methods=['GET'])
@jwt_required
def api_get_artifact(project_id, filename):
    """Read a specific artifact."""
    content = get_artifact(project_id, filename)
    if content is None:
        return jsonify({"error": "Artifact not found"}), 404
    return jsonify({"content": content}), 200

@app.route('/projects/<project_id>/query', methods=['POST'])
@jwt_required
def api_project_query(project_id):
    """Query within project context — results auto-saved as artifacts."""
    start_time = time.perf_counter()
    data = request.json
    user_query = data.get("query")
    session_id = data.get("session_id")

    if not user_query:
        return jsonify({"error": "Missing 'query' field"}), 400

    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Build context with project memory
    project_context = get_project_context(project_id)

    chat_history = []
    if session_id:
        try: chat_history = get_chat_messages(session_id)
        except: pass

    # Import AgentLoop here if not at top of file to avoid circular imports
    from agent_loop import AgentLoop
    
    loop = AgentLoop(
        query=user_query, 
        project_id=project_id, 
        session_id=session_id, 
        chat_history=chat_history
    )
    
    # Run the full plan -> retrieve -> think -> act -> store cycle
    loop_result = loop.run()
    results = loop_result["answer"]

    duration = time.perf_counter() - start_time

    # Save to chat history if session exists
    if session_id:
        try:
            add_chat_message(session_id, 'user', user_query)
            add_chat_message(session_id, 'assistant', results, round(duration, 2))
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

    set_cached_response(user_query, results)

    return jsonify({
        "Results": results,
        "execution_time": round(duration, 2),
        "artifact": loop_result["artifact"],
        "project_id": project_id,
        "confidence": loop_result["confidence"],
        "plan": loop_result["plan_executed"]
    })

# ============== REPORT AUTOMATION ENGINE ENDPOINTS ==============

@app.route('/reports/types', methods=['GET'])
@jwt_optional
def list_report_types():
    """List available report categories and their titles."""
    types = [{"id": k, "title": v["title"]} for k, v in REPORT_TYPES.items()]
    return jsonify({"report_types": types}), 200

@app.route('/reports/questions/<report_type>', methods=['GET'])
@jwt_optional
def get_report_questions(report_type):
    """Fetch the multi-step wizard schema for a report type."""
    if report_type not in REPORT_TYPES:
        return jsonify({"error": "Unknown report type"}), 404
    return jsonify({"schema": REPORT_TYPES[report_type]["sections"]}), 200

@app.route('/reports/auto-fill', methods=['POST'])
@jwt_optional
def generate_report_autofill():
    """
    Parses unstructured notes to fill out the form implicitly.
    Expects: { "type": "sprint", "raw_text": "..." }
    """
    data = request.json
    report_type = data.get("type")
    raw_text = data.get("raw_text")

    if not report_type or not raw_text:
        return jsonify({"error": "Missing report_type or raw_text"}), 400

    try:
        filled_data = engine.parse_unstructured_notes(report_type, raw_text)
        return jsonify({"answers": filled_data, "success": True}), 200
    except Exception as e:
        logger.error(f"Auto-fill failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reports/generate', methods=['POST'])
@jwt_optional
def generate_report_draft():
    """
    Generate a section-by-section draft from wizard answers.
    Expects: { "type": "sprint", "answers": {...} }
    """
    data = request.json
    report_type = data.get("type")
    answers = data.get("answers", {})
    
    if not report_type or report_type not in REPORT_TYPES:
        return jsonify({"error": "Invalid or missing report type"}), 400

    try:
        draft = engine.generate_report_draft(report_type, answers)
        return jsonify({"draft": draft, "success": True}), 200
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reports/refine', methods=['POST'])
@jwt_optional
def refine_report_section():
    """
    Refine a specific section using a targeted action (Executive, Clarify, Shorten).
    """
    data = request.json
    report_type = data.get("type")
    section_id = data.get("section_id")
    action = data.get("action")
    current_text = data.get("current_text")
    answers = data.get("answers", {})

    if not all([report_type, section_id, action, current_text]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        refined_text = engine.refine_section(report_type, section_id, action, current_text, answers)
        return jsonify({"refined_text": refined_text, "success": True}), 200
    except Exception as e:
        logger.error(f"Refinement failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reports/analyze', methods=['POST'])
@jwt_optional
def analyze_report_consistency():
    """
    Analyze the full report for inconsistencies, risks, and suggestions.
    """
    data = request.json
    report_type = data.get("type")
    sections = data.get("sections") # The current draft object

    if not report_type or not sections:
        return jsonify({"error": "Missing report type or sections"}), 400

    try:
        analysis = engine.analyze_report(report_type, sections)
        return jsonify({"analysis": analysis, "success": True}), 200
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reports/export', methods=['POST'])
@jwt_optional
def export_report_docx():
    """
    Finalize and export a report to DOCX.
    Expects: { "type": "sprint", "data": {...}, "project_id": "optional-id" }
    """
    data = request.json
    report_type = data.get("type")
    sections = data.get("sections", [])
    report_title = data.get("title", "")
    project_id = data.get("project_id")
    
    if not report_type or report_type not in REPORT_TYPES:
        return jsonify({"error": "Invalid report type"}), 400

    # 1. Generate local filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{timestamp}_{REPORT_TYPES[report_type]['title'].replace(' ', '_')}.docx"
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        # 2. Fill Template
        success = engine.export_to_docx(report_type, sections, temp_path, report_title)
        if not success:
            return jsonify({"error": "Failed to generate DOCX. Template missing?"}), 500
            
        # 3. If project_id is provided, save as artifact
        if project_id:
            from workspace_manager import save_artifact
            # Note: save_artifact takes markdown content by default, 
            # we may need a specific Binary Artifact handler later, 
            # but for now we'll just return the file.
            pass
            
        from flask import send_file
        return send_file(temp_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    logger.info("App starting...")
    
    app.run(host="0.0.0.0", port=5000, threaded=True)
    