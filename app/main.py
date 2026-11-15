from app.models import Alert, Reading
from app.db import DbInstance
from app.alert_engine import RANK, AlertEngine, AlertEvent
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi import FastAPI, Request
import threading
from typing import Optional, List
from pydantic import BaseModel


app = FastAPI(title="Astronaut Health Monitor")
templates = Jinja2Templates(directory="app/templates")

reading_count: int = 0

# In-memory stores (swap for SQLite later if time allows)
engine = AlertEngine()
lock = threading.Lock()  # FastAPI runs plain def routes in a thread pool

# Help Functions


def collapse_log(snapshot: list[Alert],
                 limit: int = 100) -> list[dict]:
    groups: list[dict] = []
    open_group: dict[tuple, dict] = {}  # (astronaut, metric) -> latest group

    for a in snapshot:  # chronological order
        key = (a.astronaut_id, a.metric)
        g = open_group.get(key)

        # extend the group if same severity, and not a fresh alert after an ack
        if g and g["severity"] == a.severity and not (g["acknowledged"]
                                                      and not a.acknowledged):
            g["count"] += 1
            g["last_ts"] = a.timestamp
            g["message"] = a.message
            g["acknowledged"] = g["acknowledged"] and a.acknowledged
        else:
            g = {
                "id": a.id,  # first alert's id = stable DOM id for morphing
                "astronaut_id": a.astronaut_id,
                "metric": a.metric,
                "severity": a.severity,
                "message": a.message,
                "first_ts": a.timestamp,
                "last_ts": a.timestamp,
                "count": 1,
                "acknowledged": a.acknowledged,
            }
            groups.append(g)
            open_group[key] = g

    groups.reverse()  # newest first
    return groups[:limit]


class IngestReadingOutput(BaseModel):
    id: int
    alert_ids: List[int]


def ingest_reading(reading: Reading) -> IngestReadingOutput:
    with lock:
        reading_id = DbInstance.add_reading(reading)
        events: List[AlertEvent] = engine.process(reading)
    alert_ids = [
        DbInstance.add_alert(
            Alert(
                id=None,
                astronaut_id=reading.astronaut_id,
                severity=ev.severity,
                metric=ev.metric,
                message=ev.message,
                timestamp=reading.timestamp,
            )
        ) for ev in events
    ]
    return IngestReadingOutput(id=reading_id, alert_ids=alert_ids)


# ---------- JSON API (simulator, /docs, anyone who wants raw data) ----------

# Dummy input
@app.post("/api/dummy/vitals")
def post_dummy_vitals(reading: Reading):
    with lock:
        DbInstance.add_reading(reading)
        # ingest_reading(reading)
        for ev in engine.process(reading):
            DbInstance.add_alert(Alert(
                id=None,
                astronaut_id=reading.astronaut_id,
                severity=ev.severity,
                metric=ev.metric,
                message=ev.message,
                timestamp=reading.timestamp
            ))
            pass
        return {"status": "ok", "stored": reading_count}


@app.get("/api/astronauts/{astronaut_id}/vitals")
def get_vitals(astronaut_id: str, limit: int = 300):
    # with lock:
    #     data = [r for r in readings if r.astronaut_id == astronaut_id]
    # return data[-limit:]
    data: List[Reading] = []
    with lock:
        data = DbInstance.get_readings(astronaut_id)
    return data


@app.post("/api/astronauts/{astronaut_id}/vitals", status_code=201)
def post_vitals(astronaut_id: str, reading: Reading) -> IngestReadingOutput:
    if astronaut_id != reading.astronaut_id:
        raise ValueError("Astronaut ID is not the same!")
    return ingest_reading(reading)


@app.get("/api/alerts")
def get_alerts(severity: Optional[str] = None) -> List[Alert]:
    # with lock:
    #     if severity:
    #         return [a for a in alerts if a.severity == severity]
    #     return list(alerts)
    alerts: List[Alert] = []
    with lock:
        alerts = DbInstance.get_alerts(severity=severity)
    return alerts


@app.get("/api/alerts/{alert_id}")
def get_alerts_by_id(alert_id: str,
                     severity: Optional[str] = None) -> List[Alert]:
    # with lock:
    #     if severity:
    #         return [a for a in alerts if a.severity == severity]
    #     return list(alerts)
    alerts: List[Alert] = []
    with lock:
        alerts = DbInstance.get_alerts(alert_id=alert_id, severity=severity)
    return alerts


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int) -> int:
    with lock:
        return DbInstance.update_alert(alert_id, acknowledged=True)
    return -1


# ---------- HTML partials for the HTMX dashboard
# (templates are front end's) ----------

@app.get("/partials/alerts")
def alerts_partial(request: Request):
    with lock:
        alerts: List[Alert] = DbInstance.get_alerts(None, active_only=True)
    # critical first, newest first
    alerts.sort(key=lambda a: (-RANK[a.severity], -a.id))
    return templates.TemplateResponse(request, "alerts.html",
                                      {"alerts": alerts})


@app.get("/partials/vitals")
def vitals_partial(request: Request):
    latest: List[Reading] = []
    with lock:
        latest = DbInstance.get_latest_readings()
        cards = sorted(latest, key=lambda r: r.astronaut_id)
    return templates.TemplateResponse(request, "vitals.html", {"cards": cards})


@app.get("/partials/alert-log")
def alert_log_partial(request: Request, severity: Optional[str] = None):
    alerts: List[Alert] = []
    with lock:
        alerts = DbInstance.get_alerts(None)
        snapshot = alerts[-500:]  # cap the scan so it stays cheap every 3s
    groups = collapse_log(snapshot)
    if severity:
        groups = [g for g in groups if g["severity"] == severity]
    return templates.TemplateResponse(request, "alert-log.html",
                                      {"groups": groups})


# ---------- Page and redirect ----------

@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("app/static/favicon.ico")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")


app.mount("/dashboard", StaticFiles(directory="app/static",
          html=True), name="dashboard")
