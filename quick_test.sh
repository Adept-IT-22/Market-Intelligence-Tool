#!/bin/bash
# Quick diagnostic for backend connectivity issue

echo "🔍 Checking docker-compose.yml port configuration..."
grep -A 2 "ports:" docker-compose.yml

echo ""
echo "🔍 Checking actual runtime port mappings..."
sudo docker compose -f docker-compose.yml ps

echo ""
echo "🧪 Testing backend directly (from host)..."
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' 2>&1 | head -c 300

echo ""
echo ""
echo "🧪 Testing backend through nginx proxy..."
curl -s http://localhost:8080/api/upload/limits 2>&1

echo ""
