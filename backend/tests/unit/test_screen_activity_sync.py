import threading
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch('database.screen_activity.db'), \
         patch('database.vector_db.Pinecone'), \
         patch('database.vector_db.pc'), \
         patch('database.vector_db.index'), \
         patch('utils.llm.clients.embeddings'):
        from main import app
        with TestClient(app) as c:
            yield c


AUTH = {"Authorization": "Bearer 123testuser"}


class TestScreenActivitySyncValidation:
    def test_empty_rows_returns_zero(self, client):
        resp = client.post("/v1/screen-activity/sync", json={"rows": []}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"synced": 0, "last_id": 0}

    def test_exceeds_100_rows_returns_400(self, client):
        rows = [{"id": i, "timestamp": "2026-01-01T00:00:00Z", "appName": "A", "windowTitle": "W", "ocrText": "x"} for i in range(101)]
        resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 400
        assert "100" in resp.json()["detail"]

    def test_exactly_100_rows_accepted(self, client):
        rows = [{"id": i, "timestamp": "2026-01-01T00:00:00Z"} for i in range(100)]
        with patch('routers.screen_activity.screen_activity_db.upsert_screen_activity', return_value=100):
            resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["synced"] == 100

    def test_no_auth_returns_401(self, client):
        resp = client.post("/v1/screen-activity/sync", json={"rows": []})
        assert resp.status_code == 401

    def test_last_id_is_max_from_batch(self, client):
        rows = [
            {"id": 5, "timestamp": "2026-01-01T00:00:00Z"},
            {"id": 99, "timestamp": "2026-01-01T00:01:00Z"},
            {"id": 3, "timestamp": "2026-01-01T00:02:00Z"},
        ]
        with patch('routers.screen_activity.screen_activity_db.upsert_screen_activity', return_value=3):
            resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["last_id"] == 99

    def test_firestore_error_returns_500(self, client):
        rows = [{"id": 1, "timestamp": "2026-01-01T00:00:00Z"}]
        with patch('routers.screen_activity.screen_activity_db.upsert_screen_activity', side_effect=Exception("Firestore down")):
            resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 500

    def test_rows_with_embeddings_spawn_thread(self, client):
        rows = [{"id": 1, "timestamp": "2026-01-01T00:00:00Z", "embedding": [0.1] * 3072}]
        with patch('routers.screen_activity.screen_activity_db.upsert_screen_activity', return_value=1), \
             patch('routers.screen_activity.threading.Thread') as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 200
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_rows_without_embeddings_no_thread(self, client):
        rows = [{"id": 1, "timestamp": "2026-01-01T00:00:00Z"}]
        with patch('routers.screen_activity.screen_activity_db.upsert_screen_activity', return_value=1), \
             patch('routers.screen_activity.threading.Thread') as mock_thread:
            resp = client.post("/v1/screen-activity/sync", json={"rows": rows}, headers=AUTH)
        assert resp.status_code == 200
        mock_thread.assert_not_called()
