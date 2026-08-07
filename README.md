<div align="center">

# ✈️ eCrew Sync

**Your Air Algérie roster, wherever you are.**

A self-hosted tool that logs into the **eCrew portal**, pulls your duty roster, and serves it as a **mobile PWA**, a **JSON API**, and a **calendar (`.ics`) export** — plus an **Android APK** build.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-ready-5A0FC8?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Android](https://img.shields.io/badge/Android-TWA%20APK-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Tests](https://img.shields.io/badge/tests-11%20passing-2ea44f?style=for-the-badge)

</div>

---

## ✨ Features

| | |
|---|---|
| 🔐 **Header-based session auth** | Reverse-engineered login (no cookies, no CAPTCHA), with cached sessions + auto re-login |
| 📅 **Roster parsing** | DayPilot roster fragments → structured duties (flight / off / standby / training / layover) |
| 📱 **Installable PWA** | Add to home screen on Android/iOS — dark mode, month navigation, live stats |
| 🤖 **Background sync** | Every 6 h, debounced, with change detection (writes nothing when nothing changed) |
| 🗓 **ICS calendar export** | One tap to add your roster to Google Calendar / Apple Calendar / Outlook |
| 📡 **JSON API** | `roster`, `sync`, `health`, `export.ics` endpoints |
| 📦 **Android APK** | Trusted Web Activity build (Bubblewrap) — a real launcher app, ~2 MB |
| 🐳 **One-command deploy** | Docker + Caddy HTTPS, or Render free tier |

---

## 🚀 Quick start (local)

```bash
cd ecrew-sync
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env              # fill in ECREW_USERNAME / ECREW_PASSWORD
python cli\main.py web              # or: uvicorn server.api:app --reload
```

Open `http://localhost:8000` on your phone's browser → **Add to Home Screen** to install as an app. 📱

---

## 🖥 CLI

| Command | What it does |
|---|---|
| `python cli\main.py sync` | One-shot login → fetch → parse → store |
| `python cli\main.py show --month 2026-08` | Print the roster to the console |
| `python cli\main.py export-ics out.ics` | Calendar export (`.ics`) |
| `python cli\main.py login-test` | Live login + fetch, saves the raw HTML for debugging |
| `python cli\main.py web` | Start the PWA server |

---

## 🧠 How it works

```
┌──────────┐   POST /ecrew/Login/<token>   ┌────────────────┐
│          │ ◄──────────────────────────── │  backend/      │
│  eCrew   │                               │  ├ auth.py     │
│  portal  │                               │  ├ fetch.py    │
│          │   POST /eCrew/Dashboard/      │  ├ parser.py   │  DayPilot events
│          │   GetMenu {"Menu":"A1"}       │  │             │  → DutyEntry
│          │ ────────────────────────────► │  ├ store.py    │  roster.json + diff
│          │                               │  └ export.py   │  .ics calendar
└──────────┘                               └──────┬───────┘
                                                  │
                     ┌───────────┐  ┌─────────────▼──────────┐
                     │  PWA app  │  │  FastAPI + scheduler   │
                     │ (frontend)│ ◄┤  server/api.py         │
                     └───────────┘  └────────────────────────┘
```

> ℹ️ The portal authenticates with **no cookies at all** — a client-generated `eCrewHeader` UUID plus a rotating `RequestVerificationToken`. Full reverse-engineering notes live in [`NOTES.md`](NOTES.md).

---

## 📡 API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Service + sync status, last sync time |
| `/api/roster?month=2026-08` | GET | Stored roster (optionally filtered by month) |
| `/api/sync` | POST | Trigger a background sync now |
| `/api/export.ics` | GET | Download the roster as a calendar file |
| `/` | GET | The PWA itself |

---

## 🚢 Deploy

### 🐳 One command (any server with Docker)

```bash
# 1. On the server, get the repo:
git clone https://github.com/smaili-sidali/ecrew-sync
cd ecrew-sync

# 2. First run only — creates .env from template, tells you to fill it in:
./deploy.sh                    # Linux/macOS
# or
.\deploy.ps1                   # Windows

# 3. After filling .env:
./deploy.sh                    # build + start + healthcheck
```

- App: `http://localhost:8000`
- Data (`roster.json`, session) persists in `./data/`
- Auto-restarts on failure / reboot (`restart: unless-stopped`)

**🔒 HTTPS (optional, needs a domain):**
1. Set your domain in `deploy/Caddyfile` and point DNS at the server.
2. `./deploy.sh https` — Caddy obtains Let's Encrypt certs automatically.

### ☁️ Render (free tier, zero setup)

1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → connect the repo.
3. Render detects `render.yaml`, builds the Docker image, and asks for
   `ECREW_USERNAME` / `ECREW_PASSWORD` (secrets).
4. Done — HTTPS URL provided automatically.

### ⚙️ Manual (no Docker)

```bash
pip install -r requirements.txt
python -m uvicorn server.api:app --host 0.0.0.0 --port 8000
```

---

## 📱 Android app (TWA / APK)

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

> ℹ️ The APK just wraps the website — it doesn't need the backend's parser.
> Data comes from your server, which parses the roster fragment
> (`backend/parser.py`) into `roster.json`. The parser targets the
> reverse-engineered DayPilot contract in `NOTES.md`; run `python -m cli.main
> login-test` once and diff `debug_roster_view.html` against
> `tests/fixtures/sample_roster.html` to confirm the selectors match the live
> portal before relying on it.

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

### 📝 TWA notes

- The APK signs with `twa/android.keystore` — **never commit it** (already
  gitignored). `assetlinks.json` is tied to that signing key; regenerate it
  only if you create a new keystore.
- `enableNotifications` is off: the roster syncs from the server; there is no
  push. Pull-to-refresh or the Sync button fetch the latest store.
- Debug APKs (signed with the default debug key) live under `app-debug.apk`
  and will NOT pass the digital-asset-link verification until you follow the
  steps above.

---

## 🧪 Testing

```bash
python -m pytest tests/ -q        # unit tests (parser, export)
python -m cli.main login-test     # live login + fetch; saves debug_roster_view.html
python -m cli.main web            # run the PWA locally (no credentials needed)
```

---

## 🗂 Project layout

```
ecrew-sync/
├── backend/           # core logic: auth, fetch, parser, store, export
│   ├── auth.py        #   header-session login (SHA-512, token rotation)
│   ├── fetch.py       #   roster fetch (GetMenu A1) + session probing
│   ├── parser.py      #   DayPilot fragment → DutyEntry
│   ├── store.py       #   roster.json + change diffing
│   └── export.py      #   .ics calendar generation
├── server/            # FastAPI + background scheduler
│   ├── api.py
│   └── scheduler.py
├── frontend/static/   # PWA: HTML/CSS/JS, manifest, service worker, icons
├── cli/               # typer CLI (sync / show / export-ics / web)
├── tests/             # unit tests + HTML fixtures
├── deploy/            # Dockerfile, compose, Caddy HTTPS
├── twa/               # Android TWA config (Bubblewrap)
├── deploy.sh / deploy.ps1    # one-command deployment
├── docker-compose.yml / render.yaml
├── NOTES.md           # reverse-engineering recon notes
└── .env.example       # credential template (never commit .env!)
```

---

## 🔒 Privacy & security

- **Your credentials never leave your machine** — they're read from `.env`
  and only sent to `ecrew.airalgerie.dz`.
- `.env`, session caches, and keystores are **gitignored**; a leaked push is
  near-impossible by design.
- The tool **refuses** to bypass password-change or 2FA (HOTP) prompts — if the
  portal asks, it fails loudly and stops.

---

## 🔄 Updating

```bash
git up        # if you set the alias (add -A, commit, push)
# or manually:
git add -A && git commit -m "your change" && git push
```

Push often, stay lazy. 🛋

---

## 🗺 Roadmap

- [x] Login + session persistence
- [x] Roster fetch (GetMenu A1)
- [x] Parser (DayPilot events → duties) + table fallback
- [x] JSON store + diffing, background scheduler
- [x] PWA (installable, dark mode, month view)
- [x] ICS export
- [x] TWA scaffold (icons, manifest, `.well-known` wiring)
- [ ] Verify parser against a live roster capture (diff `debug_roster_view.html` vs fixture)
- [ ] Build & sign the APK (needs a JDK 17 + Android SDK machine)
- [ ] Push notifications on roster changes (when `enableNotifications` is on)

---

<div align="center">

Made with ☕ and a lot of `python -m cli.main login-test`.

**eCrew Sync** · local & private · [smaili-sidali/ecrew-sync](https://github.com/smaili-sidali/ecrew-sync)

</div>
