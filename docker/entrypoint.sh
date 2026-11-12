#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting server on port ${PORT:-8000}..."
# Behind a reverse proxy, trust its X-Forwarded-* headers only from FORWARDED_ALLOW_IPS
# (default: localhost). The rate limiters rely on this to see the real client IP.
# Set WEB_CONCURRENCY to run several workers (use REDIS_URL so limits are shared).
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
