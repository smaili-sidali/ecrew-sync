"""Background sync scheduler.

Concurrency model
-----------------
FastAPI runs sync endpoints on a threadpool and the APScheduler job fires on its
own thread, so ``_do_sync`` can genuinely be entered twice at once. A plain
``STATUS["running"]`` check is a read-then-write race: two triggers arriving in
the same window both see ``False`` and both start a login. A single
``threading.Lock`` acquired non-blocking makes "is a sync already in flight?"
atomic.

Status is exposed through ``get_sync_status()`` for ``/api/health``.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime, timezone

from backend import config
from backend import notify as backend_notify

logger = logging.getLogger(__name__)


class ContractDriftError(RuntimeError):
    """The fetched fragment no longer matches the parser's expectations.

    Raised *after* the diagnosis is recorded, so the previous good roster stays
    on disk rather than being replaced with a suspect one.
    """


# Guards concurrent sync attempts. Held for the duration of a sync.
#
# Two layers, deliberately:
#   1. ``_inflight`` — a plain boolean set *synchronously* in trigger_sync()
#      before the thread starts. Without it there is a window between spawning
#      the thread and the thread setting STATUS["running"], during which a
#      second trigger (or the APScheduler job) can start a duplicate login.
#   2. ``_lock`` — the mutex _do_sync() holds for its whole body, so even if
#      something bypasses trigger_sync(), only one sync runs at a time.
_inflight = threading.Event()
_lock = threading.Lock()

STATUS: dict = {
    "last_run": None,
    "last_error": None,
    "running": False,
    "auto_interval_h": 6,
    "last_content_hash": None,
    "last_change": None,
    "contract": None,
}

# Timestamp of the last *finished* sync, used for debouncing manual triggers.
_last_finish_ts: float = 0.0
_scheduler = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _do_sync() -> None:
    """Run one full sync: login -> fetch -> parse -> store.

    Safe to call from multiple threads; a second concurrent caller returns
    immediately rather than duplicating portal logins.
    """
    global _last_finish_ts

    if not _lock.acquire(blocking=False):
        logger.info("A sync is already in progress; skipping this trigger.")
        return

    from backend import auth, contract, fetch, parser, store

    STATUS["running"] = True
    STATUS["last_error"] = None
    try:
        base_url = config.base_url()
        cookie_file = config.session_file()
        db_file = config.db_file()
        creds = auth.Credentials.from_env()

        session = auth.get_session(cookie_file)

        # Reuse an existing session id; only re-login if it's dead.
        if not fetch.is_session_alive(session):
            auth.login(session, creds.username, creds.password, base_url, cookie_file)

        # fetch_with_relogin handles a mid-flight session expiry + retry.
        html = fetch.fetch_with_relogin(
            session, creds.username, creds.password, base_url, cookie_file
        )

        # Phase 0/1: classify the fragment BEFORE trusting it. This turns a
        # silent portal change into a loud, actionable diagnosis.
        report = contract.check_fragment(html)
        contract.raise_if_broken(report)
        STATUS["contract"] = report.to_dict()
        if not report.ok:
            _notify_contract_broken(report)
            # Do not overwrite a known-good roster with a suspect one: an
            # empty/partial parse would otherwise wipe the user's calendar.
            raise ContractDriftError(
                f"{report.status.value}: {report.detail or report.remedy}"
            )

        # Conditional store: skip the write if the raw HTML is unchanged.
        content_hash = hashlib.sha256(html.encode("utf-8", "replace")).hexdigest()
        if content_hash == STATUS.get("last_content_hash") and store.load(db_file):
            logger.info("Roster unchanged since last sync; skipping store write.")
        else:
            entries = parser.parse_roster(html)

            # Report what actually changed — this is the point of diffing.
            change = store.diff(store.load(db_file), entries)
            store.save(entries, db_file)
            STATUS["last_content_hash"] = content_hash
            STATUS["last_change"] = {
                "at": _now_iso(),
                "summary": change.summary(),
                "added": [e.to_dict() for e in change.added],
                "removed": [e.to_dict() for e in change.removed],
                "changed": [
                    {"before": before.to_dict(), "after": after.to_dict()}
                    for before, after in change.changed
                ],
            }
            if not change.is_empty:
                logger.info("Roster updated: %s", change.summary())
                _notify(backend_notify.notify_roster_change, STATUS["last_change"])

        STATUS["last_run"] = _now_iso()
        STATUS["last_error"] = None
    except Exception as exc:
        logger.exception("Sync failed")
        STATUS["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
        _notify(backend_notify.notify_sync_error, STATUS["last_error"])
    finally:
        _last_finish_ts = time.monotonic()
        STATUS["running"] = False
        _inflight.clear()
        try:
            _lock.release()
        except RuntimeError:
            pass



def _notify(fn, payload) -> None:
    """Fire a webhook off the sync thread so a slow endpoint cannot stall a sync."""
    if not config.webhook_url():
        return
    threading.Thread(
        target=fn, args=(payload,), name="ecrew-notify", daemon=True
    ).start()


def _notify_contract_broken(report) -> None:
    if not config.webhook_url():
        return
    threading.Thread(
        target=backend_notify.notify_contract_broken,
        args=(report,),
        name="ecrew-notify",
        daemon=True,
    ).start()


def trigger_sync(force: bool = False) -> bool:
    """Start a sync in a background thread.

    Returns True when a run was actually scheduled, False when one is already
    running or the debounce window applies. ``force=True`` bypasses debouncing
    (but still refuses to start a second concurrent run).
    """
    if _inflight.is_set():
        return False
    min_gap = config.sync_min_gap_s()
    if (
        not force
        and min_gap > 0
        and STATUS.get("last_run")
        and time.monotonic() - _last_finish_ts < min_gap
    ):
        logger.info("Debounced: last sync finished < %ds ago.", min_gap)
        return False

    # Claim the slot synchronously — set() returns False if another thread won
    # the race, which closes the spawn-to-start window.
    if not _inflight.is_set():
        _inflight.set()
        STATUS["running"] = True
        threading.Thread(target=_do_sync, name="ecrew-sync", daemon=True).start()
        return True
    return False


def get_sync_status() -> dict:
    return {
        "last_run": STATUS["last_run"],
        "running": STATUS["running"],
        "last_error": STATUS.get("last_error"),
        "last_change": STATUS.get("last_change"),
        "contract": STATUS.get("contract"),
        "min_gap_seconds": config.sync_min_gap_s(),
    }


def get_contract_status() -> dict:
    """Portal contract canary result from the most recent sync.

    Returns ``{"checked": False}`` before the first sync so callers can tell
    "not yet verified" apart from "verified as broken".
    """
    report = STATUS.get("contract")
    if not report:
        return {
            "checked": False,
            "ok": None,
            "status": "unchecked",
            "detail": "No sync has completed yet — run one to verify the portal contract.",
        }
    return {"checked": True, **report}


def start_scheduler(interval_h: int | None = None) -> None:
    """Start the periodic background sync job (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return
    hours = interval_h if interval_h is not None else config.sync_interval_h()
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        _scheduler = BackgroundScheduler(daemon=True)
        # max_instances=1 + coalesce: APScheduler-level guard complementing _lock.
        _scheduler.add_job(
            _do_sync,
            "interval",
            hours=hours,
            id="ecrew_sync",
            max_instances=1,
            coalesce=True,  # collapse missed runs into a single one
        )
        _scheduler.start()
        STATUS["auto_interval_h"] = hours
        logger.info("Scheduler started (every %dh)", hours)
    except ImportError:
        logger.warning("APScheduler not installed; background sync disabled.")


def shutdown_scheduler() -> None:
    """Stop the scheduler (called on app shutdown)."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover - best effort
            logger.debug("Scheduler shutdown raised", exc_info=True)
        _scheduler = None
