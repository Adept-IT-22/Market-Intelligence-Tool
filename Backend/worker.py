import os
import logging
from engine_manager import TaskMetadata
from ingest_data import DataIngester
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [Worker:%(worker_id)s] - %(message)s')
raw_logger = logging.getLogger(__name__)

# Mock worker ID for lineage
WORKER_ID = f"worker_{os.getpid()}"

class WorkerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return msg, {**kwargs, 'extra': {**(kwargs.get('extra') or {}), 'worker_id': WORKER_ID}}

logger = WorkerAdapter(raw_logger, {'worker_id': WORKER_ID})

def update_job_history(task_id: str, status: str, error_message: str = None, start: bool = False, complete: bool = False, duration: float = None):
    try:
        from db_migration import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        if start:
            cur.execute("""
                UPDATE ingestion_history 
                SET status = %s, started_at = CURRENT_TIMESTAMP
                WHERE task_id = %s
            """, (status, task_id))
        elif complete:
            cur.execute("""
                UPDATE ingestion_history 
                SET status = %s, completed_at = CURRENT_TIMESTAMP, duration_seconds = %s, error_message = %s
                WHERE task_id = %s
            """, (status, duration, error_message, task_id))
        else:
            cur.execute("""
                UPDATE ingestion_history 
                SET status = %s, error_message = %s
                WHERE task_id = %s
            """, (status, error_message, task_id))
            
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(
            f"Failed to update ingestion history for task {task_id}: {e}",
            extra={"worker_id": WORKER_ID}
        )

def process_ingestion_job(metadata_dict: dict, pipeline_type: str):
    """
    Main worker function executed by RQ.
    Pipeline: Route -> Extract -> Transform -> Enrich -> Store
    """
    import time
    start_time = time.perf_counter()
    
    metadata = TaskMetadata(**metadata_dict)
    metadata.worker_id = WORKER_ID
    
    # Custom logger with worker_id
    extra = {"worker_id": WORKER_ID}
    logger.info(f"Starting ingestion job: {metadata.task_id} | Pipeline: {pipeline_type}", extra=extra)
    
    # Mark as processing
    update_job_history(metadata.task_id, status='processing', start=True)
    
    try:
        # The DataIngester now handles the Elite Pipeline internally (Extract -> Transform -> Enrich -> Store)
        # We pass the metadata to it for lineage tracking.
        ingester = DataIngester(task_metadata=metadata.dict())
        
        # Determine title from file path
        title = os.path.basename(metadata.source_file)
        
        ingester.process_input(
            input_path=metadata.source_file,
            source_type=metadata.source_type,
            title=title,
            sectors="General",
            summary="Automated Elite Engine Processing",
            department=metadata.department,
            source_url=metadata.source_url
        )
        
        duration = round(time.perf_counter() - start_time, 2)
        logger.info(f"Job {metadata.task_id} COMPLETED successfully in {duration}s.", extra=extra)
        # Mark as succeeded
        update_job_history(metadata.task_id, status='succeeded', complete=True, duration=duration)
        return {"status": "success", "task_id": metadata.task_id}

    except Exception as e:
        duration = round(time.perf_counter() - start_time, 2)
        logger.error(f"Job {metadata.task_id} FAILED after {duration}s: {str(e)}", exc_info=True, extra=extra)
        # Mark as failed
        update_job_history(metadata.task_id, status='failed', error_message=str(e), complete=True, duration=duration)
        # RQ handles the retry/failure based on the raised exception
        raise e

if __name__ == "__main__":
    # This script is usually run via `rq worker ingestion`
    print(f"Elite Worker {WORKER_ID} is online and ready for tasks.")
