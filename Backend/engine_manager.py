import os
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import redis
from rq import Queue, Retry
from ratelimit import limits, sleep_and_retry

# Configure logging
logger = logging.getLogger(__name__)

# --- Schemas ---

class TaskMetadata(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    source_type: str
    department: str = "General"
    worker_id: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.now)
    source_url: Optional[str] = None

class DataRecord(BaseModel):
    metadata: TaskMetadata
    raw_data: Dict[str, Any]
    transformed_data: Optional[Dict[str, Any]] = None
    enrichment: Optional[Dict[str, Any]] = None

# --- Engine Components ---

class DataRouter:
    """Routes incoming files to the appropriate pipeline."""
    
    @staticmethod
    def get_pipeline(file_ext: str, source_type: str) -> str:
        ext = file_ext.lower().strip('.')
        
        if ext in ['csv', 'xlsx', 'xls'] or source_type == 'structured':
            return "structured_pipeline"
        elif ext in ['pdf', 'docx', 'pptx', 'md', 'txt'] or source_type == 'rag':
            return "rag_pipeline"
        elif ext in ['json', 'log'] or source_type == 'analytics':
            return "analytics_pipeline"
        elif ext in ['png', 'jpg', 'jpeg', 'webp']:
            return "vision_pipeline"
        
        return "default_pipeline"

class DataTransformer:
    """ETL Layer: Cleaning, Validation, and Standardization."""
    
    def transform(self, raw_data: Dict[str, Any], pipeline_type: str) -> Dict[str, Any]:
        if pipeline_type == "structured_pipeline":
            return self._transform_structured(raw_data)
        elif pipeline_type == "analytics_pipeline":
            return self._transform_analytics(raw_data)
        return raw_data

    def _transform_structured(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Example cleaning: strip whitespace, handle nulls
        clean_data = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        # Standardize phone numbers, dates, etc.
        return clean_data

    def _transform_analytics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Log parsing logic here
        return data

class AIEnricher:
    """AI Layer: Sentiment, Classification, and Metadata Generation."""
    
    def __init__(self, google_api_key: Optional[str] = None, groq_api_key: Optional[str] = None):
        self.google_api_key = google_api_key
        self.groq_api_key = groq_api_key

    @sleep_and_retry
    @limits(calls=15, period=60)  # Example: 15 calls per minute
    def enrich(self, text: str, context: str = "general") -> Dict[str, Any]:
        """Calls Gemini or Groq to enrich the data."""
        # TODO: Implement actual LLM calls here
        logger.info(f"Enriching data for context: {context}")
        return {
            "sentiment": "neutral",
            "classification": "uncategorized",
            "quality_score": 0.8,
            "summary": text[:100] + "..." if len(text) > 100 else text
        }

class EngineManager:
    """Central coordinator for the Elite Data Engine."""
    
    def __init__(self):
        self.router = DataRouter()
        self.transformer = DataTransformer()
        self.enricher = AIEnricher(
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            groq_api_key=os.getenv("GROQ_API_KEY")
        )
        
        # Redis connection for status and queue management
        redis_url = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}"
        self.redis = redis.from_url(redis_url)
        self.queue = Queue("ingestion", connection=self.redis)
        self.failed_queue = Queue("failed_jobs", connection=self.redis)

    def dispatch_task(self, file_path: str, source_type: str, department: str, source_url: Optional[str] = None, original_filename: Optional[str] = None):
        """Pushes a new ingestion task to the queue."""
        ext = os.path.splitext(file_path)[1]
        pipeline = self.router.get_pipeline(ext, source_type)
        
        metadata = TaskMetadata(
            source_file=file_path,
            source_type=source_type,
            department=department,
            source_url=source_url
        )
        
        # Insert a record in ingestion_history as 'queued'
        try:
            from db_migration import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            
            filename = os.path.basename(file_path)
            orig_name = original_filename or filename
            
            file_size_kb = 0.0
            if os.path.exists(file_path):
                file_size_kb = round(os.path.getsize(file_path) / 1024.0, 2)
                
            cur.execute("""
                INSERT INTO ingestion_history 
                (task_id, filename, original_filename, file_size_kb, department, source_url, pipeline_type, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', CURRENT_TIMESTAMP)
            """, (metadata.task_id, filename, orig_name, file_size_kb, department, source_url, pipeline))
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"Logged task {metadata.task_id} to ingestion_history table.")
        except Exception as db_err:
            logger.error(f"Failed to log task {metadata.task_id} to ingestion_history: {db_err}")
        
        # Push to RQ
        job = self.queue.enqueue(
            "worker.process_ingestion_job",
            args=(metadata.dict(), pipeline),
            job_id=metadata.task_id,
            retry=Retry(max=3)  # Built-in retry logic
        )
        
        logger.info(f"Dispatched task {metadata.task_id} to pipeline {pipeline}")
        return metadata.task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Retrieves task status from Redis."""
        job = self.queue.fetch_job(task_id) or self.failed_queue.fetch_job(task_id)
        if not job:
            return {"status": "not_found"}
        
        return {
            "task_id": task_id,
            "status": job.get_status(),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "exc_info": job.exc_info
        }
