"""Unit tests for rate limiting config and logic."""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertGreaterEqual(len(RATE_POLICIES), 25)

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

    def test_shadow_mode_default_on(self):
        """Shadow mode defaults to ON (safe-first rollout)."""
        from utils.rate_limit_config import RATE_LIMIT_SHADOW

        self.assertIsInstance(RATE_LIMIT_SHADOW, bool)
        self.assertTrue(RATE_LIMIT_SHADOW)

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
        self.assertGreaterEqual(len(matches), 4, "conversations.py missing rate limit wiring")

    def test_chat_router_has_rate_limits(self):
        matches = self._grep_file("routers/chat.py", r"with_rate_limit.*chat:|voice:|file:")
        # send_message, initial(x2), voice_message, voice_transcribe, file_upload = 6
        self.assertGreaterEqual(len(matches), 5, "chat.py missing rate limit wiring")

    def test_developer_router_has_rate_limits(self):
        matches = self._grep_file("routers/developer.py", r"with_rate_limit.*dev:")
        # create_memory, batch, create_conversation, from_segments = 4
        self.assertGreaterEqual(len(matches), 4, "developer.py missing rate limit wiring")

    def test_goals_router_has_rate_limits(self):
        matches = self._grep_file("routers/goals.py", r"with_rate_limit.*goals:")
        # suggest, advice(x2), extract = 4
        self.assertGreaterEqual(len(matches), 3, "goals.py missing rate limit wiring")

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


if __name__ == '__main__':
    unittest.main()
