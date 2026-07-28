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


import testing.persona_chat_endpoint_stubs  # noqa: F401 -- sanctioned session-level stubs (backend/testing/ is exempt from the module-isolation gate)
import utils.apps as apps_utils  # noqa: E402

# Now safe to import the module under test
from utils.apps import app_can_persona_chat  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Pure capability check
# ---------------------------------------------------------------------------
class TestAppCanPersonaChat:
    def test_returns_true_when_capability_declared(self):
        app = {"capabilities": {"persona_chat"}}
        assert app_can_persona_chat(app) is True

    def test_returns_false_when_capability_absent(self):
        app = {"capabilities": set()}
        assert app_can_persona_chat(app) is False

    def test_returns_false_when_capabilities_missing(self):
        app = {}
        assert app_can_persona_chat(app) is False

    def test_returns_false_when_other_capability_declared(self):
        app = {"capabilities": {"chat"}}
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

    def test_rejects_oversized_previous_messages(self):
        """P2 from cubic AI review: Pydantic should reject more than 20
        previous_messages entries at parse time, not after reading the
        full body into memory."""
        from pydantic import ValidationError

        from models.integrations import PersonaChatRequest

        big = [{'role': 'human', 'text': f'msg-{i}'} for i in range(50)]
        with pytest.raises(ValidationError):
            PersonaChatRequest(text='hello', previous_messages=big)

    def test_caps_previous_message_text_length(self):
        """P2 from cubic AI review: Pydantic should truncate an
        oversized turn.text to 8192 chars (matching the server-side cap)
        rather than reject the whole request. Clients occasionally send
        a single huge turn and we don't want them to hard-fail."""
        from models.integrations import PersonaChatRequest

        huge_text = 'x' * 100_000
        req = PersonaChatRequest(
            text='hello',
            previous_messages=[{'role': 'human', 'text': huge_text}],
        )
        assert len(req.previous_messages[0]['text']) == 8192

    def test_rejects_oversized_context(self):
        """P2 from cubic AI review: Pydantic should reject a context
        dict with more than the recognized 5 keys (sender_name /
        sender_username / chat_type / platform / 1 spare)."""
        from pydantic import ValidationError

        from models.integrations import PersonaChatRequest

        too_many_keys = {f'k{i}': 'v' for i in range(10)}
        with pytest.raises(ValidationError):
            PersonaChatRequest(text='hello', context=too_many_keys)


# ---------------------------------------------------------------------------
# 3. Endpoint behavior
# ---------------------------------------------------------------------------


def _valid_app_dict(app_id="app-1", *, with_persona_chat_capability=True):
    """Minimal valid App dict that the Pydantic App model will accept."""
    return {
        "id": app_id,
        "name": "Test App",
        "category": "test",
        "author": "tester",
        "description": "Test",
        "image": "https://example.com/img.png",
        "capabilities": ({"persona", "persona_chat"} if with_persona_chat_capability else set()),
        "external_integration": {"actions": []},
    }


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
        # verify_api_key_for_uid returns False — run_blocking returns False -> 403
        with patch("routers.integration.run_blocking", new=AsyncMock(return_value=False)):
            resp = self.client.post(
                "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                json={"text": "hi"},
                headers={"Authorization": "Bearer bogus"},
            )
        assert resp.status_code == 403

    def test_returns_403_when_key_uid_mismatches(self):
        """Caller holds a valid app key but it's bound to a different uid —
        they can't impersonate someone else's persona."""
        from utils.apps import verify_api_key_for_uid

        async def _route(executor, fn, *args, **kwargs):
            if fn is verify_api_key_for_uid:
                return False  # key is bound to u-other, not u-1
            return True

        with patch("routers.integration.run_blocking", new=_route):
            resp = self.client.post(
                "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                json={"text": "hi"},
                headers={"Authorization": "Bearer good"},
            )
        assert resp.status_code == 403

    def test_auth_uses_strict_verify_not_loose(self):
        """Endpoint must call verify_api_key_for_uid (strict), never the loose
        verify_api_key (which would re-introduce the auth bypass the maintainer
        review flagged).
        """
        from utils.apps import verify_api_key, verify_api_key_for_uid

        called = {"strict": 0, "loose": 0}

        async def _route(executor, fn, *args, **kwargs):
            if fn is verify_api_key_for_uid:
                called["strict"] += 1
                return False
            if fn is verify_api_key:
                called["loose"] += 1
                return False
            return True

        with patch("routers.integration.run_blocking", new=_route):
            # Send an invalid auth so we exit early at the strict check; we
            # only care that the strict function got called (not loose).
            resp = self.client.post(
                "/v2/integrations/app-1/user/persona-chat?uid=u-1",
                json={"text": "hi"},
                headers={"Authorization": "Bearer x"},
            )
        # Both might be checked in cascade; we only assert strict was called
        # AT LEAST once and loose was NEVER called.
        assert called["strict"] >= 1
        assert called["loose"] == 0, (
            "endpoint called the loose verify_api_key on the persona-chat "
            "path — that re-introduces the impersonation bypass"
        )

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
            mock_apps_db.get_app_by_id_db = MagicMock(return_value=_valid_app_dict())
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
            mock_apps_db.get_app_by_id_db = MagicMock(return_value=_valid_app_dict())
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
            mock_apps_db.get_app_by_id_db = MagicMock(return_value=_valid_app_dict())
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
