"""Scheduler tests: drift protection, debounce, and the in-flight lock.

The most important behaviour here is that a *contract drift* must not destroy a
known-good roster. If the portal changes and parsing yields nothing, silently
writing an empty store would wipe the user's calendar — the exact failure this
project exists to avoid.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend import config, store
from backend.parser import parse_roster
from server import scheduler

FIXTURE = Path(__file__).parent / "fixtures" / "sample_roster.html"

# A plausible "portal changed" fragment: a calendar shell with no duties.
LAZY_FRAGMENT = (
    '<div id="schedulerContainer"></div>'
    '<script src="/js/eCrewDayPilot.js"></script>'
    '<script>var dp = new DayPilot.Calendar(); dp.events.list = [];</script>'
)


@pytest.fixture(autouse=True)
def _reset():
    import threading

    scheduler.shutdown_scheduler()
    if scheduler._lock.locked():
        scheduler._lock = threading.Lock()
    scheduler.STATUS.update(
        {
            "last_run": None,
            "last_error": None,
            "running": False,
            "last_content_hash": None,
            "last_change": None,
            "contract": None,
        }
    )
    scheduler._last_finish_ts = 0.0
    scheduler._inflight.clear()
    yield
    scheduler._inflight.clear()
    scheduler.shutdown_scheduler()


def _good_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _seed_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ECREW_DB_FILE", str(tmp_path / "roster.json"))
    entries = parse_roster(_good_html())
    store.save(entries, tmp_path / "roster.json")
    return entries


def _stub_sync(monkeypatch, fragment):
    """Force _do_sync to use a canned fragment and skip all network I/O."""
    from backend import auth, fetch

    class _Creds:
        username = "12345"
        password = "hunter2"

    monkeypatch.setattr(auth.Credentials, "from_env", classmethod(lambda cls: _Creds()))
    monkeypatch.setattr(auth, "get_session", lambda *a, **k: object())
    monkeypatch.setattr(fetch, "is_session_alive", lambda *a, **k: True)
    monkeypatch.setattr(fetch, "fetch_with_relogin", lambda *a, **k: fragment)


# --- drift protection ------------------------------------------------------ #


def test_contract_drift_does_not_wipe_the_store(tmp_path, monkeypatch):
    """The core Phase 1 guarantee."""
    original = _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, LAZY_FRAGMENT)

    scheduler._do_sync()

    assert scheduler.STATUS["last_error"], "drift must be reported"
    assert "ContractDriftError" in scheduler.STATUS["last_error"]
    # The good roster is still on disk, untouched.
    assert [e.to_dict() for e in store.load(tmp_path / "roster.json")] == [
        e.to_dict() for e in original
    ]


def test_contract_drift_records_the_diagnosis(tmp_path, monkeypatch):
    _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, LAZY_FRAGMENT)

    scheduler._do_sync()

    contract_status = scheduler.STATUS["contract"]
    assert contract_status is not None
    assert contract_status["ok"] is False
    assert contract_status["status"] == "lazy_loaded"
    assert contract_status["remedy"]


def test_healthy_sync_stores_and_reports_change(tmp_path, monkeypatch):
    _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, _good_html())

    scheduler._do_sync()

    assert scheduler.STATUS["last_error"] is None
    assert scheduler.STATUS["last_run"]
    assert scheduler.STATUS["contract"]["ok"] is True
    assert scheduler.STATUS["last_change"]["summary"] == "0 added, 0 removed, 0 changed"

# --- debounce / concurrency ----------------------------------------------- #


def test_debounce_blocks_a_second_trigger(monkeypatch):
    monkeypatch.setenv("ECREW_SYNC_MIN_GAP_S", "300")
    scheduler.STATUS["last_run"] = "2026-08-15T00:00:00+00:00"
    scheduler._last_finish_ts = time.monotonic()
    assert scheduler.trigger_sync() is False


def test_force_bypasses_debounce(monkeypatch):
    monkeypatch.setenv("ECREW_SYNC_MIN_GAP_S", "300")
    scheduler.STATUS["last_run"] = "2026-08-15T00:00:00+00:00"
    scheduler._last_finish_ts = time.monotonic()
    # Stub _do_sync so no thread work happens.
    monkeypatch.setattr(scheduler, "_do_sync", lambda: None)
    assert scheduler.trigger_sync(force=True) is True


def test_concurrent_trigger_does_not_double_login(monkeypatch):
    """Regression: the old STATUS['running'] check was a read-then-write race."""
    calls = []
    started = threading.Event()
    release = threading.Event()

    def slow_sync():
        calls.append(1)
        started.set()
        release.wait(5)

    monkeypatch.setattr(scheduler, "_do_sync", slow_sync)
    assert scheduler.trigger_sync(force=True) is True
    started.wait(5)
    # While the first is "running", further triggers must be refused.
    assert scheduler.trigger_sync(force=True) is False
    assert scheduler.trigger_sync() is False
    release.set()
    time.sleep(0.2)
    assert len(calls) == 1, f"expected 1 sync, got {len(calls)}"


# --- status surface -------------------------------------------------------- #


def test_contract_status_is_unchecked_before_first_sync():
    result = scheduler.get_contract_status()
    assert result["checked"] is False
    assert result["status"] == "unchecked"


def test_contract_status_reflects_last_run(tmp_path, monkeypatch):
    _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, _good_html())
    scheduler._do_sync()
    result = scheduler.get_contract_status()
    assert result["checked"] is True
    assert result["ok"] is True


def test_sync_status_includes_contract_key():
    assert "contract" in scheduler.get_sync_status()


def test_start_scheduler_is_idempotent():
    scheduler.start_scheduler(interval_h=1)
    first = scheduler._scheduler
    scheduler.start_scheduler(interval_h=1)
    assert scheduler._scheduler is first
    scheduler.shutdown_scheduler()
    assert scheduler._scheduler is None


def test_config_min_events_is_respected(monkeypatch):
    monkeypatch.setenv("ECREW_CONTRACT_MIN_EVENTS", "99")
    assert config.contract_min_events() == 99



def test_lock_is_released_after_a_failure(tmp_path, monkeypatch):
    """A crashed sync must not wedge the scheduler forever."""
    _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, LAZY_FRAGMENT)
    scheduler._do_sync()
    assert scheduler.STATUS["running"] is False
    assert not scheduler._lock.locked(), "lock must be released in finally"


def test_lock_is_released_after_success(tmp_path, monkeypatch):
    _seed_store(tmp_path, monkeypatch)
    _stub_sync(monkeypatch, _good_html())
    scheduler._do_sync()
    assert not scheduler._lock.locked()
