#!/usr/bin/env bash
# One-command deployment for eCrew Sync (Linux/macOS).
# Usage: ./deploy.sh   (optionally: ./deploy.sh https)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "No .env found — creating from .env.example."
    cp .env.example .env
    echo ">> Edit .env and fill in ECREW_USERNAME / ECREW_PASSWORD, then run:"
    echo "   ./deploy.sh"
    exit 1
fi

if [ "${1:-}" = "https" ]; then
    echo "Starting with HTTPS (Caddy reverse proxy)..."
    docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml up -d --build
else
    docker compose up -d --build
fi

docker compose ps
echo ""
echo "===================================================="
echo " eCrew Sync is running"
echo " Local:  http://localhost:8000"
if [ "${1:-}" = "https" ]; then
    echo " HTTPS:  https://$(grep -oP '(?<=tls )\S+' deploy/Caddyfile 2>/dev/null || echo 'your-domain')"
fi
echo "===================================================="
