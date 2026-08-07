"""Parser — turn roster HTML into structured DutyEntry records.

The roster ("My Schedule", menu A1) is an HTML fragment retrieved via
    POST /eCrew/Dashboard/GetMenu   {"Menu": "A1"}
It embeds the duty data that drives the page's DayPilot calendar, exposed to
the site's JS as a dataset like:

    var InitialSchedulerEvents = [ { "id": "...", "start": "2026-08-15T08:00:00",
      "end": "...", "type": "Flight", "resource": "A", "text": "...", ... }, ... ];

Field shape derived from the site's own code (eCrewDayPilot.js):
  - type ∈ {Flight, Off, Standby, Training, Legal, Ground, Hotel, Rest, ...}
  - resource ∈ {"A" (own duty), "PUB", crew ids}
  - event id encodes [.., date, dutyDay, flight/route] (underscore separated)

parse_roster() accepts that JSON-ish fragment, or any HTML containing the
same event objects, and additionally falls back to a simple <table> layout
when present (e.g. anonymized fixtures).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

from bs4 import BeautifulSoup

# --- Duty types: site ``type`` -> normalized DutyEntry.duty_type -------------
_TYPE_MAP = {
    "flight": "flight",
    "flt": "flight",
    "f": "flight",
    "off": "off",
    "leave": "off",
    "onleave": "off",
    "rest": "off",
    "sick": "off",
    "standby": "standby",
    "stand-by": "standby",
    "sby": "standby",
    "training": "training",
    "trn": "training",
    "reserve": "reserve",
    "rsv": "reserve",
    "legal": "legal",
    "ground": "ground",
    "hotel": "hotel",
    "layover": "hotel",
}
_UNKNOWN_TYPE_LABEL = "other"


class ParseError(RuntimeError):
    pass


@dataclass
class DutyEntry:
    date: str
    duty_type: str
    flight_number: Optional[str] = None
    report_time: Optional[str] = None
    departure_time: Optional[str] = None
    departure_airport: Optional[str] = None
    arrival_time: Optional[str] = None
    arrival_airport: Optional[str] = None
    layover_hotel: Optional[str] = None
    layover_until: Optional[str] = None
    raw: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_duty_type(raw: str) -> str:
    return _TYPE_MAP.get(raw.strip().lower(), _UNKNOWN_TYPE_LABEL)


def _get(ev: dict, *keys: str, default: Any = None) -> Any:
    """Case-insensitive dict lookup; first key that exists wins."""
    lower = {k.lower(): k for k in ev}
    for key in keys:
        k = lower.get(key.lower())
        if k is not None:
            return ev[k]
    return default


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Extraction: the events array lives in an inline <script> as a JS literal.
# ---------------------------------------------------------------------------


def _iter_events_blocks(html: str):
    """Yield JSON arrays (or objects with an array member) from ``name = [...]``.

    Uses bracket-balancing instead of a regex so nested arrays inside event
    objects do not truncate the block.  Both ``var X = [...]`` and
    ``X = {...}`` shapes are tolerated.
    """
    pos = 0
    while True:
        m = _ASSIGN_RE.search(html, pos)
        if not m:
            return
        name, eq_start = m.group(1), m.end()
        # Only treat ``= `` immediately followed by [ or { as a candidate.
        if eq_start < len(html) and html[eq_start] in "[{":
            end = _scan_bracket(html, eq_start)
            if end is not None:
                body = html[eq_start : end + 1]
                parsed = _try_json(body)
                if parsed is None:
                    # JS objects have unquoted keys — retry with them quoted.
                    parsed = _try_json(_quote_js_keys(body))
                if parsed is not None:
                    if isinstance(parsed, list):
                        yield m.group(1), parsed
                    elif isinstance(parsed, dict):
                        for member in ("events", "schedulerEvents", "data", "duties"):
                            val = parsed.get(member)
                            if isinstance(val, list):
                                yield name + "." + member, val
                                break
                pos = end + 1
                continue
        pos = eq_start + 1


def _try_json(body: str):
    try:
        return json.loads(body)
    except ValueError:
        return None


def _quote_js_keys(text: str) -> str:
    """Quote bare unquoted JavaScript object keys (inside strings untouched)."""
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if (ch.isalpha() or ch == "_" or ch == "$"):
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            k = j
            while k < n and text[k].isspace():
                k += 1
            p = i - 1
            while p >= 0 and text[p].isspace():
                p -= 1
            is_bare_key = (
                p >= 0
                and text[p] in "{,"
                and k < n
                and text[k] == ":"
            )
            if is_bare_key:
                out.append('"')
                out.append(text[i:j])
                out.append('"')
            else:
                out.append(text[i:j])
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_ASSIGN_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*")


def _scan_bracket(html: str, open_idx: int) -> Optional[int]:
    """Return index of the matching closing bracket/brace, or None if unbalanced."""
    stack = []
    in_str = False
    i = open_idx
    while i < len(html):
        ch = html[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "[{":
                stack.append("]" if ch == "[" else "}")
            elif ch in "]}":
                if not stack:
                    return None
                if stack[-1] == ch:
                    stack.pop()
                    if not stack:
                        return i
                else:
                    return None
        i += 1
    return None


def _extract_events(html: str) -> Optional[list]:
    """Best-effort: return a list of event dicts from the fragment."""
    blocks = list(_iter_events_blocks(html))
    if not blocks:
        return None

    # Prefer the biggest list of dicts (that's the roster).
    best: Optional[list] = None
    for name, parsed in blocks:
        if not isinstance(parsed, list) or not parsed:
            continue
        if not all(isinstance(x, dict) for x in parsed):
            continue
        if best is None or len(parsed) > len(best):
            best = parsed
    return best


# ---------------------------------------------------------------------------
# Event dict -> DutyEntry
# ---------------------------------------------------------------------------


_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _event_to_entry(ev: dict) -> Optional[DutyEntry]:
    start = _clean(_get(ev, "start", "start_time", "date"))
    end = _clean(_get(ev, "end", "end_time"))
    if not start:
        return None

    date = start[:10]
    m = _DATE_RE.match(date)
    if not m:
        return None

    etype_raw = _clean(_get(ev, "type", "duty_type", "status")) or ""
    css = _clean(_get(ev, "css_class", "css"))
    if not etype_raw and css:
        # cssClass like "flight_event" -> "flight"
        etype_raw = css.replace("_event", "").replace("_published", "")
    duty_type = _norm_duty_type(etype_raw)

    entry = DutyEntry(
        date=date,
        duty_type=duty_type,
        report_time=start,
        departure_time=start,
        arrival_time=end,
        raw=json.dumps(ev, ensure_ascii=False, separators=(",", ":")),
    )

    # Flight number: prefer explicit field, then event id's last segment,
    # then a label looking like AH1234.
    flt = _clean(_get(ev, "flight_no", "flt_no", "flt", "fnum", "pairing"))
    if not flt:
        eid = _clean(_get(ev, "id"))
        if eid:
            tail = eid.split("_")[-1]
            if re.search(r"[A-Z]{2}\d+", tail):
                flt = tail
    if not flt:
        text = _clean(_get(ev, "text", "title"))
        if text:
            fm = re.search(r"\b([A-Z]{2}\d{3,4})\b", text)
            if fm:
                flt = fm.group(1)
    if flt:
        entry.flight_number = flt

    # Airports: try structured fields, then the location string ("ALG / ORN").
    dep_apt = _clean(_get(ev, "departure_airport", "dep_airport", "orig_apt", "origin"))
    arr_apt = _clean(_get(ev, "arrival_airport", "arr_airport", "dest_apt", "destination"))
    if not dep_apt and not arr_apt:
        location = _clean(_get(ev, "location", "port", "route"))
        if location:
            codes = re.findall(r"\b[A-Z]{3}\b", location)
            if codes:
                dep_apt, arr_apt = codes[0], (codes[1] if len(codes) > 1 else None)
    entry.departure_airport = dep_apt
    entry.arrival_airport = arr_apt

    # Layover hotel (Hotel-type events carry it).
    if duty_type == "hotel":
        entry.layover_hotel = _clean(
            _get(ev, "hotel_info", "hotel", "location", default=_get(ev, "name"))
        )
        entry.layover_until = end

    return entry


# ---------------------------------------------------------------------------
# Table fallback (anonymized / legacy layouts)
# ---------------------------------------------------------------------------


def _parse_table(html: str) -> list[DutyEntry]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []
    rows = table.find("tbody") or table
    entries: list[DutyEntry] = []
    for tr in rows.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 2:
            continue
        date = cells[0][:10]
        if not _DATE_RE.match(date):
            continue
        entries.append(
            DutyEntry(
                date=date,
                duty_type=_norm_duty_type(cells[1]),
                flight_number=cells[2] if len(cells) > 2 else None,
                departure_time=cells[3] if len(cells) > 3 else None,
                arrival_time=cells[4] if len(cells) > 4 else None,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_roster(html: str) -> list[DutyEntry]:
    """Parse roster HTML into a list of DutyEntry.

    Raises ParseError when nothing roster-like is found, with an actionable
    message (the CLI already dumps the raw HTML to debug_last_fetch.html on
    failure, so a new selector can be derived quickly).
    """
    if not html or not html.strip():
        raise ParseError("Empty roster HTML.")

    events = _extract_events(html)
    entries: list[DutyEntry] = []
    if events:
        for ev in events:
            entry = _event_to_entry(ev)
            if entry is not None:
                entries.append(entry)

    if not entries:
        entries = _parse_table(html)

    if not entries:
        raise ParseError(
            "No roster events found in HTML. The portal layout may have changed "
            "or the schedule is empty. Run `python -m cli.main sync` to capture "
            "the raw fragment (debug_last_fetch.html) and inspect it."
        )

    # De-duplicate identical rows while preserving order.
    seen = set()
    unique: list[DutyEntry] = []
    for entry in entries:
        key = (entry.date, entry.duty_type, entry.flight_number or "", entry.raw or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def save_fixture(html: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)