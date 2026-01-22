
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
DATABASE_PATH = os.path.join(project_root, "DB", "market-intelligence.db")

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
        """
        logger.info("Level 1: Master Table Routing...")
        
        conn = sqlite3.connect(self.database_path)
        df_master = pd.read_sql_query("SELECT id, Title, Source, Summary, Datatype, Sectors, table_name FROM Master", conn)
        conn.close()
        
        if df_master.empty:
            logger.warning("Master table is empty.")
            return []

        master_context = df_master.to_string(index=False)

        system_prompt = (
            "You are a Data Architect. Your goal is to select relevant 'Routing Tables' from the Master Menu. "
            "Analyze the User Query and the Master Table. "
            "Return a comma-separated list of 'table_name' that are most relevant. "
            "If nothing is relevant, return nothing."
        )

        user_prompt = f"""
        User Query: "{self.query}"
        
        --- Master Table (Menu) ---
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
        
        # Format Qdrant Context
        qdrant_context = ""
        for point in qdrant_results:
            payload = point.payload or {}
            summary = payload.get("summary") or payload.get("content", "")
            qdrant_context += f"- {summary[:500]}\n"


        # Format SQL Context (Limit length)
        sql_context = ""
        for table, data in detail_tables.items():
            sql_context += f"\nTable: {table}\nData (Sample):\n{str(data)[:2000]}\n"

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
        
        # 1. Fetch SQL Details
        sql_tables = selection.get('sql_tables', [])
        if sql_tables:
            conn = sqlite3.connect(self.database_path)
            for table in sql_tables:
                # Validate table name (basic injection check)
                if not table.isidentifier() and not table.replace('_', '').isalnum(): 
                     logger.warning(f"Skipping suspicious table name in detail fetch: {table}")
                     continue

                try:
                    df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                    context += f"\n### Data Table: {table}\n{df.to_string(index=False)}\n"
                except Exception as e:
                    logger.error(f"Error reading Detail SQL {table}: {e}")
            conn.close()
            
        # 2. Fetch Qdrant Details
        qdrant_ids = selection.get('qdrant_ids', [])
        if qdrant_ids:
            try:
                # Validate IDs briefly (UUID check or length)
                safe_ids = [qid for qid in qdrant_ids if len(qid) > 10] # basic check
                
                if safe_ids:
                    points = self.qdrant_client.retrieve(
                        collection_name=self.collection_name,
                        ids=safe_ids
                    )
                    for point in points:
                        payload = point.payload
                        # Assuming payload has 'text' or we construct it
                        text_content = payload.get('text') or str(payload)
                        source = payload.get('source', 'Unknown')
                        context += f"\n### Text Source: {source}\n{text_content}\n"
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
             semantic_context += f"- [Semantic Match]: {text}\n"

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
                semantic_lines.append(f"- [Semantic Match]: {text}")
            semantic_data = "\n".join(semantic_lines)
            
        if semantic_data is None: semantic_data = ""
        
        system_prompt = (
            "You are an expert Market Intelligence Analyst for Kenya. "
            "Synthesize the provided data to answer the User Query. "
            "The data comes from a Deep Drill-Down (Hierarchical) and a Broad Sweep (Semantic). "
            "Prioritize the specific tabular data found in the Drill-Down. "
            "Cite your sources precisely."
        )
        
        user_prompt = f"""
        User Query: "{self.query}"
        
        === Deep Dive Data (High Confidence) ===
        {hierarchical_data}
        
        === Semantic Search Context (Broad Context) ===
        {semantic_data}
        
        Provide a detailed, Markdown-formatted answer.
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
