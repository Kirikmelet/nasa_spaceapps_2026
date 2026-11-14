from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class User(BaseModel):
    id: Optional[int]
    astronaut_id: str
    name: str


class Reading(BaseModel):
    id: Optional[int]
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
    id: Optional[int]
    astronaut_id: str
    severity: Literal["info", "warning", "critical"]
    metric: str
    message: str
    timestamp: datetime
    acknowledged: bool = False
