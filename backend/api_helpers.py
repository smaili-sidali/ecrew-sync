"""Resolve a flight number to the eCrew schedule event id it came from.

``DutyDetails/Retrieve`` is keyed by the DayPilot event id, not by the flight
number, so every consumer (API, CLI) has to resolve one from the other using the
last synced roster.
"""

from __future__ import annotations

import json
import re

from . import config, store


def normalize_flight_number(value: str | None) -> str:
    """Reduce a flight number to comparable alphanumerics: "AH-462" -> "AH462"."""
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def event_id_from_entry(entry: object) -> str:
    """Return the portal event id stored in a DutyEntry's ``raw`` payload."""
    raw = getattr(entry, "raw", None)
    if not raw:
        return ""
    event = raw
    if isinstance(raw, str):
        try:
            event = json.loads(raw)
        except ValueError:
            return ""
    if not isinstance(event, dict):
        return ""
    event_id = event.get("id")
    return event_id if isinstance(event_id, str) else ""


def find_event_id(flight_number: str, db_file: str | None = None) -> str:
    """First event id in the synced roster matching ``flight_number``."""
    wanted = normalize_flight_number(flight_number)
    if not wanted:
        return ""
    for entry in store.load(db_file or config.db_file()):
        if getattr(entry, "duty_type", None) != "flight":
            continue
        if normalize_flight_number(getattr(entry, "flight_number", None)) != wanted:
            continue
        event_id = event_id_from_entry(entry)
        if event_id:
            return event_id
    return ""
