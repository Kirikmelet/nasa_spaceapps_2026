from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Reading(BaseModel):
    astronaut_id: str
    timestamp: datetime
    hr: float          # heart rate, bpm
    spo2: float        # blood oxygen, %
    temp: float        # body temp, °C
    bp_sys: float      # systolic blood pressure
    bp_dia: float      # diastolic blood pressure
    resp: float        # respiration rate, breaths/min
    activity: Literal["rest", "sleep", "exercise", "eva"] = "rest"


class Alert(BaseModel):
    id: int
    astronaut_id: str
    severity: Literal["info", "warning", "critical"]
    metric: str
    message: str
    timestamp: datetime
    acknowledged: bool = False