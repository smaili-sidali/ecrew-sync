# eCrew Portal Reconnaissance — COMPLETE

Source: `C:\Users\PC\Downloads\ecrew.airalgerie.dz.har` (captured 31/07/2026).

## Login flow (reverse-engineered from HAR)

The portal uses **header-based session auth — NO cookies at all**.

1. `GET https://ecrew.airalgerie.dz/ecrew` → login page HTML.
   Extract from it:
   - `__RequestVerificationToken` hidden input value
   - `winObj:"<128 hex chars>"` from the inline script
   - Login URL token: `EcallUrlAsync("/ecrew/Login/<token>", ...)`
2. Generate a client-side session id: `eCrewHeader` = random v4-style UUID
   (site JS: `UID()` = `([1e3] + -1e3 + -4e3 + -8e3 + -1e11).replace(...)` — any
   random UUID with the same shape works, it is purely a client session id).
3. `POST https://ecrew.airalgerie.dz/ecrew/Login/<token>` with headers:
   - `Content-Type: application/json`
   - `eCrewHeader: <uuid>`
   - `RequestVerificationToken: <token from step 1>`
   Body (JSON):
   ```json
   {"crewid":"<crew id>","password":"<sha512 hex>","chk":"","cio":"",
    "alias":"","rad":"","winObj":"<from page>","hotp":""}
   ```
   - `password` = **SHA-512 hex digest** of the plain password (`hex_sha512`).
   - `crewid` = the plain crew id (a number, e.g. "35739").
4. Success = HTTP 200 + empty body. Failure markers in response text:
   - `"Invalid Credentials"` → bad login
   - a few specific long hashes → password-change modal or HOTP required
     (fail loudly; do NOT bypass).

## Post-login navigation

- `GET https://ecrew.airalgerie.dz/eCrew/Dashboard` → app shell (this HTML
  contains a NEW `__RequestVerificationToken`).
- `GET https://ecrew.airalgerie.dz/eCrew/Dashboard/HomeIndex?eCrewHeader=<uuid>`
  → the logged-in home view (has its own hidden token).
- Menu items map to `MenuCall('X')` → `POST /eCrew/Dashboard/GetMenu` with
  JSON `{"Menu":"X"}` → returns an HTML fragment injected into the page.
- **"My Schedule" = `A1`** (the roster page).

## Roster page (partially reverse-engineered — verify with a live capture)

- URL/endpoint: `POST /eCrew/Dashboard/GetMenu`, body `{"Menu":"A1"}`.
- **KNOWN**: the A1 response is an HTML fragment that embeds the duty data as a
  JSON-ish JS array assigned to a variable like `InitialSchedulerEvents`; the
  page hands it to DayPilot (`dp.events.list = InitialSchedulerEvents`).
  `backend/parser.py` parses that array (any `<name> = [...]` block is tried)
  and falls back to a `<table>` layout.
- Event object fields (from `eCrewDayPilot.js`):
  - `type` ∈ {Flight, Off, Standby, Training, Legal, Ground, Hotel, ...}
  - `resource` ∈ {"A" = own duty, "PUB" = published, crew ids}
  - `start` / `end` ISO datetimes; `text` label; `location` (port/route);
    `HotelNo`, `HotelInfo` for Hotel events; `ver`; event `id` is underscore
    separated, last segment often the flight/route code.
- **STILL UNVERIFIED**: the exact variable name/format of the array and the
  flight-number/airport field names inside real events. Run
  `python -m cli.main login-test` once logged in with "My Schedule" open
  (or after the scheduler syncs) and diff `debug_roster_view.html` against
  `tests/fixtures/sample_roster.html`, then adjust `parser.py` selectors.
- Detail popup endpoint (for extended duty info) is
  `POST /eCrew/DutyDetails/Retrieve` → `GET /eCrew/DutyDetails/Index?dt=...`.
- `dp.dynamicLoading` only applies to the Training Bidding view; the main
  schedule is fully embedded per page load.

## Headers used by every XHR (site JS)

```js
this.setRequestHeader('eCrewHeader', window.sessionStorage.eCrewTabID);
this.setRequestHeader('RequestVerificationToken', $('input[name="__RequestVerificationToken"]').val());
```

So: same UUID for the whole session; the verification token is refreshed
with each new page load (login page → Dashboard → HomeIndex → GetMenu view).

## Quirks

- No CAPTCHA, no cookies, no MFA in the current flow (HOTP field exists but
  is empty; if HOTP/2FA ever appears, fail loudly).
- `requestverificationtoken` rotates on every page; always take it from the
  latest HTML page loaded.
- Site is behind Cloudflare (headers seen: cf-ray, cf-cache-status DYNAMIC).
- Sample (anonymized) login request id: `35739` (crew id format is numeric).
