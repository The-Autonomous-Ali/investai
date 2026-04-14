#!/bin/bash
URL="http://localhost:8000/api/agents/advice"
echo '{"query":"should I invest in IT stocks","amount":50000}' > /tmp/req.json
curl -v -X POST "$URL" -H "Content-Type: application/json" -d @/tmp/req.json 2>&1
