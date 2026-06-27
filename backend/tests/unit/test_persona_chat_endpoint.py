"""Tests for /v2/integrations/{app_id}/user/persona-chat endpoint (T-001).

Covers:
- app_can_persona_chat capability gate (pure)
- PersonaChatRequest Pydantic model
- Endpoint auth (401/403) + capability gate + happy-path routing to execute_chat_stream
"""

import os
import sys
import types
from datetime import datetime
from enum import Enum
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test.
# utils.apps pulls a long list of names from database.{redis_db,apps,auth,...};
# we give each stub module a MagicMock for every imported attribute so the
# import chain resolves.
# ---------------------------------------------------------------------------
def _full_stub(name, *attrs):
    mod = types.ModuleType(name)
    for a in attrs:
        setattr(mod, a, MagicMock())

    # Catch-all: any attribute lookup not explicitly set returns a MagicMock.
    # Handles long import lists in utils.apps without enumerating each name.
    def _getattr(_attr):
        return MagicMock()

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    # Use setdefault so we don't clobber a real module already imported by
    # another test in the same pytest session. This matters when running
    # `pytest backend/tests/unit/` — the persona_chat test would otherwise
    # overwrite database.* stubs into sys.modules and break test collection
    # of unrelated tests (test_prompt_caching, test_users_webhook_url_validation,
    # etc. all fail with module-already-stubbed errors).
    sys.modules.setdefault(name, mod)
    return mod


_redis_attrs = (
    "delete_generic_cache",
    "get_enabled_apps",
    "get_app_reviews",
    "get_generic_cache",
    "set_generic_cache",
    "set_app_usage_history_cache",
    "get_app_usage_history_cache",
    "get_app_money_made_cache",
    "set_app_money_made_cache",
    "get_apps_installs_count",
    "get_apps_reviews",
    "get_app_cache_by_id",
    "set_app_cache_by_id",
    "get_app_money_made",
    "r",
)
_redis = _full_stub("database.redis_db", *_redis_attrs)
_redis.get_enabled_apps = MagicMock(return_value=[])

_apps_db_attrs = (
    "get_private_apps_db",
    "get_public_unapproved_apps_db",
    "get_public_approved_apps_db",
    "get_app_by_id_db",
    "get_app_usage_history_db",
    "set_app_review_in_db",
    "get_app_usage_count_db",
    "get_app_memory_created_integration_usage_count_db",
    "get_app_memory_prompt_usage_count_db",
    "add_tester_db",
    "add_app_access_for_tester_db",
    "remove_app_access_for_tester_db",
    "remove_tester_db",
    "is_tester_db",
    "can_tester_access_app_db",
    "get_apps_for_tester_db",
    "get_app_chat_message_sent_usage_count_db",
    "update_app_in_db",
    "get_audio_apps_count",
    "get_persona_by_uid_db",
    "update_persona_in_db",
    "get_omi_personas_by_uid_db",
    "get_api_key_by_hash_db",
    "get_popular_apps_db",
)
_apps_db = _full_stub("database.apps", *_apps_db_attrs)
_apps_db.get_app_by_id_db = MagicMock(return_value=None)

_full_stub(
    "database.auth",
    "get_user_name",
)
_full_stub("database.conversations", "get_conversations")
_full_stub("database.memories", "get_memories", "get_user_public_memories")
_full_stub("database.notifications")
_full_stub("database.action_items")
_full_stub("database.users")

_full_stub("google.cloud.firestore")
_full_stub("google.cloud.firestore_v1")

# NOTE: models.integrations is NOT stubbed — the real module loads so the
# test can exercise the real Pydantic PersonaChatRequest class.
# models.conversation needs real Pydantic models because FastAPI validates
# response_model at route registration time.
_conv_mod = types.ModuleType("models.conversation")


class _ExternalIntegrationCreateConversation(BaseModel):
    """Stub matching the real model's name only — we never hit this route."""

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class _SearchRequest(BaseModel):
    """Stub matching the real model's name."""

    query: str = ""


class _ConversationSource(str, Enum):
    external_integration = "external_integration"


_conv_mod.ExternalIntegrationCreateConversation = _ExternalIntegrationCreateConversation
_conv_mod.SearchRequest = _SearchRequest
_conv_mod.ConversationSource = _ConversationSource
sys.modules["models.conversation"] = _conv_mod

_full_stub(
    "utils.other.endpoints",
    "check_rate_limit_inline",
    "get_current_user_uid",
)
_full_stub(
    "utils.executors",
    "run_blocking",
    "critical_executor",
    "db_executor",
    "postprocess_executor",
)

