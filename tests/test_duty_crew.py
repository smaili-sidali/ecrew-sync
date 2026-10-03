"""Crew composition read from the portal's DutyDetails view.

Fixture shape mirrors a real browser capture (flight 463 JED-ORN, 2026-10-03)
with the colleagues' photos and contact details stripped: this sample is versioned
in a public repository, so no personal data is published. Every key the parser
reads is still present.
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse

import pytest

from backend import api_helpers, duty_details
from backend.duty_details import DutyDetailsError

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "duty_details.html"
EVENT_ID = "35739on2026-10-0505:35:00_17079_17075_137979246130_335_17079"


@pytest.fixture(scope="module")
def duty():
    parsed = duty_details.parse_duty_details(FIXTURE.read_text(encoding="utf-8"))
    assert parsed is not None
    return parsed


def test_parses_every_crew_member(duty):
    assert len(duty.crew) == 10
    assert len({m.id for m in duty.crew}) == 10


def test_parses_leg_facts(duty):
    assert duty.flight_number == "463"
    leg = duty.legs[0]
    assert leg.aircraft_type == "A335"
    assert leg.registration == "7T-VJA"
    assert leg.departure == "JED"
    assert leg.arrival == "ORN"
    assert leg.report_time == "0535"
    assert leg.debrief_time == "1405"
    assert leg.departure_time == "0705"
    assert leg.arrival_time == "1335"
    assert leg.pax == "Y246"
    assert leg.distance == "4149 Km"


def test_identifies_the_pilot_in_command(duty):
    pics = [m for m in duty.crew if m.is_pic]
    assert len(pics) == 1
    assert pics[0].role == "CP"


def test_maps_role_and_pairing(duty):
    by_role = {}
    for m in duty.crew:
        by_role.setdefault(m.role, []).append(m)
    assert set(by_role) == {"CP", "FO", "PC", "FA"}
    # 1 captain + 1 first officer + 1 cabin crew + 7 flight attendants
    assert len(by_role["FA"]) == 7
    assert len(by_role["CP"]) == 1
    assert len(by_role["FO"]) == 1
    assert len(by_role["PC"]) == 1
    assert all(m.pairing for m in duty.crew)


def test_fdp_values_are_kept(duty):
    assert all(m.max_fdp and m.actual_fdp for m in duty.crew)


def test_personal_data_is_opt_in(duty):
    stripped = duty.to_dict()
    for member in stripped["crew"]:
        assert "phone" not in member
        assert "email" not in member
        assert "address" not in member

    full = duty.to_dict(include_personal_data=True)
    assert "phone" in full["crew"][0]
    assert "photo" in full["crew"][0]


def test_missing_contact_block_is_tolerated(duty):
    # The fixture has no Contact key; parsing must not invent one.
    assert duty.crew[0].phone == ""
    assert duty.crew[0].email == ""


def test_extract_json_array_handles_brackets_inside_strings():
    html = 'var X = [{"a": "]not an end["}, {"b": 2}]; var Y = 1;'
    raw = duty_details.extract_json_array_after(html, r"\bX\s*=")
    assert raw is not None
    assert json.loads(raw) == [{"a": "]not an end["}, {"b": 2}]


@pytest.mark.parametrize(
    "assignment",
    [
        "var DutyDetails =",
        "var DutyDetails=",
        "let DutyDetails\n=\n",
        "var x; var DutyDetails =",
    ],
)
def test_parse_tolerates_spacing_around_the_assignment(assignment):
    # The portal is not consistent: "var DutyDetails = [" on one page,
    # "var DutyDetails=[" on another. Matching the literal string with a space
    # silently returned no crew.
    payload = '[{"FlightNumber":"2700","CrewOnFlight":[{"ID":"1","Name":"A","PosQual":"CP"}]}]'
    html = f"<html><body><script>{assignment}{payload};</script></body></html>"
    duty = duty_details.parse_duty_details(html)
    assert duty is not None
    assert duty.flight_number == "2700"
    assert len(duty.crew) == 1
    assert duty.crew[0].id == "1"


def test_extract_json_array_returns_none_when_absent():
    assert duty_details.extract_json_array_after("<html></html>", r"\bDutyDetails\s*=") is None


def test_parse_returns_none_on_garbage():
    assert duty_details.parse_duty_details("var DutyDetails = [ {oops ]") is None
    assert duty_details.parse_duty_details("nothing here") is None


def test_extract_session_hash():
    html = 'window.sessionStorage.setItem("Hash","' + "a1" * 64 + '");'
    assert duty_details.extract_session_hash(html) == "a1" * 64


def test_extract_session_hash_missing():
    with pytest.raises(DutyDetailsError):
        duty_details.extract_session_hash("<html></html>")


def test_fetch_requires_event_id():
    with pytest.raises(DutyDetailsError):
        duty_details.fetch_duty_crew(_FakeSession(), "")


class _FakeSession:
    """A session with no eCrewHeader id (never logged in)."""

    headers: dict = {}
    ecrew_session_id = ""


def test_fetch_requires_login():
    with pytest.raises(DutyDetailsError):
        duty_details.fetch_duty_crew(_FakeSession(), EVENT_ID)


def test_fetch_issues_the_three_portal_calls():
    calls: list[tuple[str, str]] = []
    session = _RecordingSession(calls)
    duty = duty_details.fetch_duty_crew(session, EVENT_ID)

    assert [c[0] for c in calls] == [
        "GET /Dashboard",
        "GET /HomeIndex",
        "POST /DutyDetails/Retrieve",
        "GET /DutyDetails/<ed>",
    ]
    assert duty.flight_number == "463"
    assert len(duty.crew) == 10

    sent = json.loads(calls[2][1])
    assert sent["Key"] == "b2" * 64
    assert sent["Key"] and json.loads(sent["Data"])["id"] == EVENT_ID
    assert json.loads(sent["Data"]) == {
        "id": EVENT_ID,
        "crewID": "A",
        "timesIn": "2",
        "Port": "",
        "HotelIndex": "",
        "HotelInfo": {},
    }
    # The third call is GET DutyDetails/<ed> with dt + eCrewHeader as query params.
    assert "/DutyDetails/EDTOKEN" in calls[3][1]
    assert "dt=" in calls[3][1]
    assert "eCrewHeader=sess-1" in calls[3][1]

    # Retrieve must carry the Dashboard's verification token, not a stale one.
    assert json.loads(calls[2][1])["Key"] == "b2" * 64


DASHBOARD_HTML = (
    '<input name="__RequestVerificationToken" type="hidden" value="dash-token-42" />'
    '<script>sessionStorage.setItem("Hash","' + "b2" * 64 + '")</script>'
)


class _RecordingSession:
    def __init__(self, calls: list[tuple[str, str]]) -> None:
        self.calls = calls
        self.headers: dict = {}
        self.ecrew_session_id = "sess-1"

    def get(self, url: str, headers=None, timeout=None, params=None):
        if url.endswith("/Dashboard"):
            self.calls.append(("GET /Dashboard", url))
            return _Resp(200, DASHBOARD_HTML)
        if "HomeIndex" in url:
            # Required before DutyDetails/Retrieve: it registers the duty context.
            self.calls.append(("GET /HomeIndex", url))
            return _Resp(200, "var events = [];")
        query = urllib.parse.urlencode(params or {})
        self.calls.append(("GET /DutyDetails/<ed>", f"{url}?{query}"))
        return _Resp(200, FIXTURE.read_text(encoding="utf-8"))

    def post(self, url: str, data=None, headers=None, timeout=None):
        self.calls.append(("POST /DutyDetails/Retrieve", data))
        return _Resp(200, json.dumps({"ed": "EDTOKEN", "dt": {"id": "enc"}}))

    @property
    def cookies(self):
        return _Cookies()


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


class _Cookies:
    def get_dict(self):
        return {}


def test_find_event_id_needs_a_matching_flight():
    assert api_helpers.find_event_id("") == ""
    assert api_helpers.find_event_id("9999") == ""


def test_normalize_flight_number():
    assert api_helpers.normalize_flight_number("AH-462") == "AH462"
    assert api_helpers.normalize_flight_number(" 462 ") == "462"
    assert api_helpers.normalize_flight_number(None) == ""


def test_event_id_from_entry_reads_raw():
    class Entry:
        raw = json.dumps({"id": EVENT_ID})

    assert api_helpers.event_id_from_entry(Entry()) == EVENT_ID

    class NoRaw:
        raw = None

    assert api_helpers.event_id_from_entry(NoRaw()) == ""
