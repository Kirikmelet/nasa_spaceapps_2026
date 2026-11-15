from fastapi.middleware.cors import CORSMiddleware
from app.models import Alert, Reading, User
import html
from app.db import DbInstance
from app.ai_deepseek import router as AIRouter
from app.ai_deepseek import analyze_readings
import time
from app.status import classify
from app.alert_engine import RANK, AlertEngine, AlertEvent, METRIC_INFO
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi import FastAPI, Request, HTTPException, Form
import threading
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


app = FastAPI(title="Astronaut Health Monitor")
templates = Jinja2Templates(directory="app/templates")

reading_count: int = 0

# In-memory stores (swap for SQLite later if time allows)
engine = AlertEngine()
lock = threading.Lock()  # FastAPI runs plain def routes in a thread pool

# Help Functions

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000"],
                   allow_methods=["*"], allow_headers=["*"])


def names() -> dict[str, str]:
    with lock:
        return DbInstance.get_name_map()


def one_per_metric(alerts):
    seen, out = set(), []
    for a in alerts:
        key = (a.astronaut_id, a.metric)
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def render_alerts(request: Request):
    active = DbInstance.get_alerts(None, active_only=True)
    active.sort(key=lambda a: (-RANK[a.severity], -a.id))
    active = one_per_metric(active)
    return templates.TemplateResponse(request, "alerts.html", {"alerts": active, "names": names()})


@app.get("/partials/alerts")
def alerts_partial(request: Request):
    return render_alerts(request)


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
            g["value"] = a.value
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
                timestamp=reading.timestamp,
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


@app.post("/api/astronauts/{astronaut_id}/user")
def post_user(astronaut_id: str, user: User) -> int:
    if astronaut_id != user.astronaut_id:
        raise ValueError("Astronaut ID is not the same!")
    while lock:
        return DbInstance.add_user(user=user)


@app.get("/api/astronauts/{astronaut_id}/user", status_code=201)
def get_user(astronaut_id: str) -> User:
    while lock:
        return DbInstance.get_user(astronaut_id)


@app.get("/api/alerts")
def get_alerts(severity: Optional[str] = None) -> List[Alert]:
    # with lock:
    #     if severity:
    #         return [a for a in alerts if a.severity == severity]
    #     return list(alerts)
    alerts: List[Alert] = []
    with lock:
        alerts = DbInstance.get_alerts(None, severity=severity)
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


# @app.post("/api/astronauts/{astronaut_id}/alerts/{metric}/acknowledge")
# def acknowledge_group(request: Request, astronaut_id: str, metric: str):
#     pending = [a for a in DbInstance.get_alerts(astronaut_id=astronaut_id,
#                                                 active_only=True)
#                if a.metric == metric]
#     for a in pending:
#         DbInstance.update_alert(a.id, acknowledged=True)
#     return alerts_partial(request)   # re-render the panel

@app.post("/api/astronauts/{astronaut_id}/alerts/{metric}/acknowledge")
def acknowledge_group(request: Request, astronaut_id: str, metric: str):
    with lock:
        for a in DbInstance.get_alerts(None, astronaut_id=astronaut_id, active_only=True):
            if a.metric == metric:
                DbInstance.update_alert(a.id, acknowledged=True)
    return render_alerts(request)


# ---------- HTML partials for the HTMX dashboard
# (templates are front end's) ----------

# def render_alerts(request: Request):
#     active = dbInstance.get_alerts(active_only=True)
#     active.sort(key=lambda a: (-RANK[a.severity], -a.id))
#     active = one_per_metric(active)
#     return templates.TemplateResponse(request, "alerts.html", {"alerts": active})


@app.get("/partials/astronaut-options", response_class=HTMLResponse)
def astronaut_options():
    with lock:
        roster = DbInstance.get_name_map()
        ids = {r.astronaut_id for r in DbInstance.get_latest_readings()
               } | set(roster)
    return "".join(
        f'<option value="{html.escape(i)}">{html.escape(roster.get(i, i))}</option>'
        for i in sorted(ids)
    ) or '<option value="">No crew yet</option>'


@app.get("/partials/alerts")
def alerts_partial(request: Request):
    with lock:
        return render_alerts(request)

# @app.get("/partials/alerts")
# def alerts_partial(request: Request):
#     with lock:
#         alerts: List[Alert] = DbInstance.get_alerts(None, active_only=True)
#     # critical first, newest first
#     alerts.sort(key=lambda a: (-RANK[a.severity], -a.id))
#     return templates.TemplateResponse(request, "alerts.html",
#                                       {"alerts": alerts})


