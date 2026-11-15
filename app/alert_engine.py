# """Alert engine: pure Python, no web code, so it is easy to test."""
# from collections import deque
# from dataclasses import dataclass
# from datetime import timedelta
# from statistics import mean, stdev
# from typing import Optional

# from app.models import Reading

# METRICS = ["hr", "spo2", "temp", "bp_sys", "bp_dia", "resp"]
# RANK = {"info": 0, "warning": 1, "critical": 2}

# # (critical_low, warn_low, warn_high, critical_high); None = no limit.
# # Illustrative ranges. Verify against cited sources before the README claims them.
# DEFAULT_LIMITS = {
#     "spo2": (90, 94, None, None),
#     "temp": (35.0, 35.5, 37.8, 39.0),
#     "bp_sys": (80, 90, 140, 180),
#     "bp_dia": (50, 60, 90, 120),
#     "resp": (8, 10, 20, 30),
# }
# # Heart rate limits depend on activity (the context-aware part).
# HR_LIMITS = {
#     "rest": (40, 50, 100, 130),
#     "sleep": (35, 45, 90, 110),
#     "exercise": (40, 50, 170, 190),
#     "eva": (40, 50, 160, 185),
# }


# # Readable names and units for alert messages (written for a flight surgeon).
# METRIC_INFO = {
#     "hr": ("heart rate", "bpm"),
#     "spo2": ("blood oxygen", "%"),
#     "temp": ("body temperature", "°C"),
#     "bp_sys": ("systolic blood pressure", "mmHg"),
#     "bp_dia": ("diastolic blood pressure", "mmHg"),
#     "resp": ("breathing rate", "breaths/min"),
# }
# ACTIVITY_PHRASE = {"rest": "at rest", "sleep": "during sleep",
#                    "exercise": "during exercise", "eva": "during EVA"}


# def crew_name(astronaut_id: str) -> str:
#     """astro_1 -> Astro 1"""
#     return astronaut_id.replace("_", " ").title()


# def fmt(metric: str, value: float) -> str:
#     """Value with unit, e.g. 95 bpm, 85%, 38.2 °C."""
#     unit = METRIC_INFO[metric][1]
#     v = f"{value:.1f}" if metric in ("temp", "spo2") else f"{value:.0f}"
#     if v.endswith(".0") and metric == "spo2":
#         v = v[:-2]
#     return f"{v}{unit}" if unit == "%" else f"{v} {unit}"


# @dataclass
# class AlertEvent:
#     severity: str
#     metric: str
#     message: str


# def check_hard_limits(metric: str, value: float, activity: str, astronaut_id: str = "astronaut"):
#     """Return (severity, message) if value breaks an absolute limit, else (None, '')."""
#     lims = HR_LIMITS[activity] if metric == "hr" else DEFAULT_LIMITS[metric]
#     crit_lo, warn_lo, warn_hi, crit_hi = lims
#     who = f"{crew_name(astronaut_id)}'s {METRIC_INFO[metric][0]}"
#     ctx = ACTIVITY_PHRASE.get(activity, f"during {activity}")
#     if crit_lo is not None and value < crit_lo:
#         return "critical", (f"{who} is critically low {ctx} "
#                             f"({fmt(metric, value)}, safe minimum {fmt(metric, crit_lo)})")
#     if crit_hi is not None and value > crit_hi:
#         return "critical", (f"{who} is critically high {ctx} "
#                             f"({fmt(metric, value)}, safe maximum {fmt(metric, crit_hi)})")
#     if warn_lo is not None and value < warn_lo:
#         return "warning", (f"{who} is low {ctx} "
#                            f"({fmt(metric, value)}, normal minimum {fmt(metric, warn_lo)})")
#     if warn_hi is not None and value > warn_hi:
#         return "warning", (f"{who} is high {ctx} "
#                            f"({fmt(metric, value)}, normal maximum {fmt(metric, warn_hi)})")
#     return None, ""


# class BaselineDetector:
#     """Rolling baseline for one (astronaut, metric, activity).

#     Flags a value only after `consecutive` anomalous readings in a row
#     (debounce). Anomalous values are kept out of the baseline so a fault
#     does not teach the detector that the fault is normal.
#     """

#     def __init__(self, window=60, min_samples=20, z_threshold=3.5, consecutive=3):
#         self.values = deque(maxlen=window)
#         self.min_samples = min_samples
#         self.z_threshold = z_threshold
#         self.consecutive = consecutive
#         self.streak = 0
#         self.last_mean: Optional[float] = None  # baseline mean at the last check

#     def update(self, x: float) -> Optional[float]:
#         """Return the z-score once an anomaly is confirmed, else None."""
#         if len(self.values) < self.min_samples:
#             self.values.append(x)
#             return None
#         mu = mean(self.values)
#         self.last_mean = mu
#         sd = max(stdev(self.values), 0.01 * abs(mu), 1e-6)  # floor avoids divide-by-~0
#         z = (x - mu) / sd
#         if abs(z) > self.z_threshold:
#             self.streak += 1
#             return z if self.streak >= self.consecutive else None
#         self.streak = 0
#         self.values.append(x)
#         return None


