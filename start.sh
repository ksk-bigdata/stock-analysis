#!/bin/bash
cd "$(dirname "$0")/backend"
echo "서버 시작: http://localhost:8000"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