INSIGHT_COOLDOWN = 30
_insight_cache: dict[str, tuple[float, object, datetime]] = {}


@app.post("/partials/insight")
def insight_partial(request: Request, astronaut_id: str = Form(default="")):
    astronaut_id = astronaut_id.strip()
    if not astronaut_id:
        return templates.TemplateResponse(
            request, "insight.html",
            {"error": True, "message": "Pick an astronaut first."})

    now = time.time()
    hit = _insight_cache.get(astronaut_id)
    if hit and now - hit[0] < INSIGHT_COOLDOWN:      # protects your Gemini quota
        _, result, at = hit
        cached = True
    else:
        try:
            with lock:
                readings = DbInstance.get_readings(astronaut_id, limit=60)
            if not readings:
                return templates.TemplateResponse(
                    request, "insight.html",
                    {"error": True, "message": "No readings for this astronaut yet."})

            data = [r.model_dump(mode="json", exclude={"id", "origin_id"})
                    for r in readings]
            result = analyze_readings(astronaut_id, data)
            at, cached = datetime.now(), False
            _insight_cache[astronaut_id] = (now, result, at)
        except Exception as e:
            return templates.TemplateResponse(
                request, "insight.html", {"error": True, "message": str(e)})

    return templates.TemplateResponse(
        request, "insight.html",
        {"result": result, "generated_at": at, "cached": cached, "error": False})


@app.get("/partials/vitals")
def vitals_partial(request: Request):
    latest: List[Reading] = []
    with lock:
        latest = DbInstance.get_latest_readings()
        cards = sorted(latest, key=lambda r: r.astronaut_id)
    return templates.TemplateResponse(request, "vitals.html", {"cards": cards, "names": names()})


@app.get("/partials/alert-log")
def alert_log_partial(request: Request, severity: Optional[str] = None,
                      hide_stale: bool = False):
    with lock:
        snapshot = DbInstance.get_alerts(None)[-500:]
        current = {r.astronaut_id: r.activity
                   for r in DbInstance.get_latest_readings()}

    groups = collapse_log(snapshot)
    latest = {r.astronaut_id: r for r in DbInstance.get_latest_readings()}
    for g in groups:
        r = latest.get(g["astronaut_id"])
        g["now_activity"] = r.activity if r else None

    if hide_stale:
        groups = [g for g in groups if not g["stale"]]
    if severity:
        groups = [g for g in groups if g["severity"] == severity]
    return templates.TemplateResponse(request, "alert-log.html", {"groups": groups, "names": names()})


# status colors live next to classify() now
STATUS_COLOR = {"healthy": "#34d399",
                "warning": "#fbbf24", "critical": "#f43f5e"}
DECIMALS = {"spo2": 1, "temp": 1, "resp": 1}  # everything else: 0


@app.get("/partials/metric-history")
def metric_history(request: Request, astronaut_id: str, metric: str,
                   limit: int = 50, live: bool = False):
    if metric not in METRIC_INFO:
        raise HTTPException(404, "Unknown metric")
    label, unit = METRIC_INFO[metric]
    readings = DbInstance.get_readings(
        astronaut_id, limit=limit)  # oldest first

    rows = [{
        "time": r.timestamp.strftime("%H:%M:%S"),
        "activity": r.activity,
        "value": getattr(r, metric),
        "status": classify(metric, getattr(r, metric), r.activity),
    } for r in readings]

    ctx = {
        "astronaut_id": astronaut_id, "metric": metric, "label": label, "unit": unit,
        "decimals": DECIMALS.get(metric, 0),
        "rows": rows[::-1],  # table: newest first
        "chart": {           # chart: oldest first, colors decided server-side
            "label": f"{label} ({unit})",
            "labels": [r["time"] for r in rows],
            "values": [r["value"] for r in rows],
            "colors": [STATUS_COLOR[r["status"]] for r in rows],
        },
        "names": names()
    }
    name = "metric-live.html" if live else "metric-modal.html"
    return templates.TemplateResponse(request, name, ctx)


# ---------- Page and redirect ----------

@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("app/static/favicon.ico")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")


app.include_router(AIRouter)

app.mount("/dashboard", StaticFiles(directory="app/static",
          html=True), name="dashboard")
