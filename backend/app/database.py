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
    "rest_duration_value": 5,
    "rest_duration_unit": "minutes",
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
                rest_duration_value INTEGER NOT NULL,
                rest_duration_unit TEXT NOT NULL CHECK (rest_duration_unit IN ('minutes', 'seconds')),
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
            CREATE TABLE IF NOT EXISTS timer_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'running', 'alerting', 'resting', 'paused')),
                phase_started_at TEXT,
                phase_ends_at TEXT,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                paused_remaining_seconds INTEGER,
                paused_from_status TEXT,
                active_desktop_alert_id INTEGER,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        create_desktop_alerts_table(conn)
        ensure_desktop_alert_statuses(conn)
        ensure_settings_columns(conn)
        insert_default_settings(conn)
        insert_default_timer_state(conn)


def ensure_settings_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
    if "rest_duration_value" not in columns:
        conn.execute("ALTER TABLE settings ADD COLUMN rest_duration_value INTEGER NOT NULL DEFAULT 5")
        if "rest_duration_minutes" in columns:
            conn.execute("UPDATE settings SET rest_duration_value = rest_duration_minutes WHERE id = 1")
    if "rest_duration_unit" not in columns:
        conn.execute("ALTER TABLE settings ADD COLUMN rest_duration_unit TEXT NOT NULL DEFAULT 'minutes'")


def create_desktop_alerts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS desktop_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'shown', 'acknowledged')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            shown_at TEXT,
            acknowledged_at TEXT
        )
        """
    )


def ensure_desktop_alert_statuses(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'desktop_alerts'"
    ).fetchone()
    table_sql = row["sql"] if row else ""
    if "acknowledged" in table_sql and "acknowledged_at" in table_sql:
        return

    conn.execute("ALTER TABLE desktop_alerts RENAME TO desktop_alerts_old")
    create_desktop_alerts_table(conn)
    old_columns = {row["name"] for row in conn.execute("PRAGMA table_info(desktop_alerts_old)").fetchall()}
    acknowledged_source = "closed_at" if "closed_at" in old_columns else "NULL"
    conn.execute(
        f"""
        INSERT INTO desktop_alerts (
            id,
            title,
            message,
            status,
            created_at,
            shown_at,
            acknowledged_at
        )
        SELECT
            id,
            title,
            message,
            CASE status WHEN 'closed' THEN 'acknowledged' ELSE status END,
            created_at,
            shown_at,
            {acknowledged_source}
        FROM desktop_alerts_old
        """
    )
    conn.execute("DROP TABLE desktop_alerts_old")


def insert_default_timer_state(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO timer_state (id, status) VALUES (1, 'idle')")


def insert_default_settings(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(settings)").fetchall()}
    insert_columns = [
        "id",
        "reminder_interval_minutes",
        "rest_duration_value",
        "rest_duration_unit",
        "snooze_minutes",
        "sound_enabled",
        "notification_enabled",
    ]
    values = dict(DEFAULT_SETTINGS)
    if "rest_duration_minutes" in columns:
        insert_columns.append("rest_duration_minutes")
        values["rest_duration_minutes"] = DEFAULT_SETTINGS["rest_duration_value"]
    placeholders = ", ".join(f":{column}" for column in insert_columns)
    column_names = ", ".join(insert_columns)
    conn.execute(
        f"INSERT OR IGNORE INTO settings ({column_names}) VALUES ({placeholders})",
        values,
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
                rest_duration_value = :rest_duration_value,
                rest_duration_unit = :rest_duration_unit,
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


def fetch_timer_state_row() -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        return conn.execute("SELECT * FROM timer_state WHERE id = 1").fetchone()


def save_timer_state_row(state: dict[str, object]) -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE timer_state
            SET
                status = :status,
                phase_started_at = :phase_started_at,
                phase_ends_at = :phase_ends_at,
                total_seconds = :total_seconds,
                paused_remaining_seconds = :paused_remaining_seconds,
                paused_from_status = :paused_from_status,
                active_desktop_alert_id = :active_desktop_alert_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            state,
        )
        return conn.execute("SELECT * FROM timer_state WHERE id = 1").fetchone()


def insert_desktop_alert(title: str, message: str) -> sqlite3.Row:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO desktop_alerts (title, message) VALUES (?, ?)",
            (title, message),
        )
        return conn.execute(
            "SELECT * FROM desktop_alerts WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()


def fetch_pending_desktop_alerts() -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM desktop_alerts
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 5
            """
        ).fetchall()


def fetch_desktop_alert(alert_id: int) -> sqlite3.Row | None:
    init_db()
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM desktop_alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()


def update_desktop_alert_status(alert_id: int, status: str) -> sqlite3.Row | None:
    init_db()
    normalized_status = "acknowledged" if status == "closed" else status
    timestamp_column = "shown_at" if normalized_status == "shown" else "acknowledged_at"
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE desktop_alerts
            SET status = ?, {timestamp_column} = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized_status, alert_id),
        )
        return conn.execute(
            "SELECT * FROM desktop_alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
