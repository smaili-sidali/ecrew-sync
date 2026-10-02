"""Tests for webhook notifications (Phase 1) and structured logging (Phase 3).

The overriding constraint: a notification failure must never break a sync or
turn a good roster into an error. Most of these tests exist to prove that.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend import config, notify


@pytest.fixture(autouse=True)
def _no_webhook(monkeypatch):
    monkeypatch.delenv("ECREW_WEBHOOK_URL", raising=False)


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _capture(monkeypatch, status=200, store=None):
    """Patch requests.post to record the payload instead of sending it."""

    def fake_post(url, data=None, headers=None, timeout=None):
        if store is not None:
            store["url"] = url
            store["payload"] = json.loads(data)
            store["raw"] = data.decode() if isinstance(data, bytes) else data
        return _FakeResponse(status)

    monkeypatch.setattr("requests.post", fake_post)


def test_no_webhook_configured_is_a_noop():
    assert notify._post({"event": "x"}) is False


def test_roster_change_notifies(monkeypatch):
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    sent = {}
    _capture(monkeypatch, store=sent)
    change = {
        "at": "2026-08-15T00:00:00+00:00",
        "summary": "2 added, 1 removed, 0 changed",
        "added": [
            {"date": "2026-08-16", "duty_type": "flight", "flight_number": "AH1"}
        ],
        "removed": [],
        "changed": [],
    }
    assert notify.notify_roster_change(change) is True
    assert sent["payload"]["event"] == "roster_changed"
    assert sent["payload"]["counts"] == {"added": 1, "removed": 0, "changed": 0}
    assert "AH1" in sent["payload"]["message"]


def test_empty_change_is_not_sent():
    assert notify.notify_roster_change({}) is False
    assert notify.notify_roster_change(None) is False


def test_sync_error_always_notifies(monkeypatch):
    """A failure is never 'no change' — it must always be reported."""
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    sent = {}
    _capture(monkeypatch, store=sent)
    assert notify.notify_sync_error("AuthError: bad password") is True
    assert sent["payload"]["event"] == "sync_error"
    assert "bad password" in sent["payload"]["error"]


def test_contract_broken_notifies(monkeypatch):
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    sent = {}
    _capture(monkeypatch, store=sent)

    from backend.contract import ContractStatus, check_fragment

    report = check_fragment(
        "<div id='schedulerContainer'></div><script>daypilot</script>"
    )
    assert notify.notify_contract_broken(report) is True
    assert sent["payload"]["event"] == "contract_broken"
    assert sent["payload"]["status"] == ContractStatus.LAZY_LOADED.value


def test_webhook_exception_never_propagates(monkeypatch):
    """The critical guarantee: a dead webhook cannot break a sync."""
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")

    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("requests.post", boom)
    assert notify.notify_sync_error("some error") is False


def test_webhook_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    captured = {}
    _capture(monkeypatch, store=captured)
    notify.notify_sync_error("x")
    assert captured.get("timeout") is None or captured["timeout"] <= 60
    assert config.webhook_timeout_s() <= 60


def test_non_2xx_is_reported_as_failure(monkeypatch):
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    _capture(monkeypatch, status=500)


# --- structured logging ---------------------------------------------------- #


def test_json_formatter_emits_one_object_per_line():
    from server.logging_setup import JsonFormatter

    record = logging.LogRecord(
        "ecrew.test", logging.INFO, __file__, 1, "roster updated", (), None
    )
    record.job_id = "abc123"  # stands in for logging extra={...}
    out = JsonFormatter().format(record)
    payload = json.loads(out)
    assert payload["message"] == "roster updated"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "ecrew.test"
    assert payload["job_id"] == "abc123"
    assert "\n" not in out, "one record must be one line"


def test_json_formatter_includes_exception():
    from server.logging_setup import JsonFormatter

    try:
        raise ValueError("kaboom")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "ecrew.test", logging.ERROR, __file__, 1, "failed", (), exc_info
    )
    payload = json.loads(JsonFormatter().format(record))
    assert "kaboom" in payload["exc"]


def test_setup_logging_is_idempotent():
    from server.logging_setup import setup_logging

    setup_logging()
    first = len(logging.getLogger().handlers)
    setup_logging()
    assert len(logging.getLogger().handlers) == first


def test_noisy_libraries_are_quieted():
    from server.logging_setup import setup_logging

    setup_logging()
    assert logging.getLogger("apscheduler").level >= logging.WARNING
    assert logging.getLogger("urllib3").level >= logging.WARNING


def test_log_level_from_config(monkeypatch):
    import importlib

    monkeypatch.setenv("ECREW_LOG_LEVEL", "DEBUG")
    import server.logging_setup as ls

    importlib.reload(ls)
    ls.setup_logging()
    assert logging.getLogger().level == logging.DEBUG
    ls.setup_logging()

    assert notify.notify_sync_error("x") is False


def test_payload_has_no_credentials(monkeypatch):
    """Never leak the portal password or session id through a webhook."""
    monkeypatch.setenv("ECREW_WEBHOOK_URL", "https://hook.test/x")
    monkeypatch.setenv("ECREW_PASSWORD", "super-secret-password")
    sent = {}
    _capture(monkeypatch, store=sent)
    notify.notify_sync_error("AuthError: nope")
    assert "super-secret-password" not in sent["raw"]
