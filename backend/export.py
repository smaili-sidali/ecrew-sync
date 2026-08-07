"""Export module — DutyEntry list -> .ics calendar file."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from ics import Calendar
from ics.event import Event

from .parser import DutyEntry

_DUTY_LABELS = {
    "flight": "Flight",
    "off": "Off",
    "standby": "Standby",
    "training": "Training",
    "reserve": "Reserve",
    "legal": "Legal",
    "ground": "Ground",
    "hotel": "Layover",
    "rest": "Rest",
}


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def entry_to_event(entry: DutyEntry) -> Event:
    """Convert a DutyEntry into an ICS event (one per duty day)."""

    event = Event(
        name=_summary(entry),
        description=_description(entry),
        # Deterministic UID so re-exports don't create duplicates in a calendar.
        uid=_stable_uid(entry),
    )

    begin = _parse_dt(entry.report_time or entry.departure_time or entry.date)
    end = _parse_dt(entry.arrival_time)
    if begin is not None:
        event.begin = begin
    if end is not None:
        event.end = end
    else:
        event.make_all_day()

    airport = entry.departure_airport or entry.arrival_airport
    if airport is not None:
        event.location = airport

    return event


def _summary(entry: DutyEntry) -> str:
    label = _DUTY_LABELS.get(entry.duty_type, entry.duty_type.upper())
    if entry.duty_type == "flight" and entry.flight_number:
        return f"{label}: {entry.flight_number}"
    return label


def _description(entry: DutyEntry) -> str:
    parts = []
    if entry.flight_number and entry.duty_type != "flight":
        parts.append(f"Flight: {entry.flight_number}")
    legs = []
    if entry.departure_time:
        legs.append(f"Dep {entry.departure_time} {entry.departure_airport or ''}".rstrip())
    if entry.arrival_time:
        legs.append(f"Arr {entry.arrival_time} {entry.arrival_airport or ''}".rstrip())
    if legs:
        parts.append(" \u00b7 ".join(legs))
    if entry.layover_hotel:
        parts.append(f"Hotel: {entry.layover_hotel}")
    return "\n".join(parts) or None


def _stable_uid(entry: DutyEntry) -> str:
    raw = entry.raw if entry.raw is not None else ""
    payload = json_fingerprint(entry, raw)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32] + "@ecrew-sync"


def json_fingerprint(entry: DutyEntry, raw: str) -> str:
    return "|".join(
        [
            entry.date,
            entry.duty_type,
            entry.flight_number or "",
            entry.report_time or "",
            str(raw),
        ]
    )


def export_ics(entries: Iterable[DutyEntry], out_path: str | Path) -> Path:
    calendar = Calendar()
    for entry in entries:
        calendar.events.add(entry_to_event(entry))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(calendar.serialize(), encoding="utf-8")
    return out_path