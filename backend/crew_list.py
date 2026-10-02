"""Crew List & Dispatch Report module — manages flight crew rosters (Cockpit & Cabin).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CrewMember:
    id: str
    name: str
    role: str  # CDB (Captain), OPL (First Officer), CC (Chief Cabin Crew), PNC (Flight Attendant)
    code: str  # CP, FO, PU, FA
    is_user: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "code": self.code,
            "is_user": self.is_user,
        }


# Standard Air Algérie representative crew rosters per fleet / flight number
FLIGHT_CREW_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "462": [
        {"name": "B. MEZIANE", "role": "Commandant de bord", "code": "CDB", "id": "18420"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "S. HAMIDI", "role": "Chef de cabine (CC)", "code": "CC", "id": "24110"},
        {"name": "K. BELKACEM", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "41052"},
        {"name": "F. BOUZID", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "42189"},
        {"name": "M. TALEB", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "43901"},
    ],
    "463": [
        {"name": "B. MEZIANE", "role": "Commandant de bord", "code": "CDB", "id": "18420"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "S. HAMIDI", "role": "Chef de cabine (CC)", "code": "CC", "id": "24110"},
        {"name": "K. BELKACEM", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "41052"},
        {"name": "F. BOUZID", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "42189"},
        {"name": "M. TALEB", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "43901"},
    ],
    "3156": [
        {"name": "R. BENALI", "role": "Commandant de bord", "code": "CDB", "id": "16205"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "Y. LARBI", "role": "Renfort Long-Courrier (RFO)", "code": "OPL", "id": "38210"},
        {"name": "H. CHERIF", "role": "Chef de cabine principal (CCP)", "code": "CCP", "id": "21950"},
        {"name": "N. SAIDI", "role": "Chef de cabine (CC)", "code": "CC", "id": "26400"},
        {"name": "L. KHALDI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "44120"},
        {"name": "I. DAHMANI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "45230"},
        {"name": "T. AMARA", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "45690"},
    ],
    "3157": [
        {"name": "R. BENALI", "role": "Commandant de bord", "code": "CDB", "id": "16205"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "Y. LARBI", "role": "Renfort Long-Courrier (RFO)", "code": "OPL", "id": "38210"},
        {"name": "H. CHERIF", "role": "Chef de cabine principal (CCP)", "code": "CCP", "id": "21950"},
        {"name": "N. SAIDI", "role": "Chef de cabine (CC)", "code": "CC", "id": "26400"},
        {"name": "L. KHALDI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "44120"},
        {"name": "I. DAHMANI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "45230"},
        {"name": "T. AMARA", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "45690"},
    ],
    "5360": [
        {"name": "M. KACIMI", "role": "Commandant de bord", "code": "CDB", "id": "15112"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "K. OUAHAB", "role": "Renfort Long-Courrier (RFO)", "code": "OPL", "id": "37119"},
        {"name": "A. BELHADJ", "role": "Chef de cabine principal (CCP)", "code": "CCP", "id": "20450"},
        {"name": "O. MANSOURI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "43210"},
        {"name": "Z. GACEM", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "44560"},
        {"name": "S. REZKI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "46100"},
    ],
    "5361": [
        {"name": "M. KACIMI", "role": "Commandant de bord", "code": "CDB", "id": "15112"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "K. OUAHAB", "role": "Renfort Long-Courrier (RFO)", "code": "OPL", "id": "37119"},
        {"name": "A. BELHADJ", "role": "Chef de cabine principal (CCP)", "code": "CCP", "id": "20450"},
        {"name": "O. MANSOURI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "43210"},
        {"name": "Z. GACEM", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "44560"},
        {"name": "S. REZKI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "46100"},
    ],
    "6222": [
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "D. CHABANE", "role": "Commandant de bord", "code": "CDB", "id": "19320"},
        {"name": "N. BOURAS", "role": "Chef de cabine (CC)", "code": "CC", "id": "25890"},
        {"name": "W. HADDAD", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "42301"},
    ],
    "6254": [
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "N. GUERFI", "role": "Commandant de bord", "code": "CDB", "id": "18940"},
        {"name": "M. KHELIF", "role": "Chef de cabine (CC)", "code": "CC", "id": "27120"},
        {"name": "A. BRAHIMI", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "43980"},
    ],
}


def get_crew_for_flight(flight_number: str) -> list[dict[str, Any]]:
    """Return crew composition for a flight number."""
    clean_no = flight_number.replace("AH", "").replace(" ", "").strip()
    # Direct match or fuzzy
    if clean_no in FLIGHT_CREW_REGISTRY:
        return FLIGHT_CREW_REGISTRY[clean_no]

    # Generic fallback crew
    return [
        {"name": "CDB en cours d'assignation", "role": "Commandant de bord", "code": "CDB", "id": "—"},
        {"name": "A. ZERROUKI (Vous)", "role": "Copilote (OPL)", "code": "OPL", "id": "35739", "is_user": True},
        {"name": "CC en cours d'assignation", "role": "Chef de cabine", "code": "CC", "id": "—"},
        {"name": "PNC équipage cabine", "role": "Personnel Navigant Commercial", "code": "PNC", "id": "—"},
    ]
