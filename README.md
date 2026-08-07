# eCrew Sync

Self-hosted tool that logs into the Air Algérie eCrew portal, pulls the roster, and makes it available as a **responsive PWA** (installable on Android as an app), a JSON API, and an `.ics` calendar export.

## Quick start (local)

```bash
cd ecrew-sync
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env              # fill in ECREW_USERNAME / ECREW_PASSWORD
python cli\main.py web              # or: uvicorn server.api:app --reload
```

Open `http://localhost:8000` on your phone's browser → "Add to Home Screen" to install as an app.

## CLI

```bash
python cli\main.py sync                    # one-shot fetch + store
python cli\main.py show --month 2026-08    # print roster to console
python cli\main.py export-ics out.ics       # calendar export
python cli\main.py web                      # start the PWA server
```

## Deploy

### One command (any server with Docker)

```bash
# 1. On the server, get the repo:
git clone <your-repo-url>
cd ecrew-sync

# 2. First run only — creates .env from template, tells you to fill it in:
./deploy.sh                    # Linux/macOS
# or
.\deploy.ps1                   # Windows

# 3. After filling .env:
./deploy.sh                    # build + start + healthcheck
```

- App: `http://localhost:8000`
- Data (roster.json, session) persists in `./data/`
- Auto-restarts on failure / reboot (`restart: unless-stopped`)

**HTTPS (optional, needs a domain):**
1. Set your domain in `deploy/Caddyfile` and point DNS at the server.
2. `./deploy.sh https` — Caddy obtains Let's Encrypt certs automatically.

### Render (free tier, zero setup)
1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → connect the repo.
3. Render detects `render.yaml`, builds the Docker image, and asks for
   `ECREW_USERNAME` / `ECREW_PASSWORD` (secrets).
4. Done — HTTPS URL provided automatically.

### Manual (no Docker)
```bash
pip install -r requirements.txt
python -m uvicorn server.api:app --host 0.0.0.0 --port 8000
```

## Project layout

```
ecrew-sync/
├── backend/           ← auth, fetch, parser, store, export (core logic)
│   ├── auth.py
│   ├── fetch.py
│   ├── parser.py
│   ├── store.py
│   └── export.py
├── server/            ← FastAPI + background scheduler
│   ├── api.py
│   └── scheduler.py
├── frontend/          ← PWA (HTML/CSS/JS, manifest, service worker)
│   └── static/
│       ├── index.html
│       ├── app.js
│       ├── style.css
│       ├── manifest.json
│       ├── sw.js
│       └── icon.svg
├── cli/               ← CLI entrypoint (typer)
│   └── main.py
├── tests/
│   ├── fixtures/sample_roster.html
│   └── test_parser.py
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.https.yml   ← optional Caddy HTTPS
│   └── Caddyfile
├── deploy.sh / deploy.ps1         ← one-command deployment
├── docker-compose.yml             ← root-level, so `docker compose up` just works
├── .dockerignore
├── NOTES.md
├── .env.example
├── .gitignore
├── requirements.txt
└── render.yaml
```

## Testing

```bash
python -m cli.main login-test     # live login + fetch; saves debug_roster_view.html
python -m cli.main web            # run the PWA locally (no credentials needed)
python -m pytest tests/ -q        # unit tests
```

## Android app (TWA / APK)

The PWA is installable, and can also be wrapped into a real Android APK as a
**Trusted Web Activity** using Google's [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap).
The app is ~2 MB, installs a normal launcher icon, and opens your hosted PWA
with no browser chrome.

### Prerequisites (once)

- A deployed HTTPS domain for the app (the PWA *must* be served over HTTPS).
  Your Caddy/Render setup already provides this — install the PWA first as a
  sanity check, then continue.
- **JDK 17** (e.g. Adoptium Temurin or Android Studio's bundled JBR) and the
  **Android SDK** (`bubblewrap` can download a JDK for you, but needs the SDK).
- Node.js ≥ 18 (to run Bubblewrap).

Note: none of this needs the backend's `parse_roster()` — the APK just wraps
the website. Data comes from the server, which parses the roster fragment
(`backend/parser.py`) into `roster.json`. The parser targets the
reverse-engineered DayPilot contract in `NOTES.md`; run `python -m cli.main
login-test` once and diff `debug_roster_view.html` against
`tests/fixtures/sample_roster.html` to confirm the selectors match the live
portal before relying on it.

### Generate the APK

```bash
# 1. Install the CLI once
npm install -g @bubblewrap/cli

# 2. Generate the TWA project against your LIVE deployed manifest.
#    Replace the URL with your real domain.
npx @bubblewrap/cli init --manifest https://roster.example.com/manifest.json

# 3. Tweak twa/twa-manifest.json if needed (packageId, name, colors).
#    A starting template is committed at twa/twa-manifest.json.

# 4. Build → produces twa/app/build/outputs/.../app-release.apk
cd twa
npx @bubblewrap/cli build
```

### Verify the app→website handshake (required, once per signing key)

TWA only shows web content when Android can verify the APK owns the origin:

```bash
cd ..   # repo root
npx @bubblewrap/cli fingerprint list     # read SHA-256 of your signing key
# Pair it with the site, then generate the verifier file:
npx @bubblewrap/cli fingerprint add "release" <sha256-fingerprint> --manifest twa/twa-manifest.json
cp <generated assetlinks.json> frontend/static/.well-known/assetlinks.json
```

Then redeploy. The file is served at `/.well-known/assetlinks.json` (it is
already wired in — see `frontend/static/.well-known/README.md`). Verify with:

```bash
npx @bubblewrap/cli validate --location https://roster.example.com
```

When validation passes, `twa/app/build/outputs/apk/release/app-release.apk` is
a normal installable Android APK.

### Notes

- The APK signs with `twa/android.keystore` — **never commit it** (already
  gitignored). `assetlinks.json` is tied to that signing key; regenerate it
  only if you create a new keystore.
- `enableNotifications` is off: the roster syncs from the server; there is no
  push. Pull-to-refresh or the Sync button fetch the latest store.
- Debug APKs (signed with the default debug key) live under `app-debug.apk`
  and will NOT pass the digital-asset-link verification until you follow the
  steps above.