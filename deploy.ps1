# One-command deployment for eCrew Sync (Windows PowerShell).
# Usage: .\deploy.ps1   (optionally: .\deploy.ps1 -Https)
param([switch]$Https)

Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "No .env found - created from .env.example."
    Write-Host ">> Edit .env and fill in ECREW_USERNAME / ECREW_PASSWORD, then run:"
    Write-Host "   .\deploy.ps1"
    exit 1
}

if ($Https) {
    Write-Host "Starting with HTTPS (Caddy reverse proxy)..."
    docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml up -d --build
}
else {
    docker compose up -d --build
}

docker compose ps

Write-Host ""
Write-Host "===================================================="
Write-Host " eCrew Sync is running"
Write-Host " Local:  http://localhost:8000"
if ($Https) {
    $domain = (Select-String -Path "deploy\Caddyfile" -Pattern "(?<=tls )\S+").Matches.Value
    Write-Host " HTTPS:  https://$($domain ?? 'your-domain')"
}
Write-Host "===================================================="
