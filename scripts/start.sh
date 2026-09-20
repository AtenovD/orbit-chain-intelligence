#!/bin/sh
# Build the UI, prepare a local SQLite database and start Orbit on macOS or Linux.
set -eu
cd "$(dirname "$0")/.."

(cd frontend && npm install && npm run build)
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python scripts/bootstrap_db.py
echo "Orbit: http://127.0.0.1:8000  (API docs: /docs)"
exec python -m uvicorn orchestrator.main:app --host 127.0.0.1 --port 8000
