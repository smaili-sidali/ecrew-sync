"""API tests: health, roster filtering, sync debounce, docs gating, static mount.

Uses FastAPI's TestClient (requires httpx). Skipped automatically when httpx is
not installed so the core suite still runs on a bare checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

pytest.importorskip("httpx", reason="TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend import config, store  # noqa: E402
from backend.parser import DutyEntry  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ECREW_DB_FILE", str(tmp_path / "roster.json"))
    import server.api as api

    with TestClient(api.app) as c:
        yield c


def _seed(monkeypatch, entries):
    store.save(entries, config.db_file())


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "sync_status" in body
    assert "last_error" in body["sync_status"]


def test_health_reports_entry_count(client, monkeypatch):
    _seed(monkeypatch, [DutyEntry(date="2026-08-15", duty_type="off")])
    assert client.get("/api/health").json()["entry_count"] == 1


def test_roster_empty(client):
    r = client.get("/api/roster")
    assert r.status_code == 200
    assert r.json() == {"synced_at": None, "count": 0, "entries": []}


def test_roster_sorted_by_date(client, monkeypatch):
    _seed(
        monkeypatch,
        [
            DutyEntry(date="2026-08-20", duty_type="off"),
            DutyEntry(date="2026-08-02", duty_type="off"),
            DutyEntry(date="2026-08-11", duty_type="flight", flight_number="AH1"),
        ],
    )
    dates = [e["date"] for e in client.get("/api/roster").json()["entries"]]
    assert dates == sorted(dates) == ["2026-08-02", "2026-08-11", "2026-08-20"]


def test_roster_month_filter(client, monkeypatch):
    _seed(
        monkeypatch,
        [
            DutyEntry(date="2026-08-15", duty_type="off"),
            DutyEntry(date="2026-09-15", duty_type="off"),
        ],
    )
    body = client.get("/api/roster", params={"month": "2026-08"}).json()
    assert body["count"] == 1
    assert body["entries"][0]["date"] == "2026-08-15"


@pytest.mark.parametrize("bad", ["2026-13", "not-a-month", "2026-00", "202608"])
def test_roster_rejects_bad_month(client, bad):
    """Unvalidated month strings previously flowed into a startswith() filter."""
    assert client.get("/api/roster", params={"month": bad}).status_code == 422


def test_export_ics_404_when_empty(client):
    assert client.get("/api/export.ics").status_code == 404


def test_export_ics_returns_calendar(client, monkeypatch):
    _seed(
        monkeypatch,
        [
            DutyEntry(
                date="2026-08-15",
                duty_type="flight",
                flight_number="AH6001",
                report_time="2026-08-15T08:00:00",
                arrival_time="2026-08-15T10:00:00",
            )
        ],
    )
    r = client.get("/api/export.ics")
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert "AH6001" in r.text


def test_index_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "eCrew" in r.text


def test_api_routes_are_not_shadowed_by_static_mount(client):
    """The StaticFiles mount is registered at "/" — it must not swallow /api."""
    for path in ("/api/health", "/api/roster"):
        assert client.get(path).status_code == 200


def test_docs_are_disabled_by_default(client):
    """A public deployment should not hand out a free map of the API."""
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_sync_endpoint_reports_started(client, monkeypatch):
    monkeypatch.setattr("server.scheduler.trigger_sync", lambda force=False: (True, "started"))
    r = client.post("/api/sync")
    assert r.status_code == 200
    assert "started" in r.json()


def test_docs_can_be_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ECREW_DB_FILE", str(tmp_path / "r.json"))
    monkeypatch.setenv("ECREW_ENABLE_DOCS", "1")
    import importlib

    import server.api as api

    importlib.reload(api)
    with TestClient(api.app) as c:
        assert c.get("/openapi.json").status_code == 200
    # Restore module state for other tests.
    monkeypatch.delenv("ECREW_ENABLE_DOCS", raising=False)
    monkeypatch.setenv("ECREW_DB_FILE", str(tmp_path / "r.json"))
    importlib.reload(api)


# ==========================================================================
# Phase 2: calendar subscription feed
# ==========================================================================


def test_calendar_feed_serves_ics(client, monkeypatch):
    _seed(
        monkeypatch,
        [
            DutyEntry(
                date="2026-08-15",
                duty_type="flight",
                flight_number="AH6001",
                report_time="2026-08-15T08:00:00",
                arrival_time="2026-08-15T10:00:00",
            )
        ],
    )
    r = client.get("/api/calendar.ics")
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert "BEGIN:VCALENDAR" in r.text
    assert "AH6001" in r.text


def test_calendar_feed_is_inline_and_uncacheable(client, monkeypatch):
    """A subscribed feed must not be attachment-dispositioned or cacheable."""
    _seed(monkeypatch, [DutyEntry(date="2026-08-15", duty_type="off")])
    r = client.get("/api/calendar.ics")
    assert "inline" in r.headers.get("content-disposition", "")
    assert "no-cache" in r.headers.get("cache-control", "")


def test_calendar_feed_has_stable_uids_and_last_modified(client, monkeypatch):
    """The two properties that make a subscription update in place instead of
    duplicating: stable UID, plus LAST-MODIFIED to signal a content change."""
    _seed(
        monkeypatch,
        [
            DutyEntry(
                date="2026-08-15",
                duty_type="flight",
                flight_number="AH6001",
                report_time="2026-08-15T08:00:00",
                arrival_time="2026-08-15T10:00:00",
            )
        ],
    )
    first = client.get("/api/calendar.ics").text
    second = client.get("/api/calendar.ics").text
    assert first == second, "repeated fetches must be byte-identical"
    assert "UID:" in first
    assert "LAST-MODIFIED" in first


def test_calendar_feed_404_when_empty(client):
    assert client.get("/api/calendar.ics").status_code == 404


def test_download_endpoint_is_attachment(client, monkeypatch):
    _seed(monkeypatch, [DutyEntry(date="2026-08-15", duty_type="off")])
    r = client.get("/api/export.ics")
    assert "attachment" in r.headers.get("content-disposition", "")


# ==========================================================================
# Phase 1: contract canary endpoint
# ==========================================================================


def test_contract_endpoint_reports_unchecked_before_first_sync(client):
    body = client.get("/api/contract").json()
    assert body["checked"] is False
    assert body["status"] == "unchecked"


def test_health_includes_roster_state(client):
    body = client.get("/api/health").json()
    assert body["roster_state"] in {"never_synced", "syncing", "degraded", "ok"}


# ==========================================================================
# Phase 3: API token auth
# ========================================================================== #


def test_no_auth_required_when_token_unset(client):
    assert client.get("/api/roster").status_code == 200


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    assert client.get("/api/roster").status_code == 401
    assert client.get("/api/export.ics").status_code == 401
    assert client.post("/api/sync").status_code == 401


def test_bearer_header_authenticates(client, monkeypatch):
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    r = client.get("/api/roster", headers={"Authorization": "Bearer s3cret-token"})
    assert r.status_code == 200


def test_query_token_authenticates(client, monkeypatch):
    """Calendar apps that subscribe to a feed cannot send custom headers."""
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    assert client.get("/api/roster", params={"token": "s3cret-token"}).status_code == 200


def test_wrong_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    assert client.get("/api/roster?token=wrong").status_code == 403


def test_health_stays_public_with_token_set(client, monkeypatch):
    """The container healthcheck must keep working when auth is on."""
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    assert client.get("/api/health").status_code == 200


def test_contract_endpoint_stays_public(client, monkeypatch):
    """Diagnostics carry no duty data, so they stay reachable for monitoring."""
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    assert client.get("/api/contract").status_code == 200


def test_calendar_feed_respects_token(client, monkeypatch):
    monkeypatch.setenv("ECREW_API_TOKEN", "s3cret-token")
    _seed(monkeypatch, [DutyEntry(date="2026-08-15", duty_type="off")])
    assert client.get("/api/calendar.ics").status_code == 401
    ok = client.get("/api/calendar.ics", params={"token": "s3cret-token"})
    assert ok.status_code == 200

