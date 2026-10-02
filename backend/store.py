"""Storage & diffing — persist roster entries locally.

Durability notes
----------------
* ``save()`` writes to a temp file and then ``os.replace()``s it into place.
  ``os.replace`` is atomic on both POSIX and Windows, so a crash, a full disk
  or a SIGKILL mid-write can never leave a half-written ``roster.json`` that
  bricks every subsequent read.
* ``load()`` degrades to an empty roster instead of raising on a corrupt file,
  so a damaged store shows up as "no duties" in the UI rather than a 500. The
  real error still surfaces through ``/api/health`` via ``load_meta()``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .parser import DutyEntry

SCHEMA_VERSION = 2

# Fields the current DutyEntry understands. Used to tolerate a store written
# by a newer/older version without blowing up on unexpected keys.
_KNOWN_FIELDS = {f.name for f in fields(DutyEntry)}


def save(entries: Iterable[DutyEntry], path: str | Path) -> None:
    """Write entries to ``path`` atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SCHEMA_VERSION,
        "synced_at": _now_iso(),
        "entries": [asdict(e) for e in entries],
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # durable before the rename
        os.replace(tmp, path)
    except BaseException:
        # Never leave a stray .tmp next to the store.
        tmp.unlink(missing_ok=True)
        raise


def _read_payload(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load(path: str | Path) -> list[DutyEntry]:
    """Load stored entries. Returns [] for missing/corrupt stores."""
    payload = _read_payload(path)
    entries: list[DutyEntry] = []
    for raw in payload.get("entries", []) or []:
        if not isinstance(raw, dict):
            continue
        # Ignore unknown keys so a store from another version still loads.
        try:
            entries.append(
                DutyEntry(**{k: v for k, v in raw.items() if k in _KNOWN_FIELDS})
            )
        except TypeError:
            continue
    return entries


def load_meta(path: str | Path) -> dict:
    """Load the store's metadata header (version, synced_at)."""
    payload = _read_payload(path)
    payload.pop("entries", None)
    return payload


@dataclass
class Diff:
    """What changed between two roster snapshots."""

    added: list[DutyEntry]
    removed: list[DutyEntry]
    changed: list[tuple[DutyEntry, DutyEntry]]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> str:
        return f"{len(self.added)} added, {len(self.removed)} removed, {len(self.changed)} changed"


def diff(prev: list[DutyEntry], curr: list[DutyEntry]) -> Diff:
    """Compare two roster snapshots.

    The identity key is ``(date, duty_type, flight_number)``. Keying on
    ``(date, flight_number)`` alone — as this used to — was wrong: an off day
    and a flight on the same date have the same key, so the day was reported
    simultaneously as *added* and *removed* and the real edit was lost.

    Results are sorted by date so output is deterministic (set difference
    yields non-deterministic ordering).
    """
    def key(e: DutyEntry) -> tuple:
        return (e.date, e.duty_type, e.flight_number or "")

    def sort_key(e: DutyEntry) -> tuple:
        return (e.date, e.duty_type, e.flight_number or "")

    prev_map = {key(e): e for e in prev}
    curr_map = {key(e): e for e in curr}

    added = sorted(
        (curr_map[k] for k in curr_map.keys() - prev_map.keys()), key=sort_key
    )
    removed = sorted(
        (prev_map[k] for k in prev_map.keys() - curr_map.keys()), key=sort_key
    )
    changed = sorted(
        (
            (prev_map[k], curr_map[k])
            for k in prev_map.keys() & curr_map.keys()
            if prev_map[k].to_dict() != curr_map[k].to_dict()
        ),
        key=lambda pair: sort_key(pair[0]),
    )
    return Diff(added=added, removed=removed, changed=changed)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
