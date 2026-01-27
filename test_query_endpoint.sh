#!/bin/bash
# Test the /query endpoint specifically

echo "========================================"
echo "Testing /query Endpoint"
echo "========================================"
echo ""

echo "🧪 Test 1: Simple query through nginx proxy (30s timeout)..."
curl -s -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Kenya?"}' \
  --max-time 30 | head -c 500

echo ""
echo ""

echo "========================================"
echo "🧪 Test 2: Checking backend logs for errors..."
echo "========================================"
sudo docker compose -f docker-compose.yml logs backend --tail 30

echo ""
echo "========================================"
echo "Test completed!"
echo "========================================"
