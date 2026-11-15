from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

ActivityType = Literal["rest", "sleep", "exercise", "eva"]
MetricType = Literal["hr", "spo2", "temp", "bp_sys", "bp_dia", "resp"]
SeverityType = Literal["info", "warning", "critical"]


class ThresholdRange(BaseModel):
    unit: str
    normal_min: float
    normal_max: float
    warning_low: float
    warning_high: float
    critical_low: Optional[float] = None    # None = no critical bound
    critical_high: Optional[float] = None


NASA_DATA: dict[MetricType, dict[ActivityType, ThresholdRange]] = {
    "hr": {
        "rest": ThresholdRange(
            unit="bpm", normal_min=50.0, normal_max=100.0,
            warning_low=45.0, warning_high=100.0),
        "sleep": ThresholdRange(
            unit="bpm", normal_min=40.0, normal_max=80.0,
            warning_low=35.0, warning_high=90.0),
        "exercise": ThresholdRange(
            unit="bpm", normal_min=110.0, normal_max=165.0,
            warning_low=90.0, warning_high=185.0),
        "eva": ThresholdRange(
            unit="bpm", normal_min=80.0, normal_max=150.0,
            warning_low=60.0, warning_high=175.0),
    },
    "spo2": {
        "rest": ThresholdRange(
            unit="%", normal_min=95.0, normal_max=100.0,
            warning_low=92.0, warning_high=100.0),
        "sleep": ThresholdRange(
            unit="%", normal_min=94.0, normal_max=100.0,
            warning_low=90.0, warning_high=100.0),
        "exercise": ThresholdRange(
            unit="%", normal_min=94.0, normal_max=100.0,
            warning_low=90.0, warning_high=100.0),
        "eva": ThresholdRange(
            unit="%", normal_min=95.0, normal_max=100.0,
            warning_low=92.0, warning_high=100.0),
    },
    "temp": {
        "rest": ThresholdRange(
            unit="°C", normal_min=36.1, normal_max=37.5,
            warning_low=35.0, warning_high=38.0),
        "sleep": ThresholdRange(
            unit="°C", normal_min=35.8, normal_max=37.2,
            warning_low=35.0, warning_high=37.8),
        "exercise": ThresholdRange(
            unit="°C", normal_min=36.5, normal_max=38.3,
            warning_low=35.0, warning_high=39.0),
        "eva": ThresholdRange(
            unit="°C", normal_min=36.2, normal_max=38.0,
            warning_low=35.0, warning_high=38.5),
    },
    "bp_sys": {
        "rest": ThresholdRange(
            unit="mmHg", normal_min=90.0, normal_max=139.0,
            warning_low=85.0, warning_high=140.),
        "sleep": ThresholdRange(
            unit="mmHg", normal_min=85.0, normal_max=125.0,
            warning_low=80.0, warning_high=135.0),
        "exercise": ThresholdRange(
            unit="mmHg", normal_min=120.0, normal_max=180.0,
            warning_low=100.0, warning_high=200.0),
        "eva": ThresholdRange(
            unit="mmHg", normal_min=100.0, normal_max=160.0,
            warning_low=90.0, warning_high=180.0),
    },
    "bp_dia": {
        "rest": ThresholdRange(
            unit="mmHg", normal_min=60.0, normal_max=89.0,
            warning_low=50.0, warning_high=90.0),
        "sleep": ThresholdRange(
            unit="mmHg", normal_min=50.0, normal_max=80.0,
            warning_low=45.0, warning_high=85.0),
        "exercise": ThresholdRange(
            unit="mmHg", normal_min=60.0, normal_max=90.0,
            warning_low=50.0, warning_high=100.0),
        "eva": ThresholdRange(
            unit="mmHg", normal_min=60.0, normal_max=95.0,
            warning_low=50.0, warning_high=105.0),
    },
    "resp": {
        "rest": ThresholdRange(
            unit="breaths/min", normal_min=12.0, normal_max=20.0,
            warning_low=8.0, warning_high=24.0),
        "sleep": ThresholdRange(
            unit="breaths/min", normal_min=10.0, normal_max=18.0,
            warning_low=8.0, warning_high=22.0),
        "exercise": ThresholdRange(
            unit="breaths/min", normal_min=20.0, normal_max=40.0,
            warning_low=14.0, warning_high=50.0),
        "eva": ThresholdRange(
            unit="breaths/min", normal_min=16.0, normal_max=32.0,
            warning_low=12.0, warning_high=40.0),
    },
}


class User(BaseModel):
    id: Optional[int] = None
    astronaut_id: str
    name: str


class Reading(BaseModel):
    id: Optional[int] = None
    astronaut_id: str
    timestamp: datetime
    hr: float          # heart rate, bpm
    spo2: float        # blood oxygen, %
    temp: float        # body temp, °C
    bp_sys: float      # systolic blood pressure
    bp_dia: float      # diastolic blood pressure
    resp: float        # respiration rate, breaths/min
    activity: ActivityType = "rest"
    origin_id: Optional[int] = None   # lets the log use a stable id across revisions


class Alert(BaseModel):
    id: Optional[int] = None
    astronaut_id: str
    severity: SeverityType
    metric: MetricType
    message: str
    timestamp: datetime
    acknowledged: bool = False
    activity: ActivityType = "rest"
    value: Optional[value] = None
    origin_id: Optional[int] = None
