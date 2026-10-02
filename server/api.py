"""FastAPI server — JSON API + serves the PWA frontend from frontend/.

Config is resolved lazily through ``backend.config`` (never at import time) so
a local ``.env`` is honoured — the previous module-level ``DB_FILE`` read
happened before ``load_dotenv()`` ran and silently ignored ``.env``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles

# Import as a package (server.api) or by path (uvicorn server.api:app).
try:  # pragma: no cover - import shim for direct script execution
    from backend import config, store
    from backend import export as export_mod
    from backend import crew_list as crew_mod
    from backend import layovers as layovers_mod
    from backend import leave as leave_mod
    from backend import perdiem as perdiem_mod
    from backend import stats as stats_mod
    from backend import training as training_mod
    from backend import weather as weather_mod
    from server.auth_dep import require_token
    from server.logging_setup import setup_logging
    from server.scheduler import (
        get_contract_status,
        get_sync_status,
        shutdown_scheduler,
        start_scheduler,
        trigger_sync,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend import config, store
    from backend import export as export_mod
    from backend import crew_list as crew_mod
    from backend import layovers as layovers_mod
    from backend import leave as leave_mod
    from backend import perdiem as perdiem_mod
    from backend import stats as stats_mod
    from backend import training as training_mod
    from backend import weather as weather_mod
    from server.auth_dep import require_token
    from server.logging_setup import setup_logging
    from server.scheduler import (
        get_contract_status,
        get_sync_status,
        shutdown_scheduler,
        start_scheduler,
        trigger_sync,
    )


setup_logging()
logger = logging.getLogger("ecrew.api")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_STATIC = ROOT / "frontend" / "static"

# /docs and /openapi.json are a free map of the API; keep them off in production.
_ENABLE_DOCS = config.docs_enabled()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background scheduler on boot, stop it cleanly on shutdown.

    Replaces the deprecated ``@app.on_event("startup")``.
    """
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="eCrew Sync",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if _ENABLE_DOCS else None,
    redoc_url="/redoc" if _ENABLE_DOCS else None,
    openapi_url="/openapi.json" if _ENABLE_DOCS else None,
)


# ----------------------------------------------------------------- API


@app.get("/api/health")
async def health() -> dict:
    """Liveness + sync status.

    ``status`` is "ok" whenever the process is up; ``sync_status.last_error``
    and ``sync_status.contract`` carry the real sync health so a container
    stays up (and restartable) rather than crash-looping on a portal outage.

    Always reachable without a token — the container healthcheck depends on it.
    """
    db_file = config.db_file()
    meta = store.load_meta(db_file)
    sync_status = get_sync_status()
    return {
        "status": "ok",
        "sync_status": sync_status,
        "synced_at": meta.get("synced_at"),
        "entry_count": len(store.load(db_file)),
        # "degraded" surfaces a failed or drifted contract without failing the
        # healthcheck (which would cause a restart loop during a portal outage).
        "roster_state": _roster_state(sync_status),
    }


def _roster_state(sync_status: dict) -> str:
    """ok | never_synced | stale | degraded — a single word for monitoring."""
    if sync_status.get("running"):
        return "syncing"
    if sync_status.get("last_error"):
        return "degraded"
    if not sync_status.get("last_run"):
        return "never_synced"
    contract = sync_status.get("contract") or {}
    if contract and not contract.get("ok", True):
        return "degraded"
    return "ok"


@app.get("/api/roster", dependencies=[Depends(require_token)])
async def get_roster(
    month: str | None = Query(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Filter by month, e.g. 2026-08",
    )
) -> dict:
    """Return the stored roster, optionally filtered to a single month."""
    db_file = config.db_file()
    meta = store.load_meta(db_file)
    entries = store.load(db_file)
    if month:
        entries = [e for e in entries if e.date.startswith(month)]
    entries.sort(key=lambda e: (e.date, e.departure_time or "", e.flight_number or ""))
    return {
        "synced_at": meta.get("synced_at"),
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@app.post("/api/sync", dependencies=[Depends(require_token)])
async def sync_now(force: bool = Query(False, description="Bypass the debounce window")) -> dict:
    """Trigger a background sync. Returns immediately."""
    started = trigger_sync(force=force)
    status_ = get_sync_status()
    if not started:
        reason = (
            "A sync is already running."
            if status_["running"]
            else f"Debounced — last sync finished less than {status_['min_gap_seconds']}s ago. "
            "Use ?force=true to override."
        )
        return {"started": False, "reason": reason, "status": status_}
    return {"started": True, "status": status_}


def _ics_response(body: str, *, download: bool) -> Response:
    """Common headers for both the .ics download and the subscription feed."""
    disposition = "attachment" if download else "inline"
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'{disposition}; filename="roster.ics"',
            # Calendar clients poll this; don't let a proxy cache a stale roster.
            "Cache-Control": "no-cache, max-age=0, must-revalidate",
        },
    )


