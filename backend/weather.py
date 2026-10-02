"""Aviation Weather module — live METAR and TAF directly from public aviation feeds.

Does NOT import from or depend on eCrew. Fetches official real-time METAR/TAF
from NOAA Aviation Weather Center (aviationweather.gov) with automatic IATA-to-ICAO
mapping and friendly decoding.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Common Air Algérie network IATA -> ICAO mapping
AIRPORT_MAP: dict[str, dict[str, str]] = {
    # Domestic (Algérie)
    "ALG": {"icao": "DAAG", "name": "Alger - Houari Boumédiène", "city": "Alger", "country": "DZ"},
    "CZL": {"icao": "DABC", "name": "Constantine - Mohamed Boudiaf", "city": "Constantine", "country": "DZ"},
    "ORN": {"icao": "DAOO", "name": "Oran - Ahmed Ben Bella", "city": "Oran", "country": "DZ"},
    "AAE": {"icao": "DABB", "name": "Annaba - Rabah Bitat", "city": "Annaba", "country": "DZ"},
    "TGR": {"icao": "DAAT", "name": "Touggourt - Sidi Mahdi", "city": "Touggourt", "country": "DZ"},
    "ELU": {"icao": "DAUO", "name": "El Oued - Guemar", "city": "El Oued", "country": "DZ"},
    "TMR": {"icao": "DAAT", "name": "Tamanrasset - Aguenar", "city": "Tamanrasset", "country": "DZ"},
    "BJA": {"icao": "DAAE", "name": "Béjaïa - Soummam", "city": "Béjaïa", "country": "DZ"},
    "TLM": {"icao": "DAON", "name": "Tlemcen - Zenata", "city": "Tlemcen", "country": "DZ"},
    "BSK": {"icao": "DAUB", "name": "Biskra - Mohamed Khider", "city": "Biskra", "country": "DZ"},
    "HME": {"icao": "DAUH", "name": "Hassi Messaoud - Oued Irara", "city": "Hassi Messaoud", "country": "DZ"},
    "OGX": {"icao": "DAUU", "name": "Ouargla - Ain Beida", "city": "Ouargla", "country": "DZ"},
    "GHA": {"icao": "DAUG", "name": "Ghardaïa - Noumérat", "city": "Ghardaïa", "country": "DZ"},
    "AZR": {"icao": "DAUA", "name": "Adrar - Touat Cheikh Sidi Mohamed", "city": "Adrar", "country": "DZ"},
    "INZ": {"icao": "DAUI", "name": "In Salah", "city": "In Salah", "country": "DZ"},
    "IAM": {"icao": "DAUZ", "name": "In Amenas - Zarzaitine", "city": "In Amenas", "country": "DZ"},
    "DJG": {"icao": "DAAJ", "name": "Djanet - Tiska", "city": "Djanet", "country": "DZ"},
    "BFO": {"icao": "DAOC", "name": "Bou Saâda", "city": "Bou Saâda", "country": "DZ"},

    # International (Réseau Air Algérie)
    "JED": {"icao": "OEJN", "name": "Djeddah - King Abdulaziz Intl", "city": "Djeddah", "country": "SA"},
    "MED": {"icao": "OEMA", "name": "Médine - Prince Mohammad Intl", "city": "Médine", "country": "SA"},
    "RUH": {"icao": "OERK", "name": "Riyad - King Khalid Intl", "city": "Riyad", "country": "SA"},
    "KUL": {"icao": "WMKK", "name": "Kuala Lumpur Intl", "city": "Kuala Lumpur", "country": "MY"},
    "JNB": {"icao": "FAOR", "name": "Johannesburg - O.R. Tambo Intl", "city": "Johannesburg", "country": "ZA"},
    "NBJ": {"icao": "FTTJ", "name": "N'Djamena - Hassan Djamous Intl", "city": "N'Djamena", "country": "TD"},
    "CDG": {"icao": "LFPG", "name": "Paris - Charles de Gaulle", "city": "Paris", "country": "FR"},
    "ORY": {"icao": "LFPO", "name": "Paris - Orly", "city": "Paris", "country": "FR"},
    "MRS": {"icao": "LFML", "name": "Marseille - Provence", "city": "Marseille", "country": "FR"},
    "LYS": {"icao": "LFLL", "name": "Lyon - Saint-Exupéry", "city": "Lyon", "country": "FR"},
    "NCE": {"icao": "LFMN", "name": "Nice - Côte d'Azur", "city": "Nice", "country": "FR"},
    "TLS": {"icao": "LFBO", "name": "Toulouse - Blagnac", "city": "Toulouse", "country": "FR"},
    "BOD": {"icao": "LFBD", "name": "Bordeaux - Mérignac", "city": "Bordeaux", "country": "FR"},
    "LIL": {"icao": "LFQQ", "name": "Lille - Lesquin", "city": "Lille", "country": "FR"},
    "MET": {"icao": "LFJL", "name": "Metz - Nancy Lorraine", "city": "Metz", "country": "FR"},
    "DXB": {"icao": "OMDB", "name": "Dubaï Intl", "city": "Dubaï", "country": "AE"},
    "IST": {"icao": "LTFM", "name": "Istanbul Airport", "city": "Istanbul", "country": "TR"},
    "SAW": {"icao": "LTFJ", "name": "Istanbul - Sabiha Gökçen", "city": "Istanbul", "country": "TR"},
    "CAI": {"icao": "HECA", "name": "Le Caire Intl", "city": "Le Caire", "country": "EG"},
    "TUN": {"icao": "DTTA", "name": "Tunis - Carthage Intl", "city": "Tunis", "country": "TN"},
    "CMN": {"icao": "GMMN", "name": "Casablanca - Mohammed V Intl", "city": "Casablanca", "country": "MA"},
    "DOH": {"icao": "OTHH", "name": "Doha - Hamad Intl", "city": "Doha", "country": "QA"},
    "BCN": {"icao": "LEBL", "name": "Barcelone - El Prat", "city": "Barcelone", "country": "ES"},
    "MAD": {"icao": "LEMD", "name": "Madrid - Barajas", "city": "Madrid", "country": "ES"},
    "FCO": {"icao": "LIRF", "name": "Rome - Fiumicino", "city": "Rome", "country": "IT"},
    "MXP": {"icao": "LIMC", "name": "Milan - Malpensa", "city": "Milan", "country": "IT"},
    "LHR": {"icao": "EGLL", "name": "Londres - Heathrow", "city": "Londres", "country": "GB"},
    "FRA": {"icao": "EDDF", "name": "Francfort Intl", "city": "Francfort", "country": "DE"},
    "GVA": {"icao": "LSGG", "name": "Genève - Cointrin", "city": "Genève", "country": "CH"},
    "BRU": {"icao": "EBBR", "name": "Bruxelles - Zaventem", "city": "Bruxelles", "country": "BE"},
    "YUL": {"icao": "CYUL", "name": "Montréal - Pierre-Elliott-Trudeau", "city": "Montréal", "country": "CA"},
    "PEK": {"icao": "ZBAA", "name": "Pékin - Capitale", "city": "Pékin", "country": "CN"},
    "PKX": {"icao": "ZBAD", "name": "Pékin - Daxing", "city": "Pékin", "country": "CN"},
}


def to_icao(code: str) -> str:
    """Resolve an IATA or ICAO code to 4-letter ICAO."""
    cleaned = code.strip().upper()
    if len(cleaned) == 4:
        return cleaned
    if cleaned in AIRPORT_MAP:
        return AIRPORT_MAP[cleaned]["icao"]
    # Fallback heuristic
    return f"DA{cleaned[:2]}"


def get_airport_info(code: str) -> dict[str, str]:
    """Return airport metadata (name, city, country, icao, iata)."""
    cleaned = code.strip().upper()
    if cleaned in AIRPORT_MAP:
        info = dict(AIRPORT_MAP[cleaned])
        info["iata"] = cleaned
        return info
    # Search by ICAO
    for iata, meta in AIRPORT_MAP.items():
        if meta["icao"] == cleaned:
            info = dict(meta)
            info["iata"] = iata
            return info
    return {"icao": cleaned, "iata": cleaned, "name": cleaned, "city": cleaned, "country": ""}


def _decode_metar(raw: str) -> dict[str, Any]:
    """Parse common METAR tokens into human-friendly fields."""
    result: dict[str, Any] = {
        "raw": raw,
        "flight_category": "VFR",
        "wind_speed_kt": None,
        "wind_dir_deg": None,
        "visibility_m": None,
        "temp_c": None,
        "dew_c": None,
        "qnh_hpa": None,
        "clouds": [],
        "weather": [],
    }

    # Wind: e.g. 34012KT or 09005G15KT or VRB03KT
    m_wind = re.search(r'\b(VRB|\d{3})(\d{2})(?:G\d{2})?KT\b', raw)
    if m_wind:
        result["wind_dir_deg"] = m_wind.group(1)
        result["wind_speed_kt"] = int(m_wind.group(2))

    # Visibility: e.g. 9999 or 4000 or 1 1/2SM
    m_vis = re.search(r'\b(\d{4})\b', raw)
    if m_vis and int(m_vis.group(1)) <= 9999:
        vis = int(m_vis.group(1))
        result["visibility_m"] = vis
        if vis < 1500:
            result["flight_category"] = "LIFR"
        elif vis < 5000:
            result["flight_category"] = "IFR"
        elif vis < 8000:
            result["flight_category"] = "MVFR"

    # Temp/Dew: e.g. 21/14 or M02/M05
    m_temp = re.search(r'\b(M?\d{2})/(M?\d{2})\b', raw)
    if m_temp:
        t_str, d_str = m_temp.group(1), m_temp.group(2)
        result["temp_c"] = -int(t_str[1:]) if t_str.startswith('M') else int(t_str)
        result["dew_c"] = -int(d_str[1:]) if d_str.startswith('M') else int(d_str)

    # QNH: e.g. Q1018 or A2992
    m_qnh = re.search(r'\bQ(\d{4})\b', raw)
    if m_qnh:
        result["qnh_hpa"] = int(m_qnh.group(1))

    # Clouds: FEW020, SCT045, BKN080, OVC015, CAVOK
    if "CAVOK" in raw:
        result["clouds"].append("CAVOK (Ciel clair, visi > 10 km)")
        result["flight_category"] = "VFR"
    else:
        for c in re.finditer(r'\b(FEW|SCT|BKN|OVC|VV)(\d{3})\b', raw):
            cover = c.group(1)
            alt_ft = int(c.group(2)) * 100
            result["clouds"].append(f"{cover} à {alt_ft} ft")
            if cover in ("BKN", "OVC") and alt_ft < 1000:
                result["flight_category"] = "IFR"
            elif cover in ("BKN", "OVC") and alt_ft < 3000 and result["flight_category"] == "VFR":
                result["flight_category"] = "MVFR"

    return result


def fetch_weather(code: str) -> dict[str, Any]:
    """Fetch live METAR and TAF from NOAA Aviation Weather Center for given IATA/ICAO code."""
    icao = to_icao(code)
    airport_info = get_airport_info(code)

    headers = {
        "User-Agent": "eCrewSync/2.0 (Aviation Crew Companion)",
        "Accept": "*/*",
    }

    metar_url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
    taf_url = f"https://aviationweather.gov/api/data/taf?ids={icao}&format=json"

    metar_data: dict[str, Any] = {}
    taf_data: list[str] = []

    try:
        r_metar = requests.get(metar_url, headers=headers, timeout=5)
        if r_metar.status_code == 200:
            parsed = r_metar.json()
            if isinstance(parsed, list) and len(parsed) > 0:
                item = parsed[0]
                raw = item.get("rawOb") or item.get("raw") or ""
                metar_data = _decode_metar(raw)
                metar_data["observed_at"] = item.get("obsTime") or item.get("reportTime")
    except Exception as e:
        logger.warning("Could not fetch METAR for %s: %e", icao, e)

    # Fallback to plain text feed if json endpoint fails
    if not metar_data:
        try:
            r_txt = requests.get(f"https://aviationweather.gov/api/data/metar?ids={icao}", headers=headers, timeout=5)
            if r_txt.status_code == 200 and r_txt.text.strip():
                metar_data = _decode_metar(r_txt.text.strip())
        except Exception:
            pass

    try:
        r_taf = requests.get(taf_url, headers=headers, timeout=5)
        if r_taf.status_code == 200:
            parsed = r_taf.json()
            if isinstance(parsed, list) and len(parsed) > 0:
                taf_data = [item.get("rawTAF", "") for item in parsed if item.get("rawTAF")]
    except Exception as e:
        logger.warning("Could not fetch TAF for %s: %s", icao, e)

    if not taf_data:
        try:
            r_taf_txt = requests.get(f"https://aviationweather.gov/api/data/taf?ids={icao}", headers=headers, timeout=5)
            if r_taf_txt.status_code == 200 and r_taf_txt.text.strip():
                taf_data = [r_taf_txt.text.strip()]
        except Exception:
            pass

    return {
        "airport": airport_info,
        "icao": icao,
        "metar": metar_data or {"raw": f"{icao} METAR non disponible actuellement", "flight_category": "VFR"},
        "taf": taf_data or [f"{icao} TAF non disponible"],
    }


get_weather_report = fetch_weather

