from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import advice as router_module


def _client(monkeypatch, uid: str = "user-abc-123") -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: uid
    return TestClient(app)


def _sample_advice_dict(advice_id: str = "adv-1", **overrides) -> dict:
    now = datetime.now(timezone.utc)
    base = {
        "id": advice_id,
        "content": "Take a short 5-minute break after 50 minutes of deep focus.",
        "category": "focus",
        "reasoning": "High cognitive load detected",
        "source_app": "desktop-monitor",
        "confidence": 0.85,
        "context_summary": "Intensive coding session",
        "current_activity": "Coding in VSCode",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "is_read": False,
        "is_dismissed": False,
    }
    base.update(overrides)
    return base


def test_create_advice_success(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def mock_create(uid, **kwargs):
        captured["uid"] = uid
        captured["kwargs"] = kwargs
        return _sample_advice_dict(advice_id="adv-created", **kwargs)

    monkeypatch.setattr(router_module.advice_db, "create_advice", mock_create)

    payload = {
        "content": "Stand up and drink some water.",
        "category": "wellness",
        "confidence": 0.9,
    }
    response = client.post("/v1/advice", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "adv-created"
    assert data["content"] == "Stand up and drink some water."
    assert captured["uid"] == "user-abc-123"
    assert captured["kwargs"]["category"] == "wellness"


@pytest.mark.parametrize("bad_content", ["", "   ", " \t \n "])
def test_create_advice_rejects_empty_or_whitespace_content(monkeypatch, bad_content):
    client = _client(monkeypatch)
    response = client.post("/v1/advice", json={"content": bad_content})
    assert response.status_code in (400, 422)
    if response.status_code == 400:
        assert response.json()["detail"] == "content cannot be empty or whitespace only"


def test_create_advice_db_error_masked_500(monkeypatch):
    client = _client(monkeypatch)

    def mock_create(*args, **kwargs):
        raise RuntimeError("Database connection failed with internal token sec_abc123xyz789")

    monkeypatch.setattr(router_module.advice_db, "create_advice", mock_create)

    response = client.post("/v1/advice", json={"content": "Valid advice content."})
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to create advice"
    assert "sec_abc123xyz789" not in response.text


def test_get_advice_success(monkeypatch):
    client = _client(monkeypatch)
    dummy_list = [_sample_advice_dict("adv-1"), _sample_advice_dict("adv-2")]

    monkeypatch.setattr(router_module.advice_db, "get_advice", lambda uid, **kw: dummy_list)

    response = client.get("/v1/advice?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "adv-1"
    assert data[1]["id"] == "adv-2"


def test_get_advice_with_filters(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def mock_get(uid, **kwargs):
        captured.update(kwargs)
        return [_sample_advice_dict("adv-focus")]

    monkeypatch.setattr(router_module.advice_db, "get_advice", mock_get)

    response = client.get("/v1/advice?category=focus&include_dismissed=true&limit=25&offset=5")
    assert response.status_code == 200
    assert captured["category"] == "focus"
    assert captured["include_dismissed"] is True
    assert captured["limit"] == 25
    assert captured["offset"] == 5


def test_get_advice_db_error_masked_500(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        router_module.advice_db, "get_advice", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DB query timeout"))
    )

    response = client.get("/v1/advice")
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to fetch advice"


def test_update_advice_success(monkeypatch):
    client = _client(monkeypatch)

    def mock_update(uid, advice_id, is_read=None, is_dismissed=None):
        return _sample_advice_dict(
            advice_id,
            is_read=is_read if is_read is not None else False,
            is_dismissed=is_dismissed if is_dismissed is not None else False,
        )

    monkeypatch.setattr(router_module.advice_db, "update_advice", mock_update)

    response = client.patch("/v1/advice/adv-1", json={"is_read": True})
    assert response.status_code == 200
    assert response.json()["is_read"] is True


def test_update_advice_rejects_empty_payload(monkeypatch):
    client = _client(monkeypatch)
    response = client.patch("/v1/advice/adv-1", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "At least one field (is_read or is_dismissed) must be provided"


@pytest.mark.parametrize("bad_id", ["", "   ", "%20"])
def test_update_advice_rejects_whitespace_id(monkeypatch, bad_id):
    client = _client(monkeypatch)
    response = client.patch(f"/v1/advice/{bad_id}", json={"is_read": True})
    if response.status_code == 400:
        assert response.json()["detail"] == "Valid advice_id is required"
    else:
        assert response.status_code in (404, 405)


def test_update_advice_not_found(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_module.advice_db, "update_advice", lambda *a, **k: None)

    response = client.patch("/v1/advice/missing-adv", json={"is_read": True})
    assert response.status_code == 404
    assert response.json()["detail"] == "Advice not found"


def test_update_advice_db_error_masked_500(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        router_module.advice_db, "update_advice", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Firestore down"))
    )

    response = client.patch("/v1/advice/adv-1", json={"is_read": True})
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to update advice"


def test_delete_advice_success(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_module.advice_db, "delete_advice", lambda *a, **k: True)

    response = client.delete("/v1/advice/adv-1")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_delete_advice_not_found_404(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_module.advice_db, "delete_advice", lambda *a, **k: False)

    response = client.delete("/v1/advice/missing-adv")
    assert response.status_code == 404
    assert response.json()["detail"] == "Advice not found"


@pytest.mark.parametrize("bad_id", ["", "   ", "%20"])
def test_delete_advice_rejects_whitespace_id(monkeypatch, bad_id):
    client = _client(monkeypatch)
    response = client.delete(f"/v1/advice/{bad_id}")
    if response.status_code == 400:
        assert response.json()["detail"] == "Valid advice_id is required"
    else:
        assert response.status_code in (404, 405)


def test_delete_advice_db_error_masked_500(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        router_module.advice_db,
        "delete_advice",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Firestore delete error")),
    )

    response = client.delete("/v1/advice/adv-1")
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to delete advice"


def test_mark_all_read_success(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_module.advice_db, "mark_all_advice_read", lambda uid: 5)

    response = client.post("/v1/advice/mark-all-read")
    assert response.status_code == 200
    assert response.json()["status"] == "marked 5 as read"


def test_mark_all_read_db_error_masked_500(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        router_module.advice_db,
        "mark_all_advice_read",
        lambda uid: (_ for _ in ()).throw(RuntimeError("Batch write failed")),
    )

    response = client.post("/v1/advice/mark-all-read")
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to mark all advice as read"
