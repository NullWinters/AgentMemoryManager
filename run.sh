#!/bin/bash
pkill -f "uvicorn src.main:app" 2>/dev/null
sleep 0.5
exec .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8080
