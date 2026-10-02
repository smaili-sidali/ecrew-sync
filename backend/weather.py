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

# Exhaustive Air Algérie network IATA -> ICAO mapping (90+ airports)
AIRPORT_MAP: dict[str, dict[str, str]] = {
    # --- 🇩🇿 Réseau Domestique Algérie (35 aéroports) ---
    "ALG": {"icao": "DAAG", "name": "Alger - Houari Boumédiène", "city": "Alger", "country": "DZ", "region": "Algérie"},
    "ORN": {"icao": "DAOO", "name": "Oran - Ahmed Ben Bella", "city": "Oran", "country": "DZ", "region": "Algérie"},
    "CZL": {"icao": "DABC", "name": "Constantine - Mohamed Boudiaf", "city": "Constantine", "country": "DZ", "region": "Algérie"},
    "AAE": {"icao": "DABB", "name": "Annaba - Rabah Bitat", "city": "Annaba", "country": "DZ", "region": "Algérie"},
    "TLM": {"icao": "DAON", "name": "Tlemcen - Zenata Messali Hadj", "city": "Tlemcen", "country": "DZ", "region": "Algérie"},
    "BJA": {"icao": "DAAE", "name": "Béjaïa - Soummam Abane Ramdane", "city": "Béjaïa", "country": "DZ", "region": "Algérie"},
    "BSK": {"icao": "DAUB", "name": "Biskra - Mohamed Khider", "city": "Biskra", "country": "DZ", "region": "Algérie"},
    "BLJ": {"icao": "DAAB", "name": "Batna - Mostefa Ben Boulaïd", "city": "Batna", "country": "DZ", "region": "Algérie"},
    "QSF": {"icao": "DAAS", "name": "Sétif - 8 Mai 1945", "city": "Sétif", "country": "DZ", "region": "Algérie"},
    "TBJ": {"icao": "DABP", "name": "Tébessa - Cheikh Larbi Tébessi", "city": "Tébessa", "country": "DZ", "region": "Algérie"},
    "GJL": {"icao": "DAAV", "name": "Jijel - Ferhat Abbas", "city": "Jijel", "country": "DZ", "region": "Algérie"},
    "CFK": {"icao": "DAOI", "name": "Chlef - Aboubakr Belkaid", "city": "Chlef", "country": "DZ", "region": "Algérie"},
    "TID": {"icao": "DAOB", "name": "Tiaret - Bou Chekif", "city": "Tiaret", "country": "DZ", "region": "Algérie"},
    "EBH": {"icao": "DAOY", "name": "El Bayadh", "city": "El Bayadh", "country": "DZ", "region": "Algérie"},
    "MZW": {"icao": "DAAY", "name": "Mécheria", "city": "Mécheria", "country": "DZ", "region": "Algérie"},
    "MUW": {"icao": "DAOV", "name": "Mascara - Ghriss", "city": "Mascara", "country": "DZ", "region": "Algérie"},
    "HME": {"icao": "DAUH", "name": "Hassi Messaoud - Oued Irara", "city": "Hassi Messaoud", "country": "DZ", "region": "Algérie"},
    "OGX": {"icao": "DAUU", "name": "Ouargla - Aïn Beida", "city": "Ouargla", "country": "DZ", "region": "Algérie"},
    "GHA": {"icao": "DAUG", "name": "Ghardaïa - Noumérat", "city": "Ghardaïa", "country": "DZ", "region": "Algérie"},
    "ELU": {"icao": "DAUO", "name": "El Oued - Guemar", "city": "El Oued", "country": "DZ", "region": "Algérie"},
    "TGR": {"icao": "DAUK", "name": "Touggourt - Sidi Mahdi", "city": "Touggourt", "country": "DZ", "region": "Algérie"},
    "LOO": {"icao": "DAUL", "name": "Laghouat - Moulay Ahmed Medeghri", "city": "Laghouat", "country": "DZ", "region": "Algérie"},
    "ELG": {"icao": "DAUE", "name": "El Goléa / El Ménia", "city": "El Goléa", "country": "DZ", "region": "Algérie"},
    "HRM": {"icao": "DAFH", "name": "Hassi R'Mel - Tilrhemt", "city": "Hassi R'Mel", "country": "DZ", "region": "Algérie"},
    "AZR": {"icao": "DAUA", "name": "Adrar - Touat Cheikh Sidi Mohamed", "city": "Adrar", "country": "DZ", "region": "Algérie"},
    "TMX": {"icao": "DAUT", "name": "Timimoun", "city": "Timimoun", "country": "DZ", "region": "Algérie"},
    "CBH": {"icao": "DAOR", "name": "Béchar - Boudghene Ben Ali Lotfi", "city": "Béchar", "country": "DZ", "region": "Algérie"},
    "TIN": {"icao": "DAFI", "name": "Tindouf", "city": "Tindouf", "country": "DZ", "region": "Algérie"},
    "TMR": {"icao": "DAAT", "name": "Tamanrasset - Aguenar", "city": "Tamanrasset", "country": "DZ", "region": "Algérie"},
    "INF": {"icao": "DATG", "name": "In Guezzam", "city": "In Guezzam", "country": "DZ", "region": "Algérie"},
    "INZ": {"icao": "DAUI", "name": "In Salah", "city": "In Salah", "country": "DZ", "region": "Algérie"},
    "BMW": {"icao": "DATM", "name": "Bordj Badji Mokhtar", "city": "Bordj Badji Mokhtar", "country": "DZ", "region": "Algérie"},
    "DJG": {"icao": "DAAJ", "name": "Djanet - Tiska", "city": "Djanet", "country": "DZ", "region": "Algérie"},
    "VVZ": {"icao": "DAAP", "name": "Illizi - Takhamalt", "city": "Illizi", "country": "DZ", "region": "Algérie"},
    "IAM": {"icao": "DAUZ", "name": "In Amenas - Zarzaitine", "city": "In Amenas", "country": "DZ", "region": "Algérie"},
    "BFO": {"icao": "DAOC", "name": "Bou Saâda", "city": "Bou Saâda", "country": "DZ", "region": "Algérie"},

    # --- 🇪🇺 Réseau International Europe (32 aéroports) ---
    "CDG": {"icao": "LFPG", "name": "Paris - Charles de Gaulle", "city": "Paris", "country": "FR", "region": "Europe"},
    "ORY": {"icao": "LFPO", "name": "Paris - Orly", "city": "Paris", "country": "FR", "region": "Europe"},
    "MRS": {"icao": "LFML", "name": "Marseille - Provence", "city": "Marseille", "country": "FR", "region": "Europe"},
    "LYS": {"icao": "LFLL", "name": "Lyon - Saint-Exupéry", "city": "Lyon", "country": "FR", "region": "Europe"},
    "LIL": {"icao": "LFQQ", "name": "Lille - Lesquin", "city": "Lille", "country": "FR", "region": "Europe"},
    "TLS": {"icao": "LFBO", "name": "Toulouse - Blagnac", "city": "Toulouse", "country": "FR", "region": "Europe"},
    "NCE": {"icao": "LFMN", "name": "Nice - Côte d'Azur", "city": "Nice", "country": "FR", "region": "Europe"},
    "BOD": {"icao": "LFBD", "name": "Bordeaux - Mérignac", "city": "Bordeaux", "country": "FR", "region": "Europe"},
    "MLH": {"icao": "LFSB", "name": "Bâle-Mulhouse - EuroAirport", "city": "Mulhouse", "country": "FR", "region": "Europe"},
    "MPL": {"icao": "LFMT", "name": "Montpellier - Méditerranée", "city": "Montpellier", "country": "FR", "region": "Europe"},
    "MET": {"icao": "LFJL", "name": "Metz - Nancy Lorraine", "city": "Metz", "country": "FR", "region": "Europe"},
    "BES": {"icao": "LFRB", "name": "Brest - Bretagne", "city": "Brest", "country": "FR", "region": "Europe"},
    "LHR": {"icao": "EGLL", "name": "Londres - Heathrow", "city": "Londres", "country": "GB", "region": "Europe"},
    "LGW": {"icao": "EGKK", "name": "Londres - Gatwick", "city": "Londres", "country": "GB", "region": "Europe"},
    "MAD": {"icao": "LEMD", "name": "Madrid - Barajas", "city": "Madrid", "country": "ES", "region": "Europe"},
    "BCN": {"icao": "LEBL", "name": "Barcelone - El Prat", "city": "Barcelone", "country": "ES", "region": "Europe"},
    "ALC": {"icao": "LEAL", "name": "Alicante - Elche", "city": "Alicante", "country": "ES", "region": "Europe"},
    "PMI": {"icao": "LEPA", "name": "Palma de Majorque", "city": "Palma", "country": "ES", "region": "Europe"},
    "VLC": {"icao": "LEVC", "name": "Valence - Manises", "city": "Valence", "country": "ES", "region": "Europe"},
    "FCO": {"icao": "LIRF", "name": "Rome - Fiumicino", "city": "Rome", "country": "IT", "region": "Europe"},
    "MXP": {"icao": "LIMC", "name": "Milan - Malpensa", "city": "Milan", "country": "IT", "region": "Europe"},
    "FRA": {"icao": "EDDF", "name": "Francfort - Rhein-Main", "city": "Francfort", "country": "DE", "region": "Europe"},
    "BRU": {"icao": "EBBR", "name": "Bruxelles - Zaventem", "city": "Bruxelles", "country": "BE", "region": "Europe"},
    "CRL": {"icao": "EBCI", "name": "Charleroi - Bruxelles Sud", "city": "Charleroi", "country": "BE", "region": "Europe"},
    "GVA": {"icao": "LSGG", "name": "Genève - Cointrin", "city": "Genève", "country": "CH", "region": "Europe"},
    "VIE": {"icao": "LOWW", "name": "Vienne - Schwechat", "city": "Vienne", "country": "AT", "region": "Europe"},
    "LIS": {"icao": "LPPT", "name": "Lisbonne - Humberto Delgado", "city": "Lisbonne", "country": "PT", "region": "Europe"},
    "SVO": {"icao": "UUEE", "name": "Moscou - Cheremetievo", "city": "Moscou", "country": "RU", "region": "Europe"},
    "BUD": {"icao": "LHBP", "name": "Budapest - Ferenc Liszt", "city": "Budapest", "country": "HU", "region": "Europe"},
    "IST": {"icao": "LTFM", "name": "Istanbul - Grand Aéroport", "city": "Istanbul", "country": "TR", "region": "Europe"},
    "SAW": {"icao": "LTFJ", "name": "Istanbul - Sabiha Gökçen", "city": "Istanbul", "country": "TR", "region": "Europe"},
    "AYT": {"icao": "LTAI", "name": "Antalya", "city": "Antalya", "country": "TR", "region": "Europe"},

    # --- 🇸🇦 Réseau Moyen-Orient (7 aéroports) ---
    "JED": {"icao": "OEJN", "name": "Djeddah - King Abdulaziz", "city": "Djeddah", "country": "SA", "region": "Moyen-Orient"},
    "MED": {"icao": "OEMA", "name": "Médine - Prince Mohammad", "city": "Médine", "country": "SA", "region": "Moyen-Orient"},
    "RUH": {"icao": "OERK", "name": "Riyad - King Khalid", "city": "Riyad", "country": "SA", "region": "Moyen-Orient"},
    "DXB": {"icao": "OMDB", "name": "Dubaï International", "city": "Dubaï", "country": "AE", "region": "Moyen-Orient"},
    "DOH": {"icao": "OTHH", "name": "Doha - Hamad International", "city": "Doha", "country": "QA", "region": "Moyen-Orient"},
    "AMM": {"icao": "OJAI", "name": "Amman - Queen Alia", "city": "Amman", "country": "JO", "region": "Moyen-Orient"},
    "BEY": {"icao": "OLBA", "name": "Beyrouth - Rafic Hariri", "city": "Beyrouth", "country": "LB", "region": "Moyen-Orient"},

    # --- 🌍 Réseau Afrique (14 aéroports) ---
    "TUN": {"icao": "DTTA", "name": "Tunis - Carthage", "city": "Tunis", "country": "TN", "region": "Afrique"},
    "CMN": {"icao": "GMMN", "name": "Casablanca - Mohammed V", "city": "Casablanca", "country": "MA", "region": "Afrique"},
    "CAI": {"icao": "HECA", "name": "Le Caire International", "city": "Le Caire", "country": "EG", "region": "Afrique"},
    "SSH": {"icao": "HESH", "name": "Charm el-Cheikh", "city": "Charm el-Cheikh", "country": "EG", "region": "Afrique"},
    "DSS": {"icao": "GOBD", "name": "Dakar - Blaise Diagne", "city": "Dakar", "country": "SN", "region": "Afrique"},
    "BKO": {"icao": "GABS", "name": "Bamako - Modibo Keïta", "city": "Bamako", "country": "ML", "region": "Afrique"},
    "NIM": {"icao": "DRRN", "name": "Niamey - Diori Hamani", "city": "Niamey", "country": "NE", "region": "Afrique"},
    "NKC": {"icao": "GQNO", "name": "Nouakchott - Oumtounsy", "city": "Nouakchott", "country": "MR", "region": "Afrique"},
    "OUA": {"icao": "DFFD", "name": "Ouagadougou - Thomas Sankara", "city": "Ouagadougou", "country": "BF", "region": "Afrique"},
    "ABJ": {"icao": "DIAP", "name": "Abidjan - Félix Houphouët-Boigny", "city": "Abidjan", "country": "CI", "region": "Afrique"},
    "DLA": {"icao": "FKKD", "name": "Douala International", "city": "Douala", "country": "CM", "region": "Afrique"},
    "NDJ": {"icao": "FTTJ", "name": "N'Djamena - Hassan Djamous", "city": "N'Djamena", "country": "TD", "region": "Afrique"},
    "JNB": {"icao": "FAOR", "name": "Johannesburg - O.R. Tambo", "city": "Johannesburg", "country": "ZA", "region": "Afrique"},
    "ADD": {"icao": "HAAB", "name": "Addis-Abeba - Bole", "city": "Addis-Abeba", "country": "ET", "region": "Afrique"},

    # --- 🌎 Amériques & Asie (Long-Courrier) (5 aéroports) ---
    "YUL": {"icao": "CYUL", "name": "Montréal - Pierre-Elliott-Trudeau", "city": "Montréal", "country": "CA", "region": "Long-Courrier"},
    "PEK": {"icao": "ZBAA", "name": "Pékin - Capitale", "city": "Pékin", "country": "CN", "region": "Long-Courrier"},
    "PKX": {"icao": "ZBAD", "name": "Pékin - Daxing", "city": "Pékin", "country": "CN", "region": "Long-Courrier"},
    "CAN": {"icao": "ZGGG", "name": "Canton - Baiyun", "city": "Canton", "country": "CN", "region": "Long-Courrier"},
    "KUL": {"icao": "WMKK", "name": "Kuala Lumpur International", "city": "Kuala Lumpur", "country": "MY", "region": "Long-Courrier"},
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

