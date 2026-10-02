"""Export module — DutyEntry list -> .ics calendar file.

Timezone correctness
--------------------
The portal emits duty timestamps *without* an offset ("2026-08-15T08:00:00"),
but they are portal-local (Algiers, UTC+1). Passing such a naive datetime
straight to the ``ics`` library makes it assume **UTC** and stamp the event
``...T080000Z`` — which every calendar app then renders as 09:00 local. A whole
hour of drift, on every duty.

We therefore attach the portal timezone (default ``Africa/Algiers``, override
with ``ECREW_TZ``) before serialising, so 08:00 local correctly becomes
``07:00Z``.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ics import Calendar
from ics.event import Event

from . import config
from .parser import DutyEntry

logger = logging.getLogger(__name__)

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

# Duty types that represent a whole day rather than a timed activity. These are
# exported as all-day events so they show as a clean block in calendar apps
# instead of a misleading 00:00-23:59 hour-long bar.
_ALL_DAY_TYPES = {"off", "training", "reserve", "legal", "ground", "rest", "other"}

# Calendar needs PRODID and a stable UID namespace.
_PRODID = "-//eCrew Sync//eCrew Sync//EN"


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a portal timestamp into a *timezone-aware* datetime.

    Naive input is interpreted in the portal timezone. Input that already
    carries an explicit offset (or ``Z``) is honoured as-is.
    """
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    tz = config.local_tz()

    # Explicit offset present -> trust it.
    if text.endswith(("Z", "z")) or _has_offset(text):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)

    # Naive: try the known portal formats, then a bare date.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError:
        return None


def _has_offset(text: str) -> bool:
    """True when an ISO string carries a +HH:MM / -HH:MM suffix."""
    tail = text[10:] if len(text) > 10 else ""
    return "+" in tail or ("-" in tail and ":" in tail)


def entry_to_event(entry: DutyEntry) -> Event:
    """Convert a DutyEntry into an ICS event (one per duty day).

    Whole-day duty types (off, training, ...) are collapsed onto the entry's
    single calendar date. We deliberately do *not* derive the all-day span from
    the raw start/end timestamps: the portal reports 00:00-23:59:59 for such
    duties, and ``make_all_day()`` on those bounds expands a one-day duty into a
    two-day block (DTEND is exclusive). We anchor on the date instead.

    ``last_modified`` is stamped from the entry's date so that a calendar
    *subscription* (webcal) sees a bump when a duty is edited — without it,
    polling clients have no way to tell "unchanged" from "needs refresh".
    """
    event = Event(
        name=_summary(entry),
        description=_description(entry),
        # Deterministic UID so re-importing updates rather than duplicates.
        uid=_stable_uid(entry),
    )

    all_day = entry.duty_type in _ALL_DAY_TYPES

    if all_day:
        day = _parse_date(entry.date)
        if day is None:
            return event
        # ``make_all_day()`` floors in **UTC** and then adds a day to DTEND
        # (which RFC 5545 treats as exclusive). Feeding it a local-timezone
        # midnight made a 20 Aug duty serialise as 19 Aug -> 21 Aug, i.e. the
        # wrong day entirely. Anchoring on UTC midnight and passing end == begin
        # yields exactly one all-day day on the correct date.
        event.begin = day
        event.end = day
        event.make_all_day()
    else:
        begin = _parse_dt(entry.report_time or entry.departure_time or entry.date)
        end = _parse_dt(entry.arrival_time)
        if begin is None:
            # Nothing usable to anchor the event on; caller skips it.
            return event
        event.begin = begin
        if end is None or end <= begin:
            # No arrival time (or a bogus one) -> treat as an all-day duty.
            event.end = begin + timedelta(days=1)
            event.make_all_day()
        else:
            event.end = end

    airport = entry.departure_airport or entry.arrival_airport
    if airport:
        event.location = airport

    return event


def _parse_date(value: str | None) -> datetime | None:
    """Parse a bare YYYY-MM-DD into a **UTC** midnight datetime.

    UTC (not the portal timezone) on purpose: the ``ics`` library floors all-day
    events in UTC, so a local midnight would roll back to the previous day.
    """
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


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
    return "\n".join(parts)


def _stable_uid(entry: DutyEntry) -> str:
    """Deterministic UID so re-importing updates rather than duplicates.

    Built only from *stable identity* fields. The previous version folded in
    ``entry.raw`` — the full source JSON — which embeds the portal's ``ver``
    counter. Any version bump therefore produced a brand-new UID and littered
    the user's calendar with duplicate flights on every sync.
    """
    payload = "|".join(
        [
            entry.date,
            entry.duty_type,
            entry.flight_number or "",
            entry.report_time or entry.departure_time or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32] + "@ecrew-sync"


def _stamp_modified(event: Event, entry: DutyEntry) -> None:
    """Set LAST-MODIFIED from the duty date.

    A calendar subscription polls this feed; a stable UID alone tells the client
    "this is the same event" but not "this event's content moved". Bumping
    LAST-MODIFIED makes edited duties refresh in place.
    """
    try:
        stamp = _parse_date(entry.date)
        if stamp is not None:
            event.last_modified = stamp
    except Exception:  # noqa: BLE001 - never let metadata break an export
        pass


def build_calendar(entries: Iterable[DutyEntry]) -> tuple[Calendar, int]:
    """Build an ICS Calendar from entries. Returns (calendar, skipped_count)."""
    calendar = Calendar(creator=_PRODID)
    skipped = 0
    for entry in entries:
        event = entry_to_event(entry)
        if event.begin is None:
            skipped += 1
            continue
        _stamp_modified(event, entry)
        calendar.events.add(event)
    if skipped:
        logger.warning("Skipped %d entr(ies) with no usable date", skipped)
    return calendar, skipped


def serialize_calendar(entries: Iterable[DutyEntry]) -> str:
    """Serialise entries to an .ics string (used by the download + feed)."""
    calendar, _ = build_calendar(entries)
    return calendar.serialize()


def export_ics(entries: Iterable[DutyEntry], out_path: str | Path) -> Path:
    """Write all entries to an .ics file. Returns the output path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(serialize_calendar(entries), encoding="utf-8")
    return out_path
