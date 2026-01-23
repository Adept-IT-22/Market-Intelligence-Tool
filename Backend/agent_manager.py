
import os
import sqlite3
import pandas as pd
from groq import Groq
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import logging
import json
import re
from urllib.parse import urlparse

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
QDRANT_URL = os.getenv("QDRANT_URL")

# Project Paths
current_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_directory)
DATABASE_PATH = os.getenv("DATABASE_PATH")

if not DATABASE_PATH:
    DATABASE_PATH = os.path.join(project_root, "DB", "market-intelligence.db")
    logger.info(f"DATABASE_PATH not found in .env, using default: {DATABASE_PATH}")

# Models
LLM_MODEL_NAME = "llama-3.1-8b-instant"
EMBEDDING_MODEL = "BAAI/bge-small-en"
COLLECTION_NAME = "adept_database"

# Global Cache for Embedding Model to prevent re-loading
_CACHED_EMBEDDINGS = None

def get_embeddings_model():
    global _CACHED_EMBEDDINGS
    if _CACHED_EMBEDDINGS is None:
        logger.info("Loading Embedding Model (Cached)...")
        _CACHED_EMBEDDINGS = SentenceTransformer(EMBEDDING_MODEL)
    return _CACHED_EMBEDDINGS

class AgentManager:
    def __init__(
        self,
        llm_model_name: str = LLM_MODEL_NAME,
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

        # Initialize Groq Client
        logger.info("Configuring Groq LLM")
        self.client = Groq(api_key=GROQ_API_KEY)

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
            logger.warning("No candidate routing tables found via semantic search.")
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
            response = self.client.chat.completions.create(
                model=self.llm_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            # Clean
            routing_tables = [t.strip().strip('"').strip("'") for t in content.split(',') if t.strip()]
            
            # Verify they exist in our list
            valid_tables = df_master['table_name'].tolist()
            final_tables = [t for t in routing_tables if t in valid_tables]
            
            logger.info(f"Level 1 Selected: {final_tables}")
            return final_tables
        except Exception as e:
            logger.error(f"Master Routing failed: {e}")
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
        max_total_chars = 20000 
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
            response = self.client.chat.completions.create(
                model=self.llm_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            try:
                result = json.loads(response.choices[0].message.content)
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
                    table_text = f"\n---\nSource: {source_name} (URI: {source_link})\nData:\n{df.to_string(index=False)}\n"
                    
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
            "2. CITATIONS: You MUST cite sources using Markdown hyperlinks: [Filename](URI).\n"
            "   - The visible text MUST be a clean filename/title (e.g. 'Project Alpha.pdf').\n"
            "   - The URI MUST be the full path/link provided in the context.\n"
            "   - NEVER output internal labels like '[Source: ... | Link: ...]' in the final response.\n"
            "3. REFERENCES: List all unique sources at the end under a 'References' header using the same [Filename](URI) format.\n"
        )
        
        user_prompt = f"""
        User Query: "{self.query}"
        
        === SEARCH CONTEXT ===
        {hierarchical_data}
        {semantic_data}
        
        Provide a detailed response with inline citations and a references list at the bottom.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.llm_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return "I encountered an error generating the final response."

