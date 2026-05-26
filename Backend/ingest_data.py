import os
import pandas as pd
import logging
import uuid
import re
import argparse
import requests
import psycopg2
from psycopg2 import sql, extras
import base64
from datetime import datetime
from bs4 import BeautifulSoup
import pypdf
from docx import Document
from pptx import Presentation
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from groq import Groq # Keep for legacy/future
from typing import Optional, Dict, Any
# Vision / OCR Imports (Optional)
try:
    import google.generativeai as genai
    from PIL import Image
    HAS_VISION = True
except ImportError:
    HAS_VISION = False
    class genai:
        @staticmethod
        def configure(**kwargs): pass
    class Image:
        @staticmethod
        def open(path): return None

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
COLLECTION_NAME = "adept_database"
INDEX_COLLECTION = "document_index"  # PageIndex: document-level summaries
EMBEDDING_MODEL = "BAAI/bge-small-en"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class DataIngester:
    def __init__(self, task_metadata: Optional[Dict[str, Any]] = None):
        # Postgres Connection
        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            database=os.getenv("POSTGRES_DB", "market_intelligence"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "your_password_here")
        )
        self.cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.task_metadata = task_metadata or {}
        self.summary_report = {"success": [], "failed": [], "skipped": []}
        
        # Elite Engine Components
        from engine_manager import DataTransformer, AIEnricher
        self.transformer = DataTransformer()
        self.enricher = AIEnricher(GOOGLE_API_KEY, GROQ_API_KEY)
        
        # Initialize Embedder
        logger.info("Loading embedding model...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        
        # Initialize Qdrant
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        self.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self._ensure_collection()

        # Initialize Groq (Optional)
        self.groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

        # Initialize Gemini
        if GOOGLE_API_KEY:
            genai.configure(api_key=GOOGLE_API_KEY)
        else:
            logger.warning("GOOGLE_API_KEY not found. Gemini OCR will fail.")



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
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def _validate_table_name(self, table_name):
        if not re.match(r'^[a-z0-9_]+$', table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name

    def _chunk_text(self, text, max_size=1000):
        """Semantic chunking: split on paragraph boundaries, not character count.
        Falls back to sentence splitting, then hard splits for dense text."""
        if not text: return []
        
        # Split on paragraph breaks (double newline, or section headers)
        paragraphs = re.split(r'\n\s*\n|\n(?=[A-Z#\-\*])', text)
        
        # If we only got 1 giant block, try sentence splitting
        if len(paragraphs) <= 1 and len(text) > max_size:
            paragraphs = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # If adding this paragraph exceeds limit and we have content, flush
            if len(current) + len(para) + 2 > max_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current += "\n\n" + para if current else para
        
        if current.strip():
            chunks.append(current.strip())
        
        # Safety: if any chunk is still too large, hard-split it
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > max_size * 1.5:
                for i in range(0, len(chunk), max_size):
                    final_chunks.append(chunk[i:i+max_size])
            else:
                final_chunks.append(chunk)
        
        return final_chunks

    def _extract_keywords(self, text, top_n=5):
        """Extract top keywords from text using frequency + stopword removal."""
        stopwords = {
            'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'about',
            'what', 'how', 'why', 'when', 'where', 'who', 'which', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall',
            'not', 'no', 'but', 'or', 'and', 'so', 'if', 'then', 'than', 'this',
            'that', 'these', 'those', 'it', 'its', 'from', 'also', 'more', 'their',
            'they', 'them', 'we', 'our', 'you', 'your', 'he', 'she', 'his', 'her'
        }
        tokens = re.findall(r'[a-z0-9]+', text.lower())
        filtered = [t for t in tokens if t not in stopwords and len(t) >= 3]
        # Count frequency
        freq = {}
        for t in filtered:
            freq[t] = freq.get(t, 0) + 1
        # Sort by frequency and return top N as comma-separated string
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return ",".join([t[0] for t in top])

    def _score_importance(self, text):
        """Heuristic importance score (0.0-1.0) based on content signals."""
        score = 0.3  # base score
        # Numbers/percentages indicate data-rich content
        numbers = len(re.findall(r'\d+\.?\d*%?', text))
        if numbers > 5: score += 0.3
        elif numbers > 2: score += 0.15
        # Currency/financial indicators
        if re.search(r'[$€£¥KSh]|USD|KES|revenue|profit|cost|price|budget', text, re.I):
            score += 0.1
        # Named entities (capitalized multi-word phrases)
        entities = len(re.findall(r'[A-Z][a-z]+ [A-Z][a-z]+', text))
        if entities > 3: score += 0.1
        # Length signals depth
        if len(text) > 500: score += 0.1
        return min(1.0, score)

    def process_input(self, input_path: str, source_type: str, title: str, sectors: str, summary: str, department: str = "General", source_url: Optional[str] = None):
        logger.info(f"Processing {source_type}: {input_path} for department: {department} (source_url: {source_url})")
        self.current_source_url = source_url
        
        # Normalize input path
        if not input_path.startswith(('http://', 'https://')):
            input_path = os.path.abspath(input_path)

        # Validate Input BEFORE creating Master entry
        supported_types = ['excel', 'pdf', 'url', 'docx', 'pptx', 'image', 'md']
        st_lower = source_type.lower()
        if st_lower not in supported_types:
             logger.error(f"Unsupported source type: {source_type}")
             return

        if st_lower == 'url' and not input_path.startswith(('http://', 'https://')):
             logger.error(f"Invalid URL format: {input_path}")
             return
             
        # Sanitize title
        title = re.sub(r'[^\w\s-]', '', title).strip()
        if not title: title = "Untitled Dataset"

        try:
             # 1. Level 1: Insert into Master and get assigned ID
            master_id, routing_table_name = self._create_master_entry(title, input_path, source_type, summary, sectors, department)
            
            # 2. Level 2 & 3: Process content
            if st_lower == 'excel' or input_path.endswith(('.xlsx', '.xls')):
                self._process_excel(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'pdf' or input_path.endswith('.pdf'):
                self._process_pdf(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'url':
                self._process_url(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'docx' or input_path.endswith('.docx'):
                self._process_docx(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'pptx' or input_path.endswith('.pptx'):
                self._process_pptx(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'image' or input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                self._process_image(input_path, master_id, routing_table_name, sectors, department)
            elif st_lower == 'md' or input_path.endswith('.md'):
                self._process_md(input_path, master_id, routing_table_name, sectors, department)
            
            self.summary_report["success"].append(input_path)
            logger.info("Ingestion Complete.")

        except Exception as e:
            logger.error(f"Ingestion failed for {input_path}: {e}")
            self.summary_report["failed"].append({"path": input_path, "error": str(e)})
            
            # Rollback logic for clean DB state
            if 'routing_table_name' in locals() and 'master_id' in locals():
                logger.warning(f"Rolling back: Dropping routing table {routing_table_name}")
                try:
                    self.cursor.execute(f"DROP TABLE IF EXISTS {routing_table_name}")
                    self.cursor.execute("DELETE FROM master WHERE id = %s", (master_id,))
                    self.conn.commit()
                except Exception as rollback_err:
                    logger.error(f"Rollback failed: {rollback_err}")
            raise e
        finally:
            self.current_source_url = None

    def _create_master_entry(self, title, source, source_type, summary, sectors, department):
        # Create unique routing table name prefix
        safe_title = "".join([c if c.isalnum() else "_" for c in title]).lower()
        month_str = datetime.now().strftime("%B %Y")
        
        logger.info(f"Creating Master Entry: {title} (Dept: {department})")
        
        task_id = self.task_metadata.get('task_id')
        worker_id = self.task_metadata.get('worker_id')
        
        db_source = self.current_source_url if getattr(self, 'current_source_url', None) else source
        
        self.cursor.execute("""
            INSERT INTO master (title, source, summary, datatype, sectors, table_name, month_created, department, task_id, worker_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (title, db_source, summary, source_type, sectors, "PENDING", month_str, department, task_id, worker_id))
        
        master_id = self.cursor.fetchone()['id']
        routing_table_name = f"route_{safe_title[:20]}_{master_id}"
        self._validate_table_name(routing_table_name)
        
        # Update with real routing table name
        self.cursor.execute("UPDATE master SET table_name = %s WHERE id = %s", (routing_table_name, master_id))
        
        self._create_routing_table(routing_table_name)
        self.conn.commit()
        
        # --- v2: Auto-index into PageIndex ---
        self._index_to_page_index(master_id, title, summary, db_source, sectors, department, source_type, routing_table_name)
        
        return master_id, routing_table_name

    def _index_to_page_index(self, master_id, title, summary, source, sectors, department, datatype, table_name):
        """Add this document to the PageIndex (document_index) Qdrant collection."""
        try:
            # Weight title heavily for embedding quality
            embed_text = f"{title}. {title}. {summary}. Sectors: {sectors}. Department: {department}"
            vector = self.embedder.encode(embed_text).tolist()
            
            point = PointStruct(
                id=int(master_id),
                vector=vector,
                payload={
                    "master_id": master_id,
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "sectors": sectors,
                    "department": department,
                    "datatype": datatype,
                    "table_name": table_name,
                    "indexed_at": datetime.now().isoformat()
                }
            )
            
            # Ensure collection exists
            existing = [c.name for c in self.qdrant.get_collections().collections]
            if INDEX_COLLECTION not in existing:
                from qdrant_client.models import VectorParams, Distance
                self.qdrant.create_collection(
                    collection_name=INDEX_COLLECTION,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
            
            self.qdrant.upsert(collection_name=INDEX_COLLECTION, points=[point])
            logger.info(f"PageIndex: Indexed document #{master_id} '{title}'")
        except Exception as e:
            logger.warning(f"PageIndex indexing failed for #{master_id}: {e} (non-fatal)")

    def _create_routing_table(self, table_name):
        self._validate_table_name(table_name)
        logger.info(f"Creating Routing Table: {table_name}")
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                master_id TEXT,
                title TEXT,
                datatype TEXT,
                sectors TEXT,
                department TEXT,
                table_name TEXT,
                qdrant_source TEXT,
                qdrant_point_id TEXT
            )
        """)

    def _process_excel(self, file_path, master_id, routing_table_name, sectors, department):
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                df.dropna(how='all', inplace=True)
                df.dropna(axis=1, how='all', inplace=True)
                
                safe_sheet = "".join([c if c.isalnum() else "_" for c in sheet_name]).lower()
                if not safe_sheet: safe_sheet = "sheet"
                
                if df.empty or len(df.columns) == 0:
                    logger.warning(f"Skipping empty sheet {sheet_name} in {file_path}")
                    continue
                
                detail_table_name = f"detail_{master_id}_{safe_sheet}"
                self._validate_table_name(detail_table_name)
                
                # Use SQLAlchemy engine for to_sql (Postgres requires it)
                from sqlalchemy import create_engine
                db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
                engine = create_engine(db_url)
                df.to_sql(detail_table_name, engine, if_exists='replace', index=False)
                
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, title, datatype, sectors, department, table_name)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (master_id, f"Sheet: {sheet_name}", "SQL", sectors, department, detail_table_name))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Excel processing failed for {file_path}: {e}")
            raise e

    def _process_pdf(self, file_path, master_id, routing_table_name, sectors, department):
        try:
            reader = pypdf.PdfReader(file_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text or not text.strip(): continue
                self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, department, f"Page {i+1}")
            self.conn.commit()
        except Exception as e:
            logger.error(f"PDF processing failed for {file_path}: {e}")
            raise e

    def _extract_docx_text(self, doc: Document) -> str:
        """
        Extract text from a DOCX document, including body paragraphs, tables,
        headers, footers, and text boxes where possible.
        """
        texts = []
        # Body paragraphs
        for para in doc.paragraphs:
            if para.text and para.text.strip():
                texts.append(para.text)
        # Tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if para.text and para.text.strip():
                            texts.append(para.text)
        # Headers/Footers
        for section in doc.sections:
            for hdr_ftr in (section.header, section.footer):
                if not hdr_ftr: continue
                for para in hdr_ftr.paragraphs:
                    if para.text and para.text.strip():
                        texts.append(para.text)
                for table in hdr_ftr.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for para in cell.paragraphs:
                                if para.text and para.text.strip():
                                    texts.append(para.text)
        # Text boxes via XML
        try:
            root = doc.part.element
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for t in root.xpath(".//w:txbxContent//w:t", namespaces=ns):
                if t.text and t.text.strip():
                    texts.append(t.text)
        except Exception:
            pass
        return "\n".join(texts)

    def _process_docx(self, file_path, master_id, routing_table_name, sectors, department):
        try:
            doc = Document(file_path)
            text = self._extract_docx_text(doc)
            if not text or not text.strip():
                logger.warning(f"Skipping DOCX with no extractable text: {file_path}")
                return
            self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, department, "Document Content")
            self.conn.commit()
        except Exception as e:
            logger.error(f"Docx processing failed for {file_path}: {e}")
            raise e

    def _process_pptx(self, file_path, master_id, routing_table_name, sectors, department):
        try:
            prs = Presentation(file_path)
            for i, slide in enumerate(prs.slides):
                text_runs = []
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text_runs.append(shape.text)
                text = "\n".join(text_runs)
                if not text.strip(): continue
                self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, department, f"Slide {i+1}")
            self.conn.commit()
        except Exception as e:
            logger.error(f"Pptx processing failed for {file_path}: {e}")
            raise e

    def _process_url(self, url, master_id, routing_table_name, sectors, department):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            self._upsert_text_chunks(text, url, master_id, routing_table_name, sectors, department, "Web Content")
            self.conn.commit()
        except Exception as e:
            logger.error(f"URL processing failed for {url}: {e}")
            raise e
    
    def _process_md(self, file_path, master_id, routing_table_name, sectors, department):
        """Process Markdown files by reading as plain text."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            if not text.strip():
                logger.warning(f"Skipping empty MD file: {file_path}")
                return
            self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, department, "Markdown Content")
            self.conn.commit()
        except Exception as e:
            logger.error(f"MD processing failed for {file_path}: {e}")
            raise e


    def _process_image(self, file_path, master_id, routing_table_name, sectors, department):
        """
        Extract text and insights from images using Gemini Vision.
        """
        if not HAS_VISION:
            logger.error("Vision capabilities (google-generativeai/PIL) not installed. Skipping image.")
            return

        logger.info(f"Processing image with Gemini Vision: {file_path}")
        try:
            # 1. Open image
            img = Image.open(file_path)
            
            # 2. Use Gemini 1.5 Flash for vision
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = (
                "You are an expert OCR and image analyst for a Market Intelligence Tool.\n"
                "1. EXTRACT ALL TEXT from this image exactly as it appears.\n"
                "2. DESCRIBE CHARTS/TABLES: If there are any, extract the data points and metrics.\n"
                "3. SUMMARY: Provide a concise summary of the visual content relevant to market intelligence.\n"
                "Output as structured Markdown."
            )
            
            response = model.generate_content([prompt, img])
            text = response.text
            
            if not text or not text.strip():
                logger.warning(f"No text or insights extracted from image: {file_path}")
                return

            # 3. Store in Qdrant and the SQLite routing table
            self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, department, "Image Analysis")
            self.conn.commit()
            logger.info(f"Image analysis complete for: {file_path}")
            
        except Exception as e:
            logger.error(f"Image processing failed for {file_path}: {e}")
            raise e

    def _upsert_text_chunks(self, text, source, master_id, routing_table_name, sectors, department, title_prefix, doc_type="general", section_name=None):
        chunks = self._chunk_text(text, max_size=1000)  # Now uses semantic chunking
        
        qdrant_source = self.current_source_url if getattr(self, 'current_source_url', None) else source
        
        for k, chunk in enumerate(chunks):
            embedding = self.embedder.encode(chunk).tolist()
            point_id = str(uuid.uuid4())
            
            # Metadata for both DBs
            ingested_at = datetime.now().isoformat()
            
            # --- Elite Pipeline: Transform & Enrich ---
            # 1. Transform
            transformed_chunk = self.transformer.transform({"text": chunk}, "rag_pipeline")
            chunk_to_store = transformed_chunk.get("text", chunk)
            
            # 2. Enrich (AI Metadata)
            enrichment = self.enricher.enrich(chunk_to_store, context="rag_pipeline")
            
            payload = {
                "master_id": master_id,
                "routing_table": routing_table_name,
                "source": qdrant_source,
                "text": chunk_to_store,
                "sectors": sectors,
                "department": department,
                "section_name": section_name or title_prefix,
                "doc_type": doc_type,
                "keywords": self._extract_keywords(chunk_to_store),
                "importance": self._score_importance(chunk_to_store),
                "sentiment": enrichment.get("sentiment"),
                "classification": enrichment.get("classification"),
                "ingested_at": ingested_at,
                "task_id": self.task_metadata.get("task_id"),
                "worker_id": self.task_metadata.get("worker_id")
            }
            
            # 1. Upsert to Qdrant (Semantic + Metadata)
            self.qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
            )
            
            # 2. Insert into SQL Routing Table
            table_name_safe = self._validate_table_name(routing_table_name)
            self.cursor.execute(f"""
                INSERT INTO {table_name_safe} (master_id, title, datatype, sectors, department, qdrant_source, qdrant_point_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (master_id, f"{title_prefix} Part {k+1}", "Text/Hybrid", sectors, department, qdrant_source, point_id))
        
        self.conn.commit()

    def print_summary(self):
        print("\n" + "="*50)
        print("INGESTION SUMMARY")
        print("="*50)
        print(f"Successfully processed: {len(self.summary_report['success'])}")
        print(f"Failed: {len(self.summary_report['failed'])}")
        print(f"Skipped: {len(self.summary_report['skipped'])}")
        
        if self.summary_report['failed']:
            print("\nFailures:")
            for item in self.summary_report['failed']:
                print(f"- {item['path']}: {item['error']}")
        
        if self.summary_report['skipped']:
            print("\nSkipped (Unsupported):")
            for item in self.summary_report['skipped']:
                print(f"- {item}")
        print("="*50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest data into Market Intelligence V2 Ecosystem")
    parser.add_argument("--input", required=True, help="Path to file, directory, or URL")
    parser.add_argument("--type", choices=['excel', 'pdf', 'url', 'docx', 'pptx', 'image', 'md', 'auto'], default='auto', help="Type of input data")
    parser.add_argument("--title", help="Title for the dataset")
    parser.add_argument("--sectors", default="General", help="Comma-separated sectors")
    parser.add_argument("--summary", default="", help="Brief summary of the data")
    
    args = parser.parse_args()
    ingester = DataIngester()

    if os.path.isdir(args.input):
        logger.info(f"Scanning directory: {args.input}")
        for root, dirs, files in os.walk(args.input):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                f_type = None
                if ext in ['.xlsx', '.xls']: f_type = 'excel'
                elif ext == '.pdf': f_type = 'pdf'
                elif ext == '.docx': f_type = 'docx'
                elif ext == '.pptx': f_type = 'pptx'
                elif ext == '.md': f_type = 'md'
                elif ext in ['.png', '.jpg', '.jpeg', '.webp']: f_type = 'image'
                
                if f_type:
                    full_path = os.path.join(root, file)
                    f_title = args.title if args.title else file
                    try:
                        ingester.process_input(full_path, f_type, f_title, args.sectors, args.summary)
                    except Exception as e:
                        # Error already logged and added to summary in process_input
                        pass
                else:
                    ingester.summary_report["skipped"].append(file)
                    logger.debug(f"Skipping unsupported file: {file}")

    else:
        # Use provided type or auto-detect
        type_map = {
            '.xlsx': 'excel', '.xls': 'excel', 
            '.pdf': 'pdf', 
            '.docx': 'docx', 
            '.pptx': 'pptx',
            '.md': 'md',
            '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.webp': 'image'
        }
        f_type = args.type
        if f_type == 'auto':
            ext = os.path.splitext(args.input)[1].lower()
            f_type = type_map.get(ext, 'url' if args.input.startswith('http') else None)
        
        if not f_type:
            logger.error("Could not determine file type. Please specify --type.")
        else:
            f_title = args.title if args.title else os.path.basename(args.input)
            try:
                ingester.process_input(args.input, f_type, f_title, args.sectors, args.summary)
            except Exception as e:
                # Error already logged and added to summary in process_input
                pass

    ingester.print_summary()


