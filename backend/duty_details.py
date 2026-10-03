"""Duty details & crew composition for a single flight.

Reverse-engineered from the live portal (verified 2026-10-03 against a browser
capture of ``https://ecrew.airalgerie.dz/eCrew/Dashboard``):

1. ``GET /eCrew/Dashboard`` renders the per-session key used by the detail call:
   ``window.sessionStorage.setItem("Hash", "<128 hex>")``.
2. ``POST /eCrew/DutyDetails/Retrieve`` with ``{"Key": <hash>, "Data": "<json>"}``
   where ``Data`` is ``{"id": <event id>, "crewID": "A", "timesIn": "2", ...}``.
   It answers ``{"ed": "<route token>", "dt": {...}}``.
3. ``GET /eCrew/DutyDetails/<ed>?dt=<urlencoded dt>&eCrewHeader=<session id>``
   returns an HTML document embedding ``var DutyDetails = [ { CrewOnFlight: [...] } ]``.

The event id comes from the schedule parser (``entry.raw`` -> ``id``), e.g.
``35739on2026-10-0505:35:00_17079_17075_137979246130_335_17079``. Note the crew
payload carries colleagues' personal data (home address, mobile, e-mail, photo);
callers decide what to keep.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from . import config
from .auth import ORIGIN, TIMEOUT, _extract_verification_token, get_session_id

_RE_SESSION_HASH = re.compile(
    r"""setItem\(\s*["']Hash["']\s*,\s*["']([0-9a-fA-F]{64,})["']\s*\)""",
)
_RE_ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"


class DutyDetailsError(RuntimeError):
    """The portal did not return a usable duty/crew payload."""


@dataclass(frozen=True)
class CrewMember:
    id: str
    name: str
    role: str
    initials: str = ""
    aircraft: str = ""
    base: str = ""
    is_pic: bool = False
    pairing: str = ""
    max_fdp: str = ""
    actual_fdp: str = ""
    checked_in: bool = False
    nationality: str = ""
    seniority: str = ""
    photo: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""

    def to_dict(self, include_personal_data: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "initials": self.initials,
            "aircraft": self.aircraft,
            "base": self.base,
            "is_pic": self.is_pic,
            "pairing": self.pairing,
            "max_fdp": self.max_fdp,
            "actual_fdp": self.actual_fdp,
            "checked_in": self.checked_in,
        }
        if include_personal_data:
            data.update(
                {
                    "nationality": self.nationality,
                    "seniority": self.seniority,
                    "photo": self.photo,
                    "phone": self.phone,
                    "email": self.email,
                    "address": self.address,
                }
            )
        return data


@dataclass(frozen=True)
class DutyLeg:
    flight_number: str = ""
    date: str = ""
    aircraft_type: str = ""
    registration: str = ""
    departure: str = ""
    arrival: str = ""
    departure_name: str = ""
    arrival_name: str = ""
    report_time: str = ""
    debrief_time: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    gate: str = ""
    stand: str = ""
    pax: str = ""
    distance: str = ""
    delay: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "flight_number": self.flight_number,
            "date": self.date,
            "aircraft_type": self.aircraft_type,
            "registration": self.registration,
            "departure": self.departure,
            "arrival": self.arrival,
            "departure_name": self.departure_name,
            "arrival_name": self.arrival_name,
            "report_time": self.report_time,
            "debrief_time": self.debrief_time,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "gate": self.gate,
            "stand": self.stand,
            "pax": self.pax,
            "distance": self.distance,
            "delay": self.delay,
        }


@dataclass(frozen=True)
class DutyDetails:
    flight_number: str = ""
    legs: list[DutyLeg] = field(default_factory=list)
    crew: list[CrewMember] = field(default_factory=list)

    def to_dict(self, include_personal_data: bool = False) -> dict[str, Any]:
        return {
            "flight_number": self.flight_number,
            "legs": [leg.to_dict() for leg in self.legs],
            "crew": [m.to_dict(include_personal_data) for m in self.crew],
        }


def app_base() -> str:
    base = config.base_url().rstrip("/")
    if base.endswith("/ecrew"):
        return base[: -len("/ecrew")] + "/eCrew"
    return base


