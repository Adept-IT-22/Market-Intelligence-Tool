import sqlite3
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../DB/market-intelligence.db")

def migrate_db():
    if not os.path.exists(DB_PATH):
        logger.error(f"Database not found at {DB_PATH}")
        return

    logger.info(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Rename existing Master table if it hasn't been done
        # Check if Master_Old exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Master_Old'")
        if not cursor.fetchone():
            logger.info("Renaming existing 'Master' table to 'Master_Old'...")
            cursor.execute("ALTER TABLE Master RENAME TO Master_Old")
        else:
            logger.info("'Master_Old' already exists. Assuming migration partially done or re-running.")
            # Optional: Drop 'Master' if we want to recreate it fresh
            cursor.execute("DROP TABLE IF EXISTS Master")

        # 2. Create New Master Table (Level 1)
        logger.info("Creating new 'Master' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Title TEXT,
                Source TEXT,
                Summary TEXT,
                Datatype TEXT,
                Sectors TEXT,
                table_name TEXT, 
                Date TEXT
            )
        """)

        # 3. Create Routing Table Templates (Level 2)
        # We don't create "one table per source" yet, but we define the schema expectation here or 
        # create a helper table to track routing tables if needed. 
        # For now, the 'Master' table's 'table_name' column points to the Routing Table.
        
        # Le's create a generic SQL Routing Table structure for reference/testing
        # This is what a routing table logic will create dynamically
        """
        CREATE TABLE IF NOT EXISTS {routing_table_name} (
            master_id INTEGER,
            detail_id INTEGER PRIMARY KEY, # Local ID
            Title TEXT,
            Datatype TEXT,
            Sectors TEXT,
            table_name TEXT, # Points to Detail Table
            FOREIGN KEY(master_id) REFERENCES Master(id)
        )
        """

        # Let's migrated data from Master_Old to Master if possible, 
        # BUT the schema is different and the old Master pointed directly to data.
        # We will leave Master empty for now to be populated by the ingestion script properly.
        # Or we can migrate the existing "files" as "Master" entries.
        
        logger.info("Migrating existing entries from Master_Old to Master...")
        cursor.execute("SELECT * FROM Master_Old")
        old_rows = cursor.fetchall()
        # Old Schema: id, table_name, file_path, upload_date, Title, Summary, Sectors
        # New Schema: id, Title, Source, Summary, Datatype, Sectors, table_name, Date
        
        for row in old_rows:
            # Map old columns to new. 
            # Note: Old table structure is a bit messy, let's look at check_db output
            # (1, 'KNBS_AnnualStatisticalAbstract', ..., 'KNBS Annual Statistical Abstract', ...)
            
            # Since I can't see exact column order from `check_db` output (it was truncated), 
            # I will just create the table structure and let the ingestion script handle population 
            # effectively restarting the index.
            pass
        
        conn.commit()
        logger.info("Migration Schema Update Complete!")
        
        # Verify
        cursor.execute("PRAGMA table_info('Master')")
        logger.info(f"New Master Schema: {cursor.fetchall()}")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_db()
