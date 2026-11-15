# Astronaut Health Monitor

**NASA Space Apps Challenge 2026 (Chicago): Create Health Monitoring Software for Astronauts**

A real-time crew health monitor for a flight surgeon. Simulated astronaut vitals stream into a FastAPI backend. An alert engine compares each reading to **that astronaut's own baseline** and **current activity**, then raises tiered alerts on a live dashboard.

> A flight surgeon sees one clear alert, with context, instead of a wall of threshold alarms.

**All vitals data is simulated.** See [Data disclosure](#data-disclosure).

<!-- TODO Sunday: demo video link -->
<!-- TODO Sunday: dashboard screenshot -->

---

## Why personalized baselines?

Most health monitors use fixed thresholds such as "heart rate > 100". That approach fails in two ways:

- **It misses real problems.** If an astronaut's resting heart rate is normally 62, a sustained 95 is a meaningful change. It never crosses 100, so a fixed threshold stays silent.
- **It floods the operator with false alarms.** A heart rate of 150 during exercise is healthy. A fixed threshold flags it every time, and alarm fatigue makes people ignore alerts.

Our engine learns what is normal **for each astronaut, for each activity**, and alerts on meaningful deviations from that. Hard safety limits still apply on top, and they adjust to activity too.

## Features

| Feature | What it does |
|---|---|
| **Per-astronaut baselines** | A rolling baseline per (astronaut, metric, activity), learned from that astronaut's own readings |
| **Activity-aware limits** | Heart-rate limits change with activity (rest, sleep, exercise, EVA). HR 140 is critical at rest and normal during exercise. |
| **Debounce** | A baseline anomaly must appear in 3 consecutive readings before an alert fires, so a single sensor glitch is ignored |
| **Tiered alerts** | Info, warning and critical. Critical alerts are listed first. |
| **Escalation** | A warning left unresolved for 5 minutes becomes critical |
| **No duplicate alerts** | One open alert per astronaut and metric. New alerts fire only when something is new or has escalated. |
| **Faults don't become "normal"** | Anomalous readings are excluded from the baseline, so a sustained fault can't be learned as healthy |
| **Plain-language messages** | Alerts are written for a flight surgeon, not an engineer |
| **Live dashboard** | HTMX dashboard with per-astronaut vitals cards, trend charts (Chart.js), telemetry history, and acknowledge buttons |
<!-- TODO: add alert history sidebar row when merged -->

## Architecture

```
simulator/simulate.py  --POST /vitals-->  FastAPI server            <--GET /partials/*--  Browser
(simulated vitals,                        - stores readings                              (HTMX dashboard,
 fault + activity commands)               - runs the alert engine                         polls every 3 s)
                                          - serves API + dashboard
```

- **Simulator** (`simulator/`): a separate client that generates vitals and posts them over HTTP. The engine doesn't know the simulator exists. Real sensor feeds could replace it without changing the server.
- **Server** (`app/main.py`): FastAPI. One process serves both the JSON API and the dashboard.
- **Alert engine** (`app/alert_engine.py`): pure Python with no web or database code, so it can be unit-tested in isolation.
- **Dashboard** (`app/static/`, `app/templates/`): server-rendered HTML snippets swapped in by HTMX. No JavaScript framework.
- **Storage**: in memory, guarded by a lock (it resets on restart).

## How the alert engine works

For every reading, for every metric (`hr`, `spo2`, `temp`, `bp_sys`, `bp_dia`, `resp`):

1. **Hard limits** with four thresholds: critical low, warning low, warning high, critical high. Heart-rate limits depend on activity:

   | HR activity | Critical low | Warning low | Warning high | Critical high |
   |---|---|---|---|---|
   | rest | 40 | 50 | 100 | 130 |
   | sleep | 35 | 45 | 90 | 110 |
   | exercise | 40 | 50 | 170 | 190 |
   | eva | 40 | 50 | 160 | 185 |

2. **Baseline deviation** (only checked if no hard limit is tripped):
   - Rolling window of the last **60 readings** per (astronaut, metric, activity)
   - Needs **20 samples** before it can flag anything
   - Flags when |z-score| ≥ **3.5** for **3 consecutive readings**
   - |z| ≥ 4 gives a warning, otherwise info
3. **De-duplication**: one open alert per (astronaut, metric). The engine emits only new or escalated events, and the alert can fire again once the condition clears.
4. **Escalation**: a warning unresolved for **5 minutes** (measured by reading timestamps) becomes critical.

### Tuning trade-off

The z-threshold started at 2.5. In a healthy ~14-minute simulated run, one spurious info alert appeared, so we raised it to 3.5, which makes chance hits roughly 25 times rarer. The cost is that small sustained shifts (under about 3.5 standard deviations) are not flagged. Large shifts and all hard-limit breaches are unaffected. This is the usual sensitivity vs. false-alarm trade-off, and we chose fewer false alarms because alarm fatigue is the problem we are solving.

## Running it

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt   # if requests is missing: pip install requests
python -m uvicorn app.main:app --reload
```

In a second terminal, with the venv active:

```bash
python simulator/simulate.py
```

Open **http://localhost:8000/** for the dashboard, or **http://localhost:8000/docs** for the interactive API docs.

### Simulator commands

Type these in the simulator terminal. The astronaut id is optional and defaults to `astro_1`. Let it run about 60 s first so the baselines can warm up.

| Command | Effect | Expected alert |
|---|---|---|
| `hr [id]` | Resting HR drifts to ~95 | Baseline anomaly (no hard limit is crossed) |
| `hrhigh [id]` | HR ~140 | Critical at rest, none during exercise |
| `spo2 [id]` | SpO2 ~85% | Critical |
| `temp [id]` | 38.2 °C | Warning (escalates to critical after 5 min) |
| `fever [id]` | 39.5 °C | Critical |
| `bp [id]` | ~150/95 | Warning |
| `resp [id]` | ~24 breaths/min | Warning |
| `rest` / `sleep` / `exercise [id]` | Switch activity | Shifts normal vitals and the activity context |
| `clear [id]` | Back to normal (no id clears everyone) | Open alert clears |
| `quit` | Exit | |

Scripted run: `python simulator/simulate.py --hr-fault-at 60 --spo2-fault-at 120`

### Demo: context-aware alerting

1. Start the server and simulator, then wait ~60 s.
2. `exercise astro_2`: HR rises to ~130-140 with **no alert**, because that's normal during exercise.
3. `hrhigh astro_1`: the same heart rate at rest gives a **critical** alert.
4. `hr astro_3`: a resting HR of ~95 crosses no fixed threshold, but it's flagged because it's abnormal **for that astronaut**.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/vitals` | Submit a reading. It is stored, then the engine runs on it. |
| GET | `/astronauts/{id}/vitals?limit=300` | Recent readings for one astronaut |
| GET | `/alerts?severity=` | All alerts, with an optional severity filter |
| POST | `/alerts/{id}/acknowledge` | Acknowledge an alert (404 if the id is unknown) |
| GET | `/partials/vitals`, `/partials/alerts` | HTML snippets for the dashboard |

Example reading:

```json
{"astronaut_id": "astro_1", "timestamp": "2026-11-14T11:30:00", "hr": 72, "spo2": 98,
 "temp": 36.8, "bp_sys": 118, "bp_dia": 76, "resp": 14, "activity": "rest"}
```

## Tests

```bash
python -m pytest
```

Unit tests for the alert engine cover:
- normal readings raising nothing
- hard-limit criticals
- de-duplication, and alerts re-firing after a condition clears
- activity-aware HR limits
- debounce and single-spike rejection
- escalation
- no false alarms on 5,000 noisy normal readings
- a sustained shift being flagged and not learned as the baseline

## Data disclosure

- **All vitals are simulated** by `simulator/simulate.py`. No real astronaut or patient data is used.
- **Thresholds and reference ranges are illustrative.** They are plausible values chosen for demonstration and have not been verified against NASA standards or clinical guidance. <!-- TODO: update if ranges get sourced (e.g. NASA-STD-3001) -->

## Limitations and next steps

- Only heart rate is activity-aware today. Temperature, respiration and blood pressure use one fixed table. Next, we'd unify everything into a single sourced reference table.
- Storage is in memory and resets on restart. Next is persistence with SQLite.
- Use real data sources (wearable or analog-mission datasets) instead of simulation.
- Add astronaut self-reported symptoms as additional alert context.
- Add an alert audit trail that records who acknowledged what, and when.

## Team

<!-- TODO: names and roles -->
- Backend, alert engine, simulator, tests, README: _name_
- Dashboard (HTMX + Jinja2): _name_, _name_
- Reference ranges: _name_
- Storage: _name_

Built with Python, FastAPI, Pydantic, HTMX, Jinja2 and Chart.js.