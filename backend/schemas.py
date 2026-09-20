from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Mood = Literal["happy", "calm", "sensitive", "sad", "angry"]
Energy = Literal["low", "medium", "high"]


class DailyLogCreate(BaseModel):
    entry_date: date = Field(default_factory=date.today)
    mood: Mood
    energy: Energy
    symptoms: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=500)


class DailyLog(DailyLogCreate):
    id: int
    created_at: str


class PeriodCreate(BaseModel):
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None


class Period(PeriodCreate):
    id: int
    created_at: str
