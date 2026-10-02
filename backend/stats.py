"""Flight, Duty Time and FTL (Flight Time Limitations) Statistics Module.

Calculates block hours, duty times, layover hours, sectors, and checks FTL compliance.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    cleaned = dt_str.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(cleaned[:19], fmt)
        except ValueError:
            pass
    return None


def calculate_flight_stats(entries: list[Any], target_month: str | None = None) -> dict[str, Any]:
    """Calculate flight and duty time statistics from roster duties."""
    filtered = entries
    if target_month:
        filtered = [e for e in entries if getattr(e, "date", "").startswith(target_month)]

    total_block_minutes = 0
    total_duty_minutes = 0
    total_night_minutes = 0
    total_layover_minutes = 0
    sectors_count = 0
    days_off_count = 0
    flights_count = 0

    monthly_sectors: list[dict[str, Any]] = []

    for e in filtered:
        dtype = getattr(e, "duty_type", "").lower()
        raw_str = getattr(e, "raw", "") or "{}"
        raw_obj: dict[str, Any] = {}
        if isinstance(raw_str, str):
            try:
                raw_obj = json.loads(raw_str)
            except Exception:
                pass
        elif isinstance(raw_str, dict):
            raw_obj = raw_str

        # Off days
        if dtype in ("off", "leave", "rest") and not getattr(e, "layover_hotel", None):
            days_off_count += 1
            continue

        # Layovers
        if dtype == "hotel" or getattr(e, "layover_hotel", None):
            dt_start = _parse_dt(getattr(e, "report_time", None) or raw_obj.get("start"))
            dt_end = _parse_dt(getattr(e, "arrival_time", None) or raw_obj.get("end"))
            if dt_start and dt_end and dt_end > dt_start:
                mins = int((dt_end - dt_start).total_seconds() / 60)
                total_layover_minutes += mins
            continue

        # Flights and multi-leg duties
        if dtype in ("flight", "flt", "other"):
            dt_rep = _parse_dt(getattr(e, "report_time", None) or raw_obj.get("start"))
            dt_deb = _parse_dt(getattr(e, "arrival_time", None) or raw_obj.get("end"))

            duty_mins = 0
            if dt_rep and dt_deb and dt_deb > dt_rep:
                duty_mins = int((dt_deb - dt_rep).total_seconds() / 60)
                total_duty_minutes += duty_mins

            details = raw_obj.get("details", "")
            # Look for lines like "6222 - ALG (1100) - TGR (1200)"
            leg_matches = list(re.finditer(r'(\d{3,4})\s*-\s*([A-Z]{3})\s*\((\d{4})\)\s*-\s*([A-Z]{3})\s*\((\d{4})[⁺¹]*\)', details))

            if leg_matches:
                for lm in leg_matches:
                    f_no = lm.group(1)
                    dep_apt = lm.group(2)
                    dep_t = lm.group(3)
                    arr_apt = lm.group(4)
                    arr_t = lm.group(5)

                    dep_h, dep_m = int(dep_t[:2]), int(dep_t[2:])
                    arr_h, arr_m = int(arr_t[:2]), int(arr_t[2:])
                    dur_m = (arr_h * 60 + arr_m) - (dep_h * 60 + dep_m)
                    if dur_m < 0:
                        dur_m += 24 * 60  # crossed midnight

                    total_block_minutes += dur_m
                    sectors_count += 1
                    flights_count += 1

                    # Estimate night hours (22h - 06h)
                    if dep_h >= 22 or dep_h < 6 or arr_h >= 22 or arr_h < 6:
                        total_night_minutes += dur_m

                    monthly_sectors.append({
                        "date": getattr(e, "date", ""),
                        "flight_number": f"AH{f_no}",
                        "route": f"{dep_apt}-{arr_apt}",
                        "dep": f"{dep_h:02d}:{dep_m:02d}",
                        "arr": f"{arr_h:02d}:{arr_m:02d}",
                        "block_time": f"{dur_m//60}h{dur_m%60:02d}",
                    })
            else:
                # Approximate block time from report to debrief (-60 min for reporting/debriefing)
                if duty_mins > 60:
                    est_block = duty_mins - 60
                    total_block_minutes += est_block
                    sectors_count += 1
                    flights_count += 1

    block_h = total_block_minutes // 60
    block_m = total_block_minutes % 60
    duty_h = total_duty_minutes // 60
    duty_m = total_duty_minutes % 60
    night_h = total_night_minutes // 60
    night_m = total_night_minutes % 60
    layover_h = total_layover_minutes // 60

    # FTL Limits (EASA / Air Algérie OM-A standards)
    # Monthly max block: 100h
    # 28-day max block: 100h (or 900h / year)
    # 7-day max duty: 60h
    pct_block_month = min(100.0, round((total_block_minutes / (100 * 60)) * 100, 1))
    pct_duty_month = min(100.0, round((total_duty_minutes / (190 * 60)) * 100, 1))

    return {
        "month": target_month or "All",
        "block_time": f"{block_h}h{block_m:02d}",
        "block_hours_decimal": round(total_block_minutes / 60, 1),
        "duty_time": f"{duty_h}h{duty_m:02d}",
        "duty_hours_decimal": round(total_duty_minutes / 60, 1),
        "night_time": f"{night_h}h{night_m:02d}",
        "night_hours_decimal": round(total_night_minutes / 60, 1),
        "layover_time": f"{layover_h}h",
        "sectors_count": sectors_count,
        "days_off_count": days_off_count,
        "ftl": {
            "monthly_block_limit_h": 100,
            "monthly_duty_limit_h": 190,
            "block_used_pct": pct_block_month,
            "duty_used_pct": pct_duty_month,
            "status": "CONFORME" if pct_block_month < 95 else "ATTENTION LIMITE",
        },
        "sectors": monthly_sectors,
    }
