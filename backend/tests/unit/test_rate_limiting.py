"""Unit tests for rate limiting config and logic."""

import importlib
import os
import sys
import types
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from testing.import_isolation import stub_modules
from utils.rate_limit_config import RATE_LIMIT_BOOST, RATE_POLICIES, get_effective_limit


class _RedisError(Exception):
    pass


@pytest.fixture(scope="module", autouse=True)
def _rate_limit_stubs():
    """Install import-time fakes (redis, firebase_admin, database.redis_db, ...).

    ``database.redis_db`` constructs a ``redis.Redis(...)`` client at import time
    (a Tier-1 import-purity violation), and ``utils.other.endpoints`` transitively
    pulls ``firebase_admin`` + ``database.redis_db`` + ``database.users``. These
    fakes must be active *before* those modules are exec'd, so they live inside a
    ``stub_modules`` block (the sanctioned reserve seam — see
    ``backend/docs/test_isolation.md`` and DECISIONS D2). The stub ``check_rate_limit``
    reproduces the production boundary logic with a mockable Lua callable.
    """

    firebase_admin = ModuleType("firebase_admin")
    firebase_auth = ModuleType("firebase_admin.auth")
    firebase_auth.CertificateFetchError = type("CertificateFetchError", (Exception,), {})
    firebase_auth.ExpiredIdTokenError = type("ExpiredIdTokenError", (Exception,), {})
    firebase_auth.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})
    firebase_auth.RevokedIdTokenError = type("RevokedIdTokenError", (Exception,), {})

    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.FieldFilter = MagicMock()
    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.FieldFilter = MagicMock()

    redis_pkg = ModuleType("redis")
    redis_pkg.Redis = MagicMock
    redis_exceptions = ModuleType("redis.exceptions")
    redis_exceptions.RedisError = _RedisError
    redis_pkg.exceptions = redis_exceptions

    redis_db_stub = ModuleType("database.redis_db")
    redis_db_stub._RATE_LIMIT_LUA = MagicMock(return_value=[1, 3600])
    redis_db_stub.try_acquire_listen_lock = MagicMock(return_value=True)

    def _check_rate_limit(key, policy, max_requests, window):
        """Real Python logic from redis_db.check_rate_limit, with mockable Lua."""
        redis_key = f"rl:{policy}:{key}"
        current, ttl = redis_db_stub._RATE_LIMIT_LUA(keys=[redis_key], args=[window])
        remaining = max(0, max_requests - current)
        allowed = current <= max_requests
        retry_after = max(0, ttl) if not allowed else 0
        return allowed, remaining, retry_after

    redis_db_stub.check_rate_limit = _check_rate_limit

    database_auth = ModuleType("database.auth")
    database_users = ModuleType("database.users")
    database_users.record_user_platform = MagicMock()
    database_users.record_client_device = MagicMock()

    fakes = {
        "firebase_admin": firebase_admin,
        "firebase_admin.auth": firebase_auth,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "google.cloud.firestore_v1": fv1_stub,
        "redis": redis_pkg,
        "redis.exceptions": redis_exceptions,
        "database.redis_db": redis_db_stub,
        "database.auth": database_auth,
        "database.users": database_users,
    }
    with stub_modules(fakes):
        # ``utils.other.endpoints`` binds ``check_rate_limit`` / ``try_acquire_listen_lock``
        # at import, so it must (re-)exec against the fake ``database.redis_db``.
        for _cached in (
            "utils.other.endpoints",
            "utils.other",
        ):
            sys.modules.pop(_cached, None)
        import utils.other.endpoints  # noqa: F401  (re-exec'd against fakes above)

        yield


class TestRatePolicies(unittest.TestCase):
    """Validate rate limit policy definitions."""

    def test_all_policies_have_valid_structure(self):
        for name, (max_req, window) in RATE_POLICIES.items():
            self.assertIsInstance(max_req, int, f"{name}: max_requests must be int")
            self.assertIsInstance(window, int, f"{name}: window must be int")
            self.assertGreater(max_req, 0, f"{name}: max_requests must be > 0")
            self.assertGreater(window, 0, f"{name}: window must be > 0")

    def test_policy_count(self):
        """Ensure we have a reasonable number of policies."""
        self.assertGreaterEqual(len(RATE_POLICIES), 20)

    def test_expensive_endpoints_have_low_limits(self):
        """Expensive endpoints should have lower limits."""
        expensive = ['knowledge_graph:rebuild', 'wrapped:generate', 'conversations:reprocess']
        for name in expensive:
            max_req, _ = RATE_POLICIES[name]
            self.assertLessEqual(max_req, 5, f"{name} should have low base limit")

    def test_bursty_endpoints_have_high_limits(self):
        """Agent/MCP endpoints should allow bursts."""
        bursty = ['agent:execute_tool', 'mcp:sse']
        for name in bursty:
            max_req, _ = RATE_POLICIES[name]
            self.assertGreaterEqual(max_req, 100, f"{name} should allow bursts")


