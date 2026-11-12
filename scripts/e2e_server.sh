#!/bin/sh
# Starts the app against a throwaway SQLite database with demo data, for the browser tests.
# Run from the repository root after building the web app (web/dist).
set -e

PYTHON="${PYTHON:-python}"
PORT="${E2E_PORT:-8765}"

export DATABASE_URL="sqlite:///./e2e.db"
export APP_ENV="development"
export DEMO_MODE="true"
export ALLOW_DEMO_SEED="1"
export WEB_DIST_DIR="web/dist"

rm -f e2e.db
"$PYTHON" -m alembic upgrade head
"$PYTHON" -m app.scripts.seed_demo --yes
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
