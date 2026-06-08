from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from .database import (
    fetch_desktop_alert,
    fetch_desktop_companion_health,
    fetch_pending_desktop_alerts,
    fetch_settings,
    init_db,
    insert_desktop_alert,
    insert_event,
    save_settings,
    touch_desktop_companion,
    update_desktop_alert_status,
)
from .schemas import (
    DesktopAlert,
    DesktopAlertCreate,
    DesktopAlertStatusUpdate,
    DesktopCompanionHealth,
    Event,
    EventCreate,
    Settings,
    TimerState,
)
from .timer_service import (
    acknowledge_desktop_alert,
    get_timer_state,
    pause_timer,
    reset_timer,
    resume_timer,
    skip_timer,
    snooze_timer,
    start_rest_timer,
    start_timer,
)


app = FastAPI(title="Eyes Protect API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):517[0-9]",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DESKTOP_COMPANION_TIMEOUT_SECONDS = 5


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def row_to_settings(row) -> Settings:
    return Settings(
        reminder_interval_minutes=row["reminder_interval_minutes"],
        rest_duration_value=row["rest_duration_value"],
        rest_duration_unit=row["rest_duration_unit"],
        snooze_minutes=row["snooze_minutes"],
        sound_enabled=bool(row["sound_enabled"]),
        notification_enabled=bool(row["notification_enabled"]),
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings", response_model=Settings)
def get_settings() -> Settings:
    return row_to_settings(fetch_settings())


@app.put("/api/settings", response_model=Settings)
def update_settings(settings: Settings) -> Settings:
    row = save_settings(
        {
            "reminder_interval_minutes": settings.reminder_interval_minutes,
            "rest_duration_value": settings.rest_duration_value,
            "rest_duration_unit": settings.rest_duration_unit,
            "snooze_minutes": settings.snooze_minutes,
            "sound_enabled": int(settings.sound_enabled),
            "notification_enabled": int(settings.notification_enabled),
        }
    )
    return row_to_settings(row)


@app.post("/api/events", response_model=Event)
def create_event(event: EventCreate) -> Event:
    row = insert_event(event.event_type, event.note)
    return Event(id=row["id"], event_type=row["event_type"], note=row["note"], created_at=row["created_at"])


def row_to_desktop_alert(row) -> DesktopAlert:
    return DesktopAlert(
        id=row["id"],
        title=row["title"],
        message=row["message"],
        status=row["status"],
        created_at=row["created_at"],
        shown_at=row["shown_at"],
        acknowledged_at=row["acknowledged_at"],
    )


def row_to_desktop_companion_health(row) -> DesktopCompanionHealth:
    last_seen_at = row["last_seen_at"]
    connected = False
    if last_seen_at:
        seen_at = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        if seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)
        connected = (datetime.now(timezone.utc) - seen_at).total_seconds() <= DESKTOP_COMPANION_TIMEOUT_SECONDS
    return DesktopCompanionHealth(connected=connected, last_seen_at=last_seen_at)


@app.post("/api/desktop-alerts", response_model=DesktopAlert)
def create_desktop_alert(alert: DesktopAlertCreate) -> DesktopAlert:
    return row_to_desktop_alert(insert_desktop_alert(alert.title, alert.message))


@app.get("/api/desktop-alerts/pending", response_model=list[DesktopAlert])
def get_pending_desktop_alerts() -> list[DesktopAlert]:
    get_timer_state()
    return [row_to_desktop_alert(row) for row in fetch_pending_desktop_alerts()]


@app.get("/api/desktop-alerts/{alert_id}", response_model=DesktopAlert)
def get_desktop_alert(alert_id: int) -> DesktopAlert:
    row = fetch_desktop_alert(alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Desktop alert not found")
    return row_to_desktop_alert(row)


@app.patch("/api/desktop-alerts/{alert_id}", response_model=DesktopAlert)
def update_desktop_alert(alert_id: int, update: DesktopAlertStatusUpdate) -> DesktopAlert:
    row = update_desktop_alert_status(alert_id, update.status)
    if row is None:
        raise HTTPException(status_code=404, detail="Desktop alert not found")
    if row["status"] == "acknowledged":
        acknowledge_desktop_alert(alert_id)
    return row_to_desktop_alert(row)


@app.post("/api/desktop-companion/heartbeat", response_model=DesktopCompanionHealth)
def desktop_companion_heartbeat() -> DesktopCompanionHealth:
    return row_to_desktop_companion_health(touch_desktop_companion())


@app.get("/api/desktop-companion/status", response_model=DesktopCompanionHealth)
def desktop_companion_status() -> DesktopCompanionHealth:
    return row_to_desktop_companion_health(fetch_desktop_companion_health())


@app.get("/api/timer", response_model=TimerState)
def read_timer():
    return get_timer_state()


@app.post("/api/timer/start", response_model=TimerState)
def start_timer_endpoint():
    return start_timer()


@app.post("/api/timer/pause", response_model=TimerState)
def pause_timer_endpoint():
    return pause_timer()


@app.post("/api/timer/resume", response_model=TimerState)
def resume_timer_endpoint():
    return resume_timer()


@app.post("/api/timer/reset", response_model=TimerState)
def reset_timer_endpoint():
    return reset_timer()


@app.post("/api/timer/start-rest", response_model=TimerState)
def start_rest_timer_endpoint():
    return start_rest_timer()


@app.post("/api/timer/snooze", response_model=TimerState)
def snooze_timer_endpoint():
    return snooze_timer()


@app.post("/api/timer/skip", response_model=TimerState)
def skip_timer_endpoint():
    return skip_timer()
