FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Africa/Algiers

WORKDIR /app

# Install dependencies first for better layer caching.
# requirements.txt holds runtime deps only (no test tooling in the image).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY backend/   backend/
COPY server/    server/
COPY cli/       cli/
COPY frontend/  frontend/

# Persistent data directory (mounted as a volume).
ENV ECREW_DB_FILE=/data/roster.json \
    ECREW_COOKIE_FILE=/data/session_state.json

# Keep the image small and the build cache useful.
RUN mkdir -p /data \
    && useradd --create-home --uid 10001 ecrew \
    && chown -R ecrew:ecrew /app /data

USER ecrew

EXPOSE 8000

# /api/health reports sync errors in its body but always answers 200 while the
# process is alive, so a portal outage does not trigger a restart loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" || exit 1

# One worker on purpose: the background scheduler and its in-process lock are
# per-process. Multiple workers would each run their own 6-hourly sync.
CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
