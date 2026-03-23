import os
import sqlite3
import pandas as pd
import httpx
import asyncio
from google.auth import default
from google.auth.transport.requests import Request
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import logging
import json
import re
from urllib.parse import urlparse
from typing import Optional, Any, Generator, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
import queue
import threading

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Vertex AI / Gemini Configuration ---
# DO NOT hardcode Project IDs here. Ensure these are set in your .env file on Staging.
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REGION = os.getenv("GCP_REGION", "us-central1")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

if not PROJECT_ID:
    logger.error("!!! CRITICAL: GCP_PROJECT_ID is not set in environment. Gemini calls WILL fail with DNS errors. !!!")
    PROJECT_ID = "missing-project-id"

VERTEX_ENDPOINT = (
    f"https://{REGION}-aiplatform.googleapis.com/v1/"
    f"projects/{PROJECT_ID}/locations/{REGION}/"
    f"publishers/google/models/{GEMINI_MODEL_NAME}:generateContent"
)

def _build_system_prompt(chat_history=None) -> str:
    """Consolidated system prompt logic for consistency."""
    prompt = (
        "You are an expert Market Intelligence Analyst for Adept Technologies Ltd.\n"
        "COMPANY CONTEXT:\n"
        "Adept Technologies Ltd. is headquartered in Nairobi, Kenya.\n"
        "When users refer to 'abroad', 'international', or 'overseas', they mean OUTSIDE Kenya.\n"
        "'Local' means within Kenya. Always interpret geographic terms relative to Kenya as the home base.\n\n"
        "Instructions:\n"
        "1. Prioritize provided context. If the answer is not in the context, say so.\n"
        "2. Keep responses professional, data-driven, and highly structured using clear Markdown.\n"
        "3. EXTRACT AND PRESENT DATA: You MUST extract specific facts, metrics, prices, and insights from the documents and include them directly in your response. DO NOT just provide file links or tell the user to read the documents. Actually answer their question using the data.\n"
        "4. INLINE CITATIONS: When citing sources in the text, use ONLY the markdown link format: [Filename](URI).\n"
        "   - Display text = clean filename ONLY (e.g., 'MarketReport.pdf'). NEVER use internal table names like 'route_...' or 'detail_...'.\n"
        "   - URI = The full local path provided in the context.\n"
        "   - Example: ...as seen in [ProjectSheet.pdf](C:\\shared\\ProjectSheet.pdf).\n"
        "5. SOURCES ANALYZED SECTION: At the VERY END of your response, include a 'Sources Analyzed' section for the sources actually present in the context.\n"
        "   - If no sources were retrieved, explicitly say that no supporting documents were available.\n"
        "   - List EVERY document that was provided in the context, even if you did not quote it directly.\n"
        "   - This ensures the user can access all relevant documents independently.\n"
        "   - Format: Bullet point + markdown link ONLY.\n"
        "   - Example:\n"
        "     ## Sources Analyzed\n"
        "     - [Report1.pdf](C:\\path\\to\\Report1.pdf)\n"
        "     - [Data.xlsx](C:\\path\\to\\Data.xlsx)\n"
    )
    if chat_history:
        # Take last 6 messages to avoid context overflow but maintain continuity
        recent_history = chat_history[-6:]
        history_lines = [f"{m['role'].upper()}: {m['content']}" for m in recent_history]
        prompt += "\n=== CONVERSATION HISTORY ===\n" + "\n".join(history_lines) + "\n"
    return prompt


logger.info(f"Gemini initialized for Project: {PROJECT_ID} in Region: {REGION}")

# --- Concurrency & Rate Limiting ---
RATE_LIMIT_SECONDS = 0.5  # Slightly more conservative
_gemini_lock = threading.Lock()
_last_call_time = 0

# Qdrant Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))

# Project Paths
current_directory = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.getenv("DATABASE_PATH")

if not DATABASE_PATH:
    DATABASE_PATH = os.path.join(current_directory, "DB", "market-intelligence.db")
    logger.info(f"DATABASE_PATH not found in .env, using default: {DATABASE_PATH}")

# Models
EMBEDDING_MODEL = "BAAI/bge-small-en"
COLLECTION_NAME = "adept_database"

# Global Cache for Embedding Model
_CACHED_EMBEDDINGS = None

def get_embeddings_model():
    global _CACHED_EMBEDDINGS
    if _CACHED_EMBEDDINGS is None:
        logger.info("Loading Embedding Model (Cached)...")
        _CACHED_EMBEDDINGS = SentenceTransformer(EMBEDDING_MODEL)
    return _CACHED_EMBEDDINGS

# --- Gemini API Internal (Vertex) ---

