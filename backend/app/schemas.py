from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


RestDurationUnit = Literal["minutes", "seconds"]
TimerStatus = Literal["idle", "running", "alerting", "resting", "paused"]
DesktopAlertStatus = Literal["pending", "shown", "acknowledged"]


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


class DesktopAlertCreate(BaseModel):
    title: str = Field("该休息眼睛了", min_length=1, max_length=80)
    message: str = Field("请离开屏幕，眺望远处，给眼睛一次真正的缓冲。", min_length=1, max_length=240)


class DesktopAlertStatusUpdate(BaseModel):
    status: Literal["shown", "acknowledged", "closed"]


class DesktopAlert(DesktopAlertCreate):
    id: int
    status: DesktopAlertStatus
    created_at: str
    shown_at: str | None = None
    acknowledged_at: str | None = None


class TimerState(BaseModel):
    status: TimerStatus
    remaining_seconds: int
    total_seconds: int
    paused_from_status: TimerStatus | None = None
    active_desktop_alert_id: int | None = None
    phase_started_at: str | None = None
    phase_ends_at: str | None = None
