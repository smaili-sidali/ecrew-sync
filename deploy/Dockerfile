FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
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
RUN mkdir -p /data

# Run as non-root.
RUN useradd --create-home --uid 10001 ecrew && \
    chown -R ecrew:ecrew /app /data
USER ecrew

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" || exit 1

CMD ["uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8000"]