_full_stub("utils.llm")
_full_stub(
    "utils.llm.persona",
    "initial_persona_chat_message",
    "condense_conversations",
    "condense_memories",
    "generate_persona_description",
    "condense_tweets",
)
_full_stub("utils.llm.usage_tracker", "track_usage", "Features")
_full_stub("utils.app_integrations", "send_app_notification")
_full_stub("utils.conversations")
_full_stub("utils.conversations.location", "get_google_maps_location")
_full_stub("utils.conversations.render", "redact_conversation_for_integration", "conversations_to_string")
_full_stub("utils.conversations.memories", "process_external_integration_memory")
_full_stub("utils.conversations.search", "search_conversations")
_full_stub("utils.conversations.factory", "deserialize_conversations")
_full_stub("utils.social", "get_twitter_timeline")
_full_stub("utils.stripe")
_full_stub("database.cache", "get_memory_cache", "get_pubsub_manager")
# database.users needs get_stripe_connect_account_id
_users_mod = _full_stub("database.users", "get_user_name", "get_stripe_connect_account_id")
# models.app needs App, UsageHistoryItem, UsageHistoryType
_models_app = _full_stub("models.app", "App", "UsageHistoryItem", "UsageHistoryType")
# Set non-MagicMock defaults for Pydantic-like types used in test
_models_app.App = MagicMock()
_models_app.UsageHistoryItem = MagicMock()
_models_app.UsageHistoryType = MagicMock()
_full_stub(
    "routers.conversations",
    "process_conversation",
    "trigger_external_integrations",
)

# utils.retrieval.graph (imported by integration.py transitively)
_full_stub("utils.retrieval", "graph")
sys.modules["utils.retrieval.graph"] = MagicMock(execute_chat_stream=MagicMock())

import utils.apps as apps_utils  # noqa: E402

