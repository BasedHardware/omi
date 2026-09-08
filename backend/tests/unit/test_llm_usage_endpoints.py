"""
Unit tests for LLM usage API endpoints.

``routers.users`` is import-pure (``database._client.db`` is a lazy proxy, and the
``tests/conftest.py`` session stubs cover redis/tiktoken), so this file needs no
``sys.modules`` stubbing. The two endpoints under test only call
``llm_usage_db.get_usage_summary`` / ``get_top_features``; we patch those attributes
hermetically via ``monkeypatch`` (auto-restored at teardown) instead of mutating the
real module global state.
"""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users as users_router

app = FastAPI()
app.include_router(users_router.router)
app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: "test-user"
client = TestClient(app)


def test_get_llm_usage_summary_and_top_features(monkeypatch):
    summary = {"chat": {"input_tokens": 12, "output_tokens": 8, "call_count": 2}}
    top_features = [
        {
            "feature": "chat",
            "input_tokens": 12,
            "output_tokens": 8,
            "total_tokens": 20,
            "call_count": 2,
        }
    ]
    get_usage_summary = MagicMock(return_value=summary)
    get_top_features = MagicMock(return_value=top_features)
    monkeypatch.setattr(users_router.llm_usage_db, "get_usage_summary", get_usage_summary)
    monkeypatch.setattr(users_router.llm_usage_db, "get_top_features", get_top_features)

    response = client.get("/v1/users/me/llm-usage?days=14")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "summary": summary,
        "top_features": top_features,
        "period_days": 14,
    }

    get_usage_summary.assert_called_once_with("test-user", days=14)
    get_top_features.assert_called_once_with("test-user", days=14, limit=5)


def test_get_llm_usage_top_features_endpoint(monkeypatch):
    top_features = [
        {
            "feature": "rag",
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
            "call_count": 1,
        }
    ]
    get_top_features = MagicMock(return_value=top_features)
    monkeypatch.setattr(users_router.llm_usage_db, "get_top_features", get_top_features)

    response = client.get("/v1/users/me/llm-usage/top-features?days=7&limit=2")

    assert response.status_code == 200
    assert response.json() == top_features
    get_top_features.assert_called_once_with("test-user", days=7, limit=2)
