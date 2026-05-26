import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "market_intelligence"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "your_password_here")
    )

def init_postgres_db():
    """Initializes the PostgreSQL database with the necessary tables and audit fields."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Master Table with Lineage Fields
        logger.info("Creating Master table in PostgreSQL...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS master (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT,
                summary TEXT,
                datatype TEXT,
                sectors TEXT,
                table_name TEXT,
                month_created TEXT,
                department TEXT DEFAULT 'General',
                task_id UUID,
                worker_id TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            );
        """)
        
        # 2. Ingestion Status / Logs Table
        logger.info("Creating Ingestion Logs table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_logs (
                id SERIAL PRIMARY KEY,
                task_id UUID NOT NULL,
                event_type TEXT, -- 'info', 'error', 'warning'
                message TEXT,
                payload JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Failed Jobs (Dead Letter Queue Metadata)
        logger.info("Creating Failed Jobs table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS failed_jobs (
                id SERIAL PRIMARY KEY,
                task_id UUID UNIQUE,
                source_file TEXT,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Ingestion History Table
        logger.info("Creating Ingestion History table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_history (
                id SERIAL PRIMARY KEY,
                task_id VARCHAR(255) UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT,
                file_size_kb DOUBLE PRECISION,
                department TEXT DEFAULT 'General',
                source_url TEXT,
                pipeline_type TEXT,
                status TEXT DEFAULT 'queued',
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                duration_seconds REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Backpopulate Ingestion History from Master Table
        logger.info("Backpopulating Ingestion History from Master table...")
        try:
            # Select all master records
            cur.execute("SELECT id, title, source, department, task_id, processed_at FROM master")
            master_rows = cur.fetchall()
            
            import uuid
            for row in master_rows:
                m_id, title, source, department, task_id, processed_at = row
                
                # Generate a task ID if it is missing
                t_id = task_id
                if not t_id:
                    t_id = str(uuid.uuid4())
                    # Update master table with generated task_id
                    cur.execute("UPDATE master SET task_id = %s WHERE id = %s", (t_id, m_id))
                else:
                    t_id = str(t_id)
                    
                # Check if this task already exists in ingestion_history
                cur.execute("SELECT 1 FROM ingestion_history WHERE task_id = %s", (t_id,))
                exists = cur.fetchone()
                
                if not exists:
                    # Derive pipeline type
                    ext = title.rsplit('.', 1)[1].lower() if '.' in title else 'pdf'
                    type_map = {
                        'xlsx': 'excel', 'xls': 'excel', 
                        'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx',
                        'txt': 'md', 'csv': 'excel', 'md': 'md',
                        'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image'
                    }
                    pipeline = type_map.get(ext, 'pdf') + '_pipeline'
                    
                    # Insert history record
                    cur.execute("""
                        INSERT INTO ingestion_history 
                        (task_id, filename, original_filename, file_size_kb, department, source_url, pipeline_type, status, error_message, started_at, completed_at, duration_seconds, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'succeeded', NULL, %s, %s, 10.0, %s)
                    """, (t_id, title, title, 0.0, department or 'General', source, pipeline, processed_at, processed_at, processed_at))
                    logger.info(f"Backpopulated task {t_id} for file {title}")
        except Exception as pop_err:
            logger.warning(f"Could not backpopulate ingestion history: {pop_err}")

        conn.commit()
        logger.info("PostgreSQL initialization complete.")
        
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_postgres_db()
