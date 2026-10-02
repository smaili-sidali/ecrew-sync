"""Leave Balance, Vacation Tracking & Bidding Requests Module."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import config


@dataclass
class LeavePeriod:
    id: str
    type: str  # Congé Annuel, Récupération, Événement Familial, Maladie
    start_date: str
    end_date: str
    days: int
    status: str  # Accordé, En attente, Refusé
    remarks: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BiddingRequest:
    id: str
    period: str  # e.g. "Novembre 2026"
    request_type: str  # Repos souhaité, Rotation préférée, Éviter vol
    details: str
    submitted_date: str
    status: str  # Soumis, En traitement, Validé

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_LEAVE_DATA: dict[str, Any] = {
    "annual_entitlement": 30,
    "taken_days": 18,
    "remaining_days": 12,
    "seniority_years": 8,
    "leave_history": [
        {
            "id": "leave-2026-07",
            "type": "Congé Annuel (Période Estivale)",
            "start_date": "2026-07-15",
            "end_date": "2026-07-29",
            "days": 15,
            "status": "Accordé",
            "remarks": "Validé par Division des Vols",
        },
        {
            "id": "leave-2026-03",
            "type": "Congé Récupération",
            "start_date": "2026-03-10",
            "end_date": "2026-03-12",
            "days": 3,
            "status": "Accordé",
            "remarks": "Repos compensateur",
        },
        {
            "id": "leave-2026-12",
            "type": "Congé Annuel (Fin d'Année)",
            "start_date": "2026-12-24",
            "end_date": "2026-12-31",
            "days": 8,
            "status": "En attente",
            "remarks": "Demande posée sur eCrew Bidding",
        },
    ],
    "bidding_requests": [
        {
            "id": "bid-2026-11-01",
            "period": "Novembre 2026",
            "request_type": "Souhait de repos",
            "details": "Weekend du 14-15 Novembre 2026 bloqué",
            "submitted_date": "2026-09-25",
            "status": "Validé",
        },
        {
            "id": "bid-2026-11-02",
            "period": "Novembre 2026",
            "request_type": "Vol préféré",
            "details": "Rotation Long-Courrier Djeddah (AH462/463)",
            "submitted_date": "2026-09-28",
            "status": "En traitement",
        },
    ],
}


def leave_file() -> Path:
    db = config.db_file()
    return db.parent / "leave.json"


def load_leave_data() -> dict[str, Any]:
    path = leave_file()
    if not path.exists():
        save_leave_data(DEFAULT_LEAVE_DATA)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_LEAVE_DATA


def save_leave_data(data: dict[str, Any]) -> None:
    path = leave_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
