"""CLI — commands: sync, export-ics, show, web."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Repo root (one level up from cli/)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import typer
from dotenv import load_dotenv

from backend import auth, fetch, parser, store, export as backend_mod

app = typer.Typer(add_completion=False, name="ecrew-sync")


def _base_url() -> str:
    return os.environ.get("ECREW_BASE_URL", "https://ecrew.airalgerie.dz/ecrew")


def _cookie_file() -> Path:
    return Path(os.environ.get("ECREW_COOKIE_FILE", "cookies.json"))


def _db_file() -> Path:
    return Path(os.environ.get("ECREW_DB_FILE", "roster.json"))


@app.command()
def login_test() -> None:
    """Log in and fetch the roster view, saving raw HTML to debug files."""
    load_dotenv()
    creds = auth.Credentials.from_env()
    base_url = _base_url()
    cookies = _cookie_file()

    session = auth.get_session(cookies)
    try:
        sid = auth.login(session, creds.username, creds.password, base_url, cookies)
        typer.echo(f"Logged in. session id: {sid}")
    except (auth.AuthError, NotImplementedError) as e:
        typer.echo(f"Login failed: {e}", err=True)
        raise typer.Exit(code=2)

    try:
        html = fetch.get_roster_page(session)
    except (fetch.FetchError, NotImplementedError) as e:
        typer.echo(f"Roster fetch failed: {e}", err=True)
        raise typer.Exit(code=2)

    debug = Path("debug_roster_view.html")
    debug.write_text(html, encoding="utf-8")
    typer.echo(f"Saved roster view HTML ({len(html)} bytes) to {debug}")


@app.command()
def sync() -> None:
    load_dotenv()
    creds = auth.Credentials.from_env()
    base_url = _base_url()
    cookies = _cookie_file()

    session = auth.get_session(cookies)
    try:
        auth.login(session, creds.username, creds.password, base_url, cookies)
        typer.echo("Logged in.")
    except (auth.AuthError, NotImplementedError) as e:
        typer.echo(f"auth.login() failed: {e}", err=True)
        raise typer.Exit(code=2)

    try:
        html = fetch.get_roster_page(session)
    except (fetch.FetchError, NotImplementedError) as e:
        typer.echo(f"fetch.get_roster_page() failed: {e}", err=True)
        raise typer.Exit(code=2)

    try:
        entries = parser.parse_roster(html)
    except (NotImplementedError, parser.ParseError) as e:
        typer.echo(f"parser.parse_roster() failed: {e}", err=True)
        debug = Path("debug_last_fetch.html")
        debug.write_text(html, encoding="utf-8")
        typer.echo(f"Saved HTML to {debug}")
        raise typer.Exit(code=2)

    store.save(entries, _db_file())
    typer.echo(f"Stored {len(entries)} entries to {_db_file()}.")


@app.command(name="export-ics")
def export_ics_cmd(out_path: Path) -> None:
    entries = store.load(_db_file())
    if not entries:
        typer.echo("No entries stored. Run `sync` first.", err=True)
        raise typer.Exit(code=1)
    backend_mod.export_ics(entries, out_path)
    typer.echo(f"Wrote {len(entries)} events to {out_path}.")


@app.command()
def show(month: Optional[str] = typer.Option(None, help="YYYY-MM")) -> None:
    entries = store.load(_db_file())
    if not entries:
        typer.echo("No entries stored. Run `sync` first.", err=True)
        raise typer.Exit(code=1)
    for e in entries:
        if month and not e.date.startswith(month):
            continue
        typer.echo(json.dumps(e.to_dict(), ensure_ascii=False))


@app.command()
def web(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
    import uvicorn

    typer.echo(f"Starting at http://{host}:{port}")
    uvicorn.run("server.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()