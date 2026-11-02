from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(..., min_length=1, max_length=255)


class HolidayRead(BaseModel):
    id: int
    holiday_date: date
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