def get_access_token() -> str:
    """Gets a fresh access token for Google Cloud."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        if not os.path.isabs(creds_path):
            potential_path = os.path.join(current_directory, creds_path)
            if os.path.exists(potential_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = potential_path
                logger.info(f"Resolved relative GOOGLE_APPLICATION_CREDENTIALS to: {potential_path}")
            else:
                logger.warning(f"GOOGLE_APPLICATION_CREDENTIALS set to relative path '{creds_path}' but file not found at '{potential_path}'")
        else:
            logger.info(f"Using absolute GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
            if not os.path.exists(creds_path):
                logger.warning(f"GOOGLE_APPLICATION_CREDENTIALS points to non-existent file: {creds_path}")

    try:
        creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        logger.warning(f"Failed to get GCP default credentials: {e}. Falling back to GEMINI_API_KEY env.")
        fallback_key = os.getenv("GEMINI_API_KEY", "")
        if not fallback_key:
            logger.error("No valid GCP credentials OR GEMINI_API_KEY found.")
        return fallback_key

async def _call_gemini_api_internal(prompt: str) -> str:
    """Internal function to call Gemini API with explicit retries."""
    max_attempts = 5
    last_exception = None
    
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json" if "JSON" in prompt.upper() or "Output JSON:" in prompt else "text/plain"
        },
    }

    # Reuse client across attempts for connection pooling
    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    logger.info(f"Retrying Gemini call... attempt #{attempt}")
                else:
                    logger.info("Starting Gemini API call...")

                response = await client.post(VERTEX_ENDPOINT, headers=headers, json=data)
                
                try:
                    response_data = response.json()
                except Exception as e:
                    # JSON parsing failure is usually fatal unless server error text
                    logger.error(f"Failed to parse Gemini response as JSON. Status: {response.status_code}, Error: {e}, Payload: {response.text[:500]}")
                    if response.status_code >= 500:
                        raise ValueError(f"Server Error {response.status_code}: {response.text[:500]}") from e
                    raise ValueError(f"Gemini returned non-JSON response: {response.text[:500]}") from e
                
                if response.status_code != 200:
                    logger.warning(f"Gemini API returned {response.status_code}: {response_data}")
                    
                    # Handle retryable errors directly
                    if response.status_code == 429 or response.status_code >= 500:
                        logger.warning(f"Gemini retryable error {response.status_code}. Retrying...")
                        # Calculate wait time directly here or use a helper, but reusing loop index logic is cleaner if we just continue
                        # However, we must wait before continuing to avoid tight loop if pure continue usage.
                        # Actually, better to raise a specific RetryError or handle wait here.
                        
                        wait_time = min(60, 2 ** (attempt - 1))
                        await asyncio.sleep(wait_time)
                        continue

                    # 400s are usually client errors (not retryable)
                    raise ValueError(f"Gemini API Client Error {response.status_code}: {response_data}")
                
                # Robust parsing of candidates
                candidates = response_data.get("candidates", [])
                if not candidates:
                    # Check for blocking reasons
                    prompt_feedback = response_data.get("promptFeedback", {})
                    if prompt_feedback:
                        logger.error(f"Gemini Prompt Blocked: {prompt_feedback}")
                        return "UNAVAILABLE: The query prompt was blocked by Gemini safety filters."
                    
                    logger.warning(f"Gemini returned no candidates. Full response: {response_data}")
                    raise ValueError(f"Gemini returned empty candidates list (no feedback reason). Response: {response_data}")
                
                candidate = candidates[0]
                content = candidate.get("content")
                if not content or "parts" not in content:
                    finish_reason = candidate.get("finishReason")
                    logger.error(f"Gemini content empty (Reason: {finish_reason}). Full Candidate: {candidate}")
                    return f"UNAVAILABLE: Gemini blocked the response generation. Reason: {finish_reason}"
                    
                ret_val = content["parts"][0]["text"]
                return ret_val
                
            except Exception as e:
                # Check for httpx errors that should trigger retry
                should_retry = False
                if isinstance(e, httpx.HTTPStatusError):
                     if e.response.status_code in [429, 500, 502, 503, 504]:
                         should_retry = True
                elif isinstance(e, (httpx.TimeoutException, httpx.TransportError)):
                     should_retry = True
                
                if attempt < max_attempts and should_retry:
                    wait_time = min(60, 2 ** (attempt - 1))
                    logger.warning(f"Gemini Attempt #{attempt} failed with {type(e).__name__}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                
                # If not retryable or max attempts, log as error
                logger.error(f"Gemini Attempt #{attempt} failed FATALLY with {type(e).__name__}: {e}")
                raise

            except BaseException as e:
                # Catch cancellation/system exit and re-raise immediately without retry
                logger.error(f"Gemini call INTERRUPTED/CANCELLED: {type(e).__name__}: {e}")
                raise

    # If loop finishes without success (unreachable if last_exception logic is perfect, but safe fallback)
    if last_exception:
        raise last_exception
    raise RuntimeError("Gemini Max Retries Exceeded (Unknown Error)")

async def call_gemini_async(prompt: str) -> str:
    """Call Gemini with multi-loop safe rate limiting."""
    global _last_call_time
    sleep_time = 0
    with _gemini_lock:
        import time as _time
        now = _time.time()
        elapsed = now - _last_call_time
        if elapsed < RATE_LIMIT_SECONDS:
            sleep_time = RATE_LIMIT_SECONDS - elapsed
            _last_call_time = now + sleep_time
        else:
            _last_call_time = now
            
    if sleep_time > 0:
        await asyncio.sleep(sleep_time)
    return await _call_gemini_api_internal(prompt)

async def _call_gemini_stream_internal(prompt: str) -> AsyncGenerator[str, None]:
    """Internal function to call Gemini API with multi-loop safe streaming."""
    global _last_call_time
    sleep_time = 0
    with _gemini_lock:
        import time as _time
        now = _time.time()
        elapsed = now - _last_call_time
        if elapsed < RATE_LIMIT_SECONDS:
            sleep_time = RATE_LIMIT_SECONDS - elapsed
            _last_call_time = now + sleep_time
        else:
            _last_call_time = now

    if sleep_time > 0:
        await asyncio.sleep(sleep_time)
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
        },
    }

    stream_endpoint = VERTEX_ENDPOINT.replace(":generateContent", ":streamGenerateContent")
    decoder = json.JSONDecoder()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", stream_endpoint, headers=headers, json=data) as response:
            if response.status_code != 200:
                err_text = await response.aread()
                logger.error(f"Gemini Streaming Error {response.status_code}: {err_text}")
                yield "Error connecting to Gemini stream."
                return

            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while True:
                    buffer = buffer.lstrip(" \n\r\t[,")
                    if not buffer:
                        break
                    try:
                        obj, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:].lstrip(" \n\r\t,")
                        
                        candidates = obj.get("candidates", [])
                        if candidates:
                            delta = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if delta:
                                yield delta
                    except json.JSONDecodeError:
                        break
                    except Exception as e:
                        logger.error(f"Streaming parser error: {e}")
                        break

async def call_gemini_stream_async(prompt: str) -> AsyncGenerator[str, None]:
    async for chunk in _call_gemini_stream_internal(prompt):
        yield chunk

def call_gemini_sync(prompt: str) -> str:
    """Synchronous wrapper for agent_manager."""
    try:
        return asyncio.run(call_gemini_async(prompt))
    except Exception as e:
        logger.error(f"Gemini call failed completely: {e}")
        raise

def call_gemini_stream_sync(prompt: str):
    """Bridge to run async generator in sync context for Flask.

    Uses a daemon thread + stop event so the background loop is cancelled
    if the client disconnects early (generator is closed).
    """
    q = queue.Queue()
    loop = asyncio.new_event_loop()
    stop_event = threading.Event()

    def run_async():
        asyncio.set_event_loop(loop)
        try:
            async def wrap():
                try:
                    async for chunk in call_gemini_stream_async(prompt):
                        if stop_event.is_set():
                            break
                        q.put(chunk)
                finally:
                    q.put(None)  # Always signal end-of-stream
            loop.run_until_complete(wrap())
        except Exception as e:
            logger.error(f"Streaming thread error: {e}")
            q.put(None)
        finally:
            loop.close()

    worker = threading.Thread(target=run_async, daemon=True)  # daemon=True prevents leaks
    worker.start()

    try:
        while True:
            chunk = q.get()
            if chunk is None:
                break
            yield chunk
    finally:
        stop_event.set()  # Signal background thread to stop on early disconnect

class AgentManager:
    def __init__(
        self,
        llm_model_name: str = GEMINI_MODEL_NAME,
        database_path: str = DATABASE_PATH,
        collection_name: str = COLLECTION_NAME,
        query: str = 'No prompt entered.',
        chat_history: list = None
    ):
        self.llm_model_name = llm_model_name
        self.database_path = database_path
        self.collection_name = collection_name
        self.query = query
        self.chat_history = chat_history or []

        # Initialize/Get Embeddings
        self.embeddings = get_embeddings_model()
        
        # Embed Query
        logger.info("Embedding query...")
        self.query_vector = self.embeddings.encode(self.query, convert_to_numpy=True)

        # Initialize Qdrant
        logger.info("Initializing Qdrant client")
        self.qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

        # Gemini logic is handled via call_gemini_sync
        logger.info(f"Configuring Gemini LLM ({self.llm_model_name})")

    def search_qdrant(self, top_k=5):
        logger.info("Searching Qdrant...")
        try:
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=self.query_vector,
                limit=top_k
            )
            return results
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _get_display_name(self, uri: str) -> str:
        """Helper to extract a clean filename or domain/last segment from a URI or Path."""
        if not uri or uri == "Unknown":
            return "Unknown"
        
        # Handle URLs
        if uri.startswith(('http://', 'https://')):
            try:
                parsed = urlparse(uri)
                # If there's a path beyond '/', get the last segment
                path_segments = [s for s in parsed.path.split('/') if s]
                if path_segments:
                    return path_segments[-1]
                # Fallback to domain
                return parsed.netloc
            except Exception as e:
                logger.warning(f"Failed to parse URI '{uri}': {e}")
                return uri
        
        # Handle File Paths
        return os.path.basename(uri)

    def get_table_schema(self, table_name):
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        schema = cursor.fetchall()
        conn.close()
        return schema

    def get_master_routing(self):
        """
        Level 1: Query Master table to find relevant Routing Tables.
        Optimized: Pre-filters using semantic search to avoid context overflow.
        """
        logger.info("Level 1: Master Table Routing (Optimized)...")
        
        # 1. Semantic Pre-search to find candidate tables
        # We search the main collection to see which documents are semantically relevant
        pre_search_results = self.search_qdrant(top_k=10)
        candidate_routing_tables = set()
        for point in pre_search_results:
            payload = point.payload or {}
            rt = payload.get("routing_table")
            if rt:
                candidate_routing_tables.add(rt)
        
        if not candidate_routing_tables:
            logger.info("No semantic candidates found. Falling back to keyword search.")

        # 1.5 Keyword Search Backup
        # If the user asks for a specific file by name (e.g. "Client Stories"), 
        # we should search the Master Title directly.
        
        # Simple keyword extraction: remove Stopwords (expanded to prevent substring false positives)
        stopwords = {
            'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'about',
            'what', 'how', 'why', 'when', 'where', 'who', 'which', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall',
            'not', 'no', 'nor', 'but', 'or', 'and', 'so', 'if', 'then', 'than',
            'too', 'very', 'just', 'also', 'some', 'any', 'all', 'each', 'every',
            'both', 'few', 'more', 'most', 'other', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'under', 'again',
            'there', 'here', 'this', 'that', 'these', 'those', 'it', 'its',
            'me', 'my', 'we', 'our', 'you', 'your', 'they', 'their', 'them',
            'i', 'he', 'she', 'his', 'her', 'him', 'us', 'within', 'from'
        }
        # Tokenize query into alphanumeric words, then filter out stopwords and very short tokens
        tokens = re.findall(r"[a-z0-9]+", self.query.lower())
        keywords = [w for w in tokens if w not in stopwords and len(w) >= 3]
        
        keyword_candidates = set()
        keyword_scores = {} # Map table_name -> score
        high_confidence_keyword_tables = set()  # Tables with 2+ keyword matches (auto-include)
        if keywords:
            conn = sqlite3.connect(self.database_path, check_same_thread=False)
            try:
                # Improved Keyword Search: Rank by number of match hits
                # Increase weight for Title significantly over Summary since Summaries might be generic
                match_scores = " + ".join([f"(case when Title LIKE ? then 5 else 0 end + case when Summary LIKE ? then 1 else 0 end)" for _ in keywords])
                # Double params for Title and Summary
                params_for_scores = []
                for k in keywords:
                    params_for_scores.extend([f"%{k}%", f"%{k}%"])
                
                # Filter to only rows that have at least one match in Title or Summary
                conditions = " OR ".join([f"Title LIKE ? OR Summary LIKE ?" for _ in keywords])
                params_for_where = []
                for k in keywords:
                    params_for_where.extend([f"%{k}%", f"%{k}%"])
                
                params_full = params_for_scores + params_for_where
                
                query = f"""
                    SELECT table_name, ({match_scores}) as score 
                    FROM Master 
                    WHERE {conditions} 
                    ORDER BY score DESC 
                    LIMIT 40
                """
                
                df_kw = pd.read_sql_query(query, conn, params=params_full)
                for _, row in df_kw.iterrows():
                    table_name = row['table_name']
                    score = row['score']
                    keyword_candidates.add(table_name)
                    keyword_scores[table_name] = score
                    # Auto-include tables with high Title score
                    if score >= 5:
                        high_confidence_keyword_tables.add(table_name)
                logger.info(f"Keyword search found {len(keyword_candidates)} candidates "
                           f"({len(high_confidence_keyword_tables)} high-confidence)")

            except Exception as e:
                logger.warning(f"Keyword search failed: {e}")
            conn.close()
        
        # Combine Semantic + Keyword candidates
        candidate_routing_tables.update(keyword_candidates)
        logger.info(f"Combined Candidates (Semantic + Keyword): {candidate_routing_tables}")

        if not candidate_routing_tables:
            logger.warning("No candidate routing tables found via semantic or keyword search.")
            return []

        # 2. Fetch only the relevant Master entries
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        # Validate that candidate table names are safe to include in the query
        safe_candidates = [t for t in candidate_routing_tables if re.match(r'^[a-z0-9_]+$', t)]
        
        if not safe_candidates:
            logger.warning("No safe candidate routing tables after validation.")
            conn.close()
            return []

        placeholders = ', '.join(['?'] * len(safe_candidates))
        query = f"SELECT id, Title, Source, Summary, Datatype, Sectors, table_name FROM Master WHERE table_name IN ({placeholders})"
        df_master = pd.read_sql_query(query, conn, params=safe_candidates)
        conn.close()

        # 3. Use LLM to pick the absolute best ones (Capped at 8 to avoid Level 2 overflow)
        # Priority: High confidence keyword matches come first, then others
        master_text = ""
        for _, row in df_master.iterrows():
            prefix = "[HIGH CONFIDENCE] " if row['table_name'] in high_confidence_keyword_tables else ""
            master_text += f"- {prefix}Table: {row['table_name']} | Title: {row['Title']} | Summary: {row['Summary']}\n"

        system_prompt = (
            "You are a Senior Strategic Researcher. "
            "Review the available data sources and select the TOP 8 tables most relevant to the query. "
            "CRITICAL: If the query asks for a CORRELATION between two contexts (e.g., 'Market trends' vs 'Adept projects'), you MUST select at least 3 tables from EACH context to allow the final layer to connect them. "
            "ALWAYS prioritize the 'Title' as it contains the true topic. Many 'Summary' fields of Adept internal docs are generic marketing text—do not let that deter you from selecting them if the Title matches the query. "
            "Prioritize sources with '[HIGH CONFIDENCE]' if they match the query keywords. "
            "Return a COMMA-SEPARATED list of 'table_name' strings only."
        )
        
        user_prompt = f"""
        User Query: "{self.query}"
        
        --- Available Sources ---
        {master_text}
        
        Return top 8 table names (comma-separated):
        """

        try:
            content = call_gemini_sync(user_prompt)
            logger.info(f"Level 1 Raw Response: {content.strip()}")
            # CLEANING: Handle LLM conversational drift (e.g., "The top tables are: t1, t2")
            # Extract anything that looks like a table name (route_...)
            possible_tables = re.findall(r'route_[a-z0-9_]+', content)
            if not possible_tables:
                 # Fallback to comma split if regex fails but strip carefully
                 routing_tables = [t.strip().strip('"').strip("'").strip("`").split(':')[-1].strip() for t in content.split(',') if t.strip()]
            else:
                 routing_tables = possible_tables
            
            # Clean invalid segments from split fallback
            routing_tables = [t for t in routing_tables if t.startswith('route_')]
            
            # FINAL CAP: Ensure no more than 8 tables are processed by Level 2
            if len(routing_tables) > 8:
                logger.warning(f"Cutting routing selection from {len(routing_tables)} to 8 for prompt safety.")
                routing_tables = routing_tables[:8]
            
            # Auto-include high-confidence matches if missed, but keep total <= 8
            for kw_table in high_confidence_keyword_tables:
                if kw_table not in routing_tables and len(routing_tables) < 8:
                    if re.match(r'^[a-z0-9_]+$', kw_table):
                         logger.info(f"Auto-including high-confidence keyword match: {kw_table}")
                         routing_tables.append(kw_table)

            logger.info(f"Level 1 Selected: {routing_tables}")
            return routing_tables, master_text
        except Exception as e:
            logger.error(f"Master Routing failed: {e}")
            # Fallback: return high-confidence keyword matches capped at 8
            fallback = [t for t in high_confidence_keyword_tables if re.match(r'^[a-z0-9_]+$', t)]
            return fallback[:8], master_text

    def get_routing_response(self, routing_tables: list):
        """
        Level 2: Open Routing Tables to find specific Details (SQL Tables or Qdrant Points).
        """
        logger.info(f"Level 2: Scanning Routing Tables ({len(routing_tables)})...")
        if not routing_tables:
            return {'sql_tables': [], 'qdrant_ids': []}

        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        combined_routing_sections = []
        max_total_chars = 15000 # Reduced from 20000 to avoid Groq 6000 token limit
        current_length = 0
        
        def read_routing_table(r_table):
            if not r_table.isidentifier():
                return None
            try:
                # Limit rows to 100 to prevent massive context if we have many tables
                with sqlite3.connect(self.database_path, check_same_thread=False) as conn_inner:
                    df = pd.read_sql_query(f"SELECT * FROM {r_table} LIMIT 80", conn_inner)
       
                return f"\n--- Source: {r_table} ---\n{df.to_string(index=False)}\n"
            except Exception as e:
                logger.warning(f"Could not read routing table {r_table}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=min(len(routing_tables), 8)) as executor:
            results = list(executor.map(read_routing_table, routing_tables))
        
        for section_text in results:
            if not section_text: continue
            if current_length + len(section_text) > max_total_chars:
                allowed = max_total_chars - current_length
                combined_routing_sections.append(section_text[:allowed] + "\n...[TRUNCATED]...")
                break
            combined_routing_sections.append(section_text)
            current_length += len(section_text)
        conn.close()

        combined_routing_data = "".join(combined_routing_sections)
        if not combined_routing_sections:
            logger.info("Level 2: No content found in routing tables.")
            return {'sql_tables': [], 'qdrant_ids': []}

        if not combined_routing_data:
            return {'sql_tables': [], 'qdrant_ids': []}

        system_prompt = (
            "You are a Precision Data Scout. "
            "Review the specific entries from the selected sources (Routing Tables). "
            "Identify the specific 'table_name' (for SQL/Excel) or 'qdrant_point_id' (for Text) that contain the answer. "
            "CRITICAL: If the user is asking about company projects, PRIORITIZE internal sources even if they only contain page/part references. "
            "If the query requires connecting two topics (Market vs Internal), ensure you select the BEST identifiers for BOTH topics."
            "Return a JSON object with two keys: 'sql_tables' (list of strings) and 'qdrant_ids' (list of strings)."
        )
        
        user_prompt = f"""
        User Query: "{self.query}"
        
        --- Routing Data ---
        {combined_routing_data}
        
        Output JSON: {{ "sql_tables": ["name1", ...], "qdrant_ids": ["id1", ...] }}
        """

        try:
            content = call_gemini_sync(user_prompt)
            
            try:
                # CLEANING: Strip markdown code blocks if the LLM adds them
                content_clean = re.sub(r'```json\s*|\s*```', '', content).strip()
                result = json.loads(content_clean)
                logger.info(f"Level 2 Selected: {result}")
                return result
            except json.JSONDecodeError as je:
                logger.error(f"JSON Decode Error in Routing Response: {je}")
                return {'sql_tables': [], 'qdrant_ids': []}

        except Exception as e:
            logger.error(f"Routing logic failed: {e}")
            return {'sql_tables': [], 'qdrant_ids': []}

    def get_detail_content(self, selection: dict):
        """
        Level 3: Fetch actual content.
        """
        logger.info("Level 3: Fetching Detail Content...")
        context = ""
        max_chars = 200000 
        points_hydrated = 0
        
        # 1. Fetch SQL Details
        sql_tables = selection.get('sql_tables', [])
        if sql_tables:
            conn = sqlite3.connect(self.database_path, check_same_thread=False)
            for table in sql_tables:
                if len(context) >= max_chars: break
                
                if not table.isidentifier() and not table.replace('_', '').isalnum(): 
                     logger.warning(f"Skipping suspicious table name: {table}")
                     continue

                try:
                    # Robust extraction of master_id
                    master_id = None
                    if table.startswith("route_"): # Handle route tables if selected
                         parts = table.split("_")
                         if len(parts) >= 2: master_id = parts[-1] 
                    elif table.startswith("detail_"):
                         parts = table.split("_", 2)
                         if len(parts) >= 3: master_id = parts[1]
                    
                    source_link = "Unknown"
                    if master_id and master_id.isdigit():
                        cur = conn.cursor()
                        cur.execute("SELECT Source FROM Master WHERE id = ?", (master_id,))
                        row = cur.fetchone()
                        if row: source_link = row[0]

                    source_name = self._get_display_name(source_link)
                    df = pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 10', conn) # Limit rows
                    
                    # --- NEW: Hybrid Retrieval (SQL -> Qdrant) ---
                    # If this table contains pointers to Qdrant (qdrant_point_id),
                    # we must fetch the actual text content from Qdrant.
                    fetched_text_content = []
                    if 'qdrant_point_id' in df.columns:
                        ids_to_fetch = [uuid for uuid in df['qdrant_point_id'].dropna().tolist() if uuid]
                        if ids_to_fetch:
                             try:
                                 points = self.qdrant_client.retrieve(
                                     collection_name=self.collection_name,
                                     ids=ids_to_fetch
                                 )
                                 for p in points:
                                     txt = p.payload.get('text', '')
                                     if txt: 
                                         fetched_text_content.append(f"[Content from Point {p.id}]:\n{txt}")
                                         points_hydrated += 1
                             except Exception as q_err:
                                 logger.error(f"Failed to hydrate Qdrant points for table {table}: {q_err}")

                    # Append hydrated text to the dataframe display
                    table_str = df.to_string(index=False)
                    if fetched_text_content:
                        table_str += "\n\n--- Hydrated Vector Content ---\n" + "\n".join(fetched_text_content)

                    table_text = f"\n---\nSource: {source_name} (URI: {source_link})\nData:\n{table_str}\n"
                    
                    if len(context) + len(table_text) > max_chars:
                        context += table_text[:max_chars - len(context)] + "...[Truncated]"
                        break
                    context += table_text
                except Exception as e:
                    logger.error(f"Error reading SQL {table}: {e}")
            conn.close()
            
        # 2. Fetch Qdrant Details
        qdrant_ids = selection.get('qdrant_ids', [])
        if qdrant_ids and len(context) < max_chars:
            try:
                # Limit number of points to fetch to stay under tokens
                fetch_limit = 40
                safe_ids = qdrant_ids[:fetch_limit]
                
                points = self.qdrant_client.retrieve(
                    collection_name=self.collection_name,
                    ids=safe_ids
                )
                for point in points:
                    if len(context) >= max_chars: break
                    payload = point.payload
                    text_content = payload.get('text') or str(payload)
                    source_link = payload.get('source', 'Unknown')
                    source_name = self._get_display_name(source_link)
                    
                    point_text = f"\n---\nSource: {source_name} (URI: {source_link})\nContent:\n{text_content}\n"
                    if len(context) + len(point_text) > max_chars:
                        context += point_text[:max_chars - len(context)] + "...[Truncated]"
                        break
                    context += point_text
                    points_hydrated += 1
            except Exception as e:
                logger.error(f"Error retrieving Qdrant points: {e}")
                
        logger.info(f"Level 3 Hydration Complete: {points_hydrated} chunks retrieved.")
        return context

    def _check_fast_path(self):
        """
        Detects if the query is a simple greeting or small talk that doesn't 
        require a heavy RAG search.
        """
        q = self.query.lower().strip().strip('?').strip('!')
        
        # Simple keywords for greetings/small talk
        fast_path_keywords = [
            'hi', 'hello', 'hey', 'yo', 'greetings', 'testing', 
            'thanks', 'thank you', 'how are you', 'howdy',
            'good morning', 'good afternoon', 'good evening',
            'morning', 'ok', 'okay', 'cool', 'nice', 'great'
        ]
        
        # Exact match or query is just a greeting phrase
        if q in fast_path_keywords:
            return True
            
        # Check if individual words are greetings (for things like "Hey there")
        words = q.split()
        if len(words) <= 3 and any(w in {'hi', 'hello', 'hey', 'yo', 'hola', 'thanks', 'ok', 'cool'} for w in words):
            return True
            
        return False

    def pipeline(self):
        logger.info("Starting V2 3-Level Implementation Plan Pipeline")
        
        # Check for Fast Path (Greetings/Small Talk)
        if self._check_fast_path():
            logger.info("Fast Path Triggered: Greeting/Small Talk detected.")
            return self.get_final_response([], {"Is Fast Path": True})

        # Step 1: Master -> Routing Tables
        routing_tables, master_metadata = self.get_master_routing()
        
        # --- NEW: General Query Check ---
        # If the query is about "what data do you have" or very general, skip L2/L3
        general_keywords = [
            "what data", "available data", "what do you have", "show me your data", 
            "list your sources", "what is this tool", "summary of the data",
            "overview of the data", "what does the data", "data you have show"
        ]
        is_general = any(kw in self.query.lower() for kw in general_keywords)
        
        if is_general:
            logger.info("General Query Detected: Skipping Level 2 & 3 retrieval.")
            return self.get_final_response(
                [], 
                {
                    "Hierarchical Data": f"Summary of Available Data Sources:\n{master_metadata}", 
                    "Semantic Data": "",
                    "Routing Tables": routing_tables,
                    "Is General": True
                }
            )

        # Step 2: Routing Tables -> Specific Details
        selection = self.get_routing_response(routing_tables)
        
        # Step 3 & 4: Fetch Details & Semantic Search in PARALLEL
        # Using ThreadPoolExecutor specifically for I/O bound tasks (SQL + Qdrant)
        logger.info("Starting Parallel Retrieval (L3 + Semantic)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Fetch details (L3)
            future_details = executor.submit(self.get_detail_content, selection)
            
            # Determine if we should suppress the safety net
            # Since we don't know hierarchical success yet, we run semantic search with lower k
            future_semantic = executor.submit(self.search_qdrant, top_k=5)
            
            detail_context = future_details.result()
            semantic_results = future_semantic.result()

        # Step 4: Process Semantic Search (Safety Net)
        semantic_context = ""
        # Determine if we should suppress the safety net response
        is_research_query = len(self.query.split()) > 4
        hierarchical_success = len(detail_context) > 2000
        
        if is_research_query and hierarchical_success:
            logger.info("Strong Hierarchical Context found: Suppressing Safety Net noise.")
            semantic_results = [] # Ignore semantic results to keep focus
        else:
            # Keep top results only
            semantic_results = semantic_results[:3]

        for point in semantic_results:
             payload = point.payload
             text = payload.get('text', str(payload))
             source_link = payload.get('source', 'Unknown')
             source_name = self._get_display_name(source_link)
             semantic_context += f"- Document: {source_name} (URI: {source_link})\n  Content: {text}\n\n"

        logger.info(f"Context sizes: Hierarchical={len(detail_context)} chars, Semantic={len(semantic_context)} chars")

        # Final Synthesis
        return self.get_final_response(
            semantic_results, 
            {
                "Hierarchical Data": detail_context, 
                "Semantic Data": semantic_context,
                "Routing Tables": routing_tables
            }
        )

    def pipeline_stream(self):
        """Streaming version of the pipeline."""
        logger.info("Starting Streaming Pipeline...")
        
        if self._check_fast_path():
             yield from self.get_final_response_stream([], {"Is Fast Path": True})
             return

        routing_tables, master_metadata = self.get_master_routing()
        
        general_keywords = ["what data", "available data", "what do you have", "show me your data", "summary of the data"]
        is_general = any(kw in self.query.lower() for kw in general_keywords)
        
        if is_general:
            yield from self.get_final_response_stream([], {"Hierarchical Data": f"Summary of Available Data Sources:\n{master_metadata}", "Is General": True})
            return

        selection = self.get_routing_response(routing_tables)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_details = executor.submit(self.get_detail_content, selection)
            future_semantic = executor.submit(self.search_qdrant, top_k=5)
            detail_context = future_details.result()
            semantic_results = future_semantic.result()

        # Suppress semantic noise when hierarchical retrieval is strong
        is_research_query = len(self.query.split()) > 4
        hierarchical_success = len(detail_context) > 2000
        if is_research_query and hierarchical_success:
            logger.info("[Stream] Strong Hierarchical Context: Suppressing Safety Net noise.")
            semantic_results = []
        else:
            semantic_results = semantic_results[:3]

        semantic_context = ""
        for point in semantic_results:
             payload = point.payload
             text = payload.get('text', str(payload))
             source_link = payload.get('source', 'Unknown')
             source_name = self._get_display_name(source_link)
             semantic_context += f"- Document: {source_name} (URI: {source_link})\n  Content: {text}\n\n"

        yield from self.get_final_response_stream(
            semantic_results, 
            {
                "Hierarchical Data": detail_context, 
                "Semantic Data": semantic_context,
                "Routing Tables": routing_tables
            }
        )

    def get_final_response(self, search_results, context_dict):
        # Renamed '_' to 'search_results' for backward compatibility/clarity
        logger.info("Synthesizing V2 Response...")
        
        hierarchical_data = context_dict.get("Hierarchical Data", "")
        semantic_data = context_dict.get("Semantic Data")
        routing_tables = context_dict.get("Routing Tables", [])
        is_general = context_dict.get("Is General", False)
        is_fast_path = context_dict.get("Is Fast Path", False)
        
        if is_fast_path:
             # Fast-path prompt for greetings - OMIT source instructions
             prompt = (
                 "You are the Adept Market Intelligence Assistant. "
                 f"The user said: '{self.query}'. Reply politely and professionally. "
                 "Mention that you are ready to help with market research, document analysis, or innovation insights. "
                 "DO NOT include a 'Sources Analyzed' section."
             )
             try:
                 content = call_gemini_sync(prompt)
                 return content
             except Exception:
                 return "Hello! I am your Adept Market Intelligence Assistant. How can I help you with your research today?"
        
        # Fallback if semantic data missing but search results exist
        if not semantic_data and search_results:
            semantic_lines = []
            for point in search_results:
                payload = getattr(point, "payload", {})
                text = payload.get('text', str(payload))
                source_link = payload.get('source', 'Unknown')
                source_name = self._get_display_name(source_link)
                semantic_lines.append(f"- Document: {source_name} (URI: {source_link})\n  Content: {text}")
            semantic_data = "\n".join(semantic_lines)
            
        if semantic_data is None: semantic_data = ""
        
        # Prepare Unified Prompt
        system_prompt = _build_system_prompt(self.chat_history)
        
        user_prompt = f"""
