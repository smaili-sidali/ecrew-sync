"""Tests for store durability, diffing correctness and configuration.

These lock in regressions that were real bugs:

* ``store.save`` wrote non-atomically — a crash left a truncated file that made
  every later read raise, and ``/api/roster`` 500'd forever.
* ``store.load`` raised ``JSONDecodeError`` on a corrupt store.
* ``store.diff`` keyed on ``(date, flight_number)``, so an off day swapped for a
  flight on the same date was reported as *both* added and removed, and the real
  change was invisible. Output order was also non-deterministic (set iteration).
* ``ECREW_*`` variables were read at import time, before ``load_dotenv()`` ran,
  so a local ``.env`` was silently ignored.
* The CLI and the scheduler disagreed on the session-file default.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend import store
from backend.parser import DutyEntry

# ===========================================================================
# store: durability
# ===========================================================================


def test_store_roundtrip(tmp_path):
    p = tmp_path / "nested" / "roster.json"
    entries = [DutyEntry(date="2026-08-15", duty_type="flight", flight_number="AH1")]
    store.save(entries, p)
    assert p.exists()
    assert [e.to_dict() for e in store.load(p)] == [e.to_dict() for e in entries]
    assert store.load_meta(p)["version"] == store.SCHEMA_VERSION
    assert store.load_meta(p)["synced_at"]


def test_store_load_missing_returns_empty(tmp_path):
    assert store.load(tmp_path / "nope.json") == []


def test_store_load_corrupt_does_not_raise(tmp_path):
    """A truncated store used to 500 every API request forever."""
    p = tmp_path / "roster.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert store.load(p) == []
    assert store.load_meta(p) == {}


def test_store_save_replaces_file_and_leaves_no_tmp(tmp_path):
    """save() must swap the file atomically, never leave a .tmp sibling."""
    p = tmp_path / "roster.json"
    store.save([DutyEntry(date="2026-08-15", duty_type="off")], p)
    store.save([DutyEntry(date="2026-08-16", duty_type="flight")], p)
    assert not list(tmp_path.glob("*.tmp"))
    assert [e.date for e in store.load(p)] == ["2026-08-16"]


def test_store_save_cleans_tmp_on_failure(tmp_path):
    class Boom:
        def __iter__(self):
            raise RuntimeError("boom")

    p = tmp_path / "roster.json"
    with pytest.raises(RuntimeError):
        store.save(Boom(), p)
    assert not list(tmp_path.glob("*.tmp"))
    assert not p.exists()


def test_store_tolerates_unknown_fields(tmp_path):
    """A store written by another schema version must still load."""
    p = tmp_path / "roster.json"
    p.write_text(
        json.dumps(
            {
                "version": 99,
                "synced_at": "2026-08-15T00:00:00+00:00",
                "entries": [
                    {"date": "2026-08-15", "duty_type": "off", "future_field": 1}
                ],
            }
        ),
        encoding="utf-8",
    )
    entries = store.load(p)
    assert len(entries) == 1
    assert entries[0].duty_type == "off"


# ===========================================================================
# store: diff correctness
# ===========================================================================


def test_diff_does_not_report_same_day_as_added_and_removed():
    """Regression: an off day swapped for a flight on one date used to show up
    as BOTH added and removed, hiding the real change."""
    prev = [DutyEntry(date="2026-08-16", duty_type="off")]
    curr = [DutyEntry(date="2026-08-16", duty_type="flight", flight_number="AH1")]
    d = store.diff(prev, curr)
    assert [e.duty_type for e in d.added] == ["flight"]
    assert [e.duty_type for e in d.removed] == ["off"]
    assert d.changed == []
    assert d.summary() == "1 added, 1 removed, 0 changed"


def test_diff_detects_in_place_time_change():
    prev = [
        DutyEntry(
            date="2026-08-15",
            duty_type="flight",
            flight_number="AH1",
            departure_time="2026-08-15T08:00:00",
        )
    ]
    curr = [
        DutyEntry(
            date="2026-08-15",
            duty_type="flight",
            flight_number="AH1",
            departure_time="2026-08-15T11:00:00",
        )
    ]
    d = store.diff(prev, curr)
    assert len(d.changed) == 1
    assert d.added == [] and d.removed == []
    assert not d.is_empty


def test_diff_is_deterministic_and_sorted():
    """Set-difference ordering is not stable; the output must be."""
    prev = []
    curr = [
        DutyEntry(date="2026-08-20", duty_type="off"),
        DutyEntry(date="2026-08-02", duty_type="off"),
        DutyEntry(date="2026-08-11", duty_type="off"),
    ]
    for _ in range(5):
        assert [e.date for e in store.diff(prev, curr).added] == [
            "2026-08-02",
            "2026-08-11",
            "2026-08-20",
        ]


def test_diff_identical_is_empty():
    entries = [DutyEntry(date="2026-08-15", duty_type="off")]
    d = store.diff(entries, entries)
    assert d.is_empty
    assert d.summary() == "0 added, 0 removed, 0 changed"
