#!/bin/bash
# Test Qdrant Connection from Docker Container

echo "========================================"
echo "Testing Qdrant Connection from Backend Container"
echo "========================================"
echo ""

# Check if containers are running
echo "📋 Checking container status..."
sudo docker compose -f docker-compose.yml ps

echo ""
echo "🧪 Running Qdrant connection test..."
echo ""

# Run the test script inside the backend container
sudo docker compose -f docker-compose.yml exec -T backend python test_qdrant_connection.py

echo ""
echo "========================================"
echo "Test completed!"
echo "========================================"
