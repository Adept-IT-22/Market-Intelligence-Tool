import os
import logging
import psycopg2
import redis
from qdrant_client import QdrantClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
logger = logging.getLogger(__name__)

class MonitoringSystem:
    """Health checks and system-wide monitoring for the Data Engine."""
    
    @staticmethod
    def check_postgres():
        try:
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                database=os.getenv("POSTGRES_DB", "market_intelligence"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "your_password_here"),
                connect_timeout=3
            )
            conn.close()
            return {"status": "healthy", "service": "postgresql"}
        except Exception as e:
            logger.error(f"Postgres health check failed: {e}")
            return {"status": "unhealthy", "service": "postgresql", "error": str(e)}

    @staticmethod
    def check_redis():
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=os.getenv("REDIS_PORT", "6379"),
                password=os.getenv("REDIS_PASSWORD"),
                socket_timeout=3
            )
            r.ping()
            return {"status": "healthy", "service": "redis"}
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "unhealthy", "service": "redis", "error": str(e)}

    @staticmethod
    def check_qdrant():
        try:
            client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", 7000)),
                timeout=3
            )
            client.get_collections()
            return {"status": "healthy", "service": "qdrant"}
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return {"status": "unhealthy", "service": "qdrant", "error": str(e)}

    @staticmethod
    def get_queue_stats():
        """Get Redis queue depth and worker info."""
        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD"),
                socket_timeout=3
            )
            from rq import Queue
            from rq.registry import FailedJobRegistry, StartedJobRegistry
            q = Queue(connection=r)
            failed_reg = FailedJobRegistry(queue=q)
            started_reg = StartedJobRegistry(queue=q)
            return {
                "queued": len(q),
                "active": len(started_reg),
                "failed": len(failed_reg),
            }
        except Exception as e:
            logger.warning(f"Queue stats unavailable: {e}")
            return {"queued": 0, "active": 0, "failed": 0, "error": str(e)}

    @staticmethod
    def get_storage_stats():
        """Get Qdrant collection sizes and DB file size."""
        stats = {"collections": [], "total_vectors": 0, "db_size_mb": 0}
        try:
            client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", 7000)),
                timeout=5
            )
            collections = client.get_collections().collections
            total = 0
            for col in collections:
                info = client.get_collection(col.name)
                count = info.points_count or 0
                total += count
                stats["collections"].append({
                    "name": col.name,
                    "points": count,
                    "status": str(info.status)
                })
            stats["total_vectors"] = total
        except Exception as e:
            logger.warning(f"Storage stats unavailable: {e}")
            stats["error"] = str(e)
        
        # DB file size
        db_path = os.getenv("DATABASE_PATH", os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "DB", "market-intelligence.db"
        ))
        try:
            if os.path.exists(db_path):
                stats["db_size_mb"] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        except Exception:
            pass
        
        return stats

    def get_system_health(self):
        return {
            "postgres": self.check_postgres(),
            "redis": self.check_redis(),
            "qdrant": self.check_qdrant(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_admin_stats(self):
        """Combined stats endpoint for admin dashboard."""
        return {
            "health": self.get_system_health(),
            "queue": self.get_queue_stats(),
            "storage": self.get_storage_stats(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

if __name__ == "__main__":
    mon = MonitoringSystem()
    print(mon.get_admin_stats())