# @dataclass
# class _Open:
#     severity: str
#     since: object  # datetime of the reading that opened it


# class AlertEngine:
#     def __init__(self, escalate_after: timedelta = timedelta(minutes=5)):
#         self.escalate_after = escalate_after
#         self._detectors = {}  # (astronaut, metric, activity) -> BaselineDetector
#         self._open = {}       # (astronaut, metric) -> _Open

#     def process(self, r: Reading) -> list[AlertEvent]:
#         """Feed one reading; return only NEW or ESCALATED alerts (no duplicates)."""
#         events = []
#         for metric in METRICS:
#             value = getattr(r, metric)
#             key = (r.astronaut_id, metric)

#             sev, msg = check_hard_limits(metric, value, r.activity, r.astronaut_id)

#             det = self._detectors.setdefault(
#                 (r.astronaut_id, metric, r.activity), BaselineDetector())
#             z = det.update(value)
#             if sev is None and z is not None:
#                 # Inside normal limits but unusual for THIS astronaut in THIS activity.
#                 sev = "warning" if abs(z) >= 4 else "info"
#                 direction = "high" if z > 0 else "low"
#                 msg = (f"{crew_name(r.astronaut_id)}'s {METRIC_INFO[metric][0]} is "
#                        f"unusually {direction} for them "
#                        f"{ACTIVITY_PHRASE.get(r.activity, r.activity)} "
#                        f"({fmt(metric, value)}, usually about {fmt(metric, det.last_mean)})")

#             state = self._open.get(key)
#             if sev is None:
#                 self._open.pop(key, None)  # condition cleared
#                 continue

#             if state is None or RANK[sev] > RANK[state.severity]:
#                 self._open[key] = _Open(sev, r.timestamp)
#                 events.append(AlertEvent(sev, metric, msg))
#             elif (state.severity == "warning"
#                   and r.timestamp - state.since >= self.escalate_after):
#                 state.severity = "critical"
#                 mins = (r.timestamp - state.since).total_seconds() / 60
#                 events.append(AlertEvent(
#                     "critical", metric, f"{msg}. Unresolved for {mins:.0f} min, escalated to critical"))
#         return events
"""Alert engine: pure Python, no web code, so it is easy to test."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Optional

from app.models import Reading

METRICS = ["hr", "spo2", "temp", "bp_sys", "bp_dia", "resp"]
RANK = {"info": 0, "warning": 1, "critical": 2}

# (critical_low, warn_low, warn_high, critical_high); None = no limit.
# Illustrative ranges. Verify against cited sources before the README claims them.
DEFAULT_LIMITS = {
    "spo2": (90, 94, None, None),
    "temp": (35.0, 35.5, 37.8, 39.0),
    "bp_sys": (80, 90, 140, 180),
    "bp_dia": (50, 60, 90, 120),
    "resp": (8, 10, 20, 30),
}
# Heart rate limits depend on activity (the context-aware part).
HR_LIMITS = {
    "rest": (40, 50, 100, 130),
    "sleep": (35, 45, 90, 110),
    "exercise": (40, 50, 170, 190),
    "eva": (40, 50, 160, 185),
}

# Readable names and units for alert messages (written for a flight surgeon).
METRIC_INFO = {
    "hr": ("heart rate", "bpm"),
    "spo2": ("blood oxygen", "%"),
    "temp": ("body temperature", "°C"),
    "bp_sys": ("systolic blood pressure", "mmHg"),
    "bp_dia": ("diastolic blood pressure", "mmHg"),
    "resp": ("breathing rate", "breaths/min"),
}
ACTIVITY_PHRASE = {"rest": "at rest", "sleep": "during sleep",
                   "exercise": "during exercise", "eva": "during EVA"}


# ---------- helpers ----------

def normalize_activity(activity) -> str:
    """'exercise_treadmill' -> 'exercise', enums -> their value, unknown -> 'rest'."""
    a = str(getattr(activity, "value", activity)).lower()
    return next((k for k in HR_LIMITS if a == k or a.startswith(k)), "rest")


def as_utc(dt: datetime) -> datetime:
    """Make every timestamp timezone-aware so subtraction never raises TypeError."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def crew_name(astronaut_id: str) -> str:
    """astro_1 -> Astro 1, AST-001 -> Ast 001"""
    return astronaut_id.replace("_", " ").replace("-", " ").title()


def fmt(metric: str, value: float) -> str:
    """Value with unit, e.g. 95 bpm, 85%, 38.2 °C."""
    unit = METRIC_INFO[metric][1]
    v = f"{value:.1f}" if metric in ("temp", "spo2") else f"{value:.0f}"
    if v.endswith(".0") and metric == "spo2":
        v = v[:-2]
    return f"{v}{unit}" if unit == "%" else f"{v} {unit}"


@dataclass
class AlertEvent:
    severity: str
    metric: str
    message: str


