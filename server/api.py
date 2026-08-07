"""FastAPI server — JSON API + serves the PWA frontend from frontend/."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Root of the repo (one level up from server/)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import auth, fetch, parser, store, export as export_mod
from server.scheduler import trigger_sync, get_sync_status, start_scheduler


DB_FILE = Path(os.environ.get("ECREW_DB_FILE", "roster.json"))
FRONTEND_STATIC = ROOT / "frontend" / "static"


app = FastAPI(title="eCrew Sync", version="0.1.0")


@app.on_event("startup")
async def _on_startup() -> None:
    start_scheduler()


# ----------------------------------------------------------------- API


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "sync_status": get_sync_status(),
        "synced_at": store.load_meta(DB_FILE).get("synced_at"),
    }


@app.get("/api/roster")
async def get_roster(month: Optional[str] = None) -> dict:
    meta = store.load_meta(DB_FILE)
    entries = store.load(DB_FILE)
    if month:
        entries = [e for e in entries if e.date.startswith(month)]
    return {
        "synced_at": meta.get("synced_at"),
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@app.post("/api/sync")
async def sync_now() -> dict:
    started = trigger_sync()
    return {"started": started, "status": get_sync_status()}


@app.get("/api/export.ics")
async def export_ics():
    entries = store.load(DB_FILE)
    if not entries:
        raise HTTPException(status_code=404, detail="No roster stored.")
    try:
        out = export_mod.export_ics(entries, Path(tempfile.gettempdir()) / "ecrew_export.ics")
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Export not ready.")
    return FileResponse(out, media_type="text/calendar", filename="roster.ics")


# -------------------------------------------------------------------- Static

if FRONTEND_STATIC.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_STATIC), html=True), name="frontend")