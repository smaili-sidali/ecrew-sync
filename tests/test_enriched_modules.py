"""Unit tests for enriched features: Weather, Layovers, Crew, Stats, Licenses, Per Diem, Leave."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import leave, training, weather
from server.api import app

client = TestClient(app)


@pytest.fixture
def no_network(monkeypatch):
    """Make every ``requests.get`` in backend.weather raise.

    ``/api/weather`` calls aviationweather.gov live. Without this the suite
    depends on NOAA being up and on the network being available, so a 5 s
    timeout would surface as a random failure — which is exactly how the ``%e``
    logging bug below stayed hidden.
    """

    def _boom(*args, **kwargs):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(weather.requests, "get", _boom)
    return _boom


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


def test_crew_endpoint_requires_a_synced_flight():
    # No fabricated roster any more: the crew comes from the portal's
    # DutyDetails view, keyed by an event id resolved from the synced roster.
    res_crew = client.get("/api/crew/AH462")
    assert res_crew.status_code == 404
    assert "sync" in res_crew.json()["detail"].lower()


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


def test_weather_survives_a_dead_upstream(no_network):
    """A NOAA timeout must degrade gracefully, never raise.

    Regression: the METAR handler logged with ``%e``, which is not a logging
    specifier. logging then raised TypeError *inside* the except block, turning
    a handled network failure into a 500 — and it only showed up when NOAA was
    slow. This asserts the endpoint still answers with the fallback payload.
    """
    res = client.get("/api/weather/ALG")
    assert res.status_code == 200
    body = res.json()
    assert body["icao"] == "DAAG"
    # The documented fallback shape, not an exception.
    assert "non disponible" in body["metar"]["raw"]


def test_weather_decodes_a_real_metar(monkeypatch):
    """With a stubbed upstream, decoding must use the live payload."""

    class _Resp:
        status_code = 200
        text = "METAR DAAG 020330Z 06002KT 9999 FEW010 SCT100 24/19 Q1019"

        def json(self):
            return [{"rawOb": self.text, "obsTime": "2026-08-02T03:30:00Z"}]

    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: _Resp())
    body = client.get("/api/weather/ALG").json()
    assert body["metar"]["flight_category"] == "VFR"
    assert body["metar"]["qnh_hpa"] == 1019
    assert body["metar"]["observed_at"] == "2026-08-02T03:30:00Z"


def test_api_enriched_endpoints(no_network):
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
    assert res_crew.status_code == 404

    res_wx = client.get("/api/weather/ALG")
    assert res_wx.status_code == 200
    assert "metar" in res_wx.json()

    res_airports = client.get("/api/airports")
    assert res_airports.status_code == 200
    airports = res_airports.json().get("airports", {})
    assert len(airports) >= 90
    assert "ALG" in airports
    assert "CDG" in airports
    assert "JED" in airports
    assert "YUL" in airports
    assert "BSK" in airports
    assert airports["ALG"]["icao"] == "DAAG"


def test_cli_enriched_commands(tmp_path, monkeypatch, no_network):
    from typer.testing import CliRunner

    from backend import store
    from backend.parser import DutyEntry
    from cli.main import app as cli_app

    db = tmp_path / "roster.json"
    monkeypatch.setenv("ECREW_DB_FILE", str(db))

    sample_entries = [
        DutyEntry(
            date="2026-10-04",
            duty_type="flight",
            flight_number="AH6001",
            departure_airport="ALG",
            arrival_airport="ORN",
            departure_time="2026-10-04T08:00:00",
            arrival_time="2026-10-04T09:00:00",
        ),
        DutyEntry(
            date="2026-10-05",
            duty_type="hotel",
            layover_hotel="Movenpick Jeddah",
            departure_airport="JED",
            report_time="2026-10-05T00:00:00",
            arrival_time="2026-10-06T12:00:00",
        ),
        DutyEntry(date="2026-10-07", duty_type="off"),
    ]
    store.save(sample_entries, db)

    runner = CliRunner()
    assert runner.invoke(cli_app, ["stats"]).exit_code == 0
    assert runner.invoke(cli_app, ["layovers"]).exit_code == 0
    assert runner.invoke(cli_app, ["perdiem"]).exit_code == 0
    assert runner.invoke(cli_app, ["licenses"]).exit_code == 0
    assert runner.invoke(cli_app, ["leave"]).exit_code == 0
    # "crew" now hits the portal, so only the "not in the roster" path is
    # exercised offline.
    res_crew = runner.invoke(cli_app, ["crew", "9999"])
    assert res_crew.exit_code == 1
    res_wx = runner.invoke(cli_app, ["weather", "ALG"])
    assert res_wx.exit_code == 0