# Now safe to import the module under test
from utils.apps import app_can_persona_chat  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Pure capability check
# ---------------------------------------------------------------------------
class TestAppCanPersonaChat:
    def test_returns_true_when_action_declared(self):
        app = {"external_integration": {"actions": [{"action": "persona_chat"}]}}
        assert app_can_persona_chat(app) is True

    def test_returns_false_when_no_actions(self):
        app = {"external_integration": {"actions": []}}
        assert app_can_persona_chat(app) is False

    def test_returns_false_when_external_integration_missing(self):
        app = {"external_integration": None}
        assert app_can_persona_chat(app) is False

    def test_returns_false_when_other_action_declared(self):
        app = {"external_integration": {"actions": [{"action": "create_conversation"}]}}
        assert app_can_persona_chat(app) is False

    def test_returns_false_for_none(self):
        assert app_can_persona_chat(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Request model — re-import under the test (PersonaChatRequest may not
# exist yet during RED).
# ---------------------------------------------------------------------------
class TestPersonaChatRequest:
    def test_accepts_plain_text(self):
        from models.integrations import PersonaChatRequest

        req = PersonaChatRequest(text="hello there")
        assert req.text == "hello there"

    def test_rejects_empty_text(self):
        from pydantic import ValidationError

        from models.integrations import PersonaChatRequest

        with pytest.raises(ValidationError):
            PersonaChatRequest(text="")

    def test_rejects_missing_text(self):
        from pydantic import ValidationError

        from models.integrations import PersonaChatRequest

        with pytest.raises(ValidationError):
            PersonaChatRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 3. Endpoint behavior
# ---------------------------------------------------------------------------
def _build_test_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Import the route function (will fail RED if not defined yet — that's OK)
    from routers.integration import persona_chat_via_integration

    app = FastAPI()
    app.post("/v2/integrations/{app_id}/user/persona-chat")(persona_chat_via_integration)
    return TestClient(app)


def _async_return(value):
    """Return a callable that behaves like `await run_blocking(...)` returning `value`."""

    async def _run_blocking(*_args, **_kwargs):
        return value

    return _run_blocking


def _make_run_blocking_router(routes: dict):
    """Return an async run_blocking shim that dispatches to the right callable.

    routes maps the function being called (referenced by id) -> a stub that
    returns the desired value. Used to mock routers.integration.run_blocking
    so each `await run_blocking(executor, fn, *args)` returns the right value
    for that fn. Unknown functions (e.g. verify_api_key) return True by
    default — the rate_limit_inline call doesn't care about its return.
    """

    async def _run_blocking(executor, fn, *args, **kwargs):
        stub = routes.get(id(fn))
        if stub is None:
            return True  # verify_api_key-style: True means auth passes
        return stub(*args, **kwargs)

    return _run_blocking


class TestPersonaChatEndpoint:
    def setup_method(self):
        self.client = _build_test_app()
        # Default run_blocking — used by tests that don't override it.
        # Returns True so verify_api_key passes.
        self._run_blocking_patcher = patch("routers.integration.run_blocking", new=AsyncMock(return_value=True))
        self._run_blocking_patcher.start()

    def teardown_method(self):
        self._run_blocking_patcher.stop()

    def test_returns_401_without_authorization_header(self):
        resp = self.client.post(
            "/v2/integrations/app-1/user/persona-chat?uid=u-1",
            json={"text": "hi"},
        )
        assert resp.status_code == 401

    def test_returns_403_on_invalid_api_key(self):
        # verify_api_key returns False — run_blocking returns False -> 403
        with patch("routers.integration.run_blocking", new=AsyncMock(return_value=False)):
            resp = self.client.post(
                "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                json={"text": "hi"},
                headers={"Authorization": "Bearer bogus"},
            )
        assert resp.status_code == 403

    def test_returns_404_when_app_missing(self):
        # verify_api_key passes, apps_db.get_app_by_id_db returns None.
        # Route run_blocking by the id() of the function being called.
        with patch("routers.integration.apps_db") as mock_apps_db:
            mock_apps_db.get_app_by_id_db = MagicMock(return_value=None)
            stub_apps = mock_apps_db.get_app_by_id_db
            routes = {id(stub_apps): lambda *a, **k: stub_apps(*a, **k)}
            with patch(
                "routers.integration.run_blocking",
                new=_make_run_blocking_router(routes),
            ):
                resp = self.client.post(
                    "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                    json={"text": "hi"},
                    headers={"Authorization": "Bearer good"},
                )
        assert resp.status_code == 404

    def test_returns_403_when_app_not_enabled(self):
        with patch("routers.integration.apps_db") as mock_apps_db, patch(
            "routers.integration.redis_db"
        ) as mock_redis_db:
            mock_apps_db.get_app_by_id_db = MagicMock(return_value={"id": "app-1"})
            mock_redis_db.get_enabled_apps = MagicMock(return_value=[])
            stub_apps = mock_apps_db.get_app_by_id_db
            stub_redis = mock_redis_db.get_enabled_apps
            routes = {
                id(stub_apps): lambda *a, **k: stub_apps(*a, **k),
                id(stub_redis): lambda *a, **k: stub_redis(*a, **k),
            }
            with patch(
                "routers.integration.run_blocking",
                new=_make_run_blocking_router(routes),
            ):
                resp = self.client.post(
                    "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                    json={"text": "hi"},
                    headers={"Authorization": "Bearer good"},
                )
        assert resp.status_code == 403

    def test_returns_403_when_missing_persona_chat_capability(self):
        with patch("routers.integration.apps_db") as mock_apps_db, patch(
            "routers.integration.redis_db"
        ) as mock_redis_db, patch("routers.integration.apps_utils") as mock_apps_utils:
            mock_apps_db.get_app_by_id_db = MagicMock(return_value={"id": "app-1"})
            mock_redis_db.get_enabled_apps = MagicMock(return_value=["app-1"])
            mock_apps_utils.app_can_persona_chat = MagicMock(return_value=False)
            stub_apps = mock_apps_db.get_app_by_id_db
            stub_redis = mock_redis_db.get_enabled_apps
            routes = {
                id(stub_apps): lambda *a, **k: stub_apps(*a, **k),
                id(stub_redis): lambda *a, **k: stub_redis(*a, **k),
            }
            with patch(
                "routers.integration.run_blocking",
                new=_make_run_blocking_router(routes),
            ):
                resp = self.client.post(
                    "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                    json={"text": "hi"},
                    headers={"Authorization": "Bearer good"},
                )
        assert resp.status_code == 403

    def test_returns_streaming_response_on_success(self):
        async def fake_chat_stream(*args, **kwargs):
            yield "data: hello\n\n"
            yield "data: world\n\n"
            yield None

        with patch("routers.integration.apps_db") as mock_apps_db, patch(
            "routers.integration.redis_db"
        ) as mock_redis_db, patch("routers.integration.apps_utils") as mock_apps_utils, patch(
            "routers.integration.execute_chat_stream", side_effect=fake_chat_stream
        ):
            mock_apps_db.get_app_by_id_db = MagicMock(return_value={"id": "app-1"})
            mock_redis_db.get_enabled_apps = MagicMock(return_value=["app-1"])
            mock_apps_utils.app_can_persona_chat = MagicMock(return_value=True)
            stub_apps = mock_apps_db.get_app_by_id_db
            stub_redis = mock_redis_db.get_enabled_apps
            routes = {
                id(stub_apps): lambda *a, **k: stub_apps(*a, **k),
                id(stub_redis): lambda *a, **k: stub_redis(*a, **k),
            }
            with patch(
                "routers.integration.run_blocking",
                new=_make_run_blocking_router(routes),
            ):
                resp = self.client.post(
                    "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                    json={"text": "hi"},
                    headers={"Authorization": "Bearer good"},
                )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "hello" in body
        assert "world" in body
