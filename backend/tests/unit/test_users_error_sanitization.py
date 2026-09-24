"""Unit tests for exception sanitization across user management and migration endpoints.

Ensures that internal database connection strings, paths, and raw exception details
are never leaked in HTTP 500 error responses from routers/users.py.
"""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from testing.import_isolation import AutoMockModule, stub_modules

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_STUB_MODULES = [
    "pinecone",
    "typesense",
    "stripe",
    "pycountry",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "google.cloud.firestore",
    "database._client",
    "database.vector_db",
    "services.users.account_deletion",
    "services.users.data_export",
    "utils.twilio_service",
    "utils.apps",
    "utils.llm.clients",
    "anthropic",
    "openai",
]

users_router = None
SENSITIVE_TRACE = "postgresql://admin:super_secret_pw@internal-db.prod.internal:5432/omi"


@pytest.fixture(scope="module", autouse=True)
def _isolate_dependencies():
    fakes = {name: AutoMockModule(name) for name in _STUB_MODULES}
    with stub_modules(fakes):
        from routers import users as _users_router

        mod = sys.modules[__name__]
        mod.users_router = _users_router
        yield


class TestUsersMigrationSanitization:
    def test_migrate_conversation_exception_sanitized(self):
        req = users_router.MigrationRequest(id="conv-123", type="conversation", target_level="enhanced")
        with patch.object(
            users_router.conversations_db,
            "migrate_conversations_level_batch",
            side_effect=RuntimeError(f"Database connection timeout: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.handle_migration_requests(req, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to migrate conversation conv-123"
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_migrate_memory_exception_sanitized(self):
        req = users_router.MigrationRequest(id="mem-456", type="memory", target_level="enhanced")
        with patch.object(
            users_router.memories_db,
            "migrate_memories_level_batch",
            side_effect=RuntimeError(f"Write lock failed: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.handle_migration_requests(req, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to migrate memory mem-456"
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_migrate_chat_message_exception_sanitized(self):
        req = users_router.MigrationRequest(id="chat-789", type="chat", target_level="enhanced")
        with patch.object(
            users_router.chat_db,
            "migrate_chats_level_batch",
            side_effect=RuntimeError(f"Internal storage error: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.handle_migration_requests(req, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to migrate chat message chat-789"
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_batch_migration_exceptions_sanitized(self):
        batch_request = users_router.BatchMigrationRequest(
            requests=[
                users_router.MigrationRequest(id="conv-1", type="conversation", target_level="enhanced"),
                users_router.MigrationRequest(id="mem-1", type="memory", target_level="enhanced"),
            ]
        )
        with patch.object(
            users_router.conversations_db,
            "migrate_conversations_level_batch",
            side_effect=RuntimeError(f"Batch network drop: {SENSITIVE_TRACE}"),
        ), patch.object(
            users_router.memories_db,
            "migrate_memories_level_batch",
            side_effect=RuntimeError(f"Database disk error: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.handle_batch_migration_requests(batch_request, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            detail = exc_info.value.detail
            assert isinstance(detail, dict)
            assert detail.get("message") == "Some objects failed to migrate."
            errors = detail.get("errors", [])
            assert "Failed to migrate batch of type conversation" in errors
            assert "Failed to migrate batch of type memory" in errors
            assert SENSITIVE_TRACE not in str(detail)


class TestUsersTimezoneSanitization:
    def test_daily_summary_timezone_exception_sanitized(self):
        with patch.object(users_router, "enforce_chat_quota"), patch.object(
            users_router.notification_db, "get_all_tokens", return_value=["token_123"]
        ), patch.object(users_router.notification_db, "get_user_time_zone", return_value="Invalid/Timezone"), patch(
            "pytz.timezone",
            side_effect=RuntimeError(f"pytz fatal crash: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.test_daily_summary(request=None, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to resolve user timezone."
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_create_daily_summary_timezone_exception_sanitized(self):
        request = users_router.CreateDailySummaryRequest(date="2026-09-24")
        with patch.object(users_router.notification_db, "get_user_time_zone", return_value="Invalid/Timezone"), patch(
            "pytz.timezone",
            side_effect=RuntimeError(f"pytz lookup failed: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.create_user_daily_summary(request=request, uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to resolve user timezone."
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_regenerate_daily_summary_timezone_exception_sanitized(self):
        with patch.object(users_router, "enforce_chat_quota"), patch.object(
            users_router.daily_summaries_db, "get_daily_summary", return_value={"date": "2026-09-24"}
        ), patch.object(users_router, "get_generic_cache", return_value=None), patch.object(
            users_router, "set_generic_cache", return_value=None
        ), patch.object(
            users_router.notification_db, "get_user_time_zone", return_value="Invalid/Timezone"
        ), patch(
            "pytz.timezone",
            side_effect=RuntimeError(f"pytz localize failed: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.regenerate_daily_summary(summary_id="sum-123", uid="test-uid-1")

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to resolve user timezone."
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)


class TestUsersSettingsSanitization:
    def test_daily_summary_hour_sanitized(self):
        data = users_router.DailySummarySettingsUpdate(hour=10)
        with patch.object(
            users_router.notification_db,
            "set_daily_summary_hour_local",
            side_effect=ValueError(f"Internal DB connection leak: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.update_daily_summary_settings(data=data, uid="test-uid-1")

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "Invalid hour. Must be between 0 and 23."
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)

    def test_mentor_notification_frequency_sanitized(self):
        data = users_router.MentorNotificationSettingsUpdate(frequency=3)
        with patch.object(
            users_router.notification_db,
            "set_mentor_notification_frequency",
            side_effect=ValueError(f"Internal DB connection leak: {SENSITIVE_TRACE}"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                users_router.update_mentor_notification_settings(data=data, uid="test-uid-1")

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "Invalid frequency. Must be between 0 and 5."
            assert SENSITIVE_TRACE not in str(exc_info.value.detail)
