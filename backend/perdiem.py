"""Per Diem & Mission Allowances Calculator for Air Algérie Crew.

Calculates estimated layover allowances (in Foreign Currencies and DZD) and flight pay
based on actual rotation schedules, reporting times, debriefing times, and destinations.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from typing import Any

RATES: dict[str, dict[str, Any]] = {
    "JED": {"currency": "USD", "daily_rate": 120.0, "name": "Djeddah (Arabie Saoudite)", "dzd_equiv": 16500},
    "MED": {"currency": "USD", "daily_rate": 120.0, "name": "Médine (Arabie Saoudite)", "dzd_equiv": 16500},
    "KUL": {"currency": "USD", "daily_rate": 130.0, "name": "Kuala Lumpur (Malaisie)", "dzd_equiv": 17800},
    "JNB": {"currency": "USD", "daily_rate": 115.0, "name": "Johannesburg (Afrique du Sud)", "dzd_equiv": 15800},
    "BOD": {"currency": "EUR", "daily_rate": 90.0, "name": "Bordeaux (France)", "dzd_equiv": 13000},
    "CDG": {"currency": "EUR", "daily_rate": 105.0, "name": "Paris (France)", "dzd_equiv": 15200},
    "ORY": {"currency": "EUR", "daily_rate": 105.0, "name": "Paris (France)", "dzd_equiv": 15200},
    "DXB": {"currency": "USD", "daily_rate": 140.0, "name": "Dubaï (Émirats)", "dzd_equiv": 19200},
    "ORN": {"currency": "DZD", "daily_rate": 5500.0, "name": "Oran (Escale Nationale)", "dzd_equiv": 5500},
    "CZL": {"currency": "DZD", "daily_rate": 5000.0, "name": "Constantine (Escale Nationale)", "dzd_equiv": 5000},
}

DEFAULT_INTL_RATE = {"currency": "USD", "daily_rate": 100.0, "dzd_equiv": 13800}
DEFAULT_DOM_RATE = {"currency": "DZD", "daily_rate": 4500.0, "dzd_equiv": 4500}


def calculate_per_diem(entries: list[Any], target_month: str | None = None) -> dict[str, Any]:
    """Compute per diem allowances breakdown from roster layovers and rotations."""
    filtered = entries
    if target_month:
        filtered = [e for e in entries if getattr(e, "date", "").startswith(target_month)]

    rotations: list[dict[str, Any]] = []
    total_usd = 0.0
    total_eur = 0.0
    total_dzd = 0.0

    for e in filtered:
        dtype = getattr(e, "duty_type", "").lower()
        if dtype != "hotel" and not getattr(e, "layover_hotel", None):
            continue

        raw_str = getattr(e, "raw", "") or "{}"
        raw_obj: dict[str, Any] = {}
        if isinstance(raw_str, str):
            with contextlib.suppress(Exception):
                raw_obj = json.loads(raw_str)
        elif isinstance(raw_str, dict):
            raw_obj = raw_str

        airport = getattr(e, "departure_airport", None) or getattr(e, "layover_hotel", "") or "DEST"
        airport = airport.strip().upper()

        check_in_str = getattr(e, "report_time", None) or raw_obj.get("start", "")
        check_out_str = getattr(e, "arrival_time", None) or getattr(e, "layover_until", None) or raw_obj.get("end", "")

        try:
            dt_in = datetime.fromisoformat(check_in_str.replace(" ", "T")[:19])
            dt_out = datetime.fromisoformat(check_out_str.replace(" ", "T")[:19])
            hours = max(1.0, (dt_out - dt_in).total_seconds() / 3600.0)
        except Exception:
            hours = 24.0

        days_count = max(1.0, round(hours / 24.0, 1))

        rate_info = RATES.get(airport, DEFAULT_INTL_RATE if airport not in ("ALG", "CZL", "ORN") else DEFAULT_DOM_RATE)
        curr = rate_info["currency"]
        daily = rate_info["daily_rate"]
        dzd_equiv_daily = rate_info["dzd_equiv"]

        amount = round(days_count * daily, 2)
        amount_dzd = int(days_count * dzd_equiv_daily)

        if curr == "USD":
            total_usd += amount
        elif curr == "EUR":
            total_eur += amount
        elif curr == "DZD":
            total_dzd += amount

        rotations.append({
            "date": getattr(e, "date", ""),
            "city": rate_info.get("name", airport),
            "airport": airport,
            "duration_h": round(hours, 1),
            "days": days_count,
            "currency": curr,
            "allowance": amount,
            "allowance_dzd_est": amount_dzd,
        })

    return {
        "month": target_month or "All",
        "totals": {
            "USD": round(total_usd, 2),
            "EUR": round(total_eur, 2),
            "DZD": round(total_dzd, 2),
            "total_estimated_dzd": int(total_dzd + (total_usd * 138) + (total_eur * 148)),
        },
        "rotations": rotations,
    }
