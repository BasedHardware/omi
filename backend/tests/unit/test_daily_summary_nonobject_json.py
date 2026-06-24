"""
Unit tests for generate_comprehensive_daily_summary non-object JSON handling.

Bug: json.loads() succeeds on valid-but-non-object JSON (e.g. "[]" or "5"), then
summary_data.get(...) raises AttributeError. The handler only caught
json.JSONDecodeError, so the AttributeError escaped and 500'd the endpoint / crashed
the daily-summary cron.

Fix: guard with isinstance(summary_data, dict) (raising JSONDecodeError into the
existing fallback) and broaden the except to (json.JSONDecodeError, TypeError,
AttributeError) so a malformed LLM response degrades to the basic summary instead of
crashing.

These tests call the real generate_comprehensive_daily_summary directly, stubbing only
the heavy collaborator modules (database.*, utils.* siblings) via a meta-path finder.
Red without the fix (AttributeError), green with it.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_STUB = (
    "database",
    "utils",
    "firebase_admin",
    "google",
    "pinecone",
    "opuslib",
    "pydub",
    "redis",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "stripe",
    "openai",
    "anthropic",
    "modal",
    "ulid",
    "sentry_sdk",
    "requests",
    "typesense",
    "pusher",
    "httpx",
)

_TARGET = "utils.llm.external_integrations"
# Let the target module and its (empty) parent packages load from disk so the real loader
# can find the leaf module; heavy sibling modules under utils.* still get stubbed.
_KEEP_REAL = {"utils", "utils.llm", _TARGET}


def _is(n):
    if n in _KEEP_REAL:
        return False
    return any(n == p or n.startswith(p + ".") for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from utils.llm import external_integrations as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def _drive(llm_content: str):
    """Invoke generate_comprehensive_daily_summary with the LLM returning llm_content."""
    mod.users_db.get_user_profile = MagicMock(return_value={"time_zone": "UTC", "language": "en"})
    mod.get_prompt_memories = MagicMock(return_value=("TestUser", "mem"))
    mod.conversations_to_string = MagicMock(return_value="convo text")

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = llm_content
    mod.get_llm = MagicMock(return_value=fake_llm)

    return mod.generate_comprehensive_daily_summary("uid1", [], "2026-06-24")


class TestNonObjectJsonDegrades:
    """A non-object (but valid) JSON LLM response must degrade, not raise."""

    def test_top_level_list_returns_basic_summary(self):
        # Without the fix: AttributeError ('list' object has no attribute 'get').
        result = _drive("[]")
        assert isinstance(result, dict)
        assert result["headline"] == "Your Day in Review"
        # Basic-summary shape: stats populated, empty content lists.
        assert result["stats"]["total_conversations"] == 0
        assert result["highlights"] == []

    def test_top_level_scalar_returns_basic_summary(self):
        # Without the fix: AttributeError ('int' object has no attribute 'get').
        result = _drive("5")
        assert isinstance(result, dict)
        assert result["headline"] == "Your Day in Review"
        assert result["stats"]["total_conversations"] == 0

    def test_nonlist_subfield_returns_basic_summary(self):
        # 'highlights' is a dict, not a list: iterating yields keys (str), and
        # h.get(...) on a str raises AttributeError without the fix.
        result = _drive('{"highlights": {"conversation_numbers": 1}}')
        assert isinstance(result, dict)
        assert result["headline"] == "Your Day in Review"

    def test_valid_object_still_processed(self):
        # Regression guard: a proper object must NOT be forced into the fallback.
        result = _drive('{"headline": "Custom Headline", "highlights": []}')
        assert isinstance(result, dict)
        assert result["headline"] == "Custom Headline"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
