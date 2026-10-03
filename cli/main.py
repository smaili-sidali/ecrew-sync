"""CLI — commands: login-test, sync, show, export-ics, web."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

# Ensure UTF-8 output on Windows consoles to prevent cp1252 charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    try:
        getattr(sys.stdout, "reconfigure")(encoding="utf-8", errors="replace")  # noqa: B009
        getattr(sys.stderr, "reconfigure")(encoding="utf-8", errors="replace")  # noqa: B009
    except Exception:
        pass

import typer

try:  # pragma: no cover - import shim for `python cli/main.py`
    from backend import (
        auth,
        config,
        contract,
        duty_details,
        fetch,
        layovers,
        leave,
        parser,
        perdiem,
        stats,
        store,
        training,
        weather,
    )
    from backend import export as backend_mod
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend import (
        auth,
        config,
        contract,
        duty_details,
        fetch,
        layovers,
        leave,
        parser,
        perdiem,
        stats,
        store,
        training,
        weather,
    )
    from backend import export as backend_mod


app = typer.Typer(add_completion=False, name="ecrew-sync", no_args_is_help=True)

# .env is loaded lazily by config, but do it eagerly so --help and credential
# errors report consistently regardless of which command runs first.
config._ensure_env()

try:  # keep CLI logs consistent with the server
    from server.logging_setup import setup_logging

    setup_logging()
except ImportError:  # pragma: no cover - running without the server package
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")


def _fail(message: str, code: int = 2) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=code)


def _login_and_fetch() -> str:
    """Log in (reusing a live session when possible) and return the roster HTML.

    On any failure the raw fragment is written to debug_roster_view.html so the
    parser contract can be re-derived from a real capture.
    """
    creds = auth.Credentials.from_env()
    base_url = config.base_url()
    cookie_file = config.session_file()

    session = auth.get_session(cookie_file)
    if not fetch.is_session_alive(session):
        try:
            sid = auth.login(session, creds.username, creds.password, base_url, cookie_file)
            typer.echo(f"Logged in. session id: {sid}")
        except auth.AuthError as e:
            _fail(f"Login failed: {e}")

    try:
        return fetch.fetch_with_relogin(
            session, creds.username, creds.password, base_url, cookie_file
        )
    except (fetch.FetchError, auth.AuthError) as e:
        _fail(f"Roster fetch failed: {e}")


@app.command()
def login_test() -> None:
    """Log in, fetch the roster, and diagnose whether the portal contract holds.

    This is the Phase 0 verification command. It saves the raw fragment to
    debug_roster_view.html and reports *which* way the contract broke, so you
    know what to fix instead of just seeing "no duties found".
    """
    html = _login_and_fetch()
    debug = Path("debug_roster_view.html")
    debug.write_text(html, encoding="utf-8")
    typer.echo(f"Saved roster view HTML ({len(html)} bytes) to {debug}")

    report = contract.check_fragment(html)
    typer.echo("")
    typer.echo(f"Contract canary: {report.status.value}")
    typer.echo(f"  duty-like events : {report.event_count}")
    typer.echo(f"  duties parsed    : {report.entry_count}")
    if report.duty_types:
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(report.duty_types.items()))
        typer.echo(f"  breakdown        : {breakdown}")

    if report.ok:
        typer.secho("  RESULT: contract intact.", fg=typer.colors.GREEN)
        try:
            entries = parser.parse_roster(html)
        except parser.ParseError as parse_err:  # pragma: no cover - canary passed, so rare
            typer.echo(f"  (parser disagreed with the canary: {parse_err})", err=True)
            return
        for entry in entries[:15]:
            typer.echo(f"    {entry.date}  {entry.duty_type:<9} {entry.flight_number or ''}")
        if len(entries) > 15:
            typer.echo(f"    ... and {len(entries) - 15} more")
        typer.secho(
            "\n  Next: replace tests/fixtures/sample_roster.html with this "
            "capture\n  (anonymised) so the test suite runs against reality.",
            fg=typer.colors.CYAN,
        )
        return

    typer.secho(f"  RESULT: CONTRACT DRIFT — {report.detail}", fg=typer.colors.RED, err=True)
    typer.secho(f"\n  {report.remedy}", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


@app.command()
def verify() -> None:
    """Phase 0 check: is the stored roster consistent with the live portal?

    Re-runs the contract canary against a fresh fetch and compares the duty
    dates with what is currently stored, without writing anything. Use this to
    confirm a deploy is healthy, or to see exactly what a sync would change.
    """
    html = _login_and_fetch()
    report = contract.check_fragment(html)

    typer.echo(f"Contract: {report.status.value} "
               f"({report.entry_count} duties, {report.event_count} events)")
    if not report.ok:
        typer.secho(f"  {report.remedy}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=3)

    fresh = parser.parse_roster(html)
    stored = store.load(config.db_file())
    change = store.diff(stored, fresh)

    if not stored:
        typer.secho("Nothing stored yet — run `sync` to create a baseline.",
                    fg=typer.colors.CYAN)
    elif change.is_empty:
        typer.secho("Stored roster matches the portal.", fg=typer.colors.GREEN)
    else:
        typer.echo(f"Pending changes: {change.summary()}")
        for entry in change.added:
            typer.echo(f"  + {entry.date} {entry.duty_type} {entry.flight_number or ''}")
        for entry in change.removed:
            typer.echo(f"  - {entry.date} {entry.duty_type} {entry.flight_number or ''}")
        for before, after in change.changed:
            typer.echo(f"  ~ {after.date} {after.duty_type} "
                       f"({before.departure_time} -> {after.departure_time})")


@app.command()
def token() -> None:
    """Generate a strong random API token for ECREW_API_TOKEN."""
    import secrets

    typer.echo(secrets.token_urlsafe(32))


@app.command()
def sync() -> None:
    """One-shot login -> fetch -> parse -> store."""
    html = _login_and_fetch()

    try:
        entries = parser.parse_roster(html)
    except parser.ParseError as e:
        debug = Path("debug_last_fetch.html")
        debug.write_text(html, encoding="utf-8")
        _fail(f"parser.parse_roster() failed: {e}\nSaved HTML to {debug}")

    db_file = config.db_file()
    previous = store.load(db_file)
    change = store.diff(previous, entries)
    store.save(entries, db_file)

    typer.echo(f"Stored {len(entries)} entries to {db_file}.")
    if not previous:
        typer.echo("First sync — baseline stored.")
    elif change.is_empty:
        typer.echo("No changes since last sync.")
    else:
        typer.echo(f"Changes: {change.summary()}")
        for entry in change.added:
            typer.echo(f"  + {entry.date} {entry.duty_type} {entry.flight_number or ''}")
        for entry in change.removed:
            typer.echo(f"  - {entry.date} {entry.duty_type} {entry.flight_number or ''}")
        for before, after in change.changed:
            typer.echo(
                f"  ~ {after.date} {after.duty_type} "
                f"({before.departure_time} -> {after.departure_time})"
            )


@app.command(name="export-ics")
def export_ics_cmd(out_path: Path) -> None:
    """Export the stored roster to a calendar (.ics) file."""
    entries = store.load(config.db_file())
    if not entries:
        _fail("No entries stored. Run `sync` first.", code=1)
    backend_mod.export_ics(entries, out_path)
    typer.echo(f"Wrote {len(entries)} events to {out_path}.")


@app.command()
def show(
    month: str | None = typer.Option(None, help="Filter to a month, e.g. 2026-08"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON lines"),
) -> None:
    """Print the stored roster to the console."""
    entries = store.load(config.db_file())
    if not entries:
        _fail("No entries stored. Run `sync` first.", code=1)
    if month:
        entries = [e for e in entries if e.date.startswith(month)]
    if not entries:
        typer.echo(f"No duties found{f' for {month}' if month else ''}.")
        return

    if as_json:
        for e in entries:
            typer.echo(json.dumps(e.to_dict(), ensure_ascii=False))
        return

    for e in entries:
        label = e.duty_type.upper()
        detail = e.flight_number or ""
        if e.departure_time and e.departure_airport:
            detail = f"{detail}  {e.departure_time[11:16]} {e.departure_airport}"
        typer.echo(f"{e.date}  {label:<9} {detail}".rstrip())


@app.command(name="layovers")
def layovers_cmd(
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """List layover and hotel arrangements extracted from the roster."""
    entries = store.load(config.db_file())
    items = layovers.extract_layovers(entries)
    if not items:
        typer.echo("No layovers found in stored roster.")
        return

    if as_json:
        typer.echo(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
        return

    typer.secho(f"\n🏨 ESCALES & HÔTELS ({len(items)} trouvées):\n", fg=typer.colors.BRIGHT_CYAN, bold=True)
    for lay in items:
        typer.secho(f"📍 {lay.city} ({lay.airport}) — Durée: {lay.duration_str}", fg=typer.colors.BRIGHT_YELLOW, bold=True)
        typer.echo(f"   Hôtel    : {lay.hotel_name}")
        typer.echo(f"   Check-in : {lay.check_in} | Check-out: {lay.check_out}")
        if lay.pickup_airport:
            typer.echo(f"   Navette  : {lay.pickup_airport}")
        if lay.phone:
            typer.echo(f"   Tél      : {lay.phone}")
        typer.echo(f"   Maps     : {lay.maps_url}\n")


@app.command(name="stats")
def stats_cmd(
    month: str | None = typer.Option(None, help="Filter to a month, e.g. 2026-10"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Display flight & duty time statistics and FTL compliance."""
    entries = store.load(config.db_file())
    if not entries:
        _fail("No entries stored. Run `sync` first.", code=1)
    st = stats.calculate_flight_stats(entries, target_month=month)

    if as_json:
        typer.echo(json.dumps(st, ensure_ascii=False, indent=2))
        return

    ftl = st.get("ftl", {})
    typer.secho(f"\n⏱️  STATISTIQUES DE VOL & FTL ({st.get('month')}):\n", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo(f"   Heures de vol (Block) : {st.get('block_time')} ({st.get('block_hours_decimal')}h)")
    typer.echo(f"   Temps de service (Duty): {st.get('duty_time')} ({st.get('duty_hours_decimal')}h)")
    typer.echo(f"   Heures de nuit        : {st.get('night_time')} ({st.get('night_hours_decimal')}h)")
    typer.echo(f"   Repos en escale       : {st.get('layover_time')}")
    typer.echo(f"   Nombre d'étapes (legs): {st.get('sectors_count')}")
    typer.echo(f"   Jours de repos (OFF)  : {st.get('days_off_count')}")

    status_color = typer.colors.GREEN if ftl.get("status") == "CONFORME" else typer.colors.RED
    typer.echo("\n   CONFORMITÉ FTL (Air Algérie / OM-A):")
    typer.secho(f"   Statut : {ftl.get('status')}", fg=status_color, bold=True)
    typer.echo(f"   Quota mensuel utilisé : {ftl.get('block_used_pct')}% (Max {ftl.get('monthly_block_limit_h')}h)\n")


@app.command(name="perdiem")
def perdiem_cmd(
    month: str | None = typer.Option(None, help="Filter to a month, e.g. 2026-10"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Calculate mission per diem allowances for layovers."""
    entries = store.load(config.db_file())
    if not entries:
        _fail("No entries stored. Run `sync` first.", code=1)
    pd = perdiem.calculate_per_diem(entries, target_month=month)

    if as_json:
        typer.echo(json.dumps(pd, ensure_ascii=False, indent=2))
        return

    totals = pd.get("totals", {})
    typer.secho(f"\n💰 CALCUL DES FRAIS DE MISSION / PER DIEM ({pd.get('month')}):\n", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo(f"   Total Devises USD : {totals.get('USD', 0):,.2f} $")
    typer.echo(f"   Total Devises EUR : {totals.get('EUR', 0):,.2f} €")
    typer.echo(f"   Total Escales DZD : {totals.get('DZD', 0):,.2f} DZD")
    typer.secho(f"   Valeur Totale Est.: ~ {totals.get('total_estimated_dzd', 0):,} DZD\n", fg=typer.colors.BRIGHT_YELLOW, bold=True)

    typer.echo("   Détail des rotations :")
    for rot in pd.get("rotations", []):
        typer.echo(f"   - {rot['date']} | {rot['city']:<28} | {rot['duration_h']}h ({rot['days']} j) -> {rot['allowance']} {rot['currency']}")
    typer.echo("")


@app.command(name="licenses")
def licenses_cmd(
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Track qualifications, simulator checks, and medical certificate expiry."""
    quals = training.load_qualifications()

    if as_json:
        typer.echo(json.dumps([q.to_dict() for q in quals], ensure_ascii=False, indent=2))
        return

    typer.secho(f"\n🪪 QUALIFICATIONS, VISITES MÉDICALES & CONTRÔLES ({len(quals)} titres):\n", fg=typer.colors.BRIGHT_CYAN, bold=True)
    for q in quals:
        status = q.status()
        color = typer.colors.GREEN if status == "VALID" else (typer.colors.YELLOW if status == "WARNING" else typer.colors.RED)
        days = q.days_remaining()
        days_str = f"Expire dans {days} j" if days >= 0 else f"EXPIRÉ depuis {abs(days)} j"
        typer.echo(f"   • {q.name:<45} [{q.expiry_date}] ", nl=False)
        typer.secho(f" {status:<8} ({days_str})", fg=color, bold=True)
        if q.notes:
            typer.echo(f"     Note : {q.notes}")
    typer.echo("")


@app.command(name="leave")
def leave_cmd(
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Display annual leave balance, history, and bidding requests."""
    lv = leave.load_leave_data()

    if as_json:
        typer.echo(json.dumps(lv, ensure_ascii=False, indent=2))
        return

    typer.secho("\n🏖️  SOLDE DES CONGÉS & DÉSIDÉRATA:\n", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo(f"   Droit annuel   : {lv.get('annual_entitlement')} jours")
    typer.echo(f"   Congés pris    : {lv.get('taken_days')} jours")
    typer.secho(f"   Solde restant  : {lv.get('remaining_days')} jours", fg=typer.colors.BRIGHT_GREEN, bold=True)
    typer.echo(f"   Ancienneté     : {lv.get('seniority_years')} ans\n")

    history = lv.get("leave_history", [])
    if history:
        typer.echo("   Historique récent :")
        for h in history:
            typer.echo(f"   - {h['start_date']} au {h['end_date']} ({h['days']} j) : {h['type']} [{h['status']}]")

    bids = lv.get("bidding_requests", [])
    if bids:
        typer.echo("\n   Désidérata de planning (Bidding) :")
        for b in bids:
            typer.echo(f"   - {b['period']} : {b['details']} [{b['status']}]")
    typer.echo("")


@app.command(name="crew")
def crew_cmd(
    flight: str = typer.Argument(..., help="Flight number, e.g. 462 or AH462"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
    personal_data: bool = typer.Option(False, "--personal-data", help="Include photo/phone/email"),
) -> None:
    """Real crew composition (cockpit & cabin) of one of your flights.

    Reads the eCrew DutyDetails view, so it needs credentials and a prior sync
    (the event id is resolved from the stored roster).
    """
    from backend import api_helpers

    event_id = api_helpers.find_event_id(flight)
    if not event_id:
        typer.secho(
            f"No flight {flight} in the synced roster. Run 'ecrew-sync sync' first.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    try:
        duty = duty_details.fetch_duty_crew_with_login(event_id)
    except duty_details.DutyDetailsError as exc:
        typer.secho(f"eCrew refused the crew lookup: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(json.dumps(duty.to_dict(include_personal_data=personal_data), ensure_ascii=False, indent=2))
        return

    number = duty.flight_number or flight.upper()
    typer.secho(f"\n👥 COMPOSITION D'ÉQUIPAGE — VOL {number}:\n", fg=typer.colors.BRIGHT_CYAN, bold=True)
    for m in duty.crew:
        tag = "⭐ " if m.is_pic else "   "
        details = f"Matricule: {m.id}"
        if m.pairing:
            details += f" · Pairing {m.pairing}"
        if m.max_fdp or m.actual_fdp:
            details += f" · FDP {m.actual_fdp or '—'}/{m.max_fdp or '—'}"
        typer.echo(f"{tag}[{m.role}] {m.name:<32} : {details}")
    typer.echo("")


@app.command(name="weather")
def weather_cmd(
    airport: str = typer.Argument("ALG", help="IATA or ICAO code, e.g. ALG, DAAG, JED, KUL"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Fetch live official NOAA METAR & TAF for an airport (independent of eCrew)."""
    typer.echo(f"Fetching official live aviation weather for {airport.upper()}...")
    wx = weather.fetch_weather(airport)

    if as_json:
        typer.echo(json.dumps(wx, ensure_ascii=False, indent=2))
        return

    apt = wx.get("airport", {})
    metar = wx.get("metar", {})
    taf_list = wx.get("taf", [])

    typer.secho("\n⛅ MÉTÉO AÉRONAUTIQUE (NOAA Aviation Weather Center) :", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.secho(f"   Aéroport : {apt.get('name', airport)} ({wx.get('icao')}) - {apt.get('country')}", fg=typer.colors.BRIGHT_YELLOW)

    cat = metar.get("flight_category", "VFR")
    cat_color = typer.colors.GREEN if cat == "VFR" else (typer.colors.BLUE if cat == "MVFR" else typer.colors.RED)
    typer.echo("   Catégorie de vol : ", nl=False)
    typer.secho(f"{cat}", fg=cat_color, bold=True)

    typer.echo("\n   📄 METAR BRUT :")
    typer.echo(f"   {metar.get('raw')}")

    if "wind_speed_kt" in metar:
        typer.echo("\n   DÉCODAGE :")
        typer.echo(f"   • Vent        : {metar.get('wind_dir_deg')}° / {metar.get('wind_speed_kt')} kt")
        typer.echo(f"   • Visi        : {metar.get('visibility_m')} m")
        typer.echo(f"   • Température : {metar.get('temp_c')}°C (Point de rosée: {metar.get('dew_c')}°C)")
        typer.echo(f"   • Altimètre   : QNH {metar.get('qnh_hpa')} hPa")

    if taf_list:
        typer.echo("\n   📄 TAF (Prévisions d'aérodrome) :")
        for t in taf_list:
            typer.echo(f"   {t}")
    typer.echo("")


@app.command()
def web(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = typer.Option(False, help="Enable auto-reload (development only)"),
) -> None:
    """Start the PWA web server."""
    import uvicorn

    typer.echo(f"Starting at http://{host}:{port}")
    if reload:
        typer.echo("Reload enabled — do not use this in production.")
    uvicorn.run("server.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
