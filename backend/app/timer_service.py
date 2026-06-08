from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from .database import (
    fetch_settings,
    fetch_timer_state_row,
    insert_desktop_alert,
    insert_event,
    save_timer_state_row,
    update_desktop_alert_status,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def settings_rest_seconds(settings) -> int:
    value = int(settings["rest_duration_value"])
    return value if settings["rest_duration_unit"] == "seconds" else value * 60


def settings_work_seconds(settings) -> int:
    return int(settings["reminder_interval_minutes"]) * 60


def row_to_dict(row) -> dict[str, Any]:
    return {
        "status": row["status"],
        "phase_started_at": row["phase_started_at"],
        "phase_ends_at": row["phase_ends_at"],
        "total_seconds": row["total_seconds"],
        "paused_remaining_seconds": row["paused_remaining_seconds"],
        "paused_from_status": row["paused_from_status"],
        "active_desktop_alert_id": row["active_desktop_alert_id"],
    }


def remaining_seconds(row, now: datetime | None = None) -> int:
    status = row["status"]
    if status == "paused":
        return max(0, int(row["paused_remaining_seconds"] or 0))
    if status == "alerting":
        return 0
    ends_at = parse_iso(row["phase_ends_at"])
    if not ends_at:
        return 0
    return max(0, ceil(((ends_at - (now or utc_now())).total_seconds())))


def timer_response(row) -> dict[str, Any]:
    current = utc_now()
    return {
        "status": row["status"],
        "remaining_seconds": remaining_seconds(row, current),
        "total_seconds": int(row["total_seconds"] or 0),
        "paused_from_status": row["paused_from_status"],
        "active_desktop_alert_id": row["active_desktop_alert_id"],
        "phase_started_at": row["phase_started_at"],
        "phase_ends_at": row["phase_ends_at"],
    }


def save_state(
    status: str,
    *,
    total_seconds: int = 0,
    phase_started_at: datetime | None = None,
    phase_ends_at: datetime | None = None,
    paused_remaining_seconds: int | None = None,
    paused_from_status: str | None = None,
    active_desktop_alert_id: int | None = None,
):
    return save_timer_state_row(
        {
            "status": status,
            "phase_started_at": to_iso(phase_started_at),
            "phase_ends_at": to_iso(phase_ends_at),
            "total_seconds": total_seconds,
            "paused_remaining_seconds": paused_remaining_seconds,
            "paused_from_status": paused_from_status,
            "active_desktop_alert_id": active_desktop_alert_id,
        }
    )


def start_phase(status: str, total_seconds: int, *, active_desktop_alert_id: int | None = None):
    now = utc_now()
    return save_state(
        status,
        total_seconds=total_seconds,
        phase_started_at=now,
        phase_ends_at=now + timedelta(seconds=total_seconds),
        active_desktop_alert_id=active_desktop_alert_id,
    )


def resume_phase(status: str, remaining: int, total_seconds: int, *, active_desktop_alert_id: int | None = None):
    now = utc_now()
    return save_state(
        status,
        total_seconds=total_seconds,
        phase_started_at=now,
        phase_ends_at=now + timedelta(seconds=remaining),
        active_desktop_alert_id=active_desktop_alert_id,
    )


def start_work_cycle(total_seconds: int | None = None):
    settings = fetch_settings()
    return start_phase("running", total_seconds or settings_work_seconds(settings))


def acknowledge_active_alert(row) -> None:
    alert_id = row["active_desktop_alert_id"]
    if alert_id:
        update_desktop_alert_status(int(alert_id), "acknowledged")


def start_rest_phase():
    settings = fetch_settings()
    insert_event("rest_started", "started from backend timer")
    return start_phase("resting", settings_rest_seconds(settings))


def enter_alerting(row):
    alert_id = row["active_desktop_alert_id"]
    if not alert_id:
        alert = insert_desktop_alert("该休息眼睛了", "请离开屏幕，眺望远处，给眼睛一次真正的缓冲。")
        alert_id = alert["id"]
        insert_event("reminder_triggered", "created by backend timer")
    return save_state(
        "alerting",
        total_seconds=int(row["total_seconds"] or 0),
        active_desktop_alert_id=alert_id,
    )


def advance_timer_state():
    row = fetch_timer_state_row()
    status = row["status"]
    if status not in {"running", "resting"}:
        return row
    if remaining_seconds(row) > 0:
        return row
    if status == "running":
        return enter_alerting(row)
    insert_event("rest_completed", "completed by backend timer")
    return start_work_cycle()


def get_timer_state() -> dict[str, Any]:
    return timer_response(advance_timer_state())


def start_timer() -> dict[str, Any]:
    acknowledge_active_alert(advance_timer_state())
    return timer_response(start_work_cycle())


def pause_timer() -> dict[str, Any]:
    row = advance_timer_state()
    if row["status"] not in {"running", "resting", "alerting"}:
        return timer_response(row)
    active_desktop_alert_id = row["active_desktop_alert_id"]
    if row["status"] == "alerting":
        acknowledge_active_alert(row)
        active_desktop_alert_id = None
    return timer_response(
        save_state(
            "paused",
            total_seconds=int(row["total_seconds"] or 0),
            paused_remaining_seconds=remaining_seconds(row),
            paused_from_status=row["status"],
            active_desktop_alert_id=active_desktop_alert_id,
        )
    )


def resume_timer() -> dict[str, Any]:
    row = fetch_timer_state_row()
    if row["status"] != "paused":
        return timer_response(advance_timer_state())
    paused_from = row["paused_from_status"] or "running"
    if paused_from == "alerting":
        alerting_row = save_state(
            "alerting",
            total_seconds=int(row["total_seconds"] or 0),
            active_desktop_alert_id=row["active_desktop_alert_id"],
        )
        return timer_response(
            enter_alerting(alerting_row)
        )
    return timer_response(
        resume_phase(
            paused_from,
            max(1, int(row["paused_remaining_seconds"] or 1)),
            int(row["total_seconds"] or row["paused_remaining_seconds"] or 1),
            active_desktop_alert_id=row["active_desktop_alert_id"],
        )
    )


def reset_timer() -> dict[str, Any]:
    acknowledge_active_alert(advance_timer_state())
    insert_event("reset", "reset by backend timer")
    return timer_response(save_state("idle"))


def start_rest_timer() -> dict[str, Any]:
    acknowledge_active_alert(advance_timer_state())
    return timer_response(start_rest_phase())


def snooze_timer() -> dict[str, Any]:
    acknowledge_active_alert(advance_timer_state())
    settings = fetch_settings()
    insert_event("snoozed", "snoozed by backend timer")
    return timer_response(start_phase("running", int(settings["snooze_minutes"]) * 60))


def skip_timer() -> dict[str, Any]:
    acknowledge_active_alert(advance_timer_state())
    insert_event("skipped", "skipped by backend timer")
    return timer_response(start_work_cycle())


def acknowledge_desktop_alert(alert_id: int) -> dict[str, Any]:
    row = advance_timer_state()
    if row["status"] == "alerting" and row["active_desktop_alert_id"] == alert_id:
        return timer_response(start_rest_phase())
    return timer_response(row)
