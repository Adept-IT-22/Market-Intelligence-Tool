#!/bin/bash
# Test Backend Connectivity from Frontend Container

echo "========================================"
echo "Testing Backend Connectivity"
echo "========================================"
echo ""

# Check actual port mappings
echo "📋 Current port mappings:"
sudo docker compose -f docker-compose.yml ps | grep -E "(frontend|backend)"

echo ""
echo "========================================"
echo "1️⃣ Testing backend from HOST machine"
echo "========================================"
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' | head -c 200
echo ""

echo ""
echo "========================================"
echo "2️⃣ Testing backend from FRONTEND container"
echo "========================================"
echo "Checking if frontend can reach backend:8000..."
sudo docker compose -f docker-compose.yml exec -T frontend sh -c "wget -q -O- --timeout=5 http://backend:8000/upload/limits 2>&1" || echo "❌ Failed to connect"

echo ""
echo "========================================"
echo "3️⃣ Checking nginx logs for errors"
echo "========================================"
sudo docker compose -f docker-compose.yml logs frontend --tail 20 | grep -i error || echo "No errors found in nginx logs"

echo ""
echo "========================================"
echo "4️⃣ Testing the /api proxy path"
echo "========================================"
echo "Testing: http://192.168.1.250:8080/api/upload/limits"
curl -s http://192.168.1.250:8080/api/upload/limits || echo "❌ API proxy not working"

echo ""
echo "========================================"
echo "Test completed!"
echo "========================================"
