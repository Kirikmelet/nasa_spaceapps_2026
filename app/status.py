# app/status.py
from app.alert_engine import DEFAULT_LIMITS, HR_LIMITS, normalize_activity

def classify(metric: str, value: float, activity) -> str:
    lims = (HR_LIMITS[normalize_activity(activity)] if metric == "hr"
            else DEFAULT_LIMITS.get(metric))
    if not lims:
        return "healthy"
    crit_lo, warn_lo, warn_hi, crit_hi = lims
    if (crit_lo is not None and value < crit_lo) or (crit_hi is not None and value > crit_hi):
        return "critical"
    if (warn_lo is not None and value < warn_lo) or (warn_hi is not None and value > warn_hi):
        return "warning"
    return "healthy"
