import sqlite3
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB/market-intelligence.db")

def migrate_db():
    if not os.path.exists(DB_PATH):
        logger.error(f"Database not found at {DB_PATH}")
        return

    logger.info(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create Master Table if not exists
        logger.info("Creating 'Master' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Title TEXT,
                Source TEXT,
                Summary TEXT,
                Datatype TEXT,
                Sectors TEXT,
                table_name TEXT, 
                month_created TEXT
            )
        """)
        
        # 3. Migration Logic
        logger.info("Migrating existing entries from Master_Old to Master...")
        try:
            cursor.execute("SELECT * FROM Master_Old")
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []
            old_rows = cursor.fetchall()

            if not col_names:
                logger.warning("Could not determine columns for Master_Old. Skipping migration to avoid data loss.")
            else:
                for row in old_rows:
                    row_dict = dict(zip(col_names, row))
                    try:
                        # Heuristic mapping
                        old_table_name = (
                            row_dict.get("table_name") or 
                            row_dict.get("TableName") or 
                            "Unknown"
                        )
                        
                        old_date = (
                            row_dict.get("Date") or 
                            row_dict.get("upload_date") or 
                            "Unknown"
                        )
                        
                        old_title = (
                            row_dict.get("Title") or 
                            row_dict.get("title") or 
                            old_table_name
                        )
                        
                        old_summary = (
                            row_dict.get("Summary") or 
                            row_dict.get("summary") or 
                            ""
                        )
                        
                        old_sectors = (
                            row_dict.get("Sectors") or 
                            row_dict.get("sectors") or 
                            "General"
                        )
                        
                        # Existing entries are likely files
                        datatype = "File"

                        cursor.execute("""
                            INSERT INTO Master (Title, Source, Summary, Datatype, Sectors, table_name, month_created)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (old_title, old_table_name, old_summary, datatype, old_sectors, old_table_name, old_date))
                        
                    except Exception as e:
                        logger.warning(f"Row migration skipped for {row_dict}: {e}")
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
