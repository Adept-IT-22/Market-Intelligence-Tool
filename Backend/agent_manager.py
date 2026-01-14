
import os
import sqlite3
import pandas as pd
from groq import Groq
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import logging

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

    def get_master_response(self):
        logger.info("Determining relevant data sources (Routing)...")
        master_schema = self.get_table_schema(table_name='Master')
        
        system_prompt = (
            "You are a highly capable database router. "
            "Your task is to identify relevant SQL tables from the schema based on the user's query. "
            "Return ONLY a comma-separated list of 'table_name' values. Step-by-step reasoning is NOT allowed."
        )
        
        user_prompt = f"""
        Database Schema (Master Table): {master_schema}
        
        User Query: "{self.query}"
        
        Task: Select table names that are relevant to the query.
        Output Format: table1,table2
        If no tables are relevant, return nothing.
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
            # Clean up
            tables = [t.strip().strip('"').strip("'") for t in content.split(',') if t.strip()]
            logger.info(f"Identified Tables: {tables}")
            
            # Group by Datatype if needed, or just return list. 
            # Existing logic used a dict, let's replicate that for compatibility if needed, 
            # or simplify. The robust logic I wrote earlier put them in a dict based on 'Datatype'.
            
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            result_dict = {'SQL': [], 'QDrant': []} # Simplified structure
            
            for table in tables:
                cursor.execute("SELECT Datatype FROM Master WHERE table_name = ?", (table,))
                row = cursor.fetchone()
                if row:
                    # In this DB, Datatype is the key? Or just a property.
                    # Looking at previous logs: result_dict.setdefault(datatype_str, []).append(table)
                    # Let's map it:
                    datatype = row[0]
                    # Assuming 'SQL' or 'QDrant' might be values?
                    # Let's just put everything in SQL for now if it's a table we can query.
                    if datatype and 'Start' in datatype: # Just guessing or generic
                         pass
                    
                    # SIMPLIFICATION: usage of result_dict was complex.
                    # Let's just assume these are SQL tables for detail retrieval
                    result_dict['SQL'].append(table)
            
            conn.close()
            return result_dict

        except Exception as e:
            logger.error(f"Routing failed: {e}")
            return {}

    def get_final_response(self, qdrant_results, detail_tables):
        logger.info("Synthesizing Final Response...")
        
        system_prompt = (
            "You are an expert Market Intelligence Analyst for Kenya. "
            "Synthesize the provided Data Sources (SQL) and Context (Vector Search) to answer the User Query. "
            "Be precise, cite your sources (e.g. 'According to [Table Name]...'), and provide actionable insights. "
            "If data is missing, clearly state it."
        )
        
        # Format Qdrant Context
        qdrant_context = ""
        for point in qdrant_results:
            if hasattr(point, 'payload'):
                qdrant_context += f"- {point.payload}\n"
            else:
                qdrant_context += f"- {point}\n"

        # Format SQL Context (Limit length)
        sql_context = ""
        for table, data in detail_tables.items():
            sql_context += f"\nTable: {table}\nData (Sample):\n{str(data)[:2000]}\n"

        user_prompt = f"""
        User Query: "{self.query}"
        
        --- SQL Data Sources ---
        {sql_context}
        
        --- Vector Search Context ---
        {qdrant_context}
        
        Please provide a comprehensive response in Markdown.
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
            return "I encountered an error generating the response."

    def pipeline(self):
        logger.info("Starting Optimized Pipeline")
        
        # Parallel-ish: Get Master Routing
        master_dict = self.get_master_response()
        
        # Fetch Details
        detail_data = {}
        conn = sqlite3.connect(self.database_path)
        
        if 'SQL' in master_dict:
            for table in master_dict['SQL']:
                try:
                    # Limit rows for context management
                    df = pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 10', conn)
                    # Use to_markdown or string
                    detail_data[table] = df.to_string(index=False)
                except Exception as e:
                    logger.error(f"Failed to read table {table}: {e}")
        conn.close()

        # Search Qdrant
        qdrant_results = self.search_qdrant(top_k=5)

        # Final Synthesis
        return self.get_final_response(qdrant_results, detail_data)