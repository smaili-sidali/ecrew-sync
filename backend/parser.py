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
from dataclasses import asdict, dataclass
from typing import Any

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
    flight_number: str | None = None
    report_time: str | None = None
    departure_time: str | None = None
    departure_airport: str | None = None
    arrival_time: str | None = None
    arrival_airport: str | None = None
    layover_hotel: str | None = None
    layover_until: str | None = None
    raw: str | None = None

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


def _clean(value: Any) -> str | None:
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
                    # JS literals: bare keys and/or single quotes, and often a
                    # trailing comma before a closing bracket.
                    parsed = _try_json(_strip_trailing_commas(_normalize_js(body)))
                if parsed is None:
                    parsed = _try_json(_strip_trailing_commas(body))
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


def _strip_trailing_commas(text: str) -> str:
    """Remove commas that directly precede a closing ] or } (valid JS, not JSON)."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _try_json(body: str):
    try:
        return json.loads(body)
    except ValueError:
        return None


def _normalize_js(body: str) -> str:
    """Make a JavaScript object literal acceptable to ``json.loads``.

    Handles the two things that commonly differ from JSON in inline portal
    scripts: bare unquoted keys, and single-quoted string values.
    """
    quoted = _quote_js_keys(body)
    return _single_to_double_quotes(quoted)


def _single_to_double_quotes(text: str) -> str:
    """Rewrite 'single quoted' JS strings as "double quoted".

    Quote characters that appear inside a double-quoted string are left alone,
    and escaped quotes are handled. This is a pragmatic transform: a lone
    apostrophe inside a double-quoted value is the common case and is safe.
    """
    out = []
    i = 0
    n = len(text)
    in_dq = False
    while i < n:
        ch = text[i]
        if in_dq:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_dq = False
            i += 1
            continue
        if ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            # Copy the single-quoted string across, re-quoted as double.
            j = i + 1
            buf = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    nxt = text[j + 1]
                    buf.append('"' if nxt == "'" else nxt)
                    j += 2
                    continue
                if c == "'":
                    break
                if c == '"':
                    buf.append('\\"')
                    j += 1
                    continue
                buf.append(c)
                j += 1
            out.append('"' + "".join(buf) + '"')
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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


def _scan_bracket(html: str, open_idx: int) -> int | None:
    """Return index of the matching closing bracket/brace, or None if unbalanced.

    Tracks the active quote character so that brackets *inside* strings are
    ignored, for both "double" and 'single' quoted JavaScript.
    """
    stack = []
    quote: str | None = None
    i = open_idx
    while i < len(html):
        ch = html[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in "\"'":
                quote = ch
            elif ch == "/" and html[i : i + 2] in ("//", "/*"):
                # Skip a line/block comment so stray brackets inside it are
                # not counted.
                if html[i : i + 2] == "//":
                    nl = html.find("\n", i)
                    i = len(html) if nl == -1 else nl
                    continue
                end_c = html.find("*/", i)
                i = len(html) if end_c == -1 else end_c + 2
                continue
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


def _extract_events(html: str) -> list | None:
    """Best-effort: return the most roster-like list of event dicts.

    Scoring by list length alone is fragile: a page can easily carry a longer
    array of something else (airports, crew ids, legend entries). We instead
    score each candidate on how many of its dicts look like a DayPilot duty
    (a parsable start date, plus a type/id/text), and only fall back to raw
    length as a tie-breaker.
    """
    blocks = list(_iter_events_blocks(html))
    if not blocks:
        return None

    best: list | None = None
    best_score: tuple[int, int] = (-1, -1)
    for _name, parsed in blocks:
        if not isinstance(parsed, list) or not parsed:
            continue
        if not all(isinstance(x, dict) for x in parsed):
            continue
        score = _roster_score(parsed)
        if score > best_score:
            best, best_score = parsed, score

    # Only accept a block that actually contained recognisable duties.
    if best is None or best_score[0] == 0:
        return None
    return best


# Keys that mark a dict as a DayPilot duty event.
_EVENT_HINT_KEYS = ("start", "end", "type", "id", "text", "resource", "location")


def _roster_score(events: list) -> tuple[int, int]:
    """(number of duty-like dicts, total size) — used to rank candidate arrays."""
    duty_like = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        has_date = _clean(_get(ev, "start", "start_time", "date")) is not None
        if not has_date:
            has_date = _DATE_RE.search(str(_get(ev, "id", default="") or "")) is not None
        if not has_date:
            continue
        # A date alone is not enough — require at least one more event-ish key
        # so arrays of {"date": ..., "value": ...} statistics are not mistaken
        # for the roster.
        extras = sum(1 for k in _EVENT_HINT_KEYS if _get(ev, k) is not None)
        if extras >= 2:
            duty_like += 1
    return (duty_like, len(events))


# ---------------------------------------------------------------------------
# Event dict -> DutyEntry
# ---------------------------------------------------------------------------


_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _event_to_entry(ev: dict) -> DutyEntry | None:
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

    # The portal types some flights "Default" instead of "Flight". Their event id
    # ("35739on2026-07-3102:15:00_17013_17010_137979179576_135_17013") carries a
    # non-zero CRRoute, where hotels have 0: the only reliable way to keep a real
    # flight out of the "other" bucket.
    if duty_type == "other":
        eid = _clean(_get(ev, "id"))
        if eid:
            cr_route = next((s for s in eid.split("_")[1:] if re.fullmatch(r"\d{6,}", s)), None)
            if cr_route and cr_route != "0":
                duty_type = "flight"

    entry = DutyEntry(
        date=date,
        duty_type=duty_type,
        report_time=start,
        departure_time=start,
        arrival_time=end,
        raw=json.dumps(ev, ensure_ascii=False, separators=(",", ":")),
    )

    # Flight number. eCrew uses bare numbers ("2700"), no airline prefix, and the
    # last event-id segment is a date key ("17079") - not the flight. The label is
    # "2700\r\nALG-YUL": the number is the first token of the first line.
    flt = _clean(_get(ev, "flight_no", "flt_no", "flt", "fnum", "pairing"))
    if not flt:
        eid = _clean(_get(ev, "id"))
        if eid:
            for segment in reversed(eid.split("_")):
                if re.fullmatch(r"[A-Z]{2}\d{3,4}", segment):
                    flt = segment
                    break
    if not flt:
        text = _clean(_get(ev, "text", "title"))
        if text:
            first_line = re.split(r"[\r\n]+", text)[0]
            bare = re.match(r"^\s*(\d{3,4})\b", first_line)
            if bare:
                flt = bare.group(1)
            else:
                pm = re.search(r"\b([A-Z]{2}\d{3,4})\b", first_line)
                if pm:
                    flt = pm.group(1)
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