class TestBoostFactor(unittest.TestCase):
    """Test boost factor applies correctly."""

    def test_default_boost_is_1(self):
        self.assertEqual(RATE_LIMIT_BOOST, 1.0)

    def test_boost_multiplies_limit(self):
        max_req, window = get_effective_limit("chat:send_message", boost=2.0)
        base, _ = RATE_POLICIES["chat:send_message"]
        self.assertEqual(max_req, base * 2)

    def test_boost_below_1_tightens(self):
        max_req, window = get_effective_limit("chat:send_message", boost=0.5)
        base, _ = RATE_POLICIES["chat:send_message"]
        self.assertEqual(max_req, int(base * 0.5))

    def test_boost_never_goes_below_1(self):
        max_req, _ = get_effective_limit("conversations:reprocess", boost=0.01)
        self.assertGreaterEqual(max_req, 1)

    def test_boost_preserves_window(self):
        _, window = get_effective_limit("chat:send_message", boost=5.0)
        _, base_window = RATE_POLICIES["chat:send_message"]
        self.assertEqual(window, base_window)


class TestShadowMode(unittest.TestCase):
    """Test shadow mode env var parsing."""

    def test_shadow_mode_default_off(self):
        """Shadow mode defaults to OFF (enforcement active — set RATE_LIMIT_SHADOW_MODE=true for shadow)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RATE_LIMIT_SHADOW_MODE", None)
            import utils.rate_limit_config as rlc

            importlib.reload(rlc)
            self.assertIsInstance(rlc.RATE_LIMIT_SHADOW, bool)
            self.assertFalse(rlc.RATE_LIMIT_SHADOW)
        importlib.reload(rlc)

    def test_shadow_mode_env_true(self):
        with patch.dict(os.environ, {"RATE_LIMIT_SHADOW_MODE": "true"}):
            import utils.rate_limit_config as rlc

            importlib.reload(rlc)
            self.assertTrue(rlc.RATE_LIMIT_SHADOW)
        # Restore
        importlib.reload(rlc)

    def test_shadow_mode_env_false(self):
        with patch.dict(os.environ, {"RATE_LIMIT_SHADOW_MODE": "false"}):
            import utils.rate_limit_config as rlc

            importlib.reload(rlc)
            self.assertFalse(rlc.RATE_LIMIT_SHADOW)
        importlib.reload(rlc)


class TestGetEffectiveLimit(unittest.TestCase):
    """Test get_effective_limit edge cases."""

    def test_unknown_policy_raises(self):
        with self.assertRaises(KeyError):
            get_effective_limit("nonexistent:policy")

    def test_all_policies_return_valid_tuple(self):
        for name in RATE_POLICIES:
            max_req, window = get_effective_limit(name)
            self.assertIsInstance(max_req, int)
            self.assertIsInstance(window, int)
            self.assertGreater(max_req, 0)
            self.assertGreater(window, 0)


class TestEnforceRateLimit(unittest.TestCase):
    """Test runtime enforcement logic (429, shadow mode, fail-open)."""

    def setUp(self):
        # Import here after stubs are in place
        from utils.other import endpoints as ep_mod

        self.ep = ep_mod

    @patch('utils.other.endpoints.check_rate_limit', return_value=(True, 50, 0))
    def test_allowed_request_passes(self, mock_check):
        # Should not raise
        self.ep._enforce_rate_limit("uid123", "chat:send_message")
        mock_check.assert_called_once()

    @patch('utils.other.endpoints.check_rate_limit', return_value=(False, 0, 42))
    @patch('utils.other.endpoints.RATE_LIMIT_SHADOW', False)
    def test_blocked_request_raises_429(self, mock_check):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            self.ep._enforce_rate_limit("uid123", "chat:send_message")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("42", ctx.exception.detail)
        self.assertEqual(ctx.exception.headers["Retry-After"], "42")

    @patch('utils.other.endpoints.check_rate_limit', return_value=(False, 0, 42))
    @patch('utils.other.endpoints.RATE_LIMIT_SHADOW', True)
    def test_shadow_mode_logs_instead_of_blocking(self, mock_check):
        # Should not raise even though rate limit exceeded
        self.ep._enforce_rate_limit("uid123", "chat:send_message")

    @patch('utils.other.endpoints.check_rate_limit', side_effect=_RedisError("connection lost"))
    def test_fail_open_on_redis_error(self, mock_check):
        # Should not raise — fail open
        self.ep._enforce_rate_limit("uid123", "chat:send_message")


class TestCheckRateLimitBoundary(unittest.TestCase):
    """Test check_rate_limit() Python-side logic with mocked Lua script.

    The Lua script itself runs in Redis (integration scope); these tests
    verify the boundary logic that interprets Lua's [current, ttl] return.
    """

    def setUp(self):
        from database import redis_db as rdb

        self.rdb = rdb

    def _call(self, current, ttl, max_requests=10, window=3600):
        """Call check_rate_limit with mocked Lua return."""
        with patch.object(self.rdb, '_RATE_LIMIT_LUA', return_value=[current, ttl]):
            return self.rdb.check_rate_limit("uid1", "test:policy", max_requests, window)

    def test_under_limit_allowed(self):
        allowed, remaining, retry = self._call(current=5, ttl=3000, max_requests=10)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 5)
        self.assertEqual(retry, 0)

    def test_at_exact_limit_still_allowed(self):
        allowed, remaining, retry = self._call(current=10, ttl=2500, max_requests=10)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 0)
        self.assertEqual(retry, 0)

    def test_one_over_limit_blocked(self):
        allowed, remaining, retry = self._call(current=11, ttl=1800, max_requests=10)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertEqual(retry, 1800)

    def test_way_over_limit_blocked(self):
        allowed, remaining, retry = self._call(current=999, ttl=100, max_requests=10)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertEqual(retry, 100)

    def test_first_request_allowed(self):
        allowed, remaining, retry = self._call(current=1, ttl=3600, max_requests=10)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 9)
        self.assertEqual(retry, 0)

    def test_key_namespacing(self):
        """Verify Redis key includes policy and key."""
        with patch.object(self.rdb, '_RATE_LIMIT_LUA', return_value=[1, 3600]) as mock_lua:
            self.rdb.check_rate_limit("user42", "chat:send_message", 100, 3600)
            mock_lua.assert_called_once_with(keys=['rl:chat:send_message:user42'], args=[3600])


class TestWithRateLimitWrapper(unittest.TestCase):
    """Test with_rate_limit() wrapper behavior."""

    def setUp(self):
        from utils.other import endpoints as ep_mod

        self.ep = ep_mod

    def test_unknown_policy_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.ep.with_rate_limit(lambda: "uid", "nonexistent:policy")

    def test_valid_policy_returns_callable(self):
        result = self.ep.with_rate_limit(lambda: "uid", "chat:send_message")
        self.assertTrue(callable(result))

    @patch('utils.other.endpoints._enforce_rate_limit')
    def test_check_rate_limit_inline_calls_enforce(self, mock_enforce):
        self.ep.check_rate_limit_inline("app1:uid1", "integration:memories")
        mock_enforce.assert_called_once_with("app1:uid1", "integration:memories")

    def test_rate_limit_key_for_context_prefers_app_key_identity(self):
        context = types.SimpleNamespace(uid="uid1", app_id="app1", key_id="key1")

        self.assertEqual(self.ep.rate_limit_key_for_context(context), "app:app1:key:key1")

    def test_rate_limit_key_for_context_falls_back_to_uid(self):
        context = types.SimpleNamespace(uid="uid1")

        self.assertEqual(self.ep.rate_limit_key_for_context(context), "uid1")

    def test_rate_limit_key_for_context_falls_back_to_uid_when_api_key_identity_absent(self):
        context = types.SimpleNamespace(uid="uid1", app_id=None, key_id=None)

        self.assertEqual(self.ep.rate_limit_key_for_context(context), "uid1")

    def test_rate_limit_key_for_context_rejects_partial_api_key_identity(self):
        context = types.SimpleNamespace(uid="uid1", app_id="app1", key_id=None)

        with self.assertRaises(HTTPException) as ctx:
            self.ep.rate_limit_key_for_context(context)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('utils.other.endpoints._enforce_rate_limit')
    def test_with_rate_limit_dependency_calls_enforce_and_returns_uid(self, mock_enforce):
        """Execute the async dependency closure and verify it enforces + returns uid."""
        import asyncio

        dep_func = self.ep.with_rate_limit(lambda: "test_uid", "chat:send_message")
        # The inner dependency expects uid as a keyword arg (from Depends)
        result = asyncio.run(dep_func(uid="user123"))
        mock_enforce.assert_called_once_with("user123", "chat:send_message")
        self.assertEqual(result, "user123")

    @patch('utils.other.endpoints._enforce_rate_limit', side_effect=HTTPException(status_code=429, detail="blocked"))
    def test_with_rate_limit_dependency_propagates_429(self, mock_enforce):
        """Verify 429 from _enforce propagates through the dependency."""
        import asyncio

        dep_func = self.ep.with_rate_limit(lambda: "uid", "chat:send_message")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(dep_func(uid="user123"))
        self.assertEqual(ctx.exception.status_code, 429)

    @patch('utils.other.endpoints._enforce_rate_limit')
    def test_with_rate_limit_context_uses_app_key_identity(self, mock_enforce):
        import asyncio

        dep_func = self.ep.with_rate_limit_context(lambda: "unused", "dev:conversations_read")
        context = types.SimpleNamespace(uid="uid1", app_id="app1", key_id="key1")

        result = asyncio.run(dep_func(auth_context=context))

        mock_enforce.assert_called_once_with("app:app1:key:key1", "dev:conversations_read", fail_closed=True)
        self.assertIs(result, context)

    @patch('utils.other.endpoints._enforce_rate_limit')
    def test_check_api_key_rate_limit_uses_key_identity_and_fails_closed(self, mock_enforce):
        self.ep.check_api_key_rate_limit(
            prefix="dev",
            uid="uid1",
            app_id="app1",
            key_id="key1",
            policy_name="dev:conversations_read",
        )

        mock_enforce.assert_called_once_with("dev:uid1:app1:key1", "dev:conversations_read", fail_closed=True)

    def test_check_api_key_rate_limit_rejects_missing_key_id(self):
        with self.assertRaises(HTTPException) as ctx:
            self.ep.check_api_key_rate_limit(
                prefix="dev",
                uid="uid1",
                app_id="app1",
                key_id=None,
                policy_name="dev:conversations_read",
            )
        self.assertEqual(ctx.exception.status_code, 403)


class TestBoostEnvVar(unittest.TestCase):
    """Test RATE_LIMIT_BOOST env var is picked up at import time."""

    def test_boost_env_var_applied(self):
        with patch.dict(os.environ, {"RATE_LIMIT_BOOST": "3.0"}):
            import utils.rate_limit_config as rlc

            importlib.reload(rlc)
            self.assertEqual(rlc.RATE_LIMIT_BOOST, 3.0)
            max_req, _ = rlc.get_effective_limit("chat:send_message")
            base, _ = rlc.RATE_POLICIES["chat:send_message"]
            self.assertEqual(max_req, int(base * 3.0))
        importlib.reload(rlc)


class TestRouterPolicyMapping(unittest.TestCase):
    """Verify all policies referenced in routers exist in config."""

    def test_all_router_policies_exist(self):
        """Every policy name used in routers must exist in RATE_POLICIES."""
        # These are all the policy names referenced in router files
        used_policies = [
            "conversations:create",
            "conversations:reprocess",
            "conversations:search",
            "conversations:merge",
            "chat:send_message",
            "chat:initial",
            "voice:message",
            "voice:transcribe",
            "file:upload",
            "agent:execute_tool",
            "mcp:sse",
            "memories:create",
            "memories:modify",
            "memories:delete",
            "memories:delete_all",
            "memories:batch",
            "goals:suggest",
            "goals:advice",
            "goals:extract",
            "dev:conversations",
            "dev:conversations_read",
            "dev:conversation_detail_read",
            "dev:conversation_transcript_read",
            "dev:action_items_read",
            "dev:action_items_write",
            "dev:goals_read",
            "dev:goals_write",
            "dev:memories",
            "dev:memories_read",
            "dev:memories_batch",
            "mcp:read",
            "mcp:memories_read",
            "mcp:memories_write",
            "knowledge_graph:rebuild",
            "wrapped:generate",
            "integration:conversations",
            "integration:memories",
            "test:prompt",
            "apps:generate_prompts",
        ]
        for policy in used_policies:
            self.assertIn(policy, RATE_POLICIES, f"Policy '{policy}' used in router but missing from config")


class TestRouterWiring(unittest.TestCase):
    """Verify rate limit wiring in actual router source files.

    Grep router source code for with_rate_limit / check_rate_limit_inline
    references to ensure wiring isn't accidentally removed.
    """

    def _grep_file(self, filepath: str, pattern: str) -> list[str]:
        """Return lines matching pattern in file."""
        import re

        matches = []
        with open(filepath, encoding='utf-8') as f:
            for line in f:
                if re.search(pattern, line):
                    matches.append(line.strip())
        return matches

    def test_conversations_router_has_rate_limits(self):
        matches = self._grep_file("routers/conversations.py", r"with_rate_limit.*conversations:")
        # create, reprocess, search, merge, and events = 5 endpoints
        self.assertEqual(len(matches), 5, f"conversations.py expected 5 rate limits, got {len(matches)}")

    def test_chat_router_has_rate_limits(self):
        matches = self._grep_file("routers/chat.py", r"with_rate_limit.*(?:chat:|voice:|file:)")
        # send_message, initial(x2), voice_message, voice_transcribe, file_upload(v1+v2) = 7
        self.assertEqual(len(matches), 7, f"chat.py expected 7 rate limits, got {len(matches)}")

    def test_legacy_file_upload_rate_limited(self):
        """Legacy v1/files must also be rate limited to prevent bypass."""
        matches = self._grep_file("routers/chat.py", r"with_rate_limit.*file:upload")
        self.assertEqual(len(matches), 2, f"chat.py expected 2 file:upload limits (v1+v2), got {len(matches)}")

    def test_developer_dependencies_have_rate_limits(self):
        source = open("dependencies.py", encoding='utf-8').read()
        matches = [line for line in source.splitlines() if "policy_name=\"dev:" in line]
        self.assertGreaterEqual(
            len(matches), 8, f"dependencies.py expected broad dev API rate limits, got {len(matches)}"
        )

    def test_developer_dependencies_have_read_rate_limits(self):
        source = open("dependencies.py", encoding='utf-8').read()
        for policy in [
            "dev:memories_read",
            "dev:action_items_read",
            "dev:conversations_read",
            "dev:conversation_detail_read",
            "dev:conversation_transcript_read",
            "dev:goals_read",
        ]:
            self.assertIn(policy, source)

    def test_developer_conversation_reads_split_detail_and_transcript_policies(self):
        dependencies_source = open("dependencies.py", encoding='utf-8').read()
        developer_source = open("routers/developer.py", encoding='utf-8').read()

        self.assertIn('policy_name="dev:conversation_detail_read"', dependencies_source)
        self.assertIn('policy_name="dev:conversation_transcript_read"', dependencies_source)
        self.assertIn("get_auth_with_conversations_read", developer_source)
        self.assertIn("get_auth_with_conversation_detail_read", developer_source)
        self.assertIn("check_conversation_transcript_read_limit(auth, request=request)", developer_source)

    def test_developer_conversation_reads_emit_sanitized_audit_logs(self):
        developer_source = open("routers/developer.py", encoding='utf-8').read()
        dependencies_source = open("dependencies.py", encoding='utf-8').read()

        self.assertIn("developer_api_read operation=%s", developer_source)
        self.assertIn("developer_api_rate_limit_failure policy=%s", dependencies_source)
        self.assertIn("auth.app_id or 'unknown_app'", developer_source)
        self.assertIn("auth.key_id or 'unknown_key'", developer_source)
        self.assertIn("sanitize(request.headers.get('user-agent'))", developer_source)
        self.assertNotIn("request.headers.get('Authorization'", developer_source)
        self.assertNotIn('request.headers.get("Authorization"', developer_source)
        self.assertNotIn("request.headers.get('Authorization'", dependencies_source)
        self.assertNotIn('request.headers.get("Authorization"', dependencies_source)

    def test_developer_rate_limit_failures_log_without_request(self):
        dependencies = importlib.import_module("dependencies")
        auth = dependencies.ApiKeyAuth(
            uid="uid1",
            scopes=["conversations:read"],
            app_id="test-app",
            key_id="test-key",
        )

        with patch.object(
            dependencies,
            "check_api_key_rate_limit",
            side_effect=HTTPException(status_code=429, detail="Rate limit exceeded"),
        ):
            with self.assertLogs("dependencies", level="WARNING") as logs:
                with self.assertRaises(HTTPException):
                    dependencies.check_conversation_transcript_read_limit(auth)

        log_output = "\n".join(logs.output)
        self.assertIn("developer_api_rate_limit_failure policy=dev:conversation_transcript_read", log_output)
        self.assertIn("path=unknown_path", log_output)
        self.assertIn("uid=uid1", log_output)
        self.assertIn("app_id=test-app", log_output)
        self.assertIn("key_id=test-key", log_output)
        self.assertNotIn("Authorization", log_output)

    def test_goals_router_has_rate_limits(self):
        matches = self._grep_file("routers/goals.py", r"with_rate_limit.*goals:")
        # suggest, advice(x2), extract = 4
        self.assertEqual(len(matches), 4, f"goals.py expected 4 rate limits, got {len(matches)}")

    def test_mcp_sse_router_has_rate_limit(self):
        matches = self._grep_file("routers/mcp_sse.py", r"check_rate_limit_inline.*mcp:")
        self.assertGreaterEqual(len(matches), 1, "mcp_sse.py missing rate limit wiring")

    def test_mcp_router_has_rate_limit(self):
        source = open("dependencies.py", encoding='utf-8').read()
        self.assertIn("mcp:read", source, "MCP API-key UID dependency missing read rate limit")
        self.assertIn("mcp:memories_read", source, "MCP memory auth dependency missing memory read rate limit")
        self.assertIn("mcp:memories_write", source, "MCP memory auth dependency missing memory write rate limit")

    def test_sensitive_read_page_caps(self):
        developer_source = open("routers/developer.py", encoding='utf-8').read()
        mcp_source = open("routers/mcp.py", encoding='utf-8').read()
        self.assertIn("min(limit, 25 if include_transcript else 100)", developer_source)
        self.assertIn("min(limit, 200)", mcp_source)

    def test_integration_router_has_rate_limits(self):
        matches = self._grep_file("routers/integration.py", r"check_rate_limit_inline.*integration:")
        # conversations + memories = 2
        self.assertGreaterEqual(len(matches), 2, "integration.py missing rate limit wiring")

    def test_apps_router_has_rate_limit(self):
        matches = self._grep_file("routers/apps.py", r"with_rate_limit.*apps:")
        self.assertGreaterEqual(len(matches), 1, "apps.py missing rate limit wiring")

    def test_knowledge_graph_router_has_rate_limit(self):
        matches = self._grep_file("routers/knowledge_graph.py", r"with_rate_limit.*knowledge_graph:")
        self.assertGreaterEqual(len(matches), 1, "knowledge_graph.py missing rate limit wiring")

    def test_wrapped_router_has_rate_limit(self):
        matches = self._grep_file("routers/wrapped.py", r"with_rate_limit.*wrapped:")
        self.assertGreaterEqual(len(matches), 1, "wrapped.py missing rate limit wiring")

    def test_test_prompt_wired(self):
        matches = self._grep_file("routers/conversations.py", r'with_rate_limit.*test:prompt')
        self.assertGreaterEqual(len(matches), 1, "test-prompt endpoint missing rate limit")

    def test_agent_tools_wired(self):
        matches = self._grep_file("routers/agent_tools.py", r"with_rate_limit.*agent:")
        self.assertGreaterEqual(len(matches), 1, "agent_tools.py missing rate limit wiring")

    def test_memories_router_has_rate_limits(self):
        matches = self._grep_file("routers/memories.py", r"with_rate_limit.*memories:")
        # create, batch, 3 review (list/get/resolve), delete, delete_all, 3 modify endpoints = 10
        self.assertEqual(len(matches), 10, f"memories.py expected 10 rate limits, got {len(matches)}")

    def test_memories_create_endpoint_rate_limited(self):
        matches = self._grep_file("routers/memories.py", r"with_rate_limit.*memories:create")
        self.assertEqual(len(matches), 1, "POST /v3/memories must have memories:create rate limit")

    def test_memories_delete_all_endpoint_rate_limited(self):
        matches = self._grep_file("routers/memories.py", r"with_rate_limit.*memories:delete_all")
        self.assertEqual(len(matches), 1, "DELETE /v3/memories must have memories:delete_all rate limit")


class TestRealCheckRateLimit(unittest.TestCase):
    """Load the real check_rate_limit from redis_db.py via importlib.

    This ensures the production function (not the test stub) is exercised,
    catching regressions in key format, return-value mapping, and Lua args.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util

        # Mock Redis client with a fake register_script
        mock_redis_client = MagicMock()
        mock_lua_callable = MagicMock(return_value=[1, 3600])
        mock_redis_client.register_script.return_value = mock_lua_callable

        # Patch redis.Redis to return our mock
        original_redis = sys.modules.get('redis')
        fake_redis = types.ModuleType('redis')
        fake_redis.Redis = MagicMock(return_value=mock_redis_client)
        fake_redis.exceptions = types.ModuleType('redis.exceptions')
        fake_redis.exceptions.RedisError = type('RedisError', (Exception,), {})
        sys.modules['redis'] = fake_redis
        sys.modules['redis.exceptions'] = fake_redis.exceptions

        # Load redis_db.py directly (bypasses package init chain)
        spec = importlib.util.spec_from_file_location('redis_db_real', 'database/redis_db.py')
        cls.real_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.real_module)

        # Restore original redis stub
        if original_redis:
            sys.modules['redis'] = original_redis

        cls.mock_lua = mock_lua_callable
        cls.lua_sources = [
            call.args[0] if call.args else call.kwargs.get('script', '')
            for call in mock_redis_client.register_script.call_args_list
        ]

    @classmethod
    def _rate_limit_lua_source(cls):
        # Matches by content rather than call order. These anchors are present in
        # database/redis_db.py _RATE_LIMIT_LUA; update them if those Lua variables change.
        for lua_source in cls.lua_sources:
            if 'local key = KEYS[1]' in lua_source and 'return {current, ttl}' in lua_source:
                return lua_source
        raise AssertionError('rate limit Lua script was not registered')

    def test_lua_script_has_ttl_self_heal(self):
        """Verify the registered Lua script contains TTL self-heal logic."""
        lua_source = self._rate_limit_lua_source()
        self.assertIn('TTL', lua_source)
        self.assertIn('ttl < 0', lua_source)
        self.assertIn('EXPIRE', lua_source)

    def test_lua_script_uses_incr(self):
        """Verify Lua uses INCR for atomic counter."""
        lua_source = self._rate_limit_lua_source()
        self.assertIn('INCR', lua_source)

    def test_real_check_rate_limit_key_format(self):
        """Verify production key format is rl:{policy}:{key}."""
        self.mock_lua.reset_mock()
        self.mock_lua.return_value = [5, 3000]
        self.real_module.check_rate_limit("user42", "chat:send_message", 100, 3600)
        self.mock_lua.assert_called_once_with(keys=['rl:chat:send_message:user42'], args=[3600])

    def test_real_check_rate_limit_under_limit(self):
        """Verify real function correctly interprets under-limit response."""
        self.mock_lua.return_value = [5, 3000]
        allowed, remaining, retry = self.real_module.check_rate_limit("uid1", "test:policy", 10, 3600)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 5)
        self.assertEqual(retry, 0)

    def test_real_check_rate_limit_over_limit(self):
        """Verify real function correctly interprets over-limit response."""
        self.mock_lua.return_value = [11, 1800]
        allowed, remaining, retry = self.real_module.check_rate_limit("uid1", "test:policy", 10, 3600)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertEqual(retry, 1800)

    def test_real_lua_args_only_window(self):
        """Verify Lua receives only window (not max_requests) in args."""
        self.mock_lua.reset_mock()
        self.mock_lua.return_value = [1, 3600]
        self.real_module.check_rate_limit("uid1", "p", 999, 7200)
        _, kwargs = self.mock_lua.call_args
        self.assertEqual(kwargs['args'], [7200], "Lua should only receive window, not max_requests")


if __name__ == '__main__':
    unittest.main()
