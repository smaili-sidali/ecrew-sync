"""Tests for parse_roster(), store durability/diffing, config and ICS export."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.export import entry_to_event, export_ics
from backend.parser import DutyEntry, ParseError, parse_roster

FIXTURE = Path(__file__).parent / "fixtures" / "sample_roster.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_returns_list_of_duty_entries():
    html = _html()
    entries = parse_roster(html)
    assert isinstance(entries, list)
    assert len(entries) >= 3
    assert all(isinstance(e, DutyEntry) for e in entries)


def test_parse_distinguishes_flight_from_off():
    html = _html()
    by_type = {}
    for e in parse_roster(html):
        by_type.setdefault(e.duty_type, e)
    assert by_type["flight"].date == "2026-08-15"
    assert by_type["off"].date == "2026-08-15"
    assert by_type["standby"].date == "2026-08-16"


def test_flight_fields_extracted():
    html = _html()
    flights = [e for e in parse_roster(html) if e.duty_type == "flight"]
    assert any(e.flight_number == "AH6001" for e in flights)
    ah6001 = next(e for e in flights if e.flight_number == "AH6001")
    assert ah6001.report_time == "2026-08-15T08:00:00"
    assert ah6001.departure_airport == "ALG"
    # "ORN / ALG" route code -> first is the departure airport.
    ah6002 = next(e for e in flights if e.flight_number == "AH6002")
    assert ah6002.departure_airport == "ORN"


def test_training_normalized():
    html = _html()
    assert any(e.duty_type == "training" for e in parse_roster(html))


def test_deduplicates_identical_rows():
    html = _html()
    entries = parse_roster(html)
    keys = [(e.date, e.duty_type, e.flight_number) for e in entries]
    assert len(keys) == len(set(keys))


def test_table_fallback():
    html = """
    <html><body><table id="scheduleTable"><thead>
      <tr><th>Date</th><th>Duty</th><th>Flight</th></tr>
    </thead><tbody>
      <tr class="dataRow"><td>2026-08-15</td><td>FLT</td><td>AH6001</td></tr>
      <tr class="dataRow"><td>2026-08-16</td><td>OFF</td><td></td></tr>
    </tbody></table></body></html>
    """
    entries = parse_roster(html)
    assert len(entries) == 2
    assert entries[0].flight_number == "AH6001"
    assert {e.duty_type for e in entries} == {"flight", "off"}


def test_empty_html_raises():
    with pytest.raises(ParseError):
        parse_roster("")


def test_unparseable_html_raises():
    with pytest.raises(ParseError):
        parse_roster("<html><body><p>No roster here at all.</p></body></html>")


def test_object_wrapped_events_and_nested_arrays():
    html = """
    <script>
      var SchedulerOptions = {
        events: [
          { "id": "x_1", "start": "2026-09-01T06:30:00", "type": "Flight",
            "tags": ["ALG", ["ORN", "fill2"]], "text": "AH7001" },
          { "id": "x_2", "start": "2026-09-02T00:00:00", "type": "Off", "text": "" }
        ],
        "meta": true
      };
    </script>
    """
    entries = parse_roster(html)
    assert {e.duty_type for e in entries} == {"flight", "off"}
    assert entries[0].flight_number == "AH7001"


def test_export_roundtrip():
    entries = parse_roster(_html())
    out = Path(__file__).parent / "_tmp_export.ics"
    export_ics(entries, out)
    try:
        text = out.read_text(encoding="utf-8")
        assert "BEGIN:VEVENT" in text
        assert "AH6001" in text
    finally:
        out.unlink(missing_ok=True)


def test_export_uid_stable():
    a = entry_to_event(DutyEntry(date="2026-08-15", duty_type="flight", flight_number="AH6001"))
    b = entry_to_event(DutyEntry(date="2026-08-15", duty_type="flight", flight_number="AH6001"))
    assert a.uid == b.uid
    assert a.uid != entry_to_event(DutyEntry(date="2026-08-15", duty_type="off")).uid
