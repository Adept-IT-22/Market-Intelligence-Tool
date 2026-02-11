import os
import sqlite3
import pandas as pd
import httpx
import asyncio
import time
from tenacity import retry, wait_exponential, stop_after_attempt, RetryCallState
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
from typing import Optional, Any

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Vertex AI / Gemini Configuration ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "gen-lang-client-0138772794")
REGION = os.getenv("GCP_REGION", "us-central1")
GEMINI_MODEL_NAME = "gemini-2.0-flash"

VERTEX_ENDPOINT = (
    f"https://{REGION}-aiplatform.googleapis.com/v1/"
    f"projects/{PROJECT_ID}/locations/{REGION}/"
    f"publishers/google/models/{GEMINI_MODEL_NAME}:generateContent"
)

# --- Concurrency & Rate Limiting (from user snippet) ---
MAX_CONCURRENT_REQUEST = 1
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUEST)
RATE_LIMIT_SECONDS = 6
gemini_lock = asyncio.Lock()
last_call = 0

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
    try:
        creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        logger.warning(f"Failed to get GCP default credentials: {e}. Falling back to GEMINI_API_KEY env.")
        return os.getenv("GEMINI_API_KEY", "")

def retry_if_resource_exhausted(exception: BaseException) -> bool:
    msg = str(exception).lower()
    return "429" in msg or "quota" in msg or "limit" in msg or "503" in msg

