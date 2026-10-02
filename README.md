?<div align="center">

# ✈️? eCrew Sync

**Your Air Algérie roster, wherever you are.**

A self-hosted tool that logs into the **eCrew portal**, pulls your duty roster, and serves it as a **mobile PWA**, a **JSON API**, and a **calendar (`.ics`) export** — plus an **Android APK** build.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-ready-5A0FC8?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Android](https://img.shields.io/badge/Android-TWA%20APK-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Tests](https://img.shields.io/badge/tests-142%20passing-2ea44f?style=for-the-badge)
![CI](https://img.shields.io/badge/CI-142%20tests%20+%20ruff-2ea44f?style=for-the-badge)

</div>

---

## ⚠️? Status: the portal contract is still unverified

The reverse-engineering in [`NOTES.md`](NOTES.md) is solid, but **the roster
payload shape has never been confirmed against the live portal.** Every test in
this repo runs against `tests/fixtures/sample_roster.html`, which is a
**synthetic** fixture modelled on the site's JavaScript contract — not a real
capture.

So the project ships with a **contract canary** that tells you *which* of the
plausible portal changes broke things, instead of a bare "no duties found":

| Status | Meaning | What to do |
|---|---|---|
| `ok` | Contract intact | Nothing |
| `lazy_loaded` | Container returned, no duty rows | Capture the follow-up XHR in DevTools → Network |
| `no_event_array` | The `name = [...]` array is gone | Re-run recon, update the parser |
| `unrecognised_fields` | Events found, but keys were renamed | Extend the alias lists in `parser._get()` |
| `suspiciously_few` | Fewer events than a real roster | Check for a truncated/paginated payload |

**Check it in ~5 minutes:**

```bash
python -m cli.main login-test
```

If it reports `contract intact`, the single highest-value next step is to
replace the synthetic fixture with that capture (anonymised) so the whole test
suite runs against reality.

---

## ✨ Features

| | |
|---|---|
| 🔐 **Header-based session auth** | Reverse-engineered login (no cookies, no CAPTCHA), with cached sessions + auto re-login |
| 📅 **Roster parsing** | DayPilot roster fragments → structured duties (flight / off / standby / training / layover) |
| 📱 **Installable PWA** | Add to home screen on Android/iOS — dark mode, month navigation, live stats |
| 🤖 **Background sync** | Every 6 h, debounced, with change detection (writes nothing when nothing changed) |
| 🗓 **Live calendar feed** | Subscribe once; edits update in place (stable UIDs, `LAST-MODIFIED`) |
| 🩺 **Contract canary** | Classifies portal drift instead of silently serving a stale roster |
| 🔔 **Webhook alerts** | Told when your roster changes, a sync fails, or the portal changes shape |
| 🔐 **Optional API token** | One env var locks down every endpoint (constant-time compare) |
| 📡 **JSON API** | `health`, `roster`, `sync`, `contract`, `calendar.ics`, `export.ics` |
| 🧾 **Structured logs** | One JSON object per line, ready for a log shipper |
| 📦 **Android APK** | Trusted Web Activity build (Bubblewrap) — a real launcher app, ~2 MB |
| 🐳 **One-command deploy** | Docker + Caddy HTTPS, or Render |

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
| `python cli\main.py login-test` | **Phase 0 check.** Fetch + diagnose whether the portal contract holds |
| `python cli\main.py verify` | Compare the live portal against your stored roster (read-only) |
| `python cli\main.py sync` | One-shot login → fetch → parse → store, reporting changes |
| `python cli\main.py show --month 2026-08` | Print the roster to the console |
| `python cli\main.py export-ics out.ics` | Calendar export (`.ics`) |
| `python cli\main.py token` | Generate a strong random `ECREW_API_TOKEN` |
| `python cli\main.py web` | Start the PWA server |

---

## 🧠 How it works

```
┌────────────┐   POST /ecrew/Login/<token>   ┌───────────────────┐
│          │ ◄──────────────────────────── │  backend/      │
│  eCrew   │                               │  ├ auth.py     │
│  portal  │                               │  ├ fetch.py    │
│          │   POST /eCrew/Dashboard/      │  ├ parser.py   │  DayPilot events
│          │   GetMenu {"Menu":"A1"}       │  │             │  → DutyEntry
│          │ ────────────────────────────► │  ├ store.py    │  roster.json + diff
│          │                               │  └ export.py   │  .ics calendar
└──────────┘                               └──────┬───────┘
                                                  │
                     ┌─────────────┐  ┌────────────────▼───────────┐
                     │  PWA app  │  │  FastAPI + scheduler   │
                     │ (frontend)│ ◄┤  server/api.py         │
                     └───────────┘  └────────────────────────┘
```

> ℹ️? The portal authenticates with **no cookies at all** — a client-generated `eCrewHeader` UUID plus a rotating `RequestVerificationToken`. Full reverse-engineering notes live in [`NOTES.md`](NOTES.md).

---

## 📡 API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Service + sync status, `roster_state` (no token needed) |
| `/api/roster?month=2026-08` | GET | Stored roster, optionally filtered by month |
| `/api/sync?force=1` | POST | Trigger a sync; `force` bypasses the debounce |
| `/api/calendar.ics` | GET | **Subscribable** calendar feed (stays current) |
| `/api/export.ics` | GET | One-shot `.ics` download |
| `/api/contract` | GET | Portal contract canary report (no token needed) |
| `/` | GET | The PWA itself |

> All routes except `/api/health` and `/api/contract` require
> `ECREW_API_TOKEN` when it is set. Send `Authorization: Bearer <token>` or
> `?token=<token>`.

---

## 📆 Subscribing to your calendar

`/api/export.ics` downloads a **snapshot** — static the moment you import it.
For a calendar that stays current, subscribe to the feed instead:

| App | How |
|---|---|
| Google Calendar | Settings → Other calendars → **From URL** → `webcal://your-host/api/calendar.ics` |
| Apple Calendar | File → New Calendar Subscription → `https://your-host/api/calendar.ics` |
| Outlook | Add calendar → Subscribe from web → same URL |

With `ECREW_API_TOKEN` set, append `?token=<your-token>` (calendar apps can't
send custom headers).

This works because of two properties built into the export:

- **Stable UIDs** — an edited duty *updates in place* instead of appearing twice.
- **`LAST-MODIFIED`** — lets the client tell "unchanged" from "needs refresh".

Then the Sync button becomes almost irrelevant for calendar users.

---

## 🔔 Getting told when things change

The app syncs unattended, so a silent failure is the dangerous kind. Set a
webhook and you'll hear about it:

```bash
ECREW_WEBHOOK_URL=https://ntfy.sh/my-private-topic
```

A JSON POST is sent when the roster changes, when a sync fails, and when the
contract canary detects drift. Failures are logged and swallowed — a dead
webhook can never break a sync.

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

### ☁️️ Render

1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → connect the repo.
3. Render detects `render.yaml`, builds the Docker image, and asks for
   `ECREW_USERNAME` / `ECREW_PASSWORD` (secrets).
4. Done — HTTPS URL provided automatically.

> ⚠️? `render.yaml` targets the **`starter`** plan, not `free`. Render's free tier
> has no persistent disk (so `roster.json` is lost on every deploy) and idles
> out after a few minutes, meaning a 6-hourly background sync would never fire.
> Switch `plan: free` and delete the `disk:` block if you only want on-demand
> syncs from the app.

**🔒 Before exposing it publicly:** the API is unauthenticated and serves your
roster to anyone who reaches the URL. Put it behind a private network, a VPN, or
Caddy basic auth.

### ⚙️? Manual (no Docker)

```bash
pip install -r requirements.txt
python -m uvicorn server.api:app --host 0.0.0.0 --port 8000
```

> Use a **single** worker. The background scheduler and its in-flight lock are
> per-process, so multiple workers would each run their own 6-hourly sync.

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

> ℹ️? The APK just wraps the website — it doesn't need the backend's parser.
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
pip install -r requirements-dev.txt
python -m pytest -q          # 142 tests across 9 suites
ruff check backend server cli tests
```

| Suite | Covers |
|---|---|
| `tests/test_parser.py` | DayPilot event array + `<table>` fallback |
| `tests/test_parser_contract.py` | Decoy arrays, bare JS keys, single quotes, unbalanced braces |
| `tests/test_store.py` | Atomic writes, corrupt-store recovery, diff correctness |
| `tests/test_export.py` | Timezone handling, all-day events, UID stability |
| `tests/test_config.py` | Env resolution, shared defaults, `app_base()` derivation |
| `tests/test_api.py` | Health, month validation, calendar feed, ICS, docs gating, token auth
| `tests/test_contract.py` | Contract canary: each portal-drift failure mode
| `tests/test_scheduler.py` | Drift protection, debounce, concurrency lock
| `tests/test_notify.py` | Webhook delivery, failure isolation, JSON logs |

Many of these exist because of bugs that were actually found and fixed —
see [Known bugs fixed](#known-bugs-fixed) below.

> The API tests need `httpx` (in `requirements-dev.txt`); they skip cleanly
> without it.

Run `python -m cli.main login-test` for a live end-to-end check against the
real portal — that is the only test that proves the contract itself.

---

## 🗂 Project layout

```
ecrew-sync/
├── backend/           # core logic: config, auth, fetch, parser, store, export
│   ├── config.py      #   single source of truth for all env/path resolution
│   ├── auth.py        #   header-session login (SHA-512, token rotation)
│   ├── fetch.py       #   roster fetch (GetMenu A1) + re-login on expiry
│   ├── parser.py      #   DayPilot fragment → DutyEntry (+ table fallback)
│   ├── store.py       #   atomic roster.json + change diffing
│   └── export.py      #   .ics calendar generation (timezone-correct)
├── server/            # FastAPI + background scheduler
│   ├── api.py         #   /api/health, /api/roster, /api/sync, /api/export.ics
│   └── scheduler.py   #   interval job, in-flight lock, change reporting
├── frontend/static/   # PWA: HTML/CSS/JS, manifest, service worker, icons
├── cli/               # typer CLI (login-test / sync / show / export-ics / web)
├── tests/             # 85 tests + HTML fixture
??? deploy/            # Dockerfile, compose, Caddy HTTPS
??? twa/               # Android TWA config (Bubblewrap)
├── .github/workflows/ # CI: ruff + pytest + gitignore assertions
├── pyproject.toml     # deps, pytest + ruff config
├── deploy.sh / deploy.ps1    # one-command deployment
├── docker-compose.yml / render.yaml
├── NOTES.md           # reverse-engineering recon notes
└── .env.example       # credential template (never commit .env!)
```

---

## 🔒 Privacy & security

- **Your credentials never leave your machine** — they're read from `.env`
  and only sent to `ecrew.airalgerie.dz`.
- **Never commit your roster or session.** `roster.json` and
  `session_state.json` contain real duty data and a live session UUID; both are
  gitignored, and CI asserts it on every push.
- **The API has no authentication.** Anyone who can reach your instance can read
  your roster and trigger syncs. That is fine on a LAN or behind a VPN, but if
  you expose it to the internet put it behind Caddy basic auth or a private
  network. `/docs` and `/openapi.json` are **off by default** for the same
  reason — set `ECREW_ENABLE_DOCS=1` only locally.
- **The tool refuses to bypass password-change or 2FA (HOTP) prompts** — if the
  portal asks, it fails loudly and stops. A non-empty login response body is
  treated as a contract change rather than a success.

---

## 🐛 Known bugs fixed

Each of these was a real defect found by testing, with a regression test that
now prevents it returning:

| Bug | Impact |
|---|---|
| `roster.json` / `session_state.json` not gitignored | `git add -A` would publish real duty data + a live session to a public repo |
| Naive times exported with a `Z` suffix | Every duty shifted **+1 h** in Google/Apple/Outlook calendar |
| `make_all_day()` floors in UTC | A 20 Aug day-off rendered as **19–21 Aug** |
| ICS UID built from `entry.raw` (includes portal `ver`) | A portal edit created **duplicate** calendar events |
| `store.save()` wrote in place, non-atomically | A crash left a truncated store that **500'd every read forever** |
| `store.load()` raised on a corrupt store | Same — one bad byte made the app unusable |
| `store.diff()` keyed on `(date, flight_number)` | An off→flight swap reported as **both** added *and* removed; change lost |
| `diff()` used set difference | Non-deterministic ordering between identical runs |
| `ECREW_*` read at import, before `load_dotenv()` | Local `.env` **silently ignored** (invisible in Docker) |
| CLI vs scheduler session-file defaults differed | Two session files; one leaked past `.gitignore` |
| `/api/roster?month=` unvalidated | Arbitrary string into the filter |
| Parser ranked candidate arrays by length | A 300-item **airport list** beat the 30-item roster |
| Bracket scanner ignored `//` and `/* */` | A stray bracket in a comment **truncated** the event block |
| Single-quoted JS unsupported | Common inline-script style parsed to **zero** duties |
| `on_event("startup")` | Deprecated FastAPI API |
| Sync race (`STATUS["running"]` check) | Two concurrent triggers → **two portal logins** |
| `NotImplementedError` caught in 4 places | Dead code; nothing ever raised it |
| `keyring` in requirements | Unused dependency |

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
- [x] Roster fetch (GetMenu A1) + transparent re-login on session expiry
- [x] Parser (DayPilot events → duties) + table fallback + decoy-array rejection
- [x] Atomic JSON store, correct diffing, background scheduler
- [x] PWA (installable, dark mode, month view, timezone-correct times)
- [x] ICS export (correct timezone, all-day handling, duplicate-free UIDs)
- [x] TWA scaffold (icons, manifest, `.well-known` wiring)
- [x] CI (142 tests + ruff + mypy) and a regression test per fixed bug
- [ ] **Verify the parser against a live roster capture** — run
      `python -m cli.main login-test` and diff `debug_roster_view.html` against
      `tests/fixtures/sample_roster.html`. *This is the blocking item.*
- [ ] Build & sign the APK (needs a JDK 17 + Android SDK machine)
- [ ] Push notifications on roster changes (when `enableNotifications` is on)
- [ ] Optional auth in front of the API for internet-facing deployments

---

<div align="center">

Made with ☕ and a lot of `python -m cli.main login-test`.

**eCrew Sync** · local & private · [smaili-sidali/ecrew-sync](https://github.com/smaili-sidali/ecrew-sync)

</div>
