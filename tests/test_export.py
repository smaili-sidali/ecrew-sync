"""Tests for ICS export: timezone correctness, all-day handling and UID stability.

Two real bugs are locked in here:

* Naive portal timestamps were serialised with a ``Z`` (UTC) suffix, so an 08:00
  Algiers (UTC+1) duty was stamped ``08:00Z`` and displayed as **09:00** in
  every calendar app — an hour of drift on every duty in the roster.
* The event UID folded in ``entry.raw`` (the full source JSON), which embeds the
  portal's ``ver`` counter. Any edit on the portal produced a new UID, so
  re-importing the calendar created duplicate events for the same flight.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.export import _parse_dt, entry_to_event, export_ics
from backend.parser import DutyEntry, parse_roster

FIXTURE = Path(__file__).parent / "fixtures" / "sample_roster.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _flight(report="2026-08-15T08:00:00", arrival="2026-08-15T10:00:00"):
    return DutyEntry(
        date="2026-08-15",
        duty_type="flight",
        flight_number="AH6001",
        report_time=report,
        arrival_time=arrival,
    )


# --- timezone ------------------------------------------------------------- #


def test_naive_times_are_portal_local_not_utc():
    """The core regression: 08:00 Algiers must not become 08:00Z."""
    event = entry_to_event(_flight())
    assert event.begin is not None
    assert event.begin.hour == 8, "wall-clock time must be preserved"
    assert event.begin.utcoffset().total_seconds() == 3600  # UTC+1


def test_timed_flight_keeps_duration():
    event = entry_to_event(_flight())
    assert (event.end - event.begin).total_seconds() == 2 * 3600


def test_explicit_offset_is_honoured():
    event = entry_to_event(
        _flight(report="2026-08-15T08:00:00+02:00", arrival="2026-08-15T10:00:00+02:00")
    )
    assert event.begin.utcoffset().total_seconds() == 7200


def test_z_suffix_is_parsed_as_utc():
    assert _parse_dt("2026-08-15T08:00:00Z").utcoffset().total_seconds() == 0


def test_parse_dt_handles_empty_and_garbage():
    assert _parse_dt(None) is None
    assert _parse_dt("") is None
    assert _parse_dt("   ") is None

# --- all-day handling ----------------------------------------------------- #


def test_all_day_event_lands_on_the_exact_date(tmp_path):
    """Regression: make_all_day() floors in UTC, so a local midnight rolled a
    20 Aug duty back to 19 Aug and expanded it to two days.

    Asserted on the serialised output, which is what calendar apps consume. (The
    library's in-memory ``end`` is bumped by a day, but it is omitted from the
    wire format for a one-day all-day event.)
    """
    out = export_ics(
        [
            DutyEntry(
                date="2026-08-20",
                duty_type="off",
                report_time="2026-08-20T00:00:00",
                arrival_time="2026-08-20T23:59:59",
            )
        ],
        tmp_path / "off.ics",
    )
    text = out.read_text(encoding="utf-8")
    assert "DTSTART;VALUE=DATE:20260820" in text
    # No DTEND at all == exactly one day (not a two-day block).
    assert "DTEND" not in text


def test_all_day_event_is_single_day_in_memory():
    event = entry_to_event(
        DutyEntry(
            date="2026-08-20",
            duty_type="off",
            report_time="2026-08-20T00:00:00",
            arrival_time="2026-08-20T23:59:59",
        )
    )
    assert event.all_day
    assert event.begin.strftime("%Y%m%d") == "20260820"


def test_whole_day_types_from_fixture_are_single_days():
    for entry in parse_roster(_html()):
        event = entry_to_event(entry)
        assert event.begin is not None
        if entry.duty_type in {"off", "training"}:
            assert event.all_day, f"{entry.duty_type} should be all-day"
            assert event.begin.strftime("%Y-%m-%d") == entry.date


def test_standby_stays_timed():
    """Standby is a timed activity, not an all-day block."""
    event = entry_to_event(
        DutyEntry(
            date="2026-08-16",
            duty_type="standby",
            report_time="2026-08-16T09:00:00",
            arrival_time="2026-08-16T17:00:00",
        )
    )
    assert not event.all_day
    assert event.begin.hour == 9


def test_end_before_begin_does_not_produce_inverted_event():
    event = entry_to_event(
        DutyEntry(
            date="2026-08-15",
            duty_type="flight",
            report_time="2026-08-15T10:00:00",
            arrival_time="2026-08-15T08:00:00",
        )
    )
    assert event.begin <= event.end


def test_flight_without_arrival_is_all_day():
    event = entry_to_event(
        DutyEntry(
            date="2026-08-15",
            duty_type="flight",
            flight_number="AH1",
            report_time="2026-08-15T08:00:00",
        )
    )
    assert event.begin is not None
    assert event.all_day


# --- UID stability -------------------------------------------------------- #


def test_uid_ignores_raw_version_bump():
    """A portal-side `ver` bump must not create a duplicate calendar event."""
    base = DutyEntry(date="2026-08-15", duty_type="flight", flight_number="AH1")
    bumped = DutyEntry(
        date="2026-08-15",
        duty_type="flight",
        flight_number="AH1",
        raw=json.dumps({"ver": 99, "id": "x"}),
    )
    assert entry_to_event(base).uid == entry_to_event(bumped).uid


def test_uid_differs_across_duties():
    uids = {
        entry_to_event(DutyEntry(date="2026-08-15", duty_type="flight", flight_number="AH1")).uid,
        entry_to_event(DutyEntry(date="2026-08-15", duty_type="off")).uid,
        entry_to_event(DutyEntry(date="2026-08-16", duty_type="off")).uid,
    }
    assert len(uids) == 3


# --- file output ---------------------------------------------------------- #


def test_export_roundtrip(tmp_path):
    out = export_ics(parse_roster(_html()), tmp_path / "out.ics")
    text = out.read_text(encoding="utf-8")
    assert "BEGIN:VEVENT" in text
    assert "AH6001" in text
    assert "PRODID:-//eCrew Sync//eCrew Sync//EN" in text


def test_export_is_deterministic(tmp_path):
    entries = parse_roster(_html())
    a = export_ics(entries, tmp_path / "a.ics").read_text(encoding="utf-8")
    b = export_ics(entries, tmp_path / "b.ics").read_text(encoding="utf-8")
    assert a == b


def test_export_skips_entries_with_no_usable_date(tmp_path):
    out = export_ics([DutyEntry(date="not-a-date", duty_type="off")], tmp_path / "x.ics")
    assert out.exists()
    assert "BEGIN:VEVENT" not in out.read_text(encoding="utf-8")


def test_export_creates_parent_directory(tmp_path):
    out = export_ics([], tmp_path / "deep" / "nested" / "c.ics")
    assert out.exists()

    assert _parse_dt("not a date") is None


def test_parse_dt_accepts_space_and_bare_date():
    assert _parse_dt("2026-08-15 08:30:00").hour == 8
    assert _parse_dt("2026-08-15").day == 15
