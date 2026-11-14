import random
from app.alert_engine import BaselineDetector

from datetime import datetime, timedelta

from app.alert_engine import AlertEngine
from app.models import Reading

T0 = datetime(2026, 11, 14, 12, 0, 0)


def make(i=0, **kw):
    base = dict(astronaut_id="a1", timestamp=T0 + timedelta(seconds=2 * i),
                hr=70, spo2=98, temp=36.8, bp_sys=118, bp_dia=76, resp=14,
                activity="rest")
    base.update(kw)
    return Reading(**base)


def warm(engine, n=25, **kw):
    events = []
    for i in range(n):
        events += engine.process(make(i, **kw))
    return events


def test_normal_readings_raise_nothing():
    assert warm(AlertEngine()) == []


def test_low_spo2_is_critical():
    events = AlertEngine().process(make(spo2=85))
    assert len(events) == 1
    assert events[0].severity == "critical" and events[0].metric == "spo2"


def test_no_duplicate_alert_while_condition_persists():
    e = AlertEngine()
    total = []
    for i in range(10):
        total += e.process(make(i, spo2=85))
    assert len(total) == 1


def test_alert_can_refire_after_clearing():
    e = AlertEngine()
    total = []
    total += e.process(make(0, spo2=85))
    total += e.process(make(1, spo2=98))
    total += e.process(make(2, spo2=85))
    assert len(total) == 2


def test_hr_160_is_fine_during_exercise_but_critical_at_rest():
    assert AlertEngine().process(make(hr=160, activity="exercise")) == []
    events = AlertEngine().process(make(hr=160, activity="rest"))
    assert events[0].severity == "critical" and events[0].metric == "hr"


def test_baseline_anomaly_needs_three_consecutive_readings():
    e = AlertEngine()
    assert warm(e) == []
    assert e.process(make(30, hr=95)) == []   # 95 is inside the rest limits
    assert e.process(make(31, hr=95)) == []
    events = e.process(make(32, hr=95))
    assert len(events) == 1
    assert events[0].metric == "hr" and events[0].severity == "warning"


def test_single_spikes_are_debounced():
    e = AlertEngine()
    warm(e)
    total = []
    for i, hr in enumerate([95, 70, 95, 95]):
        total += e.process(make(30 + i, hr=hr))
    assert total == []


def test_warning_escalates_to_critical_if_unresolved():
    e = AlertEngine()
    first = e.process(make(spo2=92))
    assert first[0].severity == "warning"
    later = e.process(make(spo2=92, timestamp=T0 + timedelta(minutes=6)))
    assert later[0].severity == "critical"

def test_normal_noise_never_flags():
    random.seed(0)
    d = BaselineDetector()
    for _ in range(5000):
        assert d.update(round(random.gauss(76, 2))) is None


def test_sustained_shift_flags_and_is_not_learned():
    random.seed(1)
    d = BaselineDetector()
    for _ in range(40):
        d.update(round(random.gauss(70, 2)))
    results = [d.update(round(random.gauss(95, 2))) for _ in range(100)]
    assert results[0] is None and results[1] is None
    assert all(r is not None for r in results[2:])