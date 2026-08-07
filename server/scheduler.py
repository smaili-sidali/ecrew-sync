"""Background sync scheduler — reuses a cached session when still valid,
debounces rapid triggers, and skips rewriting the store when nothing changed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DB_FILE = Path(os.environ.get("ECREW_DB_FILE", "roster.json"))
STATUS: dict = {
    "last_run": None,
    "last_error": None,
    "running": False,
    "auto_interval_h": 6,
    "last_content_hash": None,
}

# Debounce: don't re-run a sync if one finished less than this many seconds ago.
_MIN_GAP_SECONDS = 300
_last_finish_ts: float = 0.0
_scheduler = None


def _do_sync() -> None:
    global _last_finish_ts

    from backend import auth, fetch, parser, store

    STATUS["running"] = True
    STATUS["last_error"] = None

    try:
        load_dotenv()
        base_url = os.environ.get("ECREW_BASE_URL", "https://ecrew.airalgerie.dz/ecrew")
        cookie_file = Path(os.environ.get("ECREW_COOKIE_FILE", "session_state.json"))
        creds = auth.Credentials.from_env()

        session = auth.get_session(cookie_file)

        # Reuse an existing session id; only re-login if it's dead.
        if not fetch.is_session_alive(session):
            auth.login(session, creds.username, creds.password, base_url, cookie_file)

        # Try the roster fetch; re-login once on session expiry, then retry.
        try:
            html = fetch.get_roster_page(session)
        except fetch.SessionExpiredError:
            auth.login(session, creds.username, creds.password, base_url, cookie_file)
            html = fetch.get_roster_page(session)

        # Conditional store: skip if the raw HTML is unchanged since last sync.
        content_hash = hashlib.sha256(html.encode("utf-8", "replace")).hexdigest()
        if content_hash == STATUS.get("last_content_hash"):
            logger.info("Roster unchanged since last sync; skipping store write.")
        else:
            entries = parser.parse_roster(html)
            store.save(entries, DB_FILE)
            STATUS["last_content_hash"] = content_hash

        from datetime import datetime, timezone
        STATUS["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        STATUS["last_error"] = None
    except NotImplementedError as e:
        STATUS["last_error"] = f"Not ready: {e}"
    except Exception as exc:
        logger.exception("Sync failed")
        STATUS["last_error"] = str(exc)[:500]
    finally:
        _last_finish_ts = time.monotonic()
        STATUS["running"] = False


def trigger_sync() -> bool:
    """Run a sync now in a background thread. Returns True if a new run was
    actually scheduled (False if one is already running or we're inside the
    debounce window)."""
    if STATUS["running"]:
        return False
    if time.monotonic() - _last_finish_ts < _MIN_GAP_SECONDS and STATUS.get("last_run"):
        return False
    threading.Thread(target=_do_sync, daemon=True).start()
    return True


def get_sync_status() -> dict:
    return {
        "last_run": STATUS["last_run"],
        "running": STATUS["running"],
        "last_error": STATUS.get("last_error"),
        "min_gap_seconds": _MIN_GAP_SECONDS,
    }


def start_scheduler(interval_h: int = 6) -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(_do_sync, "interval", hours=interval_h, id="ecrew_sync")
        _scheduler.start()
        STATUS["auto_interval_h"] = interval_h
        logger.info("Scheduler started (every %dh)", interval_h)
    except ImportError:
        logger.warning("APScheduler not installed; background sync disabled.")
