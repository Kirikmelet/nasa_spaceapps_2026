# Astronaut Health Monitor

**NASA Space Apps Challenge 2026 (Chicago): Create Health Monitoring Software for Astronauts**

A real-time crew health monitor for a flight surgeon. Simulated astronaut vitals stream into a FastAPI backend. An alert engine checks each reading against activity-aware safety limits **and** against that astronaut's own learned baseline, then raises tiered alerts on a live dashboard.

> A flight surgeon sees one clear alert, with context, instead of a wall of threshold alarms.

**All vitals data is simulated.** See [Data disclosure](#data-disclosure).

<!-- TODO Sunday: demo video link -->
<!-- TODO Sunday: dashboard screenshot -->

---

## Why personalized baselines?

Most health monitors use fixed thresholds such as "heart rate > 100". That approach fails in two ways:

- **It misses real problems.** If an astronaut's resting heart rate is normally 70, a sustained 95 is a meaningful change. It never crosses 100, so a fixed threshold stays silent.
- **It floods the operator with false alarms.** A heart rate of 160 during exercise is expected. A fixed threshold flags it every time, and alarm fatigue makes people ignore alerts.

Our engine does two things. It applies safety limits that depend on what the astronaut is doing (for heart rate), and it learns what is normal **for each astronaut, for each activity**, flagging sustained deviations from that baseline.

## Features

| Feature | What it does |
|---|---|
| **Per-astronaut baselines** | A rolling baseline per (astronaut, metric, activity), learned from that astronaut's own readings |
| **Activity-aware HR limits** | Heart-rate limits change with activity (rest, sleep, exercise, EVA). HR 160 is fine during exercise and critical at rest. |
| **Debounce** | A baseline anomaly must appear in 3 consecutive readings before it fires, so a single spike is ignored |
| **Tiered alerts** | Info, warning and critical. The dashboard lists critical first, then newest first. |
| **Escalation** | A warning left unresolved for 5 minutes becomes critical |
| **No duplicate alerts** | One open alert per astronaut and metric. The engine emits only new or escalated alerts, and the alert can fire again after the condition clears. |
| **Faults don't become "normal"** | Anomalous readings are kept out of the baseline, so a sustained fault isn't learned as healthy |
| **Live dashboard** | Vitals cards per astronaut, a collapsible active-alerts panel with acknowledge buttons, and a per-metric modal with a trend chart and a color-coded reading history |
<!-- TODO: add alert history sidebar row once it's on main -->

## Architecture

```
simulator/simulate.py  --POST /vitals-->  FastAPI server            <--GET /partials/*--  Browser
(simulated vitals,                        - stores readings                              (HTMX dashboard,
 fault + activity commands)               - runs the alert engine                         polls every 3 s)
                                          - serves API + dashboard
```

- **Simulator** (`simulator/simulate.py`): a separate client that generates vitals for 3 astronauts and posts them over HTTP every 2 s. The server doesn't know the simulator exists, so a real sensor feed could replace it.
- **Server** (`app/main.py`): FastAPI. One process serves the JSON API, the HTML partials and the static dashboard.
- **Alert engine** (`app/alert_engine.py`): pure Python with no web code, so it is unit-tested in isolation.
- **Dashboard** (`app/static/index.html`, `app/templates/`): HTMX polls server-rendered partials every 3 s (with idiomorph to avoid flicker). Tailwind for styling, Chart.js for the trend chart.
- **Storage**: in-memory lists guarded by a `threading.Lock`. Data resets when the server restarts.

## How the alert engine works

For every reading, for every metric (`hr`, `spo2`, `temp`, `bp_sys`, `bp_dia`, `resp`):

1. **Hard limits**: four thresholds per metric (critical low, warning low, warning high, critical high).

   | Metric | Critical low | Warning low | Warning high | Critical high |
   |---|---|---|---|---|
   | HR, rest | 40 | 50 | 100 | 130 |
   | HR, sleep | 35 | 45 | 90 | 110 |
   | HR, exercise | 40 | 50 | 170 | 190 |
   | HR, EVA | 40 | 50 | 160 | 185 |
   | SpO2 (%) | 90 | 94 | none | none |
   | Temp (°C) | 35.0 | 35.5 | 37.8 | 39.0 |
   | BP systolic | 80 | 90 | 140 | 180 |
   | BP diastolic | 50 | 60 | 90 | 120 |
   | Resp (breaths/min) | 8 | 10 | 20 | 30 |

   Only heart rate depends on activity. The other metrics use the same limits for every activity.

2. **Baseline deviation** (used only when no hard limit is tripped):
   - Rolling window of the last **60 readings** per (astronaut, metric, activity)
   - Needs **20 samples** before it can flag anything (about 40 s at one reading every 2 s)
   - Flags when |z| > **3.5** for **3 consecutive readings**. Any normal reading resets the streak.
   - |z| ≥ 4 is a warning, otherwise info
   - The standard deviation is floored at 1% of the mean so tiny variance can't cause huge z-scores
3. **De-duplication**: one open alert per (astronaut, metric). A new alert is emitted only when the condition is new or its severity goes up. When the condition clears, the alert can fire again later.
4. **Escalation**: a warning still open after **5 minutes** (by reading timestamps) becomes critical.

### Tuning trade-off

The z-threshold started at 2.5. In a healthy ~14-minute simulated run, one spurious info alert appeared, so we raised it to 3.5, which makes chance hits roughly 25 times rarer. The cost is that small sustained shifts (under about 3.5 standard deviations) are not flagged. Large shifts and all hard-limit breaches are unaffected. We chose fewer false alarms because alarm fatigue is the problem we are solving.

## Running it

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

In a second terminal, with the venv active:

```bash
python simulator/simulate.py
```

Open **http://localhost:8000/** for the dashboard, or **http://localhost:8000/docs** for the interactive API docs.

### Simulator commands

Type these in the simulator terminal. The astronaut id (`astro_1`, `astro_2`, `astro_3`) is optional and defaults to `astro_1`. Let it run about 60 s first so the baselines can warm up.

| Command | Effect | Expected alert |
|---|---|---|
| `hr [id]` | HR drifts to ~95 | Baseline anomaly at rest (no hard limit crossed) |
| `hrhigh [id]` | HR ~140 | Critical at rest |
| `spo2 [id]` | SpO2 ~85% | Critical |
| `temp [id]` | 38.2 °C | Warning, escalates to critical after 5 min |
| `fever [id]` | 39.5 °C | Critical |
| `bp [id]` | ~150/95 | Warning |
| `resp [id]` | ~24 breaths/min | Warning |
| `rest` / `sleep` / `exercise [id]` | Switch activity | Shifts that astronaut's normal vitals and tags readings with the activity |
| `clear [id]` | Remove the fault (no id clears everyone) | Open condition clears |
| `quit` | Exit | |

Scripted run: `python simulator/simulate.py --hr-fault-at 60 --spo2-fault-at 120` (HR fault on astro_1, SpO2 fault on astro_2).

Baselines are per activity, so after an activity switch, baseline alerts pause for about 40 s while the new baseline builds. Hard limits apply immediately.

### Demo: context-aware alerting

1. Start the server and simulator, then wait ~60 s.
2. `exercise astro_2`: HR rises to ~130 with **no alert**, because that's within exercise limits.
3. `hrhigh astro_1`: a similar heart rate at rest gives a **critical** alert.
4. `hr astro_3`: a resting HR of ~95 crosses no fixed threshold, but it's flagged because it's abnormal **for that astronaut**.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/vitals` | Submit a reading. It is stored and run through the alert engine. Returns `{"status": "ok", "stored": <total readings>}`. |
| GET | `/astronauts/{id}/vitals?limit=300` | Most recent readings for one astronaut |
| GET | `/alerts?severity=` | All alerts, with an optional severity filter |
| POST | `/alerts/{id}/acknowledge` | Acknowledge an alert (404 if the id is unknown) |
| GET | `/partials/alerts` | HTML: unacknowledged alerts, critical first |
| GET | `/partials/vitals` | HTML: latest reading per astronaut |
| GET | `/` | Redirects to `/dashboard/` |

Example reading:

```json
{"astronaut_id": "astro_1", "timestamp": "2026-11-14T11:30:00", "hr": 72, "spo2": 98,
 "temp": 36.8, "bp_sys": 118, "bp_dia": 76, "resp": 14, "activity": "rest"}
```

## Tests

```bash
python -m pytest
```

10 unit tests in `tests/test_alert_engine.py`:
- normal readings raise nothing
- SpO2 85 is critical
- no duplicate alert while a condition persists
- an alert refires after the condition clears
- HR 160 is fine during exercise but critical at rest
- a baseline anomaly needs 3 consecutive readings
- single spikes are debounced
- an unresolved warning escalates to critical
- 5,000 noisy normal readings never flag
- a sustained shift is flagged and not learned into the baseline

## Data disclosure

- **All vitals are simulated** by `simulator/simulate.py`. No real astronaut or patient data is used.
- **Thresholds and reference ranges are illustrative.** They are plausible values chosen for demonstration and have not been verified against NASA standards or clinical guidance.
<!-- TODO: if the "Normal" ranges in NASA_DATA came from the NASA-STD-3001 spreadsheet in the repo, say so here and cite NASA-STD-3001 -->

## Limitations and next steps

- Only heart rate is activity-aware in the engine. The other metrics use one fixed table.
- There are two sets of ranges: the engine's limits, and the "Normal" ranges shown on the vitals cards (from `NASA_DATA` in `app/models.py`). They don't fully match. Next step: one shared, sourced reference table.
- Storage is in memory and resets on restart. A SQLite layer (`app/db.py`) is started but not connected yet.
- Use real data sources (wearables or analog-mission datasets) instead of simulation.
- Astronaut self-reported symptoms as additional alert context.

## Project layout

```
app/
  main.py           routes, in-memory stores
  alert_engine.py   hard limits, baseline detector, de-duplication, escalation
  models.py         Reading / Alert models, reference-range table
  db.py             SQLite storage (work in progress, not used yet)
  ai.py             Gemini client (experimental, not used yet)
  static/           dashboard page and CSS
  templates/        HTMX partials (alerts.html, vitals.html)
simulator/
  simulate.py       vitals generator with fault and activity commands
tests/
  test_alert_engine.py
```

## Team

Troy Dwijanto, Ayaan Khan, Jing Chen
- Backend, alert engine, simulator, tests, README: Ayaan Khan
- TODO - Add contributions

## Credits

Built with these open-source projects. Each is used under its own license.

- [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/) and [Pydantic](https://docs.pydantic.dev/): API server and data models
- [Jinja2](https://jinja.palletsprojects.com/): server-rendered templates
- [HTMX](https://htmx.org/) and [idiomorph](https://github.com/bigskysoftware/idiomorph): live dashboard updates
- [Tailwind CSS](https://tailwindcss.com/): styling
- [Chart.js](https://www.chartjs.org/): trend charts

## License

Released under the [MIT License](LICENSE).