"""Storage & diffing — persist roster entries locally."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .parser import DutyEntry


def save(entries: Iterable[DutyEntry], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "synced_at": _now_iso(), "entries": [asdict(e) for e in entries]}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load(path: str | Path) -> list[DutyEntry]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return [DutyEntry(**e) for e in payload.get("entries", [])]


def load_meta(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


@dataclass
class Diff:
    added: list[DutyEntry]
    removed: list[DutyEntry]
    changed: list[tuple[DutyEntry, DutyEntry]]


def diff(prev: list[DutyEntry], curr: list[DutyEntry]) -> Diff:
    def key(e: DutyEntry) -> tuple:
        return (e.date, e.flight_number or "")

    prev_map = {key(e): e for e in prev}
    curr_map = {key(e): e for e in curr}
    added = [curr_map[k] for k in curr_map.keys() - prev_map.keys()]
    removed = [prev_map[k] for k in prev_map.keys() - curr_map.keys()]
    changed = [
        (prev_map[k], curr_map[k])
        for k in prev_map.keys() & curr_map.keys()
        if prev_map[k].to_dict() != curr_map[k].to_dict()
    ]
    return Diff(added=added, removed=removed, changed=changed)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")