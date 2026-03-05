from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch('database.screen_activity.db'), \
         patch('database.focus_sessions.db'), \
         patch('database.advice.db'), \
         patch('database.vector_db.Pinecone'), \
         patch('database.vector_db.pc'), \
         patch('database.vector_db.index'), \
         patch('utils.llm.clients.embeddings'):
        from main import app
        with TestClient(app) as c:
            yield c


AUTH = {"Authorization": "Bearer 123testuser"}


class TestCreateAdvice:
    def test_create_minimal(self, client):
        data = {"content": "Take a break"}
        with patch('routers.advice.advice_db.create_advice') as mock_create:
            mock_create.return_value = {
                "id": "adv-1", "content": "Take a break", "category": "other",
                "confidence": 0.5, "is_read": False, "is_dismissed": False,
                "created_at": datetime.now(timezone.utc),
            }
            resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["content"] == "Take a break"
        assert resp.json()["category"] == "other"

    def test_create_with_all_fields(self, client):
        data = {
            "content": "Drink water", "category": "health", "reasoning": "Dehydrated",
            "source_app": "Chrome", "confidence": 0.9, "context_summary": "Long session",
            "current_activity": "Browsing",
        }
        with patch('routers.advice.advice_db.create_advice') as mock_create:
            mock_create.return_value = {"id": "adv-2", **data, "is_read": False, "is_dismissed": False, "created_at": datetime.now(timezone.utc)}
            resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["category"] == "health"
        assert resp.json()["confidence"] == 0.9

    def test_create_invalid_category_returns_400(self, client):
        data = {"content": "Test", "category": "invalid_cat"}
        resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "category" in resp.json()["detail"]

    def test_create_confidence_below_zero_returns_400(self, client):
        data = {"content": "Test", "confidence": -0.1}
        resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_create_confidence_above_one_returns_400(self, client):
        data = {"content": "Test", "confidence": 1.1}
        resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_create_confidence_boundary_zero(self, client):
        data = {"content": "Test", "confidence": 0.0}
        with patch('routers.advice.advice_db.create_advice') as mock_create:
            mock_create.return_value = {"id": "adv-3", "content": "Test", "confidence": 0.0, "category": "other", "is_read": False, "is_dismissed": False, "created_at": datetime.now(timezone.utc)}
            resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_create_confidence_boundary_one(self, client):
        data = {"content": "Test", "confidence": 1.0}
        with patch('routers.advice.advice_db.create_advice') as mock_create:
            mock_create.return_value = {"id": "adv-4", "content": "Test", "confidence": 1.0, "category": "other", "is_read": False, "is_dismissed": False, "created_at": datetime.now(timezone.utc)}
            resp = client.post("/v1/advice", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_create_no_auth_returns_401(self, client):
        resp = client.post("/v1/advice", json={"content": "Test"})
        assert resp.status_code == 401

    def test_create_firestore_error_returns_500(self, client):
        with patch('routers.advice.advice_db.create_advice', side_effect=Exception("DB down")):
            resp = client.post("/v1/advice", json={"content": "Test"}, headers=AUTH)
        assert resp.status_code == 500

    def test_create_each_valid_category(self, client):
        for cat in ('productivity', 'health', 'communication', 'learning', 'other'):
            data = {"content": "Test", "category": cat}
            with patch('routers.advice.advice_db.create_advice') as mock_create:
                mock_create.return_value = {"id": "x", "content": "Test", "category": cat, "confidence": 0.5, "is_read": False, "is_dismissed": False, "created_at": datetime.now(timezone.utc)}
                resp = client.post("/v1/advice", json=data, headers=AUTH)
            assert resp.status_code == 200, f"Failed for category {cat}"


class TestGetAdvice:
    def test_get_empty(self, client):
        with patch('routers.advice.advice_db.get_advice', return_value=[]):
            resp = client.get("/v1/advice", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_with_category_filter(self, client):
        with patch('routers.advice.advice_db.get_advice', return_value=[]) as mock_get:
            resp = client.get("/v1/advice?category=health", headers=AUTH)
        assert resp.status_code == 200
        assert mock_get.call_args[1]['category'] == 'health'

    def test_get_invalid_category_skips_filter(self, client):
        with patch('routers.advice.advice_db.get_advice', return_value=[]) as mock_get:
            resp = client.get("/v1/advice?category=bad_cat", headers=AUTH)
        assert resp.status_code == 200
        assert mock_get.call_args[1]['category'] is None

    def test_get_include_dismissed(self, client):
        with patch('routers.advice.advice_db.get_advice', return_value=[]) as mock_get:
            resp = client.get("/v1/advice?include_dismissed=true", headers=AUTH)
        assert resp.status_code == 200
        assert mock_get.call_args[1]['include_dismissed'] is True

    def test_get_with_pagination(self, client):
        with patch('routers.advice.advice_db.get_advice', return_value=[]) as mock_get:
            resp = client.get("/v1/advice?limit=50&offset=20", headers=AUTH)
        assert resp.status_code == 200
        assert mock_get.call_args[1]['limit'] == 50
        assert mock_get.call_args[1]['offset'] == 20

    def test_get_firestore_error_returns_empty(self, client):
        with patch('routers.advice.advice_db.get_advice', side_effect=Exception("err")):
            resp = client.get("/v1/advice", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateAdvice:
    def test_mark_as_read(self, client):
        with patch('routers.advice.advice_db.update_advice') as mock_update:
            mock_update.return_value = {"id": "adv-1", "is_read": True, "is_dismissed": False, "content": "x", "category": "other", "confidence": 0.5, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
            resp = client.patch("/v1/advice/adv-1", json={"is_read": True}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_mark_as_dismissed(self, client):
        with patch('routers.advice.advice_db.update_advice') as mock_update:
            mock_update.return_value = {"id": "adv-1", "is_read": False, "is_dismissed": True, "content": "x", "category": "other", "confidence": 0.5, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
            resp = client.patch("/v1/advice/adv-1", json={"is_dismissed": True}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["is_dismissed"] is True

    def test_empty_update_still_updates_timestamp(self, client):
        with patch('routers.advice.advice_db.update_advice') as mock_update:
            mock_update.return_value = {"id": "adv-1", "is_read": False, "is_dismissed": False, "content": "x", "category": "other", "confidence": 0.5, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
            resp = client.patch("/v1/advice/adv-1", json={}, headers=AUTH)
        assert resp.status_code == 200

    def test_update_not_found_returns_500(self, client):
        with patch('routers.advice.advice_db.update_advice', return_value=None):
            resp = client.patch("/v1/advice/adv-1", json={"is_read": True}, headers=AUTH)
        assert resp.status_code == 500

    def test_update_firestore_error_returns_500(self, client):
        with patch('routers.advice.advice_db.update_advice', side_effect=Exception("err")):
            resp = client.patch("/v1/advice/adv-1", json={"is_read": True}, headers=AUTH)
        assert resp.status_code == 500


class TestDeleteAdvice:
    def test_delete_returns_ok(self, client):
        with patch('routers.advice.advice_db.delete_advice', return_value=True):
            resp = client.delete("/v1/advice/adv-1", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_delete_firestore_error_returns_500(self, client):
        with patch('routers.advice.advice_db.delete_advice', side_effect=Exception("err")):
            resp = client.delete("/v1/advice/adv-1", headers=AUTH)
        assert resp.status_code == 500


class TestMarkAllRead:
    def test_mark_all_read_returns_count(self, client):
        with patch('routers.advice.advice_db.mark_all_advice_read', return_value=5):
            resp = client.post("/v1/advice/mark-all-read", headers=AUTH)
        assert resp.status_code == 200
        assert "5" in resp.json()["status"]

    def test_mark_all_read_zero(self, client):
        with patch('routers.advice.advice_db.mark_all_advice_read', return_value=0):
            resp = client.post("/v1/advice/mark-all-read", headers=AUTH)
        assert resp.status_code == 200
        assert "0" in resp.json()["status"]

    def test_mark_all_read_firestore_error(self, client):
        with patch('routers.advice.advice_db.mark_all_advice_read', side_effect=Exception("err")):
            resp = client.post("/v1/advice/mark-all-read", headers=AUTH)
        assert resp.status_code == 500
