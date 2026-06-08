from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import fetch_settings, init_db, insert_event, save_settings
from .schemas import Event, EventCreate, Settings


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
