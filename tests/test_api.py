import os

import pytest
from fastapi.testclient import TestClient

os.environ["SANA_START_OLLAMA"] = "0"

from backend import database, main  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def register(client: TestClient, email: str = "amina@example.com") -> dict:
    response = client.post(
        "/api/auth/register",
        json={"name": "Amina", "email": email, "password": "strong-pass-123"},
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['token']}"}


def test_registration_login_and_logout(client: TestClient):
    auth = register(client)
    headers = auth_headers(auth)

    assert auth["user"]["email"] == "amina@example.com"
    assert auth["token"]
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    login = client.post(
        "/api/auth/login",
        json={"email": "AMINA@example.com", "password": "strong-pass-123"},
    )
    assert login.status_code == 200
    assert login.json()["token"] != auth["token"]

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_user_data_is_isolated_from_guest_and_other_user(client: TestClient):
    first = register(client, "first@example.com")
    second = register(client, "second@example.com")
    payload = {
        "entry_date": "2026-10-04",
        "mood": "calm",
        "energy": "medium",
        "symptoms": ["headache"],
        "notes": "Private note",
    }

    assert client.post("/api/logs", headers=auth_headers(first), json=payload).status_code == 201
    assert len(client.get("/api/logs", headers=auth_headers(first)).json()) == 1
    assert client.get("/api/logs", headers=auth_headers(second)).json() == []
    assert client.get("/api/logs").json() == []


def test_log_upsert_summary_and_clear(client: TestClient):
    auth = register(client)
    headers = auth_headers(auth)
    payload = {
        "entry_date": "2026-10-04",
        "mood": "sad",
        "energy": "low",
        "symptoms": ["headache", "bloating"],
        "notes": "First version",
    }
    first = client.post("/api/logs", headers=headers, json=payload)
    payload["mood"] = "calm"
    payload["notes"] = "Updated note"
    second = client.post("/api/logs", headers=headers, json=payload)

    assert first.json()["id"] == second.json()["id"]
    assert client.get("/api/logs", headers=headers).json()[0]["notes"] == "Updated note"
    summary = client.get("/api/summary", headers=headers).json()
    assert summary["logs_count"] == 1
    assert summary["mood_counts"] == {"calm": 1}
    assert summary["symptom_counts"] == {"headache": 1, "bloating": 1}

    assert client.delete("/api/data", headers=headers).status_code == 204
    assert client.get("/api/logs", headers=headers).json() == []


def test_period_update_and_calendar_forecast(client: TestClient):
    auth = register(client)
    headers = auth_headers(auth)
    first = client.post(
        "/api/periods",
        headers=headers,
        json={"start_date": "2026-08-10", "end_date": "2026-08-14"},
    )
    second = client.post(
        "/api/periods",
        headers=headers,
        json={"start_date": "2026-09-07", "end_date": None},
    )
    assert first.status_code == second.status_code == 201

    period_id = second.json()["id"]
    updated = client.patch(
        f"/api/periods/{period_id}",
        headers=headers,
        json={"end_date": "2026-09-11"},
    )
    assert updated.status_code == 200
    assert updated.json()["end_date"] == "2026-09-11"

    invalid = client.patch(
        f"/api/periods/{period_id}",
        headers=headers,
        json={"end_date": "2026-09-01"},
    )
    assert invalid.status_code == 422

    calendar = client.get(
        "/api/calendar?year=2026&month=10", headers=headers
    ).json()
    assert calendar["has_data"] is True
    assert calendar["cycle_length"] == 28
    assert calendar["period_length"] == 5
    assert calendar["next_period_start"] is not None