def check_hard_limits(metric: str, value: float, activity: str, astronaut_id: str = "astronaut"):
    """Return (severity, message) if value breaks an absolute limit, else (None, '')."""
    activity = normalize_activity(activity)
    lims = HR_LIMITS[activity] if metric == "hr" else DEFAULT_LIMITS[metric]
    crit_lo, warn_lo, warn_hi, crit_hi = lims
    who = f"{crew_name(astronaut_id)}'s {METRIC_INFO[metric][0]}"
    ctx = ACTIVITY_PHRASE[activity]
    if crit_lo is not None and value < crit_lo:
        return "critical", (f"{who} is critically low {ctx} "
                            f"({fmt(metric, value)}, safe minimum {fmt(metric, crit_lo)})")
    if crit_hi is not None and value > crit_hi:
        return "critical", (f"{who} is critically high {ctx} "
                            f"({fmt(metric, value)}, safe maximum {fmt(metric, crit_hi)})")
    if warn_lo is not None and value < warn_lo:
        return "warning", (f"{who} is low {ctx} "
                           f"({fmt(metric, value)}, normal minimum {fmt(metric, warn_lo)})")
    if warn_hi is not None and value > warn_hi:
        return "warning", (f"{who} is high {ctx} "
                           f"({fmt(metric, value)}, normal maximum {fmt(metric, warn_hi)})")
    return None, ""


class BaselineDetector:
    """Rolling baseline for one (astronaut, metric, activity).

    Flags a value only after `consecutive` anomalous readings in a row
    (debounce). Anomalous values are kept out of the baseline so a fault
    does not teach the detector that the fault is normal. If the "anomaly"
    lasts `adapt_after` readings in a row, it is treated as a genuine shift
    and the baseline restarts from the new level.
    """

    def __init__(self, window=60, min_samples=20, z_threshold=3.5,
                 consecutive=3, adapt_after=50):
        self.values = deque(maxlen=window)
        self.min_samples = min_samples
        self.z_threshold = z_threshold
        self.consecutive = consecutive
        self.adapt_after = adapt_after
        self.streak = 0
        self.last_mean: Optional[float] = None  # baseline mean at the last check

    def update(self, x: float) -> Optional[float]:
        """Return the z-score once an anomaly is confirmed, else None."""
        if len(self.values) < self.min_samples:
            self.values.append(x)
            return None
        mu = mean(self.values)
        self.last_mean = mu
        sd = max(stdev(self.values), 0.01 * abs(mu), 1e-6)  # floor avoids divide-by-~0
        z = (x - mu) / sd
        if abs(z) > self.z_threshold:
            self.streak += 1
            if self.streak >= self.adapt_after:  # permanent shift: relearn
                self.values.clear()
                self.values.append(x)
                self.streak = 0
                return None
            return z if self.streak >= self.consecutive else None
        self.streak = 0
        self.values.append(x)
        return None


@dataclass
class _Open:
    severity: str
    since: datetime            # reading time that opened (or re-armed) it
    escalated: bool = False    # True once escalated by time, stays until cleared


class AlertEngine:
    def __init__(self, escalate_after: timedelta = timedelta(minutes=5)):
        self.escalate_after = escalate_after
        self._detectors = {}  # (astronaut, metric, activity) -> BaselineDetector
        self._open = {}       # (astronaut, metric) -> _Open

    def process(self, r: Reading) -> list[AlertEvent]:
        """Feed one reading; return only NEW or ESCALATED alerts (no duplicates)."""
        events = []
        activity = normalize_activity(r.activity)
        ts = as_utc(r.timestamp)

        for metric in METRICS:
            value = getattr(r, metric)
            key = (r.astronaut_id, metric)

            sev, msg = check_hard_limits(metric, value, activity, r.astronaut_id)

            # Only learn from readings inside the hard limits, so faults
            # never poison the baseline.
            z = None
            if sev is None:
                det = self._detectors.setdefault(
                    (r.astronaut_id, metric, activity), BaselineDetector())
                z = det.update(value)
                if z is not None:
                    # Inside normal limits but unusual for THIS astronaut in THIS activity.
                    sev = "warning" if abs(z) >= 4 else "info"
                    direction = "high" if z > 0 else "low"
                    msg = (f"{crew_name(r.astronaut_id)}'s {METRIC_INFO[metric][0]} is "
                           f"unusually {direction} for them {ACTIVITY_PHRASE[activity]} "
                           f"({fmt(metric, value)}, usually about {fmt(metric, det.last_mean)})")

            state = self._open.get(key)
            if sev is None:
                self._open.pop(key, None)  # condition cleared
                continue

            if state is None or RANK[sev] > RANK[state.severity]:
                self._open[key] = _Open(sev, ts)
                events.append(AlertEvent(sev, metric, msg))
            elif state.escalated:
                continue  # already escalated by time; stay critical until cleared
            elif RANK[sev] < RANK[state.severity]:
                self._open[key] = _Open(sev, ts)  # de-escalated: re-arm, no new event
            elif sev == "warning" and ts - state.since >= self.escalate_after:
                state.severity = "critical"
                state.escalated = True
                mins = (ts - state.since).total_seconds() / 60
                events.append(AlertEvent(
                    "critical", metric,
                    f"{msg}. Unresolved for {mins:.0f} min, escalated to critical"))
        return events
