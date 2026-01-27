#!/usr/bin/env python3
"""
Test Qdrant Connection
This script verifies that the Qdrant connection is working properly.
"""

import os
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_qdrant_connection():
    """Test connection to Qdrant and verify collection exists."""
    
    # Load environment variables
    load_dotenv()
    
    # Get Qdrant configuration
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    collection_name = "adept_database"
    
    logger.info("=" * 60)
    logger.info("QDRANT CONNECTION TEST")
    logger.info("=" * 60)
    logger.info(f"Host: {qdrant_host}")
    logger.info(f"Port: {qdrant_port}")
    logger.info(f"Collection: {collection_name}")
    logger.info("=" * 60)
    
    try:
        # Initialize Qdrant client
        logger.info("🔌 Initializing Qdrant client...")
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        logger.info("✅ Qdrant client initialized successfully")
        
        # Test connection by getting collections
        logger.info("📋 Fetching collections list...")
        collections = client.get_collections()
        logger.info(f"✅ Successfully retrieved collections")
        logger.info(f"📦 Available collections: {[col.name for col in collections.collections]}")
        
        # Check if our collection exists
        collection_names = [col.name for col in collections.collections]
        if collection_name in collection_names:
            logger.info(f"✅ Collection '{collection_name}' exists!")
            
            # Get collection info
            logger.info(f"📊 Getting collection info...")
            collection_info = client.get_collection(collection_name)
            logger.info(f"   - Vectors count: {collection_info.points_count}")
            logger.info(f"   - Vector size: {collection_info.config.params.vectors.size}")
            logger.info(f"   - Distance: {collection_info.config.params.vectors.distance}")
            
            # Try a simple scroll to verify we can read data
            logger.info("📖 Testing data retrieval (scroll first 5 points)...")
            scroll_result = client.scroll(
                collection_name=collection_name,
                limit=5,
                with_payload=True,
                with_vectors=False
            )
            
            points, _ = scroll_result
            logger.info(f"✅ Retrieved {len(points)} sample points")
            
            if points:
                logger.info("📝 Sample point structure:")
                first_point = points[0]
                logger.info(f"   - Point ID: {first_point.id}")
                logger.info(f"   - Payload keys: {list(first_point.payload.keys()) if first_point.payload else 'None'}")
                
                # Show a sample of the payload
                if first_point.payload:
                    logger.info("   - Sample payload:")
                    for key, value in list(first_point.payload.items())[:3]:
                        value_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        logger.info(f"      {key}: {value_preview}")
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ ALL TESTS PASSED - Qdrant is working correctly!")
            logger.info("=" * 60)
            return True
            
        else:
            logger.error(f"❌ Collection '{collection_name}' NOT FOUND!")
            logger.error(f"Available collections: {collection_names}")
            logger.error("\n💡 TIP: You may need to run the data ingestion script first:")
            logger.error("   python ingest_data.py --input <your_file>")
            return False
            
    except ConnectionError as e:
        logger.error("=" * 60)
        logger.error("❌ CONNECTION ERROR")
        logger.error("=" * 60)
        logger.error(f"Error: {str(e)}")
        logger.error(f"\n💡 TROUBLESHOOTING:")
        logger.error(f"   1. Check if Qdrant is running: docker compose ps")
        logger.error(f"   2. Verify the connection details:")
        logger.error(f"      - Host: {qdrant_host}")
        logger.error(f"      - Port: {qdrant_port}")
        logger.error(f"   3. If using Docker, ensure you're connecting to the right host")
        logger.error(f"      - From host machine: use 'localhost'")
        logger.error(f"      - From Docker container: use service name 'qdrant'")
        return False
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ UNEXPECTED ERROR")
        logger.error("=" * 60)
        logger.exception(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    success = test_qdrant_connection()
    sys.exit(0 if success else 1)
