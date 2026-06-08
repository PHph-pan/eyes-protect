from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import init_db, save_timer_state_row
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("EYES_PROTECT_DB_PATH", str(tmp_path / "test.db"))
    init_db()


def test_default_settings_are_returned():
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "reminder_interval_minutes": 20,
        "rest_duration_value": 5,
        "rest_duration_unit": "minutes",
        "snooze_minutes": 5,
        "sound_enabled": True,
        "notification_enabled": True,
    }


def test_settings_can_be_updated():
    payload = {
        "reminder_interval_minutes": 30,
        "rest_duration_value": 8,
        "rest_duration_unit": "minutes",
        "snooze_minutes": 3,
        "sound_enabled": False,
        "notification_enabled": True,
    }

    response = client.put("/api/settings", json=payload)

    assert response.status_code == 200
    assert response.json() == payload

    persisted_response = client.get("/api/settings")
    assert persisted_response.status_code == 200
    assert persisted_response.json()["sound_enabled"] is False


def test_rest_duration_can_be_set_in_seconds():
    payload = {
        "reminder_interval_minutes": 20,
        "rest_duration_value": 30,
        "rest_duration_unit": "seconds",
        "snooze_minutes": 5,
        "sound_enabled": True,
        "notification_enabled": True,
    }

    response = client.put("/api/settings", json=payload)

    assert response.status_code == 200
    assert response.json() == payload


def test_invalid_settings_are_rejected():
    response = client.put(
        "/api/settings",
        json={
            "reminder_interval_minutes": 0,
            "rest_duration_value": 5,
            "rest_duration_unit": "minutes",
            "snooze_minutes": 5,
            "sound_enabled": True,
            "notification_enabled": True,
        },
    )

    assert response.status_code == 422


