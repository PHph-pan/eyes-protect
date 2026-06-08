import pytest
from fastapi.testclient import TestClient

from app.database import init_db
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

    pending_response = client.get("/api/desktop-alerts/pending")
    assert pending_response.status_code == 200
    assert [alert["id"] for alert in pending_response.json()] == [created["id"]]

    shown_response = client.patch(f"/api/desktop-alerts/{created['id']}", json={"status": "shown"})
    assert shown_response.status_code == 200
    assert shown_response.json()["status"] == "shown"
    assert shown_response.json()["shown_at"] is not None

    closed_response = client.patch(f"/api/desktop-alerts/{created['id']}", json={"status": "closed"})
    assert closed_response.status_code == 200
    assert closed_response.json()["status"] == "closed"
    assert closed_response.json()["closed_at"] is not None

    pending_after_close = client.get("/api/desktop-alerts/pending")
    assert pending_after_close.status_code == 200
    assert pending_after_close.json() == []
