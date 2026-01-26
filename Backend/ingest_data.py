import os
import pandas as pd
import logging
import uuid
import re
import argparse
import requests
import sqlite3
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
import google.generativeai as genai
from PIL import Image
import io

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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class DataIngester:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self.summary_report = {"success": [], "failed": [], "skipped": []}
        
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

    def _process_image(self, file_path, master_id, routing_table_name, sectors):
        """
        Uses Google Gemini (Flash) for OCR/Vision since Groq Vision is unavailable.
        """
        logger.info(f"Processing image with Gemini: {file_path}")
        
        if not GOOGLE_API_KEY:
            logger.error("Skipping Image OCR: GOOGLE_API_KEY is missing.")
            return

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Load image using PIL
            image_file = Image.open(file_path)
            
            response = model.generate_content([
                "Transcribe the text in this image perfectly. Output ONLY the text content. If it's a chart or diagram, describe the key data points in detail.", 
                image_file
            ])
            
            text_content = response.text
            
            if not text_content or not text_content.strip():
                logger.warning(f"No text extracted from image: {file_path}")
                return

            logger.info("OCR Success (Gemini). Upserting text...")
            self._upsert_text_chunks(text_content, file_path, master_id, routing_table_name, sectors, "Image Content")
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Gemini OCR failed for {file_path}: {e}")
            raise e

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
        
        # Normalize input path
        if not input_path.startswith(('http://', 'https://')):
            input_path = os.path.abspath(input_path)

        # Validate Input BEFORE creating Master entry
        supported_types = ['excel', 'pdf', 'url', 'docx', 'pptx', 'image']
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
            master_id, routing_table_name = self._create_master_entry(title, input_path, source_type, summary, sectors)
            
            # 2. Level 2 & 3: Process content
            if st_lower == 'excel' or input_path.endswith(('.xlsx', '.xls')):
                self._process_excel(input_path, master_id, routing_table_name, sectors)
            elif st_lower == 'pdf' or input_path.endswith('.pdf'):
                self._process_pdf(input_path, master_id, routing_table_name, sectors)
            elif st_lower == 'url':
                self._process_url(input_path, master_id, routing_table_name, sectors)
            elif st_lower == 'docx' or input_path.endswith('.docx'):
                self._process_docx(input_path, master_id, routing_table_name, sectors)
            elif st_lower == 'pptx' or input_path.endswith('.pptx'):
                self._process_pptx(input_path, master_id, routing_table_name, sectors)
            elif st_lower == 'image' or input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                self._process_image(input_path, master_id, routing_table_name, sectors)
            
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
                    self.cursor.execute("DELETE FROM Master WHERE id = ?", (master_id,))
                    self.conn.commit()
                except Exception as rollback_err:
                    logger.error(f"Rollback failed: {rollback_err}")
            raise e

    def _create_master_entry(self, title, source, source_type, summary, sectors):
        # Create unique routing table name prefix
        safe_title = "".join([c if c.isalnum() else "_" for c in title]).lower()
        month_str = datetime.now().strftime("%B %Y")
        
        logger.info(f"Creating Master Entry: {title}")
        self.cursor.execute("""
            INSERT INTO Master (Title, Source, Summary, Datatype, Sectors, table_name, month_created)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, source, summary, source_type, sectors, "PENDING", month_str))
        
        master_id = self.cursor.lastrowid
        routing_table_name = f"route_{safe_title[:20]}_{master_id}"
        self._validate_table_name(routing_table_name)
        
        # Update with real routing table name
        self.cursor.execute("UPDATE Master SET table_name = ? WHERE id = ?", (routing_table_name, master_id))
        
        self._create_routing_table(routing_table_name)
        self.conn.commit()
        
        return master_id, routing_table_name

    def _create_routing_table(self, table_name):
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
                df.to_sql(detail_table_name, self.conn, if_exists='replace', index=False)
                
                self.cursor.execute(f"""
                    INSERT INTO {routing_table_name} (master_id, Title, Datatype, Sectors, table_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (master_id, f"Sheet: {sheet_name}", "SQL", sectors, detail_table_name))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Excel processing failed for {file_path}: {e}")
            raise e

    def _process_pdf(self, file_path, master_id, routing_table_name, sectors):
        try:
            reader = pypdf.PdfReader(file_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text or not text.strip(): continue
                self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, f"Page {i+1}")
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

    def _process_docx(self, file_path, master_id, routing_table_name, sectors):
        try:
            doc = Document(file_path)
            text = self._extract_docx_text(doc)
            if not text or not text.strip():
                logger.warning(f"Skipping DOCX with no extractable text: {file_path}")
                return
            self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, "Document Content")
            self.conn.commit()
        except Exception as e:
            logger.error(f"Docx processing failed for {file_path}: {e}")
            raise e

    def _process_pptx(self, file_path, master_id, routing_table_name, sectors):
        try:
            prs = Presentation(file_path)
            for i, slide in enumerate(prs.slides):
                text_runs = []
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text_runs.append(shape.text)
                text = "\n".join(text_runs)
                if not text.strip(): continue
                self._upsert_text_chunks(text, file_path, master_id, routing_table_name, sectors, f"Slide {i+1}")
            self.conn.commit()
        except Exception as e:
            logger.error(f"Pptx processing failed for {file_path}: {e}")
            raise e

    def _process_url(self, url, master_id, routing_table_name, sectors):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            self._upsert_text_chunks(text, url, master_id, routing_table_name, sectors, "Web Content")
            self.conn.commit()
        except Exception as e:
            logger.error(f"URL processing failed for {url}: {e}")
            raise e
    
    def _encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _process_image(self, file_path, master_id, routing_table_name, sectors):
        """
        Attempts to use Groq Vision for OCR. 
        Currently disabled/guarded as Llama 3.2 Vision models are decommissioned on Groq.
        """
        logger.info(f"Processing image: {file_path}")
        logger.warning("Groq Vision models (Llama 3.2 11b/90b) are currently DECOMMISSIONED by Groq.")
        logger.warning("Image OCR is skipped. Please provide a valid OpenAI/Gemini key or wait for Groq updates.")
        
        # Placeholder for future implementation or fallback
        # For now, we insert a placeholder text so the record exists but isn't empty
        placeholder_text = "[Image OCR Skipped: Vision capabilities currently unavailable downstream]"
        self._upsert_text_chunks(placeholder_text, file_path, master_id, routing_table_name, sectors, "Image Content (Skipped)")
        
        return
        
        # Original implementation (kept for reference if models return)
        """
        try:
            base64_image = self._encode_image(file_path)
            chat_completion = self.groq_client.chat.completions.create(
                messages=[...],
                model="llama-3.2-90b-vision-preview",
            )
            ...
        """

    def _upsert_text_chunks(self, text, source, master_id, routing_table_name, sectors, title_prefix):
        chunks = self._chunk_text(text, 1000)
        for k, chunk in enumerate(chunks):
            embedding = self.embedder.encode(chunk).tolist()
            point_id = str(uuid.uuid4())
            payload = {
                "master_id": master_id,
                "routing_table": routing_table_name,
                "source": source,
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
            """, (master_id, f"{title_prefix} Part {k+1}", "Text", sectors, source, point_id))
        
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
    parser.add_argument("--type", choices=['excel', 'pdf', 'url', 'docx', 'pptx', 'image', 'auto'], default='auto', help="Type of input data")
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


