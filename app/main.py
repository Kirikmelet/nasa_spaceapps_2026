import threading
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.alert_engine import RANK, AlertEngine
from app.db import dbInstance
from app.models import Alert, Reading, ReadingActivityType

app = FastAPI(title="Astronaut Health Monitor")
templates = Jinja2Templates(directory="app/templates")

engine = AlertEngine()
engine_lock = threading.Lock()  # the engine keeps rolling state; the DB has its own lock


class ActivityIn(BaseModel):
    activity: ReadingActivityType


def ingest_reading(reading: Reading) -> dict:
    """Store a reading, run it through the alert engine, store any alerts."""
    reading_id = dbInstance.add_reading(reading)
    with engine_lock:
        events = engine.process(reading)
    alert_ids = [
        dbInstance.add_alert(Alert(
            astronaut_id=reading.astronaut_id,
            severity=ev.severity,
            metric=ev.metric,
            message=ev.message,
            timestamp=reading.timestamp,
        ))
        for ev in events
    ]
    return {"id": reading_id, "alert_ids": alert_ids}


# ---------- JSON API ----------

@app.post("/vitals", status_code=201)  # simulator endpoint
def post_vitals(reading: Reading):
    return ingest_reading(reading)


@app.post("/astronauts/{astronaut_id}/vitals", status_code=201)
def add_reading(astronaut_id: str, reading: Reading):
    if reading.astronaut_id != astronaut_id:
        raise HTTPException(status_code=400, detail="astronaut_id mismatch")
    return ingest_reading(reading)


@app.get("/astronauts/{astronaut_id}/vitals", response_model=List[Reading])
def get_vitals(astronaut_id: str, limit: int = 300):
    return dbInstance.get_readings(astronaut_id, limit=limit)


@app.post("/astronauts/{astronaut_id}/activity", status_code=201)
def set_activity(astronaut_id: str, body: ActivityIn):
    latest = dbInstance.get_latest_reading(astronaut_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No readings for astronaut")
    return {"id": dbInstance.update_reading(latest.id, activity=body.activity)}


@app.get("/astronauts/{astronaut_id}/alerts", response_model=List[Alert])
def get_astronaut_alerts(astronaut_id: str, limit: int = 300):
    return dbInstance.get_alerts(astronaut_id=astronaut_id, limit=limit)


@app.post("/astronauts/{astronaut_id}/alerts", status_code=201)
def create_alert(astronaut_id: str, alert: Alert):
    if alert.astronaut_id != astronaut_id:
        raise HTTPException(status_code=400, detail="astronaut_id mismatch")
    return {"id": dbInstance.add_alert(alert)}


@app.get("/alerts", response_model=List[Alert])
def get_alerts(severity: Optional[str] = None):
    return dbInstance.get_alerts(severity=severity)


@app.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int):
    try:
        new_id = dbInstance.update_alert(alert_id, acknowledged=True)
    except LookupError:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"id": new_id, "acknowledged": True}


# ---------- HTML partials for the HTMX dashboard ----------

@app.get("/partials/alerts")
def alerts_partial(request: Request):
    active = dbInstance.get_alerts(active_only=True)
    active.sort(key=lambda a: (-RANK[a.severity], -a.id))  # critical first, newest first
    return templates.TemplateResponse(request, "alerts.html", {"alerts": active})


@app.get("/partials/vitals")
def vitals_partial(request: Request):
    cards = sorted(dbInstance.get_latest_readings(), key=lambda r: r.astronaut_id)
    return templates.TemplateResponse(request, "vitals.html", {"cards": cards})


# ---------- Page and redirect ----------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")


app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="dashboard")
