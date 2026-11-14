import threading
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.alert_engine import RANK, AlertEngine
from app.models import Alert, Reading

app = FastAPI(title="Astronaut Health Monitor")
templates = Jinja2Templates(directory="app/templates")

# In-memory stores (swap for SQLite later if time allows)
readings: list[Reading] = []
latest: dict[str, Reading] = {}   # most recent reading per astronaut
alerts: list[Alert] = []
_next_alert_id = 1
engine = AlertEngine()
lock = threading.Lock()  # FastAPI runs plain def routes in a thread pool


def add_alert(astronaut_id: str, severity: str, metric: str, message: str, ts: datetime) -> Alert:
    global _next_alert_id
    alert = Alert(
        id=_next_alert_id,
        astronaut_id=astronaut_id,
        severity=severity,
        metric=metric,
        message=message,
        timestamp=ts,
    )
    _next_alert_id += 1
    alerts.append(alert)
    return alert


# ---------- JSON API (simulator, /docs, anyone who wants raw data) ----------

@app.post("/vitals")
def post_vitals(reading: Reading):
    with lock:
        readings.append(reading)
        latest[reading.astronaut_id] = reading
        for ev in engine.process(reading):
            add_alert(reading.astronaut_id, ev.severity, ev.metric,
                      ev.message, reading.timestamp)
        return {"status": "ok", "stored": len(readings)}


@app.get("/astronauts/{astronaut_id}/vitals")
def get_vitals(astronaut_id: str, limit: int = 300):
    with lock:
        data = [r for r in readings if r.astronaut_id == astronaut_id]
    return data[-limit:]


@app.get("/alerts")
def get_alerts(severity: Optional[str] = None):
    with lock:
        if severity:
            return [a for a in alerts if a.severity == severity]
        return list(alerts)


@app.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int):
    with lock:
        for a in alerts:
            if a.id == alert_id:
                a.acknowledged = True
                return a
    raise HTTPException(status_code=404, detail="Alert not found")


# ---------- HTML partials for the HTMX dashboard (templates are front end's) ----------

@app.get("/partials/alerts")
def alerts_partial(request: Request):
    with lock:
        active = [a for a in alerts if not a.acknowledged]
    active.sort(key=lambda a: (-RANK[a.severity], -a.id))  # critical first, newest first
    return templates.TemplateResponse(request, "alerts.html", {"alerts": active})


@app.get("/partials/vitals")
def vitals_partial(request: Request):
    with lock:
        cards = sorted(latest.values(), key=lambda r: r.astronaut_id)
    return templates.TemplateResponse(request, "vitals.html", {"cards": cards})


# ---------- Page and redirect ----------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")


app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="dashboard")