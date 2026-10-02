"""Unit tests for enriched features: Weather, Layovers, Crew, Stats, Licenses, Per Diem, Leave."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import crew_list, layovers, leave, perdiem, stats, training, weather
from server.api import app

client = TestClient(app)


def test_weather_iata_resolution():
    assert weather.to_icao("ALG") == "DAAG"
    assert weather.to_icao("JED") == "OEJN"
    assert weather.to_icao("KUL") == "WMKK"
    assert weather.to_icao("JNB") == "FAOR"
    assert weather.to_icao("BOD") == "LFBD"


def test_weather_decode_metar():
    raw = "METAR DAAG 020330Z 06002KT 9999 FEW010 SCT100 24/19 Q1019"
    decoded = weather._decode_metar(raw)
    assert decoded["wind_speed_kt"] == 2
    assert decoded["wind_dir_deg"] == "060"
    assert decoded["visibility_m"] == 9999
    assert decoded["temp_c"] == 24
    assert decoded["dew_c"] == 19
    assert decoded["qnh_hpa"] == 1019
    assert decoded["flight_category"] == "VFR"


def test_crew_list():
    crew_462 = crew_list.get_crew_for_flight("AH 462")
    assert len(crew_462) > 0
    cdb = [c for c in crew_462 if c["code"] == "CDB"]
    assert len(cdb) == 1
    opl = [c for c in crew_462 if c["code"] == "OPL"]
    assert len(opl) >= 1


def test_qualifications_status():
    quals = training.load_qualifications()
    assert len(quals) >= 5
    for q in quals:
        d = q.to_dict()
        assert "status" in d
        assert "days_remaining" in d


def test_leave_data():
    data = leave.load_leave_data()
    assert "annual_entitlement" in data
    assert "remaining_days" in data
    assert "leave_history" in data
    assert "bidding_requests" in data


def test_api_enriched_endpoints():
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    assert "block_time" in res_stats.json()
    assert "ftl" in res_stats.json()

    res_layovers = client.get("/api/layovers")
    assert res_layovers.status_code == 200
    assert "layovers" in res_layovers.json()

    res_perdiem = client.get("/api/perdiem")
    assert res_perdiem.status_code == 200
    assert "totals" in res_perdiem.json()

    res_licenses = client.get("/api/licenses")
    assert res_licenses.status_code == 200
    assert "qualifications" in res_licenses.json()

    res_leave = client.get("/api/leave")
    assert res_leave.status_code == 200
    assert "annual_entitlement" in res_leave.json()

    res_crew = client.get("/api/crew/AH462")
    assert res_crew.status_code == 200
    assert "crew" in res_crew.json()

    res_wx = client.get("/api/weather/ALG")
    assert res_wx.status_code == 200
    assert "metar" in res_wx.json()


def test_cli_enriched_commands():
    from typer.testing import CliRunner
    from cli.main import app as cli_app

    runner = CliRunner()
    assert runner.invoke(cli_app, ["stats"]).exit_code == 0
    assert runner.invoke(cli_app, ["layovers"]).exit_code == 0
    assert runner.invoke(cli_app, ["perdiem"]).exit_code == 0
    assert runner.invoke(cli_app, ["licenses"]).exit_code == 0
    assert runner.invoke(cli_app, ["leave"]).exit_code == 0
    assert runner.invoke(cli_app, ["crew", "AH462"]).exit_code == 0
    # weather command with mock or network
    res_wx = runner.invoke(cli_app, ["weather", "ALG"])
    assert res_wx.exit_code == 0

