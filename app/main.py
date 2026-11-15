from app.models import Alert, Reading
from app.ai import geminiClient
from app.alert_engine import RANK, AlertEngine
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from fastapi import FastAPI, HTTPException, Request
import threading
from datetime import datetime
from typing import Optional
import time
import json


_insight_cache = {"ts": 0.0, "text": None, "at": None}
INSIGHT_COOLDOWN = 30  # seconds

app = FastAPI(title="Astronaut Health Monitor")
templates = Jinja2Templates(directory="app/templates")

# In-memory stores (swap for SQLite later if time allows)
readings: list[Reading] = []
latest: dict[str, Reading] = {}   # most recent reading per astronaut
alerts: list[Alert] = []
_next_alert_id = 1
engine = AlertEngine()
lock = threading.Lock()  # FastAPI runs plain def routes in a thread pool


def build_insight_prompt() -> str:
    # copy data under the lock, then release it BEFORE the slow API call
    with lock:
        crew = [r.model_dump(mode="json") for r in sorted(
            latest.values(), key=lambda r: r.astronaut_id)]
        snapshot = alerts[-500:]
    recent = collapse_log(snapshot, limit=15)

    alert_lines = [
        {
            "astronaut": g["astronaut_id"],
            "metric": g["metric"],
            "severity": g["severity"],
            "count": g["count"],
            "last_seen": g["last_ts"].strftime("%H:%M:%S"),
            "acknowledged": g["acknowledged"],
        }
        for g in recent
    ]

    return (
        "You are a flight-surgeon assistant reviewing simulated astronaut telemetry.\n"
        "Summarize crew status in under 120 words: who needs attention first, "
        "any worrying trends, and one suggested next step. Plain text, no markdown.\n\n"
        f"Latest vitals per astronaut:\n{json.dumps(crew)}\n\n"
        f"Recent alerts (newest first, repeats collapsed):\n{json.dumps(alert_lines)}"
    )


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
    # critical first, newest first
    active.sort(key=lambda a: (-RANK[a.severity], -a.id))
    return templates.TemplateResponse(request, "alerts.html", {"alerts": active})


@app.get("/partials/vitals")
def vitals_partial(request: Request):
    with lock:
        cards = sorted(latest.values(), key=lambda r: r.astronaut_id)
    return templates.TemplateResponse(request, "vitals.html", {"cards": cards})


@app.get("/partials/alert-log")
def alert_log_partial(request: Request, severity: Optional[str] = None):
    with lock:
        snapshot = alerts[-500:]  # cap the scan so it stays cheap every 3s
    groups = collapse_log(snapshot)
    if severity:
        groups = [g for g in groups if g["severity"] == severity]
    return templates.TemplateResponse(request, "alert-log.html", {"groups": groups})


@app.post("/partials/insight")
def insight_partial(request: Request):
    now = time.time()
    error = None

    if _insight_cache["text"] and now - _insight_cache["ts"] < INSIGHT_COOLDOWN:
        text, cached = _insight_cache["text"], True
    else:
        try:
            text = geminiClient.query(build_insight_prompt())
            if not text:
                raise ValueError("Model returned empty!")
            _insight_cache.update(ts=now, text=text)
            cached = False
        except Exception as e:
            text, error = None, str(e)

    return templates.TemplateResponse(
        request, "insight.html",
        {"text": text, "error": error, "generated_at": _insight_cache["at"]},
    )


# ---------- Page and redirect ----------

@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("app/static/favicon.ico")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")

def collapse_log(snapshot: list[Alert], limit: int = 100) -> list[dict]:
    groups: list[dict] = []
    open_group: dict[tuple, dict] = {}  # (astronaut, metric) -> latest group

    for a in snapshot:  # chronological order
        key = (a.astronaut_id, a.metric)
        g = open_group.get(key)

        # extend the group if same severity, and not a fresh alert after an ack
        if g and g["severity"] == a.severity and not (g["acknowledged"] and not a.acknowledged):
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


app.mount("/dashboard", StaticFiles(directory="app/static", html=True), name="dashboard")