def test_event_can_be_recorded():
    response = client.post(
        "/api/events",
        json={"event_type": "reminder_triggered", "note": "test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] > 0
    assert body["event_type"] == "reminder_triggered"
    assert body["note"] == "test"
    assert "created_at" in body


def test_desktop_alert_lifecycle():
    create_response = client.post(
        "/api/desktop-alerts",
        json={"title": "测试提醒", "message": "请休息"},
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["id"] > 0
    assert created["title"] == "测试提醒"
    assert created["message"] == "请休息"
    assert created["status"] == "pending"

    detail_response = client.get(f"/api/desktop-alerts/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]
    assert detail_response.json()["status"] == "pending"

    pending_response = client.get("/api/desktop-alerts/pending")
    assert pending_response.status_code == 200
    assert [alert["id"] for alert in pending_response.json()] == [created["id"]]

    shown_response = client.patch(f"/api/desktop-alerts/{created['id']}", json={"status": "shown"})
    assert shown_response.status_code == 200
    assert shown_response.json()["status"] == "shown"
    assert shown_response.json()["shown_at"] is not None

    acknowledged_response = client.patch(f"/api/desktop-alerts/{created['id']}", json={"status": "acknowledged"})
    assert acknowledged_response.status_code == 200
    assert acknowledged_response.json()["status"] == "acknowledged"
    assert acknowledged_response.json()["acknowledged_at"] is not None

    acknowledged_detail_response = client.get(f"/api/desktop-alerts/{created['id']}")
    assert acknowledged_detail_response.status_code == 200
    assert acknowledged_detail_response.json()["status"] == "acknowledged"
    assert acknowledged_detail_response.json()["acknowledged_at"] is not None

    pending_after_close = client.get("/api/desktop-alerts/pending")
    assert pending_after_close.status_code == 200
    assert pending_after_close.json() == []


def test_legacy_closed_status_is_accepted_as_acknowledged():
    create_response = client.post(
        "/api/desktop-alerts",
        json={"title": "兼容提醒", "message": "请休息"},
    )
    created = create_response.json()

    response = client.patch(f"/api/desktop-alerts/{created['id']}", json={"status": "closed"})

    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert response.json()["acknowledged_at"] is not None


def test_missing_desktop_alert_returns_404():
    response = client.get("/api/desktop-alerts/999")

    assert response.status_code == 404


def test_desktop_companion_health_defaults_to_disconnected():
    response = client.get("/api/desktop-companion/status")

    assert response.status_code == 200
    assert response.json() == {"connected": False, "last_seen_at": None}


def test_desktop_companion_heartbeat_marks_connected():
    heartbeat_response = client.post("/api/desktop-companion/heartbeat")

    assert heartbeat_response.status_code == 200
    heartbeat = heartbeat_response.json()
    assert heartbeat["connected"] is True
    assert heartbeat["last_seen_at"] is not None

    status_response = client.get("/api/desktop-companion/status")
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is True
    assert status_response.json()["last_seen_at"] == heartbeat["last_seen_at"]


def test_timer_start_pause_resume_and_reset():
    start_response = client.post("/api/timer/start")
    assert start_response.status_code == 200
    started = start_response.json()
    assert started["status"] == "running"
    assert started["total_seconds"] == 20 * 60
    assert started["remaining_seconds"] > 0

    pause_response = client.post("/api/timer/pause")
    assert pause_response.status_code == 200
    paused = pause_response.json()
    assert paused["status"] == "paused"
    assert paused["paused_from_status"] == "running"
    assert paused["remaining_seconds"] > 0

    resume_response = client.post("/api/timer/resume")
    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed["status"] == "running"
    assert resumed["remaining_seconds"] > 0

    reset_response = client.post("/api/timer/reset")
    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "idle"


def test_timer_expiration_enters_alerting_and_creates_desktop_alert():
    past = datetime.now(timezone.utc) - timedelta(seconds=2)
    save_timer_state_row(
        {
            "status": "running",
            "phase_started_at": (past - timedelta(seconds=1)).isoformat(),
            "phase_ends_at": past.isoformat(),
            "total_seconds": 1,
            "paused_remaining_seconds": None,
            "paused_from_status": None,
            "active_desktop_alert_id": None,
        }
    )

    response = client.get("/api/timer")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alerting"
    assert body["remaining_seconds"] == 0
    assert body["active_desktop_alert_id"] is not None

    pending_response = client.get("/api/desktop-alerts/pending")
    assert pending_response.status_code == 200
    assert [alert["id"] for alert in pending_response.json()] == [body["active_desktop_alert_id"]]


def test_pending_desktop_alerts_advances_expired_timer_without_frontend():
    past = datetime.now(timezone.utc) - timedelta(seconds=2)
    save_timer_state_row(
        {
            "status": "running",
            "phase_started_at": (past - timedelta(seconds=1)).isoformat(),
            "phase_ends_at": past.isoformat(),
            "total_seconds": 1,
            "paused_remaining_seconds": None,
            "paused_from_status": None,
            "active_desktop_alert_id": None,
        }
    )

    pending_response = client.get("/api/desktop-alerts/pending")

    assert pending_response.status_code == 200
    pending = pending_response.json()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"

    timer_response = client.get("/api/timer")
    assert timer_response.status_code == 200
    assert timer_response.json()["status"] == "alerting"
    assert timer_response.json()["active_desktop_alert_id"] == pending[0]["id"]


def test_acknowledged_desktop_alert_starts_rest_phase():
    past = datetime.now(timezone.utc) - timedelta(seconds=2)
    save_timer_state_row(
        {
            "status": "running",
            "phase_started_at": (past - timedelta(seconds=1)).isoformat(),
            "phase_ends_at": past.isoformat(),
            "total_seconds": 1,
            "paused_remaining_seconds": None,
            "paused_from_status": None,
            "active_desktop_alert_id": None,
        }
    )
    alerting = client.get("/api/timer").json()

    response = client.patch(
        f"/api/desktop-alerts/{alerting['active_desktop_alert_id']}",
        json={"status": "acknowledged"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"

    timer_response = client.get("/api/timer")
    assert timer_response.status_code == 200
    body = timer_response.json()
    assert body["status"] == "resting"
    assert body["total_seconds"] == 5 * 60
    assert body["remaining_seconds"] > 0


def test_timer_rest_expiration_starts_next_work_cycle():
    past = datetime.now(timezone.utc) - timedelta(seconds=2)
    save_timer_state_row(
        {
            "status": "resting",
            "phase_started_at": (past - timedelta(seconds=1)).isoformat(),
            "phase_ends_at": past.isoformat(),
            "total_seconds": 1,
            "paused_remaining_seconds": None,
            "paused_from_status": None,
            "active_desktop_alert_id": None,
        }
    )

    response = client.get("/api/timer")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["total_seconds"] == 20 * 60


def test_timer_snooze_skip_and_manual_start_rest():
    client.post("/api/timer/start")

    snooze_response = client.post("/api/timer/snooze")
    assert snooze_response.status_code == 200
    assert snooze_response.json()["status"] == "running"
    assert snooze_response.json()["total_seconds"] == 5 * 60

    rest_response = client.post("/api/timer/start-rest")
    assert rest_response.status_code == 200
    assert rest_response.json()["status"] == "resting"
    assert rest_response.json()["total_seconds"] == 5 * 60

    skip_response = client.post("/api/timer/skip")
    assert skip_response.status_code == 200
    assert skip_response.json()["status"] == "running"
    assert skip_response.json()["total_seconds"] == 20 * 60