@app.get("/api/export.ics", dependencies=[Depends(require_token)])
async def export_ics():
    """Download the roster as a one-shot .ics file.

    The file is static once downloaded. For an always-current calendar use
    ``/api/calendar.ics`` instead.
    """
    entries = store.load(config.db_file())
    if not entries:
        raise HTTPException(status_code=404, detail="No roster stored.")
    try:
        return _ics_response(export_mod.serialize_calendar(entries), download=True)
    except Exception as exc:  # noqa: BLE001 - surface the real reason
        logger.exception("ICS export failed")
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc


@app.get("/api/calendar.ics", dependencies=[Depends(require_token)])
async def calendar_feed() -> Response:
    """Subscribable calendar feed (Phase 2).

    Subscribe a calendar app to this URL and it stays current automatically:
    every sync rewrites the feed, stable UIDs mean edits update in place, and
    LAST-MODIFIED lets the client tell "unchanged" from "needs refresh".

    Google Calendar: "Other calendars" > "From URL" > this URL (prefix with
    ``webcal://``). Apple Calendar: New Calendar Subscription > this URL.
    """
    entries = store.load(config.db_file())
    if not entries:
        raise HTTPException(status_code=404, detail="No roster stored yet.")
    return _ics_response(export_mod.serialize_calendar(entries), download=False)


@app.get("/api/contract")
async def contract_status() -> dict:
    """Portal contract canary report from the most recent sync (Phase 0/1).

    Read-only diagnostics — contains no duty data, so it is reachable without
    a token even when auth is enabled.
    """
    return get_contract_status()


# --- Enriched Modules ----------------------------------------------------- #

@app.get("/api/layovers", dependencies=[Depends(require_token)])
async def get_layovers() -> dict:
    """Hotel & Layover Logistics (Addresses, contacts, pick-ups, map links)."""
    entries = store.load(config.db_file())
    layover_list = layovers_mod.extract_layovers(entries)
    return {"count": len(layover_list), "layovers": [l.to_dict() for l in layover_list]}


@app.get("/api/stats", dependencies=[Depends(require_token)])
async def get_stats(month: str | None = None) -> dict:
    """Flight & Duty time statistics + FTL limits compliance."""
    entries = store.load(config.db_file())
    return stats_mod.calculate_flight_stats(entries, target_month=month)


@app.get("/api/perdiem", dependencies=[Depends(require_token)])
async def get_perdiem(month: str | None = None) -> dict:
    """Per Diem & mission allowances calculation (USD / EUR / DZD)."""
    entries = store.load(config.db_file())
    return perdiem_mod.calculate_per_diem(entries, target_month=month)


@app.get("/api/licenses", dependencies=[Depends(require_token)])
async def get_licenses() -> dict:
    """License & Medical Expiry tracking with countdowns and status."""
    quals = training_mod.load_qualifications()
    return {"count": len(quals), "qualifications": [q.to_dict() for q in quals]}


@app.get("/api/leave", dependencies=[Depends(require_token)])
async def get_leave() -> dict:
    """Vacation / Annual Leave balance, history and bidding requests."""
    return leave_mod.load_leave_data()


@app.get("/api/crew/{flight_number}", dependencies=[Depends(require_token)])
async def get_crew(flight_number: str) -> dict:
    """Crew list (Cockpit & Cabin) for a flight number."""
    crew = crew_mod.get_crew_for_flight(flight_number)
    return {"flight_number": flight_number, "crew": crew}


@app.get("/api/weather/{code}")
async def get_weather(code: str) -> dict:
    """Live official METAR/TAF aviation weather (NOAA feed, independent of eCrew)."""
    return weather_mod.fetch_weather(code)


# -------------------------------------------------------------------- Static


if FRONTEND_STATIC.is_dir():
    # Mounted last so the /api routes above take precedence.
    app.mount("/", StaticFiles(directory=str(FRONTEND_STATIC), html=True), name="frontend")
