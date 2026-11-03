from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(..., min_length=1, max_length=255)


class HolidayUpdate(BaseModel):
    holiday_date: Optional[date] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)

    model_config = ConfigDict(from_attributes=True)


class HolidayRead(BaseModel):
    id: int
    holiday_date: date
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
