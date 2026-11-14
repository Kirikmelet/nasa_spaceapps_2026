from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException

from app.models import Alert, Reading

app = FastAPI(title="Astronaut Health Monitor")

# In-memory stores (swap for SQLite later if time allows)
readings: list[Reading] = []
alerts: list[Alert] = []
_next_alert_id = 1


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


@app.post("/vitals")
def post_vitals(reading: Reading):
    readings.append(reading)
    # Placeholder hard limit; the real alert engine plugs in here later
    if reading.spo2 < 90:
        add_alert(reading.astronaut_id, "critical", "spo2",
                  f"SpO2 {reading.spo2}% below 90%", reading.timestamp)
    return {"status": "ok", "stored": len(readings)}


@app.get("/astronauts/{astronaut_id}/vitals")
def get_vitals(astronaut_id: str, limit: int = 300):
    data = [r for r in readings if r.astronaut_id == astronaut_id]
    return data[-limit:]


@app.get("/alerts")
def get_alerts(severity: Optional[str] = None):
    if severity:
        return [a for a in alerts if a.severity == severity]
    return alerts


@app.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int):
    for a in alerts:
        if a.id == alert_id:
            a.acknowledged = True
            return a
    raise HTTPException(status_code=404, detail="Alert not found")