def _s(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def extract_session_hash(html: str) -> str:
    """Return the per-session key the portal stores as sessionStorage.Hash."""
    m = _RE_SESSION_HASH.search(html or "")
    if not m:
        raise DutyDetailsError("Session key (Hash) absent from the eCrew Dashboard page.")
    return m.group(1)


def extract_json_array_after(html: str, pattern: str) -> str | None:
    """Slice the JSON array literal that follows ``pattern``, string-aware.

    ``pattern`` is a regex whose match must end right before the opening
    bracket - the portal is not consistent on spacing (``var DutyDetails = [{``
    on one page, ``var DutyDetails=[{`` on another).
    """
    text = html or ""
    found = re.search(pattern, text)
    if not found:
        return None
    start = found.end()
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "[":
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_duty_details(html: str) -> DutyDetails | None:
    """Parse ``var DutyDetails = [...]`` into a :class:`DutyDetails`."""
    raw = extract_json_array_after(html, r"\bDutyDetails\s*=")
    if not raw:
        return None
    try:
        legs_raw = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(legs_raw, list) or not legs_raw:
        return None

    legs: list[DutyLeg] = []
    crew: list[CrewMember] = []
    seen: set[str] = set()

    for leg_raw in legs_raw:
        if not isinstance(leg_raw, dict):
            continue
        legs.append(
            DutyLeg(
                flight_number=_s(leg_raw.get("FlightNumber")),
                date=_s(leg_raw.get("Date")),
                aircraft_type=_s(leg_raw.get("AcType")),
                registration=_s(leg_raw.get("Registration")),
                departure=_s(leg_raw.get("DepStation")),
                arrival=_s(leg_raw.get("ArrStation")),
                departure_name=_s(leg_raw.get("DepStationDescription")),
                arrival_name=_s(leg_raw.get("ArrStationDescription")),
                report_time=_s(leg_raw.get("StartTime")),
                debrief_time=_s(leg_raw.get("EndTime")),
                departure_time=_s(leg_raw.get("LegStartTime")),
                arrival_time=_s(leg_raw.get("LegEndTime")),
                gate=_s(leg_raw.get("Gate")),
                stand=_s(leg_raw.get("Stand")),
                pax=_s(leg_raw.get("ExpPax")),
                distance=_s(leg_raw.get("Distance")),
                delay=_s(leg_raw.get("Delay")),
            )
        )

        members = leg_raw.get("CrewOnFlight")
        if not isinstance(members, list):
            continue
        for member in members:
            if not isinstance(member, dict):
                continue
            crew_id = _s(member.get("ID"))
            if not crew_id or crew_id in seen:
                continue
            seen.add(crew_id)
            contact = member.get("Contact")
            contact = contact if isinstance(contact, dict) else {}
            photo = member.get("CrewPhoto")
            photo = photo if isinstance(photo, str) else ""
            crew.append(
                CrewMember(
                    id=crew_id,
                    name=_s(member.get("Name")),
                    role=_s(member.get("PosQual")),
                    initials=_s(member.get("Initials")),
                    aircraft=_s(member.get("AcQual")),
                    base=_s(member.get("BaseQual")),
                    is_pic=bool(member.get("IsPilotInCommand"))
                    or _s(member.get("Pic")).upper() == "PIC",
                    pairing=_s(member.get("STRoute")),
                    max_fdp=_s(member.get("MaxFDP")),
                    actual_fdp=_s(member.get("ActualFDP")),
                    checked_in=member.get("CheckedIn") is True,
                    nationality=_s(member.get("Nationality")),
                    seniority=_s(member.get("CrewSeniority")),
                    photo=photo,
                    phone=_s(contact.get("Phone")),
                    email=_s(contact.get("Email")),
                    address=_s(contact.get("Address")),
                )
            )

    return DutyDetails(
        flight_number=legs[0].flight_number if legs else "",
        legs=legs,
        crew=crew,
    )


def fetch_duty_crew(
    session: requests.Session,
    event_id: str,
    crew_resource: str = "A",
    times_in: str = "2",
) -> DutyDetails:
    """Fetch the crew of one flight. The session must already be logged in.

    ``event_id`` is the schedule event id (``entry.raw`` -> ``id``).
    """
    if not event_id:
        raise DutyDetailsError("Missing event id: cannot resolve the crew for this flight.")

    session_id = get_session_id(session)
    if not session_id:
        raise DutyDetailsError("Not logged in: no eCrewHeader session id.")

    base = app_base()

    dash = session.get(
        f"{base}/Dashboard",
        headers={"Referer": config.base_url(), "Accept": _RE_ACCEPT_HTML},
        timeout=TIMEOUT,
    )
    if dash.status_code != 200:
        raise DutyDetailsError(f"Dashboard returned HTTP {dash.status_code}")
    session_hash = extract_session_hash(dash.text)

    # Le jeton de verification tourne a chaque page : c'est celui du Dashboard
    # qui doit accompanyer les appels suivants. Le header de session ne le
    # contient pas (il n'est pose que sur le POST de login), d'ou l'extraction.
    try:
        active_token = _extract_verification_token(dash.text)
    except Exception as exc:  # pragma: no cover - layout change
        raise DutyDetailsError(f"Verification token absent du Dashboard: {exc}") from exc

    # HomeIndex d'abord : c'est lui qui enregistre le contexte du planning et le
    # Hash cote serveur. Sans cet appel, Dashboard/Retrieve renvoie 400 "Another
    # active session" alors que le login a reussi. Un 400 ici est tolere (le
    # portail le renvoie parfois), l'etape suivante est celle qui compte.
    session.get(
        f"{base}/Dashboard/HomeIndex",
        params={"eCrewHeader": session_id},
        headers={"Referer": f"{base}/Dashboard", "Accept": _RE_ACCEPT_HTML},
        timeout=TIMEOUT,
    )

    duty_data = {
        "id": event_id,
        "crewID": crew_resource or "A",
        "timesIn": str(times_in or "2"),
        "Port": "",
        "HotelIndex": "",
        "HotelInfo": {},
    }
    home_referer = f"{base}/Dashboard/HomeIndex?eCrewHeader={session_id}"

    retrieve = session.post(
        f"{base}/DutyDetails/Retrieve",
        data=json.dumps({"Key": session_hash, "Data": json.dumps(duty_data)}),
        headers={
            "Content-Type": "application/json",
            "eCrewHeader": session_id,
            "ecrewheader": session_id,
            "RequestVerificationToken": active_token,
            "Origin": ORIGIN,
            "Referer": home_referer,
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=TIMEOUT,
    )
    if retrieve.status_code != 200:
        raise DutyDetailsError(f"DutyDetails/Retrieve returned HTTP {retrieve.status_code}")
    try:
        token = retrieve.json()
    except ValueError as exc:
        raise DutyDetailsError("DutyDetails/Retrieve returned an unreadable body.") from exc
    if not isinstance(token, dict) or not token.get("ed") or not token.get("dt"):
        raise DutyDetailsError("Portal returned no duty token for this flight.")

    detail = session.get(
        f"{base}/DutyDetails/{token['ed']}",
        params={"dt": json.dumps(token["dt"]), "eCrewHeader": session_id},
        headers={
            "eCrewHeader": session_id,
            "ecrewheader": session_id,
            "Referer": home_referer,
            "Accept": _RE_ACCEPT_HTML,
        },
        timeout=TIMEOUT,
    )
    if detail.status_code != 200:
        raise DutyDetailsError(f"DutyDetails page returned HTTP {detail.status_code}")

    duty = parse_duty_details(detail.text)
    if duty is None or not duty.crew:
        raise DutyDetailsError("Portal returned no crew members for this flight.")
    return duty


def fetch_duty_crew_with_login(
    event_id: str,
    crew_resource: str = "A",
    times_in: str = "2",
    base_url: str | None = None,
) -> DutyDetails:
    """Open a dedicated eCrew session, fetch the crew, then release the lock.

    The portal allows a single active session per crew id and a roster sync
    releases it on the way out, so the crew lookup cannot borrow the scheduler's
    session. Same shape as the mobile client: log in, ask, log out.
    """
    from . import auth as _auth

    session = _auth.get_session()
    try:
        _auth.login(session, **_auth.Credentials.from_env().__dict__, base_url=base_url or config.base_url())
        return fetch_duty_crew(session, event_id, crew_resource, times_in)
    finally:
        _auth.logout(session, base_url=base_url or config.base_url())