User Query: "{self.query}"

=== SEARCH CONTEXT ===
{hierarchical_data}
{semantic_data}

IMPORTANT: Synthesize information from ALL provided documents in the search context above.
Cross-reference data across multiple sources where relevant.
Provide a detailed, structured response with:
- Specific data points, numbers, actual text, and facts extracted from the documents. Do not tell the user to read the files, read them yourself and summarize the answers.
- Inline citations using [Filename](URI) format only for claims supported by retrieved context.
- If multiple independent documents are available, cross-reference them. If only one source is available, answer from it and state that corroboration was not available.
- A 'Sources Analyzed' section listing every unique source actually present in the context. If none were retrieved, say so instead of inventing citations.
"""
        
        try:
            content = call_gemini_sync(f"{system_prompt}\n\n{user_prompt}")
            return content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return "I encountered an error generating the final response."


    def get_final_response_stream(self, search_results, context_dict):
        """Streaming synthesis — uses same system prompt as non-streaming path."""
        hierarchical_data = context_dict.get("Hierarchical Data", "")
        semantic_data = context_dict.get("Semantic Data", "")
        is_fast_path = context_dict.get("Is Fast Path", False)

        # Use the global shared system prompt builder
        system_prompt = _build_system_prompt(self.chat_history)

        if is_fast_path:
             prompt = (
                 "You are the Adept Market Intelligence Assistant. "
                 f"The user said: '{self.query}'. Reply politely and professionally. "
                 "Mention that you are ready to help with market research, document analysis, or innovation insights. "
                 "DO NOT include a 'Sources Analyzed' section."
             )
             yield from call_gemini_stream_sync(prompt)
             return

        user_prompt = f"""
User Query: "{self.query}"

=== SEARCH CONTEXT ===
{hierarchical_data}
{semantic_data}

IMPORTANT: Synthesize information from ALL provided documents in the search context above.
Cross-reference data across multiple sources where relevant.
Provide a detailed, structured response with:
- Specific data points, numbers, actual text, and facts extracted from the documents. Do not tell the user to read the files, read them yourself and summarize the answers.
- Inline citations using [Filename](URI) format for every claim.
- Data from multiple documents where available — do NOT rely on a single source.
- A 'Sources Analyzed' section listing EVERY unique source provided in the context, even those not directly cited.
"""
        
        yield from call_gemini_stream_sync(f"{system_prompt}\n\n{user_prompt}")
