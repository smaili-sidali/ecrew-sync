"""Central configuration — the single source of truth for paths, URLs and secrets.

Why this module exists
----------------------
The CLI, the API server and the scheduler each used to read the environment
themselves and each carried its *own* default. Two real bugs came out of that:

1. ``server/api.py`` and ``server/scheduler.py`` resolved ``ECREW_DB_FILE`` at
   *module import* time, before ``load_dotenv()`` ever ran. Anyone relying on a
   local ``.env`` silently got ``roster.json`` instead. Docker hid the bug
   because the compose file exports real environment variables.
2. The CLI defaulted the session file to ``cookies.json`` while the scheduler
   defaulted to ``session_state.json``, so a CLI sync and the web server never
   shared a session and the CLI leaked a second session file.

Every accessor here is a *function*, not a module-level constant. Reading
lazily means ``load_dotenv()`` has always run by the time anyone asks, which
removes the import-order trap entirely.
"""

from __future__ import annotations

import os
from datetime import timedelta, timezone, tzinfo
from pathlib import Path

from dotenv import load_dotenv

# --- Defaults ------------------------------------------------------------- #
DEFAULT_BASE_URL = "https://ecrew.airalgerie.dz/ecrew"
DEFAULT_DB_FILE = "roster.json"
DEFAULT_SESSION_FILE = "session_state.json"

# Single source of truth for the version string.
#
# It used to be hardcoded in four places that drifted apart (pyproject 0.2.0,
# package.json 1.0.0, twa-manifest 1.0.0, the NOAA User-Agent claiming 2.0),
# so the API advertised a version nobody could map to an APK. pyproject.toml is
# the canonical file; tests/test_version_consistency.py fails if anything else
# disagrees. Override at runtime only if you really need to.
APP_VERSION = "2.5.0"

# Duty times arrive from the portal without an offset; they are portal-local.
DEFAULT_TZ = "Africa/Algiers"

# Algiers observes no DST (UTC+1 year-round). Used when the tz database is
# unavailable — notably on Windows images without the `tzdata` package.
_FALLBACK_TZ = timezone(timedelta(hours=1), name="Algiers")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}

_env_loaded = False


def _ensure_env() -> None:
    """Load .env exactly once, lazily."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv()
        _env_loaded = True


def _raw_env(name: str) -> str | None:
    _ensure_env()
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _str_env(name: str, default: str) -> str:
    return _raw_env(name) or default


def _int_env(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(_str_env(name, str(default))))
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _raw_env(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    return default


# --- Public accessors ----------------------------------------------------- #


def base_url() -> str:
    """eCrew portal base URL, without a trailing slash."""
    return _str_env("ECREW_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def app_version() -> str:
    """The one version string, shared by the API and the outgoing User-Agent.

    Sourced from ``APP_VERSION``, which is asserted to match pyproject.toml,
    package.json and twa/twa-manifest.json by the test suite.
    """
    return APP_VERSION


def db_file() -> Path:
    """Where the parsed roster JSON store lives."""
    return Path(_str_env("ECREW_DB_FILE", DEFAULT_DB_FILE))


def session_file() -> Path:
    """Where the cached ``eCrewHeader`` session id is kept between runs."""
    return Path(_str_env("ECREW_COOKIE_FILE", DEFAULT_SESSION_FILE))


def local_tz() -> tzinfo:
    """Timezone the portal's naive duty timestamps are expressed in."""
    name = _str_env("ECREW_TZ", DEFAULT_TZ)
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # pragma: no cover - missing tzdata
        return _FALLBACK_TZ


def sync_interval_h() -> int:
    """Hours between automatic background syncs."""
    return _int_env("ECREW_SYNC_INTERVAL_H", 6, minimum=1)


def sync_min_gap_s() -> int:
    """Minimum seconds between two syncs (debounce for manual triggers)."""
    return _int_env("ECREW_SYNC_MIN_GAP_S", 300, minimum=0)


def docs_enabled() -> bool:
    """Whether to expose /docs and /openapi.json.

    Off by default: a public deployment should not hand out a free map of the
    API. Set ECREW_ENABLE_DOCS=1 locally when you want the Swagger UI.
    """
    return _bool_env("ECREW_ENABLE_DOCS", False)


# --- Phase 3: security / observability ------------------------------------ #


def api_token() -> str | None:
    """Optional bearer token required on every /api route.

    Leave unset for a LAN-only deployment. **Set this before exposing the
    service to the internet** — the API serves your roster to anyone who can
    reach it, and /api/sync triggers a real portal login.
    """
    return _raw_env("ECREW_API_TOKEN")


def require_auth() -> bool:
    """Whether /api routes must present a valid token."""
    return api_token() is not None


def log_level() -> str:
    return _str_env("ECREW_LOG_LEVEL", "INFO").upper()


def log_json() -> bool:
    """Emit machine-readable JSON logs (for log shippers / container stdout)."""
    return _bool_env("ECREW_LOG_JSON", False)


def contract_check_enabled() -> bool:
    """Run the portal-contract canary after each fetch (Phase 0/1).

    On by default: it is the only thing standing between a silent portal
    change and a stale roster you find out about on the wrong morning.
    """
    return _bool_env("ECREW_CONTRACT_CHECK", True)


def contract_min_events() -> int:
    """Below this many duty-like events, treat the fragment as suspect.

    A real month has tens of duties. A threshold of 1 catches the lazy-loading
    case (container returned, no rows) without failing on a genuinely quiet
    period.
    """
    return _int_env("ECREW_CONTRACT_MIN_EVENTS", 2, minimum=1)


def webhook_url() -> str | None:
    """Optional HTTP endpoint notified when the roster changes or a sync fails.

    Point it at ntfy, a Telegram bot bridge, or your own endpoint. Sent as a
    JSON POST from a background thread; failures are logged, never raised.
    """
    return _raw_env("ECREW_WEBHOOK_URL")


def webhook_timeout_s() -> int:
    return _int_env("ECREW_WEBHOOK_TIMEOUT_S", 10, minimum=1)


def notify_on_change() -> bool:
    """Send a webhook only when the roster actually changed (not every sync)."""
    return _bool_env("ECREW_NOTIFY_ON_CHANGE", True)
