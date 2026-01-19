import os
import sqlite3
import pandas as pd
import logging
import uuid
import re
from datetime import datetime
import argparse
import requests
from bs4 import BeautifulSoup

# Qdrant & Embedding Imports
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# File parsers
import pypdf 

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../DB/market-intelligence.db")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
COLLECTION_NAME = "adept_database"
EMBEDDING_MODEL = "BAAI/bge-small-en"

class DataIngester:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        
        # Initialize Embedder
        logger.info("Loading embedding model...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        
        # Initialize Qdrant
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        self.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.qdrant.get_collections().collections
            exists = any(c.name == COLLECTION_NAME for c in collections)
            if not exists:
                logger.info(f"Creating collection {COLLECTION_NAME}")
                self.qdrant.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def _validate_table_name(self, table_name):
        if not re.match(r'^[a-z0-9_]+$', table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    def _chunk_text(self, text, size=1000):
        """Helper to chunk text into specific sizes."""
        if not text: return []
        return [text[i:i+size] for i in range(0, len(text), size)]

    def process_input(self, input_path: str, source_type: str, title: str, sectors: str, summary: str):
        logger.info(f"Processing {source_type}: {input_path}")
        
        # Validate Input BEFORE creating Master entry
        if source_type.lower() not in ['excel', 'pdf', 'url']:
             logger.error(f"Unsupported source type: {source_type}")
             return

        if source_type.lower() == 'url' and not input_path.startswith(('http://', 'https://')):
             logger.error(f"Invalid URL format: {input_path}")
             return
             
        master_id = str(uuid.uuid4())
        try:
             # 1. Level 1: Insert into Master
            routing_table_name = self._create_master_entry(master_id, title, input_path, source_type, summary, sectors)
            
            # 2. Level 2 & 3: Process content
            if source_type.lower() == 'excel' or (isinstance(input_path, str) and input_path.endswith(('.xlsx', '.xls'))):
                self._process_excel(input_path, master_id, routing_table_name, sectors)
            elif source_type.lower() == 'pdf' or (isinstance(input_path, str) and input_path.endswith('.pdf')):
                self._process_pdf(input_path, master_id, routing_table_name, sectors)
            elif source_type.lower() == 'url':
                self._process_url(input_path, master_id, routing_table_name, sectors)
                
            logger.info("Ingestion Complete.")
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            # Optional: Rollback Master entry (Delete row from Master and drop routing table)
            if 'routing_table_name' in locals():
                logger.warning(f"Rolling back: Dropping routing table {routing_table_name}")
                try:
                    self.cursor.execute(f"DROP TABLE IF EXISTS {routing_table_name}")
                    self.cursor.execute("DELETE FROM Master WHERE id = ?", (master_id,))
                    self.conn.commit()
                except Exception as rollback_err:
                    logger.error(f"Rollback failed: {rollback_err}")
            raise e

    def _create_master_entry(self, master_id, title, source, source_type, summary, sectors):
        """
        Creates an entry in the Master table and initializes the Routing Table.
        """
        # Create unique routing table name
        safe_title = "".join([c if c.isalnum() else "_" for c in title]).lower()
        routing_table_name = f"route_{safe_title[:20]}_{master_id[:8]}"
        self._validate_table_name(routing_table_name)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Creating Master Entry: {title} -> {routing_table_name}")
        self.cursor.execute("""
            INSERT INTO Master (id, Title, Source, Summary, Datatype, Sectors, table_name, Date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (master_id, title, source, summary, source_type, sectors, routing_table_name, date_str))
        
        self._create_routing_table(routing_table_name)
        self.conn.commit()
        
        return routing_table_name

    def _create_routing_table(self, table_name):
        """
        Creates the Level 2 Routing Table.
        """
        self._validate_table_name(table_name)
        logger.info(f"Creating Routing Table: {table_name}")
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id TEXT,
                Title TEXT,
                Datatype TEXT,
                Sectors TEXT,
                table_name TEXT,       -- For SQL Details
                qdrant_source TEXT,    -- For Text Details
                qdrant_point_id TEXT   -- For Text Details
            )
        """)

    def _process_excel(self, file_path, master_id, routing_table_name, sectors):
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                logger.info(f"Processing Sheet: {sheet_name}")
                df = pd.read_excel(xls, sheet_name=sheet_name)
                
                df.dropna(how='all', inplace=True)
                df.dropna(axis=1, how='all', inplace=True)
                
                safe_sheet = "".join([c if c.isalnum() else "_" for c in sheet_name]).lower()
                if not safe_sheet: safe_sheet = "sheet"
                
                detail_table_name = f"detail_{master_id[:8]}_{safe_sheet}"
                self._validate_table_name(detail_table_name)
                
                # Write Detail Table (Level 3)
                df.to_sql(detail_table_name, self.conn, if_exists='replace', index=False)
                
                # Update Routing Table (Level 2)
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, table_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (master_id, f"Sheet: {sheet_name}", "SQL", sectors, detail_table_name))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Excel processing failed: {e}")
            raise e

    def _process_pdf(self, file_path, master_id, routing_table_name, sectors):
        try:
            reader = pypdf.PdfReader(file_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text or not text.strip(): continue
                
                chunks = self._chunk_text(text, 1000)
                
                for k, chunk in enumerate(chunks):
                    embedding = self.embedder.encode(chunk).tolist()
                    point_id = str(uuid.uuid4())
                    
                    payload = {
                        "master_id": master_id,
                        "routing_table": routing_table_name,
                        "source": os.path.basename(file_path),
                        "page": i + 1,
                        "text": chunk,
                        "sectors": sectors
                    }
                    
                    # Store in Qdrant (Level 3)
                    self.qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
                    )
                    
                    # Update Routing Table (Level 2)
                    chunk_title = f"Page {i+1} Part {k+1}"
                    self.cursor.execute(f"""
                        INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, qdrant_source, qdrant_point_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (master_id, chunk_title, "Text", sectors, os.path.basename(file_path), point_id))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            raise e

    def _process_url(self, url, master_id, routing_table_name, sectors):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()
                
            text = soup.get_text(separator=' ', strip=True)
            
            chunks = self._chunk_text(text, 1000)
            
            for k, chunk in enumerate(chunks):
                embedding = self.embedder.encode(chunk).tolist()
                point_id = str(uuid.uuid4())
                
                payload = {
                    "master_id": master_id,
                    "routing_table": routing_table_name,
                    "source": url,
                    "text": chunk,
                    "sectors": sectors
                }
                
                # Store in Qdrant (Level 3)
                self.qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
                )
                
                # Update Routing Table (Level 2)
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, qdrant_source, qdrant_point_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (master_id, f"Section {k+1}", "Text", sectors, url, point_id))
                
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"URL processing failed: {e}")
            raise e
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest data into Market Intelligence V2 Ecosystem")
    parser.add_argument("--input", required=True, help="Path to file or URL")
    parser.add_argument("--type", choices=['excel', 'pdf', 'url'], required=True, help="Type of input data")
    parser.add_argument("--title", required=True, help="Title for the dataset")
    parser.add_argument("--sectors", default="General", help="Comma-separated sectors")
    parser.add_argument("--summary", default="", help="Brief summary of the data")
    
    args = parser.parse_args()
    
    ingester = DataIngester()
    ingester.process_input(args.input, args.type, args.title, args.sectors, args.summary)
