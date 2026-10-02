"""Outbound notifications (Phase 1).

The app syncs unattended every few hours, so a failure that only shows up when
you happen to open the PWA is a failure you learn about too late. This module
POSTs a small JSON payload to ``ECREW_WEBHOOK_URL`` when the roster changes or
a sync fails.

Design constraints:

* **Never raises.** A webhook that is down must not break a sync, and must not
  turn a good roster into an error state. Failures are logged and swallowed.
* **Never blocks the sync thread for long.** Short timeout, and callers may run
  it on a daemon thread.
* **No secret in the payload.** Only duty data you already own.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import config

logger = logging.getLogger(__name__)


def _post(payload: dict[str, Any]) -> bool:
    """POST JSON to the configured webhook. Returns True on 2xx."""
    url = config.webhook_url()
    if not url:
        return False

    try:
        import requests

        resp = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "ecrew-sync/0.2"},
            timeout=config.webhook_timeout_s(),
        )
        if 200 <= resp.status_code < 300:
            logger.info("Webhook delivered (%s)", resp.status_code)
            return True
        logger.warning("Webhook returned HTTP %s", resp.status_code)
        return False
    except Exception as exc:  # noqa: BLE001 - notifications must never propagate
        logger.warning("Webhook delivery failed: %s", exc)
        return False


def notify_roster_change(change: dict) -> bool:
    """Notify that the roster changed. Honours ECREW_NOTIFY_ON_CHANGE."""
    if not change:
        return False
    if config.notify_on_change() and change.get("summary") in (None, ""):
        return False
    added = change.get("added") or []
    removed = change.get("removed") or []
    changed = change.get("changed") or []

    lines = [f"Roster updated: {change.get('summary', '?')}"]
    for e in added[:10]:
        lines.append(f"+ {e.get('date')} {e.get('duty_type')} {e.get('flight_number') or ''}".rstrip())
    for e in removed[:10]:
        lines.append(f"- {e.get('date')} {e.get('duty_type')} {e.get('flight_number') or ''}".rstrip())
    for pair in changed[:10]:
        after = pair.get("after", {})
        before = pair.get("before", {})
        lines.append(
            f"~ {after.get('date')} {after.get('duty_type')} "
            f"({before.get('departure_time')} -> {after.get('departure_time')})"
        )

    return _post(
        {
            "event": "roster_changed",
            "at": change.get("at"),
            "summary": change.get("summary"),
            "counts": {
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
            },
            "message": "\n".join(lines),
        }
    )


def notify_sync_error(error: str, context: str | None = None) -> bool:
    """Notify that a sync failed. Always sent (a failure is never 'no change')."""
    message = f"eCrew Sync failed: {error}"
    if context:
        message += f"\n{context}"
    return _post({"event": "sync_error", "message": message, "error": error})


def notify_contract_broken(report) -> bool:
    """Notify that the portal contract appears to have drifted."""
    status = getattr(report.status, "value", str(report.status))
    return _post(
        {
            "event": "contract_broken",
            "status": status,
            "detail": getattr(report, "detail", ""),
            "remedy": getattr(report, "remedy", ""),
            "message": f"eCrew portal contract may have changed ({status}). "
            f"{getattr(report, 'remedy', '')}",
        }
    )
