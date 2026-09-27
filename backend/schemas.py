from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator


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


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least 2 characters")
        return cleaned


class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr


class UserPublic(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: str


class AuthResponse(BaseModel):
    message: str
    user: UserPublic
