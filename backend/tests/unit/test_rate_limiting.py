"""Unit tests for rate limiting config and logic."""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

# Stub heavy dependencies before importing our modules
for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'google.cloud',
    'google.cloud.firestore',
    'database.redis_db',
    'database.auth',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Stub redis
redis_mock = types.ModuleType('redis')
redis_mock.Redis = MagicMock
redis_mock.exceptions = types.ModuleType('redis.exceptions')


class _RedisError(Exception):
    pass


redis_mock.exceptions.RedisError = _RedisError
sys.modules['redis'] = redis_mock
sys.modules['redis.exceptions'] = redis_mock.exceptions

# Stub firebase_admin.auth
firebase_auth = sys.modules['firebase_admin.auth']
firebase_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# Stub database.redis_db with real check_rate_limit logic (Lua script mocked)
redis_db_stub = sys.modules['database.redis_db']
redis_db_stub._RATE_LIMIT_LUA = MagicMock(return_value=[1, 3600])
redis_db_stub.try_acquire_listen_lock = MagicMock(return_value=True)


def _check_rate_limit(key, policy, max_requests, window):
    """Real Python logic from redis_db.check_rate_limit, with mockable Lua."""
    redis_key = f'rl:{policy}:{key}'
    current, ttl = redis_db_stub._RATE_LIMIT_LUA(keys=[redis_key], args=[window])
    remaining = max(0, max_requests - current)
    allowed = current <= max_requests
    retry_after = max(0, ttl) if not allowed else 0
    return allowed, remaining, retry_after


redis_db_stub.check_rate_limit = _check_rate_limit

from utils.rate_limit_config import RATE_POLICIES, get_effective_limit, RATE_LIMIT_BOOST


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
            "dev:memories",
            "dev:memories_batch",
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
        with open(filepath) as f:
            for line in f:
                if re.search(pattern, line):
                    matches.append(line.strip())
        return matches

    def test_conversations_router_has_rate_limits(self):
        matches = self._grep_file("routers/conversations.py", r"with_rate_limit.*conversations:")
        # create, reprocess, search, merge = 4 endpoints
        self.assertEqual(len(matches), 4, f"conversations.py expected 4 rate limits, got {len(matches)}")

    def test_chat_router_has_rate_limits(self):
        matches = self._grep_file("routers/chat.py", r"with_rate_limit.*(?:chat:|voice:|file:)")
        # send_message, initial(x2), voice_message, voice_transcribe, file_upload(v1+v2) = 7
        self.assertEqual(len(matches), 7, f"chat.py expected 7 rate limits, got {len(matches)}")

    def test_legacy_file_upload_rate_limited(self):
        """Legacy v1/files must also be rate limited to prevent bypass."""
        matches = self._grep_file("routers/chat.py", r"with_rate_limit.*file:upload")
        self.assertEqual(len(matches), 2, f"chat.py expected 2 file:upload limits (v1+v2), got {len(matches)}")

    def test_developer_router_has_rate_limits(self):
        matches = self._grep_file("routers/developer.py", r"with_rate_limit.*dev:")
        # create_memory, batch, create_conversation, from_segments = 4
        self.assertEqual(len(matches), 4, f"developer.py expected 4 rate limits, got {len(matches)}")

    def test_goals_router_has_rate_limits(self):
        matches = self._grep_file("routers/goals.py", r"with_rate_limit.*goals:")
        # suggest, advice(x2), extract = 4
        self.assertEqual(len(matches), 4, f"goals.py expected 4 rate limits, got {len(matches)}")

    def test_mcp_sse_router_has_rate_limit(self):
        matches = self._grep_file("routers/mcp_sse.py", r"check_rate_limit_inline.*mcp:")
        self.assertGreaterEqual(len(matches), 1, "mcp_sse.py missing rate limit wiring")

    def test_mcp_router_has_rate_limit(self):
        matches = self._grep_file("routers/mcp.py", r"with_rate_limit.*memories:")
        self.assertGreaterEqual(len(matches), 1, "mcp.py missing rate limit wiring")

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
        # create, batch, delete, delete_all, modify(review), modify(edit), modify(visibility) = 7
        self.assertEqual(len(matches), 7, f"memories.py expected 7 rate limits, got {len(matches)}")

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

    def test_lua_script_has_ttl_self_heal(self):
        """Verify the registered Lua script contains TTL self-heal logic."""
        # register_script was called with the Lua source
        call_args = self.real_module.r.register_script.call_args
        lua_source = call_args[0][0]
        self.assertIn('TTL', lua_source)
        self.assertIn('ttl < 0', lua_source)
        self.assertIn('EXPIRE', lua_source)

    def test_lua_script_uses_incr(self):
        """Verify Lua uses INCR for atomic counter."""
        lua_source = self.real_module.r.register_script.call_args[0][0]
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
