from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


RestDurationUnit = Literal["minutes", "seconds"]


class Settings(BaseModel):
    reminder_interval_minutes: int = Field(20, ge=1, le=240)
    rest_duration_value: int = Field(5, ge=1)
    rest_duration_unit: RestDurationUnit = "minutes"
    snooze_minutes: int = Field(5, ge=1, le=60)
    sound_enabled: bool = True
    notification_enabled: bool = True

    @model_validator(mode="after")
    def validate_rest_duration(self) -> "Settings":
        max_value = 3600 if self.rest_duration_unit == "seconds" else 60
        if self.rest_duration_value > max_value:
            unit_label = "seconds" if self.rest_duration_unit == "seconds" else "minutes"
            raise ValueError(f"rest_duration_value must be less than or equal to {max_value} {unit_label}")
        return self


class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=40)
    note: str | None = Field(None, max_length=240)


class Event(EventCreate):
    id: int
    created_at: str
