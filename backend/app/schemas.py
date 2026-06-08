from __future__ import annotations

from pydantic import BaseModel, Field


class Settings(BaseModel):
    reminder_interval_minutes: int = Field(20, ge=1, le=240)
    rest_duration_minutes: int = Field(5, ge=1, le=60)
    snooze_minutes: int = Field(5, ge=1, le=60)
    sound_enabled: bool = True
    notification_enabled: bool = True


class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=40)
    note: str | None = Field(None, max_length=240)


class Event(EventCreate):
    id: int
    created_at: str
