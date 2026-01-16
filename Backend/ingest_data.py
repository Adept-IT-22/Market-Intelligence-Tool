import os
import sqlite3
import pandas as pd
import logging
import uuid
import re
from datetime import datetime
import argparse

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
        
        # Initialize AI Models
        logger.info("Loading Embedding Model...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        self.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        # Ensure Qdrant Collection Exists
        self._ensure_collection()

    def _ensure_collection(self):
        collections = self.qdrant.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            logger.info(f"Creating collection {COLLECTION_NAME}")
            self.qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def _validate_table_name(self, table_name):
        """Ensures table name is safe for SQL interpolation."""
        if not re.match(r'^[a-z0-9_]+$', table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    def process_input(self, input_path: str, source_type: str, title: str, sectors: str, summary: str):
        """
        Main entry point for ingestion.
        input_path: File path or URL
        source_type: 'Unknown', 'Excel', 'PDF', 'URL' (derived or explicit)
        """
        logger.info(f"Processing {source_type}: {input_path}")
        
        # 1. Level 1: Insert into Master
        master_id, routing_table_name = self._create_master_entry(title, source_type, summary, sectors)
        
        # 2. Level 2 & 3: Process content based on type
        if source_type.lower() == 'excel' or input_path.endswith(('.xlsx', '.xls')):
            self._process_excel(input_path, master_id, routing_table_name, sectors)
        elif source_type.lower() == 'pdf' or input_path.endswith('.pdf'):
            self._process_pdf(input_path, master_id, routing_table_name, sectors)
        elif source_type.lower() == 'url' or input_path.startswith(('http', 'www')):
            self._process_url(input_path, master_id, routing_table_name, sectors)
        else:
            logger.error("Unsupported file type")
            return

        logger.info("Ingestion Complete.")

    def _create_master_entry(self, title, datatype, summary, sectors):
        # Generate a unique name for the routing table
        safe_title = "".join([c if c.isalnum() else "_" for c in title]).lower()
        # Ensure it starts with a letter and is alphanumeric
        safe_title = re.sub(r'^[^a-z]+', '', safe_title)
        if not safe_title: safe_title = "u_data"
        
        timestamp = int(datetime.now().timestamp())
        routing_table_name = f"routing_{safe_title}_{timestamp}"
        
        # Validate immediately
        self._validate_table_name(routing_table_name)
        
        current_date = datetime.now().strftime("%Y-%m-%d")

        self.cursor.execute("""
            INSERT INTO Master (Title, Source, Summary, Datatype, Sectors, table_name, Date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, "User Upload", summary, datatype, sectors, routing_table_name, current_date))
        self.conn.commit()
        
        master_id = self.cursor.lastrowid
        logger.info(f"Created Master Entry ID: {master_id}, Routing Table: {routing_table_name}")
        
        # Create the Routing Table
        self._create_routing_table(routing_table_name, datatype)
        
        return master_id, routing_table_name

    def _create_routing_table(self, table_name, datatype):
        # Validation
        self._validate_table_name(table_name)

        if datatype.lower() in ['excel', 'sql']:
            # SQL Routing Table
            self.cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    master_id INTEGER,
                    detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Title TEXT,
                    Datatype TEXT,
                    Sectors TEXT,
                    table_name TEXT
                )
            """)
        else:
            # Text/Qdrant Routing Table
            self.cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    master_id INTEGER,
                    detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Title TEXT,
                    Datatype TEXT,
                    Sectors TEXT,
                    qdrant_source TEXT,
                    qdrant_point_id TEXT
                )
            """)
        self.conn.commit()

    def _process_excel(self, file_path, master_id, routing_table_name, sectors):
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            logger.info(f"Processing Sheet: {sheet_name}")
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Clean generic empty rows/cols
            df.dropna(how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            
            # Level 3: Create Detail Table for this sheet
            safe_sheet = "".join([c if c.isalnum() else "_" for c in sheet_name]).lower()
            detail_table_name = f"detail_{master_id}_{safe_sheet}"
            
            # Validate detail table name
            self._validate_table_name(detail_table_name)
            
            df.to_sql(detail_table_name, self.conn, if_exists='replace', index=False)
            
            # Level 2: Insert into Routing Table
            # Note: routing_table_name is already validated
            self.cursor.execute(f"""
                INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, table_name)
                VALUES (?, ?, ?, ?, ?)
            """, (master_id, f"Sheet: {sheet_name}", "SQL", sectors, detail_table_name))
        
        self.conn.commit()

    def _process_pdf(self, file_path, master_id, routing_table_name, sectors):
        reader = pypdf.PdfReader(file_path)
        
        # Simply chunk by page for now, can be improved
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text.strip():
                continue
                
            # Chunking logic (Naive 1000 chars for now)
            chunks = [text[j:j+1000] for j in range(0, len(text), 1000)]
            
            for k, chunk in enumerate(chunks):
                # 1. Embed
                embedding = self.embedder.encode(chunk).tolist()
                point_id = str(uuid.uuid4())
                
                # 2. Upsert to Qdrant (Level 3 equivalent)
                payload = {
                    "master_id": master_id,
                    "routing_table": routing_table_name,
                    "source": os.path.basename(file_path),
                    "page": i + 1,
                    "text": chunk,
                    "sectors": sectors
                }
                
                self.qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
                )
                
                # 3. Insert into Routing Table (Level 2)
                chunk_title = f"Page {i+1} Part {k+1}"
                
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, qdrant_source, qdrant_point_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (master_id, chunk_title, "Text", sectors, os.path.basename(file_path), point_id))
        
        self.conn.commit()

    def _process_url(self, url, master_id, routing_table_name, sectors):
        import requests
        from bs4 import BeautifulSoup
        
        try:
            resp = requests.get(url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Extract main text
            text = soup.get_text(separator='\n')
            
            # Chunking
            chunks = [text[j:j+1000] for j in range(0, len(text), 1000)]
            
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
                
                self.qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
                )
                
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, qdrant_source, qdrant_point_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (master_id, f"Section {k+1}", "Text", sectors, url, point_id))
                
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"URL processing failed: {e}")

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
