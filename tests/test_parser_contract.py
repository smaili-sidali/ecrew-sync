"""Parser tests, including robustness against decoy arrays in the fragment.

The real portal fragment is unverified (see NOTES.md), so the parser must be
defensive about *which* embedded array it trusts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.parser import ParseError, _extract_events, parse_roster

FIXTURE = Path(__file__).parent / "fixtures" / "sample_roster.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_yields_expected_duties():
    entries = parse_roster(_html())
    assert len(entries) >= 5
    assert {e.duty_type for e in entries} >= {"flight", "off", "standby", "training"}


def test_prefers_roster_over_longer_decoy_array():
    """A fragment can carry a long non-duty array (airports, legend). Ranking by
    length alone picked that decoy and produced zero duties."""
    decoy = ",".join(
        f'{{"code": "ZZ{i:03d}", "name": "Somewhere"}}' for i in range(300)
    )
    html = (
        "<script>"
        "var AirportsList = [" + decoy + "];"
        "var InitialSchedulerEvents = ["
        '{"id":"1_2026-08-15","start":"2026-08-15T08:00:00",'
        '"end":"2026-08-15T10:00:00","type":"Flight","text":"AH1000"}'
        "];"
        "</script>"
    )
    picked = _extract_events(html)
    assert picked is not None
    assert len(picked) == 1, "must pick the 1-item roster, not the 300-item decoy"

    entries = parse_roster(html)
    assert [(e.date, e.flight_number) for e in entries] == [("2026-08-15", "AH1000")]


def test_rejects_array_of_dated_non_events():
    """A stats array of {date, value} dicts is not a roster."""
    html = (
        "<script>var Monthly = ["
        '{"date":"2026-08-01","value":3},{"date":"2026-08-02","value":5}'
        "];</script>"
    )
    assert _extract_events(html) is None
    with pytest.raises(ParseError):
        parse_roster(html)


def test_falls_back_to_table_when_no_event_array():
    html = """
    <table><tbody>
      <tr><td>2026-08-15</td><td>FLT</td><td>AH6001</td></tr>
      <tr><td>2026-08-16</td><td>OFF</td><td></td></tr>
    </tbody></table>
    """
    entries = parse_roster(html)
    assert len(entries) == 2
    assert entries[0].flight_number == "AH6001"


def test_empty_and_unparseable_raise():
    with pytest.raises(ParseError):
        parse_roster("")
    with pytest.raises(ParseError):
        parse_roster("   ")
    with pytest.raises(ParseError):
        parse_roster("<html><body><p>nothing here</p></body></html>")


def test_deduplicates_identical_rows():
    entries = parse_roster(_html())
    keys = [(e.date, e.duty_type, e.flight_number) for e in entries]
    assert len(keys) == len(set(keys))


def test_handles_bare_js_object_keys():
    html = """
    <script>
    var Events = [
      { id: 'a_2026-09-01', start: '2026-09-01T06:00:00',
        end: '2026-09-01T08:00:00', type: 'Flight', text: 'AH2000' }
    ];
    </script>
    """
    entries = parse_roster(html)
    assert entries[0].flight_number == "AH2000"
    assert entries[0].duty_type == "flight"


def test_survives_unbalanced_braces():
    """A truncated fragment must raise ParseError, not hang or IndexError."""
    html = '<script>var E = [{"start":"2026-08-15T08:00:00","type":"Flight"};'
    with pytest.raises(ParseError):
        parse_roster(html)


def test_nested_arrays_do_not_truncate_block():
    html = """
    <script>
    var Opts = { events: [
      {"id":"x_1","start":"2026-09-01T06:30:00","type":"Flight",
       "tags":["ALG",["ORN","fill"]],"text":"AH7001"},
      {"id":"x_2","start":"2026-09-02T00:00:00","type":"Off","text":""}
    ]};
    </script>
    """
    entries = parse_roster(html)
    assert {e.duty_type for e in entries} == {"flight", "off"}
    assert entries[0].flight_number == "AH7001"


def test_unknown_duty_type_maps_to_other():
    html = (
        '<script>var E=[{"start":"2026-08-15T08:00:00","type":"WeirdDuty",'
        '"end":"2026-08-15T09:00:00","text":"?"}];</script>'
    )
    assert parse_roster(html)[0].duty_type == "other"


def test_airport_codes_extracted_from_location():
    html = (
        '<script>var E=[{"start":"2026-08-15T08:00:00","end":"2026-08-15T10:00:00",'
        '"type":"Flight","text":"AH1 ALG - ORN","location":"ALG / ORN"}];</script>'
    )
    entry = parse_roster(html)[0]
    assert entry.departure_airport == "ALG"
    assert entry.arrival_airport == "ORN"
