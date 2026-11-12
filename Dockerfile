# Stage 1: Build the React web frontend bundle
FROM node:25-alpine AS web

WORKDIR /web

# Copy package descriptors first to leverage Docker layer caching
COPY web/package.json web/package-lock.json ./
RUN npm ci

# Copy the rest of the web application source code and compile
COPY web/ ./
RUN npm run build

# Stage 2: Production Python runtime
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Pick up Debian security fixes released since the base image was built (e.g. zlib)
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install runtime Python dependencies only, then drop build tooling the app does not need.
# setuptools and wheel bundle copies of other packages that scanners flag.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y setuptools wheel

# Copy backend application source code, Alembic migrations, and runtime scripts
COPY app/ /app/app/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini
COPY scripts/ /app/scripts/
COPY docker/ /app/docker/

# Copy compiled frontend from the web build stage
COPY --from=web /web/dist /app/web/dist
ENV WEB_DIST_DIR=/app/web/dist

# Create and switch to a non-root system user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /app/docker/entrypoint.sh

USER appuser

EXPOSE 8000

# Health check using Python's standard urllib (no curl needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request, sys; port = os.environ.get('PORT', '8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health').getcode() == 200 else 1)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
