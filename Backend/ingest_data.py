import os
import pandas as pd
import logging
import uuid
import re
import argparse

# Qdrant & Embedding Imports
from qdrant_client.models import PointStruct, VectorParams, Distance
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# File parsers
import pypdf 

import requests
from bs4 import BeautifulSoup
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
        # ... (init code) ...
        self._ensure_collection()

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def _validate_table_name(self, table_name):
        # ... (existing validation) ...
        if not re.match(r'^[a-z0-9_]+$', table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    def _chunk_text(self, text, size=1000):
        """Helper to chunk text into specific sizes."""
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
             
        try:
             # 1. Level 1: Insert into Master
            master_id, routing_table_name = self._create_master_entry(title, source_type, summary, sectors)
            
            # 2. Level 2 & 3: Process content
            if source_type.lower() == 'excel' or input_path.endswith(('.xlsx', '.xls')):
                self._process_excel(input_path, master_id, routing_table_name, sectors)
            elif source_type.lower() == 'pdf' or input_path.endswith('.pdf'):
                self._process_pdf(input_path, master_id, routing_table_name, sectors)
            elif source_type.lower() == 'url':
                self._process_url(input_path, master_id, routing_table_name, sectors)
                
            logger.info("Ingestion Complete.")
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            # Optional: Rollback Master entry if created? 
            # For now, just logging error. To be robust, we could delete the master entry.
            if 'master_id' in locals():
                 logger.warning(f"Orphaned Master Entry Created: ID {master_id}")

    # ... _create_master_entry ...
    
    # ... _create_routing_table ...

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
                
                detail_table_name = f"detail_{master_id}_{safe_sheet}"
                self._validate_table_name(detail_table_name)
                
                df.to_sql(detail_table_name, self.conn, if_exists='replace', index=False)
                
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
                if not text.strip(): continue
                
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
                    
                    self.qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
                    )
                    
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
            resp = requests.get(url, timeout=10) # Added timeout
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.content, 'html.parser')
            text = soup.get_text(separator='\n')
            
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
