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


class TestCreateFocusSession:
    def test_create_focused_session(self, client):
        data = {"status": "focused", "app_or_site": "VSCode", "description": "Coding"}
        with patch('routers.focus_sessions.focus_sessions_db.create_focus_session') as mock_create:
            mock_create.return_value = {
                "id": "abc-123", "status": "focused", "app_or_site": "VSCode",
                "description": "Coding", "created_at": datetime.now(timezone.utc),
            }
            resp = client.post("/v1/focus-sessions", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "focused"

    def test_create_distracted_session(self, client):
        data = {"status": "distracted", "app_or_site": "Twitter", "description": "Scrolling"}
        with patch('routers.focus_sessions.focus_sessions_db.create_focus_session') as mock_create:
            mock_create.return_value = {
                "id": "abc-456", "status": "distracted", "app_or_site": "Twitter",
                "description": "Scrolling", "created_at": datetime.now(timezone.utc),
            }
            resp = client.post("/v1/focus-sessions", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "distracted"

    def test_create_invalid_status_returns_400(self, client):
        data = {"status": "invalid", "app_or_site": "X", "description": "Y"}
        resp = client.post("/v1/focus-sessions", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "focused" in resp.json()["detail"]

    def test_create_with_optional_fields(self, client):
        data = {
            "status": "focused", "app_or_site": "VSCode", "description": "Coding",
            "message": "Keep going!", "duration_seconds": 300,
        }
        with patch('routers.focus_sessions.focus_sessions_db.create_focus_session') as mock_create:
            mock_create.return_value = {
                "id": "abc-789", "message": "Keep going!", "duration_seconds": 300,
                **{k: v for k, v in data.items()}, "created_at": datetime.now(timezone.utc),
            }
            resp = client.post("/v1/focus-sessions", json=data, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["message"] == "Keep going!"
        assert resp.json()["duration_seconds"] == 300

    def test_create_no_auth_returns_401(self, client):
        data = {"status": "focused", "app_or_site": "X", "description": "Y"}
        resp = client.post("/v1/focus-sessions", json=data)
        assert resp.status_code == 401

    def test_create_firestore_error_returns_500(self, client):
        data = {"status": "focused", "app_or_site": "X", "description": "Y"}
        with patch('routers.focus_sessions.focus_sessions_db.create_focus_session', side_effect=Exception("DB down")):
            resp = client.post("/v1/focus-sessions", json=data, headers=AUTH)
        assert resp.status_code == 500


class TestGetFocusSessions:
    def test_get_empty_returns_list(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions', return_value=[]):
            resp = client.get("/v1/focus-sessions", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_with_date_filter(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions', return_value=[]) as mock_get:
            resp = client.get("/v1/focus-sessions?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['date'] == '2026-03-05'

    def test_get_invalid_date_skips_filter(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions', return_value=[]) as mock_get:
            resp = client.get("/v1/focus-sessions?date=not-a-date", headers=AUTH)
        assert resp.status_code == 200
        assert mock_get.call_args[1]['date'] is None

    def test_get_with_limit_and_offset(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions', return_value=[]) as mock_get:
            resp = client.get("/v1/focus-sessions?limit=50&offset=10", headers=AUTH)
        assert resp.status_code == 200
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['limit'] == 50
        assert mock_get.call_args[1]['offset'] == 10

    def test_get_firestore_error_returns_empty(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions', side_effect=Exception("err")):
            resp = client.get("/v1/focus-sessions", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []


class TestDeleteFocusSession:
    def test_delete_returns_ok(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.delete_focus_session', return_value=True):
            resp = client.delete("/v1/focus-sessions/abc-123", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_delete_firestore_error_returns_500(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.delete_focus_session', side_effect=Exception("err")):
            resp = client.delete("/v1/focus-sessions/abc-123", headers=AUTH)
        assert resp.status_code == 500


class TestFocusStats:
    def test_stats_empty_sessions(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=[]):
            resp = client.get("/v1/focus-stats?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-03-05"
        assert data["session_count"] == 0
        assert data["focused_count"] == 0
        assert data["distracted_count"] == 0
        assert data["top_distractions"] == []

    def test_stats_with_sessions(self, client):
        sessions = [
            {"status": "focused", "app_or_site": "VSCode", "duration_seconds": 120},
            {"status": "distracted", "app_or_site": "Twitter", "duration_seconds": 60},
            {"status": "distracted", "app_or_site": "Twitter", "duration_seconds": 90},
            {"status": "distracted", "app_or_site": "Reddit", "duration_seconds": 30},
        ]
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=sessions):
            resp = client.get("/v1/focus-stats?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["focused_count"] == 1
        assert data["distracted_count"] == 3
        assert data["session_count"] == 4
        assert len(data["top_distractions"]) == 2
        assert data["top_distractions"][0]["app_or_site"] == "Twitter"
        assert data["top_distractions"][0]["total_seconds"] == 150

    def test_stats_defaults_to_today(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=[]) as mock_get:
            resp = client.get("/v1/focus-stats", headers=AUTH)
        assert resp.status_code == 200
        called_date = mock_get.call_args[0][1]
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        assert called_date == today

    def test_stats_invalid_date_defaults_to_today(self, client):
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=[]) as mock_get:
            resp = client.get("/v1/focus-stats?date=bad", headers=AUTH)
        assert resp.status_code == 200
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        assert mock_get.call_args[0][1] == today

    def test_stats_distraction_without_duration_defaults_60(self, client):
        sessions = [
            {"status": "distracted", "app_or_site": "YouTube"},
        ]
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=sessions):
            resp = client.get("/v1/focus-stats?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["top_distractions"][0]["total_seconds"] == 60

    def test_stats_distraction_with_zero_duration_keeps_zero(self, client):
        sessions = [
            {"status": "distracted", "app_or_site": "Slack", "duration_seconds": 0},
        ]
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=sessions):
            resp = client.get("/v1/focus-stats?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["top_distractions"][0]["total_seconds"] == 0

    def test_stats_top5_limit(self, client):
        sessions = [
            {"status": "distracted", "app_or_site": f"App{i}", "duration_seconds": i * 10}
            for i in range(8)
        ]
        with patch('routers.focus_sessions.focus_sessions_db.get_focus_sessions_for_stats', return_value=sessions):
            resp = client.get("/v1/focus-stats?date=2026-03-05", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["top_distractions"]) == 5
