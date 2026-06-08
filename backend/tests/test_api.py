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
        "rest_duration_minutes": 5,
        "snooze_minutes": 5,
        "sound_enabled": True,
        "notification_enabled": True,
    }


def test_settings_can_be_updated():
    payload = {
        "reminder_interval_minutes": 30,
        "rest_duration_minutes": 8,
        "snooze_minutes": 3,
        "sound_enabled": False,
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
            "rest_duration_minutes": 5,
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
