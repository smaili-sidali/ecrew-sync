"""Layover and Hotel Logistics module — extracts hotel details, shuttle pick-up times,
and contacts directly from roster data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from datetime import datetime


@dataclass
class Layover:
    id: str
    city: str
    airport: str
    hotel_name: str
    check_in: str
    check_out: str
    duration_str: str
    pickup_airport: str | None = None
    pickup_hotel: str | None = None
    address: str | None = None
    phone: str | None = None
    maps_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "city": self.city,
            "airport": self.airport,
            "hotel_name": self.hotel_name,
            "check_in": self.check_in,
            "check_out": self.check_out,
            "duration": self.duration_str,
            "pickup_airport": self.pickup_airport,
            "pickup_hotel": self.pickup_hotel,
            "address": self.address,
            "phone": self.phone,
            "maps_url": self.maps_url,
        }


KNOWN_HOTELS: dict[str, dict[str, str]] = {
    "JED": {
        "name": "Radisson Blu Hotel, Jeddah Corniche",
        "city": "Djeddah",
        "address": "Corniche Road, Ash Shati, Jeddah, Saudi Arabia",
        "phone": "+966 12 510 7000",
    },
    "KUL": {
        "name": "DoubleTree by Hilton Putrajaya Lakeside",
        "city": "Kuala Lumpur / Putrajaya",
        "address": "2, Jalan P5/5, Presint 5, 62200 Putrajaya, Malaysia",
        "phone": "+60 3-8890 0000",
    },
    "JNB": {
        "name": "@Sandton Hotel",
        "city": "Johannesburg",
        "address": "5 Benmore Rd, Benmore Gardens, Sandton, 2196, South Africa",
        "phone": "+27 11 440 1444",
    },
    "ORN": {
        "name": "Oran Bay Hotel (ex-Sheraton)",
        "city": "Oran",
        "address": "Route des Falaises, Canastel, Oran, Algérie",
        "phone": "+213 41 59 01 00",
    },
    "CZL": {
        "name": "Hôtel Militaire / Novotel Constantine",
        "city": "Constantine",
        "address": "Constantine, Algérie",
        "phone": "+213 31 92 20 00",
    },
}


def extract_layovers(entries: list[Any]) -> list[Layover]:
    """Extract structured layover entries from duty list."""
    layovers: list[Layover] = []

    for idx, e in enumerate(entries):
        # We look for hotel duties, or duties where layover_hotel is set
        is_hotel = (
            getattr(e, "duty_type", "").lower() == "hotel"
            or bool(getattr(e, "layover_hotel", None))
        )
        if not is_hotel:
            continue

        raw_str = getattr(e, "raw", None) or "{}"
        raw_obj: dict[str, Any] = {}
        if isinstance(raw_str, str):
            try:
                raw_obj = json.loads(raw_str)
            except Exception:
                pass
        elif isinstance(raw_str, dict):
            raw_obj = raw_str

        airport = getattr(e, "departure_airport", None) or getattr(e, "layover_hotel", "") or "DEST"
        airport = airport.strip().upper()

        text = raw_obj.get("text", "")
        details = raw_obj.get("details", "")
        hotel_info = raw_obj.get("HotelInfo", {}) or {}

        # 1. Hotel name extraction
        hotel_name = hotel_info.get("HotelName", "").strip()
        if not hotel_name:
            # Try to extract from text: "Rest RADISSON BLU JEDDAH CORNICHE (02/10/2026..."
            m_hotel = re.search(r'Rest\s+([A-Za-z0-9@\s\-,\'\.]+?)\s*(?:\(|\d{2}/\d{2}|$)', text, re.I)
            if m_hotel:
                extracted = m_hotel.group(1).strip()
                if len(extracted) > 2 and extracted.lower() != "rest":
                    hotel_name = extracted

        known = KNOWN_HOTELS.get(airport, {})
        if not hotel_name or hotel_name.lower() in ("rest", airport.lower()):
            hotel_name = known.get("name", f"Hôtel Escale {airport}")

        city = known.get("city", airport)
        address = hotel_info.get("ADDRESS", "").strip() or known.get("address", "")
        phone = hotel_info.get("TELEPHONE1", "").strip() or known.get("phone", "")

        # Duration
        m_dur = re.search(r'\((\d{1,3}:\d{2})\)', text)
        if m_dur:
            duration_str = m_dur.group(1)
        else:
            duration_str = hotel_info.get("Rest", "Escale")

        check_in = getattr(e, "report_time", None) or raw_obj.get("start", "")
        check_out = getattr(e, "arrival_time", None) or getattr(e, "layover_until", None) or raw_obj.get("end", "")

        # Pickups
        pickup_apt = hotel_info.get("PickUpAirportStr") or hotel_info.get("PickUpAirportDate")
        if pickup_apt in ("-", "", None):
            pickup_apt = f"Arrivée escale ({check_in[11:16] if len(check_in) >= 16 else ''})"

        pickup_htl = hotel_info.get("PickUpHotelStr") or hotel_info.get("PickUpHotelDate")
        if pickup_htl in ("-", "", None):
            pickup_htl = f"Départ hôtel ({check_out[11:16] if len(check_out) >= 16 else ''})"

        maps_query = f"{hotel_name} {city}"
        maps_url = f"https://www.google.com/maps/search/?api=1&query={maps_query.replace(' ', '+')}"

        layovers.append(
            Layover(
                id=f"layover-{airport}-{getattr(e, 'date', idx)}",
                city=city,
                airport=airport,
                hotel_name=hotel_name,
                check_in=check_in,
                check_out=check_out,
                duration_str=duration_str,
                pickup_airport=pickup_apt,
                pickup_hotel=pickup_htl,
                address=address,
                phone=phone,
                maps_url=maps_url,
            )
        )

    return layovers