@retry(
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    retry=retry_if_resource_exhausted,
    reraise=True,
    before=lambda rs: logger.info(f"Retrying Gemini call... attempt #{rs.attempt_number}"),
)
async def _call_gemini_api_internal(prompt: str) -> str:
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json" if "JSON" in prompt.upper() else "text/plain"
        },
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(VERTEX_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

async def call_gemini_async(prompt: str) -> str:
    global last_call
    async with semaphore:
        async with gemini_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - last_call
            if elapsed < RATE_LIMIT_SECONDS:
                sleep_time = RATE_LIMIT_SECONDS - elapsed
                await asyncio.sleep(sleep_time)
            last_call = asyncio.get_event_loop().time()
        return await _call_gemini_api_internal(prompt)

def call_gemini_sync(prompt: str) -> str:
    """Synchronous wrapper for agent_manager."""
    try:
        return asyncio.run(call_gemini_async(prompt))
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        raise

class AgentManager:
    def __init__(
        self,
        llm_model_name: str = GEMINI_MODEL_NAME,
        database_path: str = DATABASE_PATH,
        collection_name: str = COLLECTION_NAME,
        query: str = 'No prompt entered.'
    ):
        self.llm_model_name = llm_model_name
        self.database_path = database_path
        self.collection_name = collection_name
        self.query = query

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
        conn = sqlite3.connect(self.database_path)
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
            conn = sqlite3.connect(self.database_path)
            try:
                # Improved Keyword Search: Rank by number of match hits
                match_scores = " + ".join([f"(case when Title LIKE ? then 1 else 0 end)" for _ in keywords])
                params = [f"%{k}%" for k in keywords]
                # Filter to only rows that have at least one match
                conditions = " OR ".join([f"Title LIKE ?" for _ in keywords])
                params_full = params + params
                
                query = f"""
                    SELECT table_name, ({match_scores}) as score 
                    FROM Master 
                    WHERE {conditions} 
                    ORDER BY score DESC 
                    LIMIT 20
                """
                
                df_kw = pd.read_sql_query(query, conn, params=params_full)
                for _, row in df_kw.iterrows():
                    table_name = row['table_name']
                    score = row['score']
                    keyword_candidates.add(table_name)
                    keyword_scores[table_name] = score
                    # Auto-include tables matching 2+ keywords (high confidence)
                    if score >= 2:
                        high_confidence_keyword_tables.add(table_name)
                logger.info(f"Keyword search found {len(keyword_candidates)} candidates "
                           f"({len(high_confidence_keyword_tables)} high-confidence): "
                           f"{df_kw.to_dict(orient='records')}")
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
        conn = sqlite3.connect(self.database_path)
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
        
        if df_master.empty:
            logger.warning("No matching Master entries for candidates in database." \
            "semantic_candidates = %d, safe_candidates = %d", len(candidate_routing_tables), len(safe_candidates))
            return [] # Returning empty list instead of unverified candidates as per best practice

        master_context = df_master.to_string(index=False)

        system_prompt = (
            "You are a Data Architect. Your goal is to select relevant 'Routing Tables' from the Master Menu. "
            "Analyze the User Query and the filtered Master Table. "
            "Return a comma-separated list of 'table_name' that are most relevant to answering the query. "
            "If nothing is relevant, return nothing."
        )

        user_prompt = f"""
        User Query: "{self.query}"
        
        --- Filtered Master Table (Candidates) ---
        {master_context}
        
        Output Format: table_name1, table_name2
        """

        try:
            content = call_gemini_sync(user_prompt)
            content = content.strip()
            # Clean
            routing_tables = [t.strip().strip('"').strip("'") for t in content.split(',') if t.strip()]
            
            # Verify they exist in our list
            valid_tables = df_master['table_name'].tolist()
            final_tables = [t for t in routing_tables if t in valid_tables]
            
            # Always include high-confidence keyword matches (LLM may miss them)
            # Sort high confidence tables by score descending
            sorted_hc = sorted(high_confidence_keyword_tables, key=lambda t: (-keyword_scores.get(t, 0), t))
            for hc_table in sorted_hc:
                if hc_table in valid_tables and hc_table not in final_tables:
                    final_tables.append(hc_table)
                    logger.info(f"Auto-included high-confidence keyword match: {hc_table}")
            
            logger.info(f"Level 1 Selected: {final_tables}")
            return final_tables
        except Exception as e:
            logger.error(f"Master Routing failed: {e}")
            # Fallback: return high-confidence keyword matches even if LLM fails
            if high_confidence_keyword_tables:
                fallback = [t for t in high_confidence_keyword_tables if re.match(r'^[a-z0-9_]+$', t)]
                logger.info(f"Using keyword fallback: {fallback}")
                return fallback
            return []

    def get_routing_response(self, routing_tables: list):
        """
        Level 2: Open Routing Tables to find specific Details (SQL Tables or Qdrant Points).
        """
        logger.info(f"Level 2: Scanning Routing Tables ({len(routing_tables)})...")
        if not routing_tables:
            return {'sql_tables': [], 'qdrant_ids': []}

        conn = sqlite3.connect(self.database_path)
        combined_routing_sections = []
        max_total_chars = 15000 # Reduced from 20000 to avoid Groq 6000 token limit
        current_length = 0
        
        for r_table in routing_tables:
            # Basic validation to prevent injection if list comes from untrusted source
            if not r_table.isidentifier():
                 logger.warning(f"Skipping invalid table name: {r_table}")
                 continue

            if current_length >= max_total_chars:
                logger.warning("Routing data budget exceeded. Skipping remaining tables.")
                break

            try:
                # Limit rows to 50 to prevent massive context
                df = pd.read_sql_query(f"SELECT * FROM {r_table} LIMIT 50", conn)
                section_text = f"\n--- Source: {r_table} ---\n{df.to_string(index=False)}\n"
                
                if current_length + len(section_text) > max_total_chars:
                    # Truncate
                    allowed = max_total_chars - current_length
                    section_text = section_text[:allowed] + "\n...[TRUNCATED]..."
                    combined_routing_sections.append(section_text)
                    current_length += allowed
                    break
                
                combined_routing_sections.append(section_text)
                current_length += len(section_text)
                
            except Exception as e:
                logger.warning(f"Could not read routing table {r_table}: {e}")
        conn.close()

        combined_routing_data = "".join(combined_routing_sections)

        if not combined_routing_data:
            return {'sql_tables': [], 'qdrant_ids': []}

        system_prompt = (
            "You are a Precision Data Scout. "
            "Review the specific entries from the selected sources (Routing Tables). "
            "Identify the specific 'table_name' (for SQL/Excel) or 'qdrant_point_id' (for Text) that contain the answer. "
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
                result = json.loads(content)
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
        max_chars = 15000 # Stay safe within Groq's 6k token limit (~18k-24k chars)
        
        # 1. Fetch SQL Details
        sql_tables = selection.get('sql_tables', [])
        if sql_tables:
            conn = sqlite3.connect(self.database_path)
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
                                     if txt: fetched_text_content.append(f"[Content from Point {p.id}]:\n{txt}")
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
                fetch_limit = 15
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
            except Exception as e:
                logger.error(f"Error retrieving Qdrant points: {e}")
                
        return context

    def pipeline(self):
        logger.info("Starting V2 3-Level Implementation Plan Pipeline")
        
        # Step 1: Master -> Routing Tables
        routing_tables = self.get_master_routing()
        
        # Step 2: Routing Tables -> Specific Details
        selection = self.get_routing_response(routing_tables)
        
        # Step 3: Fetch Details
        detail_context = self.get_detail_content(selection)
        
        # Step 4: Hybrid Search (Safety Net) - Run standard Semantic Search as well
        # This catches things the hierarchical drill-down might miss
        semantic_results = self.search_qdrant(top_k=3)
        semantic_context = ""
        for point in semantic_results:
             payload = point.payload
             text = payload.get('text', str(payload))
             source_link = payload.get('source', 'Unknown')
             source_name = self._get_display_name(source_link)
             semantic_context += f"- Document: {source_name} (URI: {source_link})\n  Content: {text}\n\n"

        # Final Synthesis
        return self.get_final_response(semantic_results, {"Hierarchical Data": detail_context, "Semantic Data": semantic_context})

    def get_final_response(self, search_results, context_dict):
        # Renamed '_' to 'search_results' for backward compatibility/clarity
        logger.info("Synthesizing V2 Response...")
        
        hierarchical_data = context_dict.get("Hierarchical Data", "")
        semantic_data = context_dict.get("Semantic Data")
        
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
        
        system_prompt = (
            "You are an expert Market Intelligence Analyst for Adept Technologies Ltd. "
            "Synthesize the provided data to answer the User Query accurately. "
            "Formatting Rules:\n"
            "1. Use clear, professional Markdown.\n"
            "2. INLINE CITATIONS: When citing sources in the text, use ONLY the markdown link format: [Filename](URI).\n"
            "   - Display text = clean filename only (e.g., 'ProjectSheet.pdf')\n"
            "   - URI = full path from context\n"
            "   - DO NOT add the path in parentheses after the link\n"
            "   - Example: ...mentioned in [Report.pdf](C:\\path\\to\\Report.pdf) and [Analysis.xlsx](C:\\path\\to\\Analysis.xlsx)\n"
            "   - WRONG: ...mentioned in 'Report.pdf' (C:\\path\\to\\Report.pdf) [Report.pdf](C:\\path\\to\\Report.pdf)\n"
            "3. REFERENCES SECTION: At the end, list unique sources under a 'References' header.\n"
            "   - Format: Bullet point + markdown link ONLY\n"
            "   - Example: • [ProjectSheet.pdf](C:\\full\\path\\to\\file.pdf)\n"
            "   - DO NOT add the path in parentheses\n"
            "   - WRONG: • [ProjectSheet.pdf](C:\\path) (C:\\path\\to\\file.pdf)\n"
        )
        
        user_prompt = f"""
        User Query: "{self.query}"
        
        === SEARCH CONTEXT ===
        {hierarchical_data}
        {semantic_data}
        
        Provide a detailed response with inline citations and a references list at the bottom.
        """
        
        try:
            content = call_gemini_sync(f"{system_prompt}\n\n{user_prompt}")
            return content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return "I encountered an error generating the final response."

