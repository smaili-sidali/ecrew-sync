"""Tests for the portal contract canary (Phase 0/1).

The canary's job is to tell you *which* of the plausible portal changes broke
the parser, so the failure is actionable rather than a bare "no duties found".
These tests pin each diagnosis to the failure mode it represents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend import config
from backend.contract import (
    ContractStatus,
    check_entries,
    check_fragment,
    raise_if_broken,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_roster.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _enable_canary(monkeypatch):
    monkeypatch.delenv("ECREW_CONTRACT_CHECK", raising=False)


# --- healthy path --------------------------------------------------------- #


def test_intact_contract_passes():
    report = check_fragment(_html())
    assert report.ok
    assert report.status is ContractStatus.OK
    assert report.entry_count == 5
    assert report.event_count == 5
    assert report.duty_types["flight"] == 2
    assert report.duty_types["off"] == 1


def test_report_is_json_serialisable():
    data = check_fragment(_html()).to_dict()
    assert data["status"] == "ok"
    assert isinstance(data["duty_types"], dict)


def test_min_events_threshold_is_configurable(monkeypatch):
    # A 5-event fixture is below a threshold of 10 -> suspicious.
    report = check_fragment(_html(), min_events=10)
    assert not report.ok
    assert report.status is ContractStatus.SUSPICIOUSLY_FEW


# --- failure modes -------------------------------------------------------- #

# The most likely real-world break: the A1 view is a calendar shell whose rows
# arrive via a follow-up XHR. NOTES.md flags this explicitly.
LAZY_CONTAINER = """<div id="schedulerContainer"></div>
<script src="/js/eCrewDayPilot.js"></script>
<script>var dp = new DayPilot.Calendar(); dp.events.list = [];</script>"""


def test_detects_lazy_loaded_container():
    report = check_fragment(LAZY_CONTAINER)
    assert not report.ok
    assert report.status is ContractStatus.LAZY_LOADED
    assert "lazy" in report.remedy.lower()
    assert "DevTools" in report.remedy


def test_detects_renamed_event_array():
    """The variable was renamed, so no duty array can be found at all."""
    report = check_fragment("<html><body><p>Roster</p></body></html>")
    assert not report.ok
    assert report.status is ContractStatus.NO_EVENT_ARRAY
    assert "recon" in report.remedy.lower() or "renamed" in report.remedy.lower()


def test_detects_renamed_event_fields():
    """Events are present but their keys moved, so no usable date is found."""
    html = (
        '<script>var Events=[{"when":"2026-08-15T08:00:00","kind":"Flight"}];</script>'
    )
    report = check_fragment(html)
    assert not report.ok
    assert report.status is ContractStatus.UNRECOGNISED_FIELDS
    assert "parser._get()" in report.remedy or "alias" in report.remedy.lower()


def test_detects_empty_fragment():
    report = check_fragment("")
    assert not report.ok
    assert report.status is ContractStatus.NO_EVENT_ARRAY


def test_detects_whitespace_only_fragment():
    report = check_fragment("   \n  ")
    assert not report.ok


def test_canary_never_raises_on_garbage():
    """A canary that crashes is worse than no canary."""
    for junk in ("<<<>>>", "{[}", "<script>var x = [[[[", "\x00\x01", "<html>" * 50):
        report = check_fragment(junk)
        assert isinstance(report.status, ContractStatus)
        assert isinstance(report.ok, bool)


def test_check_entries_flags_empty():
    report = check_entries([])
    assert not report.ok
    assert report.status is ContractStatus.LAZY_LOADED


def test_check_entries_ok():
    from backend.parser import parse_roster

    report = check_entries(parse_roster(_html()))
    assert report.ok
    assert report.entry_count == 5


# --- toggling & logging --------------------------------------------------- #


def test_canary_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ECREW_CONTRACT_CHECK", "0")
    report = check_fragment("total garbage")
    assert report.ok, "disabled canary must not fail the sync"
    assert report.status is ContractStatus.DISABLED


def test_raise_if_broken_logs_an_error(caplog):
    report = check_fragment(LAZY_CONTAINER)
    with caplog.at_level("ERROR"):
        raise_if_broken(report)
    text = caplog.text
    assert "CONTRACT canary FAILED" in text or "canary FAILED" in text
    assert "Remedy" in text


def test_raise_if_broken_is_quiet_when_ok(caplog):
    with caplog.at_level("ERROR"):
        raise_if_broken(check_fragment(_html()))
    assert "FAILED" not in caplog.text


def test_every_status_has_a_remedy():
    for status in ContractStatus:
        assert config is not None  # sanity
        from backend.contract import REMEDIES

        assert REMEDIES[status], f"{status} has no remedy text"
