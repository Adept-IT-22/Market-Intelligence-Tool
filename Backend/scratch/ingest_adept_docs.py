import os
import sys
import logging
from datetime import datetime

# Add the Backend directory to path so we can import DataIngester
sys.path.append(os.path.join(os.getcwd(), "Backend"))
from ingest_data import DataIngester

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ingest_adept_knowledge():
    ingester = DataIngester()
    
    docs = [
        {
            "path": r"C:\Users\imain\Downloads\Innovation & Delivery Best Practice Guide.docx",
            "title": "Adept Best Practice Guide",
            "doc_type": "guideline",
            "section": "Best Practice"
        },
        {
            "path": r"C:\Users\imain\Downloads\202604-Rec-Adept Footer.docx",
            "title": "Adept Branding Footer",
            "doc_type": "template",
            "section": "Branding"
        },
        {
            "path": r"C:\Users\imain\Downloads\Adept Delivery Playbook v0_1.docx",
            "title": "Adept Delivery Playbook",
            "doc_type": "logic",
            "section": "Delivery Lifecycle"
        }
    ]
    
    for doc in docs:
        if not os.path.exists(doc["path"]):
            print(f"ERROR: File not found: {doc['path']}")
            continue
            
        print(f"INFO: Ingesting {doc['title']} from {doc['path']}...")

        
        # We need to manually call the processing logic with the custom metadata
        try:
            # 1. Register in Master Table
            ingester.cursor.execute("""
                INSERT INTO MasterIndex (Title, Datatype, Sectors, Summary, IngestedAt)
                VALUES (?, ?, ?, ?, ?)
            """, (doc["title"], "DOCX/Adept-Knowledge", "Internal", doc["title"], datetime.now().isoformat()))
            master_id = ingester.cursor.lastrowid
            
            # 2. Create Routing Table
            routing_table_name = f"RT_Adept_{master_id}"
            ingester.cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {routing_table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    master_id INTEGER,
                    Title TEXT,
                    Datatype TEXT,
                    Sectors TEXT,
                    Department TEXT,
                    qdrant_source TEXT,
                    qdrant_point_id TEXT
                )
            """)
            
            # 3. Process the file
            # Extract text (using the Docx logic inside DataIngester)
            # Since DataIngester._process_docx is private, we'll use it directly
            # Note: _process_docx currently calls _upsert_text_chunks which we updated
            
            # We'll temporarily override the _upsert_text_chunks behavior to pass our special metadata
            # by wrapping the call or using the new parameters we added.
            
            text = ingester._extract_text_from_docx(doc["path"])
            if text:
                ingester._upsert_text_chunks(
                    text=text,
                    source=doc["path"],
                    master_id=master_id,
                    routing_table_name=routing_table_name,
                    sectors="Internal",
                    department="Adept-Engine",
                    title_prefix=doc["title"],
                    doc_type=doc["doc_type"],
                    section_name=doc["section"]
                )
                logger.info(f"Successfully ingested {doc['title']}")
            else:
                logger.warning(f"No text found in {doc['path']}")
                
        except Exception as e:
            logger.error(f"Failed to ingest {doc['title']}: {e}")
            
    ingester.conn.commit()
    logger.info("Adept knowledge ingestion complete.")

if __name__ == "__main__":
    ingest_adept_knowledge()
