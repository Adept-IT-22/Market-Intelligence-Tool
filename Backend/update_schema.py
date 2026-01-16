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
        
        # 3. Migration Logic
        logger.info("Migrating existing entries from Master_Old to Master...")
        try:
            cursor.execute("SELECT * FROM Master_Old")
            old_rows = cursor.fetchall()
            
            for row in old_rows:
                # Attempt to map old schema
                # Heuristic mapping based on common structure
                try:
                     # Minimal valid shape?
                     if len(row) >= 4:
                         old_table_name = row[1]
                         old_date = row[3] if len(row) > 3 else "Unknown"
                         old_title = row[4] if len(row) > 4 else old_table_name
                         old_summary = row[5] if len(row) > 5 else ""
                         old_sectors = row[6] if len(row) > 6 else "General"
                         
                         datatype = "File" 
                         
                         cursor.execute("""
                            INSERT INTO Master (Title, Source, Summary, Datatype, Sectors, table_name, Date)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                         """, (old_title, old_table_name, old_summary, datatype, old_sectors, old_table_name, old_date))
                except Exception as e:
                    logger.warning(f"Row migration skipped for {row}: {e}")
                    continue
        except Exception as ex:
             logger.warning(f"Could not read Master_Old or it is empty: {ex}")

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
