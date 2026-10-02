"""Portal contract canary (Phase 0/1).

The problem this solves
----------------------
The roster fragment is a reverse-engineered contract that nobody has confirmed
against the live portal (see NOTES.md). When it drifts, the failure is **silent
and delayed**: parsing raises, the store keeps serving last week's roster, and
you discover it on the morning you needed it.

This module classifies *how* the contract looks, so the failure is loud and
actionable instead. Each status maps to a specific remedy:

===========================  =========================================
``ContractStatus``           Meaning / what to do
===========================  =========================================
``OK``                       Contract intact — normal operation.
``LAZY_LOADED``              Container returned, no duty rows. The case
                             NOTES.md flags as most likely: the A1 view
                             lazy-loads via a follow-up AJAX call that
                             is still unknown. Capture it in DevTools.
``NO_EVENT_ARRAY``           No ``name = [...]`` block — variable renamed
                             or data inlined.
``UNRECOGNISED_FIELDS``      Events found but duty fields moved (renamed
                             keys). Update aliases in parser._get().
``SUSPICIOUSLY_FEW``         Fewer events than a real roster should have —
                             partial or truncated payload.
===========================  =========================================
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum

from . import config
from .parser import (
    DutyEntry,
    ParseError,
    _extract_events,
    _iter_events_blocks,
    parse_roster,
)

logger = logging.getLogger(__name__)


class ContractStatus(str, Enum):
    """How the fetched fragment relates to what the parser expects."""

    OK = "ok"
    DISABLED = "disabled"
    LAZY_LOADED = "lazy_loaded"
    NO_EVENT_ARRAY = "no_event_array"
    UNRECOGNISED_FIELDS = "unrecognised_fields"
    SUSPICIOUSLY_FEW = "suspiciously_few"
    PARSE_ERROR = "parse_error"


# Human-readable next step for each failure mode.
REMEDIES: dict[ContractStatus, str] = {
    ContractStatus.OK: "Portal contract looks intact.",
    ContractStatus.LAZY_LOADED: (
        "The A1 view came back but carried no duty rows — the roster is almost "
        "certainly lazy-loaded. Open 'My Schedule' in a browser, open DevTools > "
        "Network, and capture the follow-up XHR that populates the calendar. "
        "Add it to backend/fetch.py, then re-run login-test."
    ),
    ContractStatus.NO_EVENT_ARRAY: (
        "No 'name = [...]' array was found in the fragment. The portal either "
        "renamed the DayPilot variable or now inlines the data. Re-run recon "
        "(NOTES.md) and update parser._iter_events_blocks()."
    ),
    ContractStatus.UNRECOGNISED_FIELDS: (
        "Duty events were found but their fields did not yield usable dates, so "
        "the keys were probably renamed. Compare debug_roster_view.html against "
        "the fixture and extend the alias lists in parser._get()."
    ),
    ContractStatus.SUSPICIOUSLY_FEW: (
        "Fewer duty events than a real roster should contain — the payload may "
        "be truncated, paginated, or covering a shorter period than expected. "
        "Check the raw HTML before trusting the stored roster."
    ),
    ContractStatus.PARSE_ERROR: (
        "The parser could not build a roster from this fragment. "
        "debug_last_fetch.html has the raw HTML for inspection."
    ),
    ContractStatus.DISABLED: "Contract checking is disabled (ECREW_CONTRACT_CHECK=0).",
}


@dataclass
class ContractReport:
    """Outcome of one canary run. Safe to serialise into /api/health."""

    status: ContractStatus = ContractStatus.OK
    ok: bool = True
    event_count: int = 0
    entry_count: int = 0
    duty_types: dict[str, int] = field(default_factory=dict)
    detail: str = ""
    remedy: str = ""
    captured_html_bytes: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    def summary(self) -> str:
        if self.ok:
            return f"contract {self.status.value} ({self.entry_count} duties)"
        return f"CONTRACT {self.status.value}: {self.remedy}"


def check_fragment(html: str, *, min_events: int | None = None) -> ContractReport:
    """Inspect a raw roster fragment and classify it. Never raises."""
    if not config.contract_check_enabled():
        return ContractReport(
            status=ContractStatus.DISABLED,
            ok=True,
            remedy=REMEDIES[ContractStatus.DISABLED],
        )

    threshold = min_events if min_events is not None else config.contract_min_events()
    report = ContractReport(captured_html_bytes=len(html or ""))

    if not html or not html.strip():
        report.ok = False
        report.status = ContractStatus.NO_EVENT_ARRAY
        report.detail = "Empty fragment."
        report.remedy = REMEDIES[ContractStatus.NO_EVENT_ARRAY]
        return report

    # 1. Look at raw assignment blocks, not just _extract_events().
    #
    # _extract_events() deliberately returns None when no array looks
    # duty-like, which is exactly what happens when the portal renames the
    # event fields. To tell "the array is gone" apart from "the fields moved",
    # the canary inspects the blocks directly.
    raw_blocks = list(_iter_events_blocks(html))
    report.event_count = len(_extract_events(html) or [])
    has_dict_array = any(
        isinstance(parsed, list)
        and parsed
        and all(isinstance(x, dict) for x in parsed)
        for _name, parsed in raw_blocks
    )

    # 2. Can we build a roster?
    try:
        entries = parse_roster(html)
    except ParseError as exc:
        report.ok = False
        report.detail = str(exc)[:300]
        if has_dict_array:
            # The array is there, but its contents are not recognisable
            # duties -> the field names almost certainly changed.
            report.status = ContractStatus.UNRECOGNISED_FIELDS
        elif _looks_like_lazy_container(html):
            report.status = ContractStatus.LAZY_LOADED
        else:
            report.status = ContractStatus.NO_EVENT_ARRAY
        report.remedy = REMEDIES[report.status]
        return report

    report.entry_count = len(entries)
    for entry in entries:
        report.duty_types[entry.duty_type] = report.duty_types.get(entry.duty_type, 0) + 1

    # 3. Parsed fine, but is the volume plausible?
    if report.event_count < threshold:
        report.ok = False
        report.status = ContractStatus.SUSPICIOUSLY_FEW
        report.detail = (
            f"Only {report.event_count} duty-like event(s) found; "
            f"expected at least {threshold}."
        )
        report.remedy = REMEDIES[ContractStatus.SUSPICIOUSLY_FEW]
        return report

    return report


def check_entries(entries: list[DutyEntry], html: str = "") -> ContractReport:
    """Validate already-parsed entries (used by tests and the CLI)."""
    report = ContractReport(
        entry_count=len(entries),
        captured_html_bytes=len(html or ""),
    )
    for entry in entries:
        report.duty_types[entry.duty_type] = report.duty_types.get(entry.duty_type, 0) + 1
    if not entries:
        report.ok = False
        report.status = ContractStatus.LAZY_LOADED
        report.detail = "No duties parsed."
        report.remedy = REMEDIES[ContractStatus.LAZY_LOADED]
    return report


def _looks_like_lazy_container(html: str) -> bool:
    """Heuristic: an empty calendar shell rather than a broken payload.

    Looks for the markers a not-yet-populated DayPilot view carries: a calendar
    container div, a DayPilot script reference, and no duty data.
    """
    lowered = html.lower()
    return any(
        marker in lowered
        for marker in ("daypilot", "schedulercontainer", "dp.events", "calendarview")
    )


def raise_if_broken(report: ContractReport) -> None:
    """Log loudly when the contract has drifted.

    Called by the scheduler after every fetch. We log rather than raise: a
    contract drift must not crash a background thread, but it must be
    impossible to miss in the logs or /api/health.
    """
    if report.ok:
        logger.info("Contract canary: %s", report.summary())
        return
    logger.error("Contract canary FAILED: %s — %s", report.status.value, report.detail)
    logger.error("Remedy: %s", report.remedy)

