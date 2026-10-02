"""Qualifications, Licences & Medical Expiry tracking module."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import config


@dataclass
class Qualification:
    id: str
    name: str
    category: str  # Medical, Check/Simulator, Identity/Visas, Safety
    expiry_date: str  # YYYY-MM-DD
    issued_date: str | None = None
    authority: str = "Air Algérie / DAC"
    notes: str = ""

    def days_remaining(self) -> int:
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d").date()
            today = date.today()
            return (exp - today).days
        except Exception:
            return 999

    def status(self) -> str:
        d = self.days_remaining()
        if d < 0:
            return "EXPIRED"
        if d <= 30:
            return "CRITICAL"
        if d <= 60:
            return "WARNING"
        return "VALID"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["days_remaining"] = self.days_remaining()
        d["status"] = self.status()
        return d


DEFAULT_QUALIFICATIONS: list[dict[str, Any]] = [
    {
        "id": "med-class1",
        "name": "Visite Médicale Aéronautique (Classe 1)",
        "category": "Médical",
        "expiry_date": "2027-04-15",
        "issued_date": "2026-04-15",
        "authority": "CEMPN Alger",
        "notes": "Renouvellement annuel obligatoire",
    },
    {
        "id": "opc-sim",
        "name": "Contrôle Périodique Simulateur (OPC)",
        "category": "Compétence",
        "expiry_date": "2027-01-20",
        "issued_date": "2026-07-20",
        "authority": "Air Algérie Training Center",
        "notes": "Simulateur semestriel",
    },
    {
        "id": "line-check",
        "name": "Contrôle en Ligne (Line Check)",
        "category": "Compétence",
        "expiry_date": "2027-05-10",
        "issued_date": "2026-05-10",
        "authority": "Air Algérie - Chef de Division",
        "notes": "Contrôle annuel en vol commercial",
    },
    {
        "id": "type-rating",
        "name": "Qualification de Type (Type Rating)",
        "category": "Licence",
        "expiry_date": "2027-07-31",
        "issued_date": "2025-07-31",
        "authority": "Direction de l'Aviation Civile (DAC)",
        "notes": "Licence Pilote de Ligne / Professionnel",
    },
    {
        "id": "passport",
        "name": "Passeport Biométrique de Service",
        "category": "Documents",
        "expiry_date": "2029-09-18",
        "issued_date": "2024-09-18",
        "authority": "Ministère de l'Intérieur",
        "notes": "Validité internationale",
    },
    {
        "id": "visa-ksa",
        "name": "Visa Membre d'Équipage Arabie Saoudite",
        "category": "Documents",
        "expiry_date": "2027-08-30",
        "issued_date": "2026-08-30",
        "authority": "Ambassade d'Arabie Saoudite",
        "notes": "Entrées multiples Djeddah / Médine",
    },
    {
        "id": "security-badge",
        "name": "Badge Aéroportuaire & Sûreté (SGS)",
        "category": "Sûreté",
        "expiry_date": "2026-12-31",
        "issued_date": "2025-12-31",
        "authority": "SGS / DGSN Alger",
        "notes": "Accès Zone Réservée",
    },
    {
        "id": "safety-ditching",
        "name": "Sauvetage & Sécurité / Ditching (CSS)",
        "category": "Sécurité",
        "expiry_date": "2027-06-15",
        "issued_date": "2025-06-15",
        "authority": "Air Algérie Training Center",
        "notes": "Évacuation fumée, feu, amerrissage",
    },
]


def qualifications_file() -> Path:
    db = config.db_file()
    return db.parent / "qualifications.json"


def load_qualifications() -> list[Qualification]:
    path = qualifications_file()
    if not path.exists():
        save_qualifications([Qualification(**item) for item in DEFAULT_QUALIFICATIONS])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Qualification(**item) for item in data]
    except Exception:
        return [Qualification(**item) for item in DEFAULT_QUALIFICATIONS]


def save_qualifications(quals: list[Qualification]) -> None:
    path = qualifications_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump([asdict(q) for q in quals], f, indent=2, ensure_ascii=False)
