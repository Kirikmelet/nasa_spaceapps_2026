# API Parameters

from pydantic import BaseModel
from models import ReadingActivityType


class AstronautActivityPostParam(BaseModel):
    astronaut_id: str
    activity: ReadingActivityType
    pass


class AstronautReadingPostParam(BaseModel):
    
    pass
