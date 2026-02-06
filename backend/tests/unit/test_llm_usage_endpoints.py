"""
Unit tests for LLM usage API endpoints.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Stub Firestore client to avoid ADC lookups during import.
mock_client_module = types.ModuleType("database._client")
mock_client_module.db = MagicMock()
sys.modules["database._client"] = mock_client_module

# Stub firebase_admin auth to keep dependency injection lightweight.
firebase_admin = types.ModuleType("firebase_admin")
firebase_admin.auth = MagicMock()
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin.auth

# Stub database submodules used by routers.users to avoid heavy imports.
for name in [
    "database.conversations",
    "database.memories",
    "database.chat",
    "database.user_usage",
    "database.notifications",
    "database.daily_summaries",
    "database.redis_db",
    "database.users",
    "database.cache",
]:
    sys.modules[name] = types.ModuleType(name)

sys.modules["database.conversations"].get_in_progress_conversation = MagicMock()
sys.modules["database.conversations"].get_conversation = MagicMock()

redis_mod = sys.modules["database.redis_db"]
for attr in [
    "cache_user_geolocation",
    "get_cached_user_geolocation",
    "set_user_webhook_db",
    "get_user_webhook_db",
    "disable_user_webhook_db",
    "enable_user_webhook_db",
    "user_webhook_status_db",
    "set_user_preferred_app",
    "set_user_data_protection_level",
    "get_generic_cache",
    "set_generic_cache",
    "remove_user_soniox_speech_profile",
    "set_speech_profile_duration",
    "r",
]:
    setattr(redis_mod, attr, MagicMock())

users_mod = sys.modules["database.users"]
users_mod.get_user_transcription_preferences = MagicMock()
users_mod.set_user_transcription_preferences = MagicMock()
users_mod.__all__ = []

llm_usage_mod = types.ModuleType("database.llm_usage")
llm_usage_mod.get_usage_summary = MagicMock()
llm_usage_mod.get_top_features = MagicMock()
sys.modules["database.llm_usage"] = llm_usage_mod

# Stub utils modules that pull in external dependencies.
for name in [
    "utils.apps",
    "utils.subscription",
    "utils.stripe",
    "utils.llm.followup",
    "utils.notifications",
    "utils.llm.external_integrations",
    "utils.webhooks",
    "utils.other.storage",
]:
    sys.modules[name] = types.ModuleType(name)

sys.modules["utils.apps"].get_available_app_by_id = MagicMock()
subscription_mod = sys.modules["utils.subscription"]
subscription_mod.get_plan_limits = MagicMock()
subscription_mod.get_plan_features = MagicMock()
subscription_mod.get_monthly_usage_for_subscription = MagicMock()
subscription_mod.reconcile_basic_plan_with_stripe = MagicMock()

sys.modules["utils.llm.followup"].followup_question_prompt = MagicMock()
notifications_mod = sys.modules["utils.notifications"]
notifications_mod.send_notification = MagicMock()
notifications_mod.send_training_data_submitted_notification = MagicMock()

sys.modules["utils.llm.external_integrations"].generate_comprehensive_daily_summary = MagicMock()

sys.modules["utils.webhooks"].webhook_first_time_setup = MagicMock()

storage_mod = sys.modules["utils.other.storage"]
storage_mod.delete_all_conversation_recordings = MagicMock()
storage_mod.get_speech_sample_signed_urls = MagicMock()
storage_mod.delete_user_person_speech_samples = MagicMock()
storage_mod.delete_user_person_speech_sample = MagicMock()

endpoints_module = types.ModuleType("utils.other.endpoints")
endpoints_module.get_current_user_uid = lambda: "test-user"
sys.modules["utils.other.endpoints"] = endpoints_module

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users as users_router

app = FastAPI()
app.include_router(users_router.router)
app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: "test-user"
client = TestClient(app)


def test_get_llm_usage_summary_and_top_features():
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
    users_router.llm_usage_db.get_usage_summary = MagicMock(return_value=summary)
    users_router.llm_usage_db.get_top_features = MagicMock(return_value=top_features)

    response = client.get("/v1/users/me/llm-usage?days=14")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "summary": summary,
        "top_features": top_features,
        "period_days": 14,
    }

    users_router.llm_usage_db.get_usage_summary.assert_called_once_with("test-user", days=14)
    users_router.llm_usage_db.get_top_features.assert_called_once_with("test-user", days=14, limit=5)


def test_get_llm_usage_top_features_endpoint():
    top_features = [
        {
            "feature": "rag",
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
            "call_count": 1,
        }
    ]
    users_router.llm_usage_db.get_top_features = MagicMock(return_value=top_features)

    response = client.get("/v1/users/me/llm-usage/top-features?days=7&limit=2")

    assert response.status_code == 200
    assert response.json() == top_features
    users_router.llm_usage_db.get_top_features.assert_called_once_with("test-user", days=7, limit=2)
