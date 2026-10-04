<div align="center">

# ✈️ eCrew Sync

**Your Air Algérie roster, wherever you are.**

A self-hosted tool that logs into the **eCrew portal**, pulls your duty roster, and serves it as a **mobile PWA**, a **JSON API**, and a **calendar (`.ics`) export** — plus an **Android APK** build.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-ready-5A0FC8?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Android](https://img.shields.io/badge/Android-Capacitor%20APK-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Tests](https://img.shields.io/badge/tests-231%20python%20%2B%2031%20JS-2ea44f?style=for-the-badge)
![CI](https://img.shields.io/badge/CI-pytest%20%2B%20node%20%2B%20ruff%20%2B%20mypy-2ea44f?style=for-the-badge)

</div>

---

## ⚠️ Status: the portal contract is still unverified

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
| 📡 **JSON API** | 14 endpoints — roster, sync, calendar, stats, crew, weather |
| 🧾 **Structured logs** | One JSON object per line, ready for a log shipper |
| 📦 **Android APK** | Capacitor standalone build — a real launcher app, ~4 MB |
| 🌦 **Live METAR/TAF weather** | Official NOAA feed, decoded, for any of the 90+ airports in the network |
| 🛬 **Real crew composition** | Cockpit + cabin for a given flight, read from the portal's DutyDetails view |
| 🛏 **Layover logistics** | Hotel, address, contact and map link per layover |
| 💶 **Per diem & FTL stats** | Block hours, flight-time limits, monthly allowances |
| 📋 **Licences & leave** | Medical/check expiry countdowns, leave balance and bidding history |
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
| `python cli\main.py stats` | Block hours, flight time and FTL compliance |
| `python cli\main.py layovers` | Hotels, addresses and contacts for your layovers |
| `python cli\main.py perdiem` | Monthly per-diem / mission allowance totals |
| `python cli\main.py licenses` | Licence & medical expiry countdowns |
| `python cli\main.py leave` | Leave balance, history and bidding requests |
| `python cli\main.py crew <flight>` | Real cockpit + cabin crew for one of your flights |
| `python cli\main.py weather ALG` | Live METAR/TAF, decoded |
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

> ℹ️ The portal authenticates with **no cookies at all** — a client-generated `eCrewHeader` UUID plus a rotating `RequestVerificationToken`. Full reverse-engineering notes live in [`NOTES.md`](NOTES.md).

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
| `/api/stats?month=` | GET | Block hours, flight time, FTL limits |
| `/api/layovers` | GET | Hotels, addresses, contacts, map links |
| `/api/perdiem?month=` | GET | Per-diem / mission allowance totals |
| `/api/licenses` | GET | Licence & medical expiry countdowns |
| `/api/leave` | GET | Leave balance, history, bidding requests |
| `/api/crew/{flight}` | GET | Real cockpit + cabin crew for one flight |
| `/api/weather/{code}` | GET | Live METAR/TAF for an IATA code (e.g. `ALG`) |
| `/api/airports` | GET | The 90+ airports in the Air Algérie network |
| `/` | GET | The PWA itself |

> All routes except `/api/health` and `/api/contract` require
> `ECREW_API_TOKEN` when it is set. Send `Authorization: Bearer <token>` or
> `?token=<token>`.
>
> ⚠️ `/api/crew/{flight}` and `/api/weather/{code}` reach out to the portal and
> to NOAA respectively. Keep the token set if you expose the service.

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

> ⚠️ `render.yaml` targets the **`starter`** plan, not `free`. Render's free tier
> has no persistent disk (so `roster.json` is lost on every deploy) and idles
> out after a few minutes, meaning a 6-hourly background sync would never fire.
> Switch `plan: free` and delete the `disk:` block if you only want on-demand
> syncs from the app.

**🔒 Before exposing it publicly:** the API is unauthenticated and serves your
roster to anyone who reaches the URL. Put it behind a private network, a VPN, or
Caddy basic auth.

### ⚙️ Manual (no Docker)

```bash
pip install -r requirements.txt
python -m uvicorn server.api:app --host 0.0.0.0 --port 8000
```

> Use a **single** worker. The background scheduler and its in-flight lock are
> per-process, so multiple workers would each run their own 6-hourly sync.

---

## 📱 Android app (Capacitor)

The Android app is a **Capacitor** build — it ships the PWA as real assets
inside the APK, so it syncs directly against the eCrew portal and works with
no server of your own. The app is ~4 MB and installs as a normal launcher icon.

> ℹ️ The app is **standalone**: `frontend/static/ecrew-core.js` re-implements the
> login, the DayPilot parser and the store in the browser, using Capacitor's
> native HTTP and cookie plugins (`CapacitorHttp` / `CapacitorCookies` are
> enabled in `capacitor.config.json`). The Python backend is *not* involved.

### Build the APK

```bash
npm install
npx cap sync android
cd android && ./gradlew assembleDebug
# → android/app/build/outputs/apk/debug/app-debug.apk  (~4 MB)
```

CI does this automatically on every push — see
`.github/workflows/build-apk.yml`, which runs on Node 22 + JDK 21 and uploads
`app-debug.apk` as a workflow artifact.

For a **release** build you need your own signing key; see the Android
`build.gradle` signing config. Never commit a keystore (already gitignored).

### 🧾 Two parsers, so both are tested

Because the app is standalone, the portal contract is parsed twice:

| Path | Parser | Tests |
|---|---|---|
| Server / PWA | `backend/parser.py` | `tests/test_parser*.py` + the contract canary |
| Android APK | `frontend/static/ecrew-core.js` | `frontend/static/ecrew-core.test.js` (`npm test`) |

Both score candidate arrays by *duty-likeness* rather than array length, so a
longer decoy array (airports, legend) can't displace the real roster. If you
change one parser, change the other — and run both suites.

### 📝 Capacitor notes

- `CapacitorHttp` + `CapacitorCookies` are enabled because the portal uses
  header-based session auth; the native HTTP client is what makes the session
  and the `Another active session` recovery work inside the WebView.
- Debug APKs are signed with the standard Android debug key, so they install
  over each other but are not distributable as-is.
- Built APKs land in `android/app/build/outputs/apk/`; `dist-apk/` holds
  archived named builds and is gitignored.
- The older **TWA/Bubblewrap** scaffold is still in `twa/` for reference, but it
  is *not* the shipping pipeline — it only wrapped a hosted URL, which meant
  the phone needed your server to be online.

---

## 🧪 Testing

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 231 tests across 14 suites
ruff check backend server cli tests
mypy                         # type check
npm test                     # 31 tests for the standalone Android engine
```

**Both suites are hermetic** — no test touches the network. Anything that would
(weather, portal calls) is mocked, so a slow NOAA endpoint can't turn into a
random red build.

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
| `tests/test_auth.py` | Header-session login, SHA-512, token rotation |
| `tests/test_conflict_error_page.py` | The portal's "Another active session" HTML page |
| `tests/test_session_conflict_detection.py` | Conflict vs. ordinary page discrimination |
| `tests/test_duty_crew.py` | DutyDetails crew parsing |
| `tests/test_enriched_modules.py` | Weather, layovers, per diem, licences, leave, stats |
| `tests/test_version_consistency.py` | One version string across all manifests |
| `frontend/static/ecrew-core.test.js` | The standalone JS engine: parser, tokens, ICS |

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
├── backend/           # core logic
│   ├── config.py      #   single source of truth for env, paths and version
│   ├── auth.py        #   header-session login (SHA-512, token rotation)
│   ├── fetch.py       #   roster fetch (GetMenu A1) + re-login on expiry
│   ├── parser.py      #   DayPilot fragment → DutyEntry (+ table fallback)
│   ├── store.py       #   atomic roster.json + change diffing
│   ├── export.py      #   .ics calendar generation (timezone-correct)
│   ├── contract.py    #   portal-drift canary
│   ├── duty_details.py#   real crew composition from the portal
│   ├── weather.py     #   METAR/TAF + the 90+ airport network map
│   ├── layovers.py    #   hotel / layover logistics
│   ├── stats.py       #   block hours + FTL limits
│   ├── perdiem.py     #   mission allowances
│   ├── training.py    #   licence & medical expiry tracking
│   └── leave.py       #   leave balance, history, bidding
├── server/            # FastAPI + background scheduler
│   ├── api.py         #   the 14 /api routes
│   ├── scheduler.py   #   interval job, in-flight lock, change reporting
│   ├── auth_dep.py    #   optional bearer-token gate
│   └── logging_setup.py
├── frontend/static/   # PWA + standalone engine
│   ├── index.html / style.css / app.js
│   ├── ecrew-core.js  #   standalone JS engine (login, parser, ICS)
│   ├── ecrew-core.test.js  # its 31 tests (npm test)
│   ├── sw.js / manifest.json / icons/
│   └── .well-known/    #  assetlinks.json for the TWA fallback path
├── cli/               # typer CLI (14 commands)
├── tests/             # 231 tests + HTML fixtures
├── android/           # Capacitor Android project (the shipping APK)
├── twa/               # legacy Bubblewrap scaffold (reference only)
├── deploy/            # Dockerfile, compose, Caddy HTTPS
├── .github/workflows/ # CI (pytest + node + ruff + mypy) and build-apk.yml
├── pyproject.toml     # deps, pytest + ruff + mypy config
├── capacitor.config.json
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
  gitignored, and CI asserts it on every push. `leave.json` and
  `qualifications.json` (leave history, bidding requests, seniority, medical and
  licence expiry dates) are gitignored for the same reason — both modules seed
  themselves from the defaults in `backend/leave.py` and
  `backend/training.py`, so nothing is lost.
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
| `logger.warning("... %e", e)` in `weather.py` | `%e` isn't a logging specifier → `TypeError` inside the `except` turned a NOAA timeout into a **500** |
| `/api/weather/` hit the live network in tests | A slow NOAA endpoint made CI fail at random; hid the bug above |
| JS `generateICS` emitted `DTEND` == `DTSTART` | RFC 5545 `DTEND` is exclusive → every **all-day duty was zero-length** and vanished from the calendar |
| JS `parseRosterHtml` ranked arrays by length | The same decoy-array bug the Python parser had already fixed — a longer airport list won on the phone |
| Version string hardcoded in 4 files (0.2.0 / 1.0.0 / 1.0.0 / "2.0") | The API advertised a version that matched no shipped APK |

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
- [x] Live METAR/TAF weather + the 90+ airport network map
- [x] Real crew composition per flight (portal DutyDetails)
- [x] Layovers, per diem, FTL stats, licences & leave tracking
- [x] Capacitor Android app (standalone — syncs with no server)
- [x] Hermetic test suites: 231 Python + 31 JS, plus ruff + mypy in CI
- [x] A single version string, asserted across every manifest
- [ ] **Verify the parser against a live roster capture** — run
      `python -m cli.main login-test` and diff `debug_roster_view.html` against
      `tests/fixtures/sample_roster.html`. *This is the blocking item, and it
      applies to `ecrew-core.js` as much as to `backend/parser.py`.*
- [ ] Release-sign the APK (needs your own keystore)
- [ ] Push notifications on roster changes
- [ ] Optional auth in front of the API for internet-facing deployments
- [ ] Retire the legacy `twa/` Bubblewrap scaffold

---

<div align="center">

Made with ☕ and a lot of `python -m cli.main login-test`.

**eCrew Sync** · local & private · [smaili-sidali/ecrew-sync](https://github.com/smaili-sidali/ecrew-sync)

</div>
