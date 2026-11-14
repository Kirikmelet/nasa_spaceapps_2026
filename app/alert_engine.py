"""Alert engine: pure Python, no web code, so it is easy to test."""
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
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


@dataclass
class AlertEvent:
    severity: str
    metric: str
    message: str


def check_hard_limits(metric: str, value: float, activity: str):
    """Return (severity, message) if value breaks an absolute limit, else (None, '')."""
    lims = HR_LIMITS[activity] if metric == "hr" else DEFAULT_LIMITS[metric]
    crit_lo, warn_lo, warn_hi, crit_hi = lims
    ctx = f"during {activity}"
    if crit_lo is not None and value < crit_lo:
        return "critical", f"{metric} {value:g} below critical limit {crit_lo:g} {ctx}"
    if crit_hi is not None and value > crit_hi:
        return "critical", f"{metric} {value:g} above critical limit {crit_hi:g} {ctx}"
    if warn_lo is not None and value < warn_lo:
        return "warning", f"{metric} {value:g} below {warn_lo:g} {ctx}"
    if warn_hi is not None and value > warn_hi:
        return "warning", f"{metric} {value:g} above {warn_hi:g} {ctx}"
    return None, ""


class BaselineDetector:
    """Rolling baseline for one (astronaut, metric, activity).

    Flags a value only after `consecutive` anomalous readings in a row
    (debounce). Anomalous values are kept out of the baseline so a fault
    does not teach the detector that the fault is normal.
    """

    def __init__(self, window=60, min_samples=20, z_threshold=2.5, consecutive=3):
        self.values = deque(maxlen=window)
        self.min_samples = min_samples
        self.z_threshold = z_threshold
        self.consecutive = consecutive
        self.streak = 0

    def update(self, x: float) -> Optional[float]:
        """Return the z-score once an anomaly is confirmed, else None."""
        if len(self.values) < self.min_samples:
            self.values.append(x)
            return None
        mu = mean(self.values)
        sd = max(stdev(self.values), 0.01 * abs(mu), 1e-6)  # floor avoids divide-by-~0
        z = (x - mu) / sd
        if abs(z) > self.z_threshold:
            self.streak += 1
            return z if self.streak >= self.consecutive else None
        self.streak = 0
        self.values.append(x)
        return None


@dataclass
class _Open:
    severity: str
    since: object  # datetime of the reading that opened it


class AlertEngine:
    def __init__(self, escalate_after: timedelta = timedelta(minutes=5)):
        self.escalate_after = escalate_after
        self._detectors = {}  # (astronaut, metric, activity) -> BaselineDetector
        self._open = {}       # (astronaut, metric) -> _Open

    def process(self, r: Reading) -> list[AlertEvent]:
        """Feed one reading; return only NEW or ESCALATED alerts (no duplicates)."""
        events = []
        for metric in METRICS:
            value = getattr(r, metric)
            key = (r.astronaut_id, metric)

            sev, msg = check_hard_limits(metric, value, r.activity)

            det = self._detectors.setdefault(
                (r.astronaut_id, metric, r.activity), BaselineDetector())
            z = det.update(value)
            if sev is None and z is not None:
                # Inside normal limits but unusual for THIS astronaut in THIS activity.
                sev = "warning" if abs(z) >= 4 else "info"
                msg = (f"{metric} {value:g} deviates from {r.astronaut_id}'s "
                       f"{r.activity} baseline (z={z:+.1f})")

            state = self._open.get(key)
            if sev is None:
                self._open.pop(key, None)  # condition cleared
                continue

            if state is None or RANK[sev] > RANK[state.severity]:
                self._open[key] = _Open(sev, r.timestamp)
                events.append(AlertEvent(sev, metric, msg))
            elif (state.severity == "warning"
                  and r.timestamp - state.since >= self.escalate_after):
                state.severity = "critical"
                mins = (r.timestamp - state.since).total_seconds() / 60
                events.append(AlertEvent(
                    "critical", metric, f"{msg} (unresolved for {mins:.0f} min, escalated)"))
        return events