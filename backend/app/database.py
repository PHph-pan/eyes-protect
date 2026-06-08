from __future__ import annotations

import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "eyes_protect.db"

DEFAULT_SETTINGS = {
    "id": 1,
    "reminder_interval_minutes": 20,
    "rest_duration_minutes": 5,
    "snooze_minutes": 5,
    "sound_enabled": 1,
    "notification_enabled": 1,
}


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = Path(os.getenv("EYES_PROTECT_DB_PATH", str(DB_PATH)))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                reminder_interval_minutes INTEGER NOT NULL,
                rest_duration_minutes INTEGER NOT NULL,
                snooze_minutes INTEGER NOT NULL,
                sound_enabled INTEGER NOT NULL CHECK (sound_enabled IN (0, 1)),
                notification_enabled INTEGER NOT NULL CHECK (notification_enabled IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (
                id,
                reminder_interval_minutes,
                rest_duration_minutes,
                snooze_minutes,
                sound_enabled,
                notification_enabled
            ) VALUES (:id, :reminder_interval_minutes, :rest_duration_minutes, :snooze_minutes, :sound_enabled, :notification_enabled)
            """,
            DEFAULT_SETTINGS,
        )


def fetch_settings() -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return row


def save_settings(settings: dict[str, int]) -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE settings
            SET
                reminder_interval_minutes = :reminder_interval_minutes,
                rest_duration_minutes = :rest_duration_minutes,
                snooze_minutes = :snooze_minutes,
                sound_enabled = :sound_enabled,
                notification_enabled = :notification_enabled,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            settings,
        )
        return conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def insert_event(event_type: str, note: str | None) -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO reminder_events (event_type, note) VALUES (?, ?)",
            (event_type, note),
        )
        return conn.execute(
            "SELECT * FROM reminder_events WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
