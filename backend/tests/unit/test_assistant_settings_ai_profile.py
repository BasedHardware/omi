from datetime import datetime, timezone
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


class TestAssistantSettingsValidation:
    def test_get_empty_returns_200(self, client):
        with patch('routers.users.get_assistant_settings', return_value={}):
            resp = client.get("/v1/users/assistant-settings", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_patch_prompt_exceeds_10000_chars(self, client):
        data = {"focus": {"analysis_prompt": "x" * 10001}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "10000" in resp.json()["detail"]

    def test_patch_prompt_at_10000_chars_accepted(self, client):
        data = {"focus": {"analysis_prompt": "x" * 10000}}
        with patch('routers.users.update_assistant_settings', return_value=data):
            resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_allowed_apps_exceeds_500(self, client):
        data = {"task": {"allowed_apps": ["app"] * 501}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "500" in resp.json()["detail"]

    def test_patch_browser_keywords_exceeds_500(self, client):
        data = {"task": {"browser_keywords": ["kw"] * 501}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_task_confidence_below_zero(self, client):
        data = {"task": {"min_confidence": -0.1}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_task_confidence_above_one(self, client):
        data = {"task": {"min_confidence": 1.5}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_task_confidence_zero_accepted(self, client):
        data = {"task": {"min_confidence": 0.0}}
        with patch('routers.users.update_assistant_settings', return_value=data):
            resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_task_confidence_one_accepted(self, client):
        data = {"task": {"min_confidence": 1.0}}
        with patch('routers.users.update_assistant_settings', return_value=data):
            resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_advice_confidence_above_one(self, client):
        data = {"advice": {"min_confidence": 1.1}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_memory_confidence_below_zero(self, client):
        data = {"memory": {"min_confidence": -0.5}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_empty_body_returns_current(self, client):
        with patch('routers.users.get_assistant_settings', return_value={"focus": {"enabled": True}}):
            resp = client.patch("/v1/users/assistant-settings", json={}, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_task_prompt_exceeds_10000_chars(self, client):
        data = {"task": {"analysis_prompt": "x" * 10001}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "task" in resp.json()["detail"]

    def test_patch_advice_prompt_exceeds_10000_chars(self, client):
        data = {"advice": {"analysis_prompt": "x" * 10001}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "advice" in resp.json()["detail"]

    def test_patch_memory_prompt_exceeds_10000_chars(self, client):
        data = {"memory": {"analysis_prompt": "x" * 10001}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400
        assert "memory" in resp.json()["detail"]

    def test_patch_advice_confidence_below_zero(self, client):
        data = {"advice": {"min_confidence": -0.1}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_memory_confidence_above_one(self, client):
        data = {"memory": {"min_confidence": 1.5}}
        resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_excludes_none_fields(self, client):
        data = {"task": {"enabled": True}}
        with patch('routers.users.update_assistant_settings', return_value=data) as mock_update:
            resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 200
        call_data = mock_update.call_args[0][1]
        assert "min_confidence" not in call_data.get("task", {})

    def test_patch_update_channel(self, client):
        data = {"update_channel": "beta"}
        with patch('routers.users.update_assistant_settings', return_value={"update_channel": "beta"}) as mock_update:
            resp = client.patch("/v1/users/assistant-settings", json=data, headers=AUTH)
        assert resp.status_code == 200
        call_data = mock_update.call_args[0][1]
        assert call_data["update_channel"] == "beta"


class TestAIProfileValidation:
    def test_get_empty_returns_null(self, client):
        with patch('routers.users.get_ai_user_profile', return_value=None):
            resp = client.get("/v1/users/ai-profile", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() is None

    def test_patch_valid_rfc3339_z(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00Z", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile', return_value=data):
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_valid_rfc3339_offset(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00+05:30", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile', return_value=data):
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_valid_rfc3339_fractional(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00.123Z", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile', return_value=data):
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200

    def test_patch_invalid_no_timezone(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00", "data_sources_used": 1}
        resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_invalid_no_t_separator(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05 10:00:00Z", "data_sources_used": 1}
        resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_invalid_short_offset(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00+00", "data_sources_used": 1}
        resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_invalid_garbage(self, client):
        data = {"profile_text": "test", "generated_at": "not-a-date", "data_sources_used": 1}
        resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_invalid_calendar_date(self, client):
        # Feb 30 passes regex but fails fromisoformat
        data = {"profile_text": "test", "generated_at": "2026-02-30T10:00:00Z", "data_sources_used": 1}
        resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 400

    def test_patch_generated_at_stored_as_datetime(self, client):
        data = {"profile_text": "test", "generated_at": "2026-03-05T10:00:00Z", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile') as mock_update:
            mock_update.return_value = {}
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200
        call_data = mock_update.call_args[0][1]
        assert isinstance(call_data['generated_at'], datetime)
        assert call_data['generated_at'].tzinfo is not None

    def test_profile_text_truncation_at_boundary(self, client):
        # 10001 bytes of ASCII should truncate to 10000
        long_text = "x" * 10001
        data = {"profile_text": long_text, "generated_at": "2026-03-05T10:00:00Z", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile') as mock_update:
            mock_update.return_value = {"profile_text": "x" * 10000}
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200
        call_data = mock_update.call_args[0][1]
        assert len(call_data['profile_text']) == 10000

    def test_profile_text_multibyte_truncation(self, client):
        # Multibyte UTF-8: emoji is 4 bytes, test boundary doesn't split mid-char
        text = "a" * 9998 + "\U0001F600"  # 9998 + 4 bytes = 10002 bytes
        data = {"profile_text": text, "generated_at": "2026-03-05T10:00:00Z", "data_sources_used": 1}
        with patch('routers.users.update_ai_user_profile') as mock_update:
            mock_update.return_value = {}
            resp = client.patch("/v1/users/ai-profile", json=data, headers=AUTH)
        assert resp.status_code == 200
        call_data = mock_update.call_args[0][1]
        # Should not have broken emoji — truncated to 9998 'a's
        assert len(call_data['profile_text'].encode('utf-8')) <= 10000
