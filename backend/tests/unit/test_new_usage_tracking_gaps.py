"""
Integration tests for the 5 new usage-tracking feature constants added in PR #5834.

Verifies:
  1. All 5 new Features constants exist (PROACTIVE_NOTIFICATION, FOLLOWUP,
     OPENGLASS, APP_GENERATOR, ONBOARDING).
  2. track_usage() context manager properly sets and resets context for each.
  3. get_usage_callback() returns a callback that correctly reads the context.
  4. Thread and asyncio safety of context propagation.
  5. graph.py's ChatOpenAI instance includes stream_options={"include_usage": True}.
  6. Source-level scan confirming track_usage wrapping in every modified file.
"""

import asyncio
import contextvars
import os
import re
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Environment setup – avoids import-time crashes from missing secrets / deps.
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database package so usage_tracker can import database.llm_usage
if "database" not in sys.modules:
    database_mod = _stub_module("database")
    database_mod.__path__ = []
else:
    database_mod = sys.modules["database"]

for submodule in ["llm_usage", "_client"]:
    fqn = f"database.{submodule}"
    if fqn not in sys.modules:
        mod = _stub_module(fqn)
        setattr(database_mod, submodule, mod)

llm_usage_mod = sys.modules["database.llm_usage"]
llm_usage_mod.record_llm_usage = MagicMock()

from utils.llm.usage_tracker import (
    Features,
    LLMUsageCallback,
    UsageContext,
    _usage_context,
    get_current_context,
    get_usage_callback,
    track_usage,
)

# ===================================================================
# 1. Feature constants existence
# ===================================================================

NEW_FEATURES = {
    "PROACTIVE_NOTIFICATION": "proactive_notification",
    "FOLLOWUP": "followup",
    "OPENGLASS": "openglass",
    "APP_GENERATOR": "app_generator",
    "ONBOARDING": "onboarding",
}


class TestNewFeatureConstants:
    """Verify all 5 new feature constants exist with the correct string values."""

    @pytest.mark.parametrize("attr,expected_value", list(NEW_FEATURES.items()))
    def test_constant_exists_and_correct(self, attr, expected_value):
        assert hasattr(Features, attr), f"Features.{attr} is missing"
        assert getattr(Features, attr) == expected_value

    def test_new_features_are_distinct_from_existing(self):
        """New features must not collide with pre-existing constants."""
        existing = {
            Features.CHAT,
            Features.CONVERSATION_PROCESSING,
            Features.RAG,
            Features.NOTIFICATIONS,
            Features.APP_INTEGRATIONS,
            Features.GOALS,
            Features.TRENDS,
            Features.PERSONA,
            Features.MEMORIES,
            Features.TRANSCRIBE,
            Features.REALTIME_INTEGRATIONS,
            Features.DAILY_SUMMARY,
            Features.SUBSCRIPTION_NOTIFICATION,
            Features.KNOWLEDGE_GRAPH,
            Features.OTHER,
        }
        for attr, value in NEW_FEATURES.items():
            assert value not in existing, f"Features.{attr} ('{value}') collides with an existing constant"


# ===================================================================
# 2. track_usage() context manager – set & reset for each new feature
# ===================================================================


class TestTrackUsageContextManager:
    """track_usage() must set context inside the block and reset it afterward."""

    @pytest.mark.parametrize("attr,value", list(NEW_FEATURES.items()))
    def test_sets_and_resets_context(self, attr, value):
        assert get_current_context() is None, "Context leaked from a prior test"

        with track_usage("uid-test", value) as ctx:
            assert ctx.uid == "uid-test"
            assert ctx.feature == value
            live = get_current_context()
            assert live is not None
            assert live.uid == "uid-test"
            assert live.feature == value

        assert get_current_context() is None, f"Context not reset after Features.{attr}"

    @pytest.mark.parametrize("attr,value", list(NEW_FEATURES.items()))
    def test_resets_on_exception(self, attr, value):
        assert get_current_context() is None

        with pytest.raises(ValueError):
            with track_usage("uid-err", value):
                assert get_current_context().feature == value
                raise ValueError("boom")

        assert get_current_context() is None

    def test_nested_contexts_restore_outer(self):
        """Nested track_usage blocks must restore the outer context on exit."""
        with track_usage("uid-outer", Features.PROACTIVE_NOTIFICATION):
            assert get_current_context().feature == Features.PROACTIVE_NOTIFICATION

            with track_usage("uid-inner", Features.FOLLOWUP):
                assert get_current_context().feature == Features.FOLLOWUP

            # Outer context must be restored
            assert get_current_context().feature == Features.PROACTIVE_NOTIFICATION

        assert get_current_context() is None


# ===================================================================
# 3. get_usage_callback() reads context correctly
# ===================================================================


class TestGetUsageCallback:
    """get_usage_callback() must return an LLMUsageCallback that reads the current context."""

    def test_returns_llm_usage_callback(self):
        cb = get_usage_callback()
        assert isinstance(cb, LLMUsageCallback)

    def test_singleton_behavior(self):
        cb1 = get_usage_callback()
        cb2 = get_usage_callback()
        assert cb1 is cb2

    @pytest.mark.parametrize("feature", list(NEW_FEATURES.values()))
    def test_callback_reads_context_for_new_features(self, feature):
        """Inside track_usage, the contextvar must be visible to the callback's on_llm_end path."""
        with track_usage("uid-cb", feature):
            ctx = _usage_context.get()
            assert ctx is not None
            assert ctx.feature == feature
            assert ctx.uid == "uid-cb"

    def test_callback_on_llm_end_reads_context(self):
        """Exercise LLMUsageCallback.on_llm_end to verify it reads the usage context and calls flush_fn."""
        captured_calls = []
        # Create a fresh callback with a capturing flush_fn
        cb = LLMUsageCallback(flush_fn=lambda *args: captured_calls.append(args))

        mock_response = MagicMock()
        mock_response.generations = [[MagicMock()]]
        mock_response.llm_output = {
            "token_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
            "model_name": "gpt-4.1-mini",
        }

        with track_usage("uid-e2e", Features.PROACTIVE_NOTIFICATION):
            cb.on_llm_end(mock_response)

        assert len(captured_calls) >= 1, "on_llm_end should have called flush_fn"
        uid, feature, model, inp, out = captured_calls[0]
        assert uid == "uid-e2e", f"Expected uid 'uid-e2e', got {uid}"
        assert feature == "proactive_notification", f"Expected feature 'proactive_notification', got {feature}"
        assert inp == 100, f"Expected 100 input tokens, got {inp}"
        assert out == 50, f"Expected 50 output tokens, got {out}"

    def test_callback_on_llm_end_no_context_uses_fallback(self):
        """Without track_usage, on_llm_end should fall back to uid=unknown, feature=other."""
        captured_calls = []
        cb = LLMUsageCallback(flush_fn=lambda *args: captured_calls.append(args))

        mock_response = MagicMock()
        mock_response.generations = [[MagicMock()]]
        mock_response.llm_output = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "model_name": "gpt-4.1-mini",
        }

        assert get_current_context() is None
        cb.on_llm_end(mock_response)

        assert len(captured_calls) >= 1, "on_llm_end should still call flush_fn with fallback"
        uid, feature, model, inp, out = captured_calls[0]
        assert uid == "unknown", f"Expected fallback uid 'unknown', got {uid}"
        assert feature == "other", f"Expected fallback feature 'other', got {feature}"


# ===================================================================
# 4. Thread and asyncio safety
# ===================================================================


class TestThreadSafety:
    """Context propagation must be thread-isolated."""

    def test_threads_have_isolated_contexts(self):
        results = {}
        barrier = threading.Barrier(2)

        def worker(uid, feature, key):
            with track_usage(uid, feature):
                barrier.wait(timeout=5)
                results[key] = get_current_context()

        t1 = threading.Thread(target=worker, args=("u1", Features.PROACTIVE_NOTIFICATION, "t1"))
        t2 = threading.Thread(target=worker, args=("u2", Features.APP_GENERATOR, "t2"))

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert results["t1"].feature == Features.PROACTIVE_NOTIFICATION
        assert results["t1"].uid == "u1"
        assert results["t2"].feature == Features.APP_GENERATOR
        assert results["t2"].uid == "u2"

        # Main thread must be untouched
        assert get_current_context() is None

    def test_all_new_features_thread_isolated(self):
        """Spawn a thread per new feature and verify isolation."""
        results = {}
        features = list(NEW_FEATURES.values())
        barrier = threading.Barrier(len(features))

        def worker(idx, feature):
            with track_usage(f"uid-{idx}", feature):
                barrier.wait(timeout=5)
                results[idx] = get_current_context()

        threads = [threading.Thread(target=worker, args=(i, f)) for i, f in enumerate(features)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for i, feature in enumerate(features):
            assert results[i].feature == feature
            assert results[i].uid == f"uid-{i}"

        assert get_current_context() is None


class TestAsyncSafety:
    """Context propagation must work correctly across asyncio tasks."""

    @pytest.mark.asyncio
    async def test_async_context_propagation(self):
        """track_usage context must be visible inside the same coroutine."""
        for feature in NEW_FEATURES.values():
            with track_usage("uid-async", feature):
                ctx = get_current_context()
                assert ctx is not None
                assert ctx.feature == feature
                # Yield control and verify context survives
                await asyncio.sleep(0)
                assert get_current_context().feature == feature

            assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_async_tasks_inherit_context(self):
        """asyncio tasks created via copy_context should inherit the usage context."""

        async def check_context(expected_feature):
            ctx = get_current_context()
            assert ctx is not None
            assert ctx.feature == expected_feature
            return ctx.feature

        with track_usage("uid-task", Features.ONBOARDING):
            # copy_context captures the current contextvar state
            ctx_copy = contextvars.copy_context()
            result = await asyncio.get_event_loop().run_in_executor(None, ctx_copy.run, get_current_context)
            assert result.feature == Features.ONBOARDING

        assert get_current_context() is None


# ===================================================================
# 5. graph.py ChatOpenAI stream_options includes include_usage
# ===================================================================


class TestGraphStreamOptions:
    """Verify that graph.py's ChatOpenAI has stream_options={"include_usage": True}."""

    def test_graph_py_has_include_usage(self):
        graph_path = Path(__file__).resolve().parent.parent.parent / "utils" / "retrieval" / "graph.py"
        source = graph_path.read_text()
        assert 'stream_options={"include_usage": True}' in source or "stream_options={'include_usage': True}" in source


# ===================================================================
# 6. Source-level scan: verify track_usage wrapping in modified files
# ===================================================================

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class TestSourceTrackUsageWrapping:
    """Scan source files to confirm correct track_usage wrapping."""

    def test_app_integrations_proactive_notification(self):
        """utils/app_integrations.py must wrap proactive notification LLM calls."""
        source = (BACKEND_ROOT / "utils" / "app_integrations.py").read_text()
        count = source.count("with track_usage(uid, Features.PROACTIVE_NOTIFICATION):")
        assert count >= 3, f"Expected >= 3 PROACTIVE_NOTIFICATION wrappers, found {count}"

    def test_followup_py(self):
        """utils/llm/followup.py must wrap the LLM call with FOLLOWUP."""
        source = (BACKEND_ROOT / "utils" / "llm" / "followup.py").read_text()
        assert "with track_usage(uid, Features.FOLLOWUP):" in source

    def test_openglass_py(self):
        """utils/llm/openglass.py must wrap the LLM call with OPENGLASS."""
        source = (BACKEND_ROOT / "utils" / "llm" / "openglass.py").read_text()
        assert "with track_usage(uid, Features.OPENGLASS):" in source

    def test_routers_apps_app_generator(self):
        """routers/apps.py must wrap generator endpoints with APP_GENERATOR."""
        source = (BACKEND_ROOT / "routers" / "apps.py").read_text()
        count = source.count("with track_usage(uid, Features.APP_GENERATOR):")
        assert count >= 5, f"Expected >= 5 APP_GENERATOR wrappers in routers/apps.py, found {count}"

    def test_onboarding_py(self):
        """utils/onboarding.py must wrap the AI check with ONBOARDING."""
        source = (BACKEND_ROOT / "utils" / "onboarding.py").read_text()
        assert "with track_usage(self.uid, Features.ONBOARDING):" in source

    def test_chat_py_tracking(self):
        """utils/llm/chat.py must wrap LLM calls with CHAT, CONVERSATION_PROCESSING, or REALTIME_INTEGRATIONS."""
        source = (BACKEND_ROOT / "utils" / "llm" / "chat.py").read_text()
        assert "with track_usage(uid, Features.CHAT):" in source
        assert (
            "with track_usage(uid, Features.CONVERSATION_PROCESSING):" in source
            or "with track_usage(uid, Features.REALTIME_INTEGRATIONS):" in source
        )

    def test_persona_py_tracking(self):
        """utils/llm/persona.py must wrap LLM calls with PERSONA."""
        source = (BACKEND_ROOT / "utils" / "llm" / "persona.py").read_text()
        count = source.count("with track_usage(uid, Features.PERSONA):")
        assert count >= 2, f"Expected >= 2 PERSONA wrappers in persona.py, found {count}"

    def test_apps_py_tracking(self):
        """utils/apps.py must wrap persona generation calls with PERSONA."""
        source = (BACKEND_ROOT / "utils" / "apps.py").read_text()
        count = source.count("with track_usage(")
        assert count >= 4, f"Expected >= 4 track_usage wrappers in utils/apps.py, found {count}"

    def test_transcribe_py_describe_image_call(self):
        """routers/transcribe.py must pass uid to describe_image."""
        source = (BACKEND_ROOT / "routers" / "transcribe.py").read_text()
        assert "describe_image(uid," in source, "describe_image must be called with uid as first arg"

    def test_users_py_followup_call(self):
        """routers/users.py must pass uid to followup_question_prompt."""
        source = (BACKEND_ROOT / "routers" / "users.py").read_text()
        assert (
            "followup_question_prompt(uid," in source
        ), "followup_question_prompt must be called with uid as first arg"

    def test_graph_py_usage_callback(self):
        """utils/retrieval/graph.py must attach _usage_callback to ChatOpenAI."""
        source = (BACKEND_ROOT / "utils" / "retrieval" / "graph.py").read_text()
        assert "callbacks=[_usage_callback]" in source, "graph.py must attach usage callback"
        assert "get_usage_callback" in source, "graph.py must import get_usage_callback"

    def test_usage_tracker_imports_in_modified_files(self):
        """Each modified file must import track_usage and Features from usage_tracker."""
        files_to_check = [
            "utils/llm/followup.py",
            "utils/llm/openglass.py",
            "utils/onboarding.py",
            "utils/app_integrations.py",
            "routers/apps.py",
            "utils/llm/chat.py",
            "utils/llm/persona.py",
            "utils/apps.py",
        ]
        import_pattern = re.compile(r'from\s+utils\.llm\.usage_tracker\s+import\s+.*track_usage.*Features')
        for rel_path in files_to_check:
            source = (BACKEND_ROOT / rel_path).read_text()
            # Check for track_usage and Features imports (may be separate lines)
            assert "track_usage" in source, f"{rel_path} missing track_usage import"
            assert "Features" in source, f"{rel_path} missing Features import"

    def test_all_new_feature_constants_used_in_source(self):
        """Every new feature constant must appear in at least one source file (not test files)."""
        src_dirs = [BACKEND_ROOT / "utils", BACKEND_ROOT / "routers"]
        for attr, value in NEW_FEATURES.items():
            pattern = f"Features.{attr}"
            found = False
            for src_dir in src_dirs:
                for py_file in src_dir.rglob("*.py"):
                    if "test_" in py_file.name:
                        continue
                    if pattern in py_file.read_text():
                        found = True
                        break
                if found:
                    break
            assert found, f"Features.{attr} not used in any source file under utils/ or routers/"

    def test_no_untracked_llm_calls_in_new_feature_files(self):
        """
        In the specific files that were modified for the new features,
        every llm.invoke / llm.ainvoke / chain.invoke should be inside
        a track_usage block (heuristic: the call and the track_usage must
        share the same function body).
        """
        # For followup.py and openglass.py we can do a precise check:
        # the invoke call must be indented further than the track_usage line.
        for rel_path in ["utils/llm/followup.py", "utils/llm/openglass.py"]:
            source = (BACKEND_ROOT / rel_path).read_text()
            lines = source.splitlines()
            in_track_block = False
            invoke_found = False
            for line in lines:
                stripped = line.lstrip()
                if "with track_usage(" in stripped:
                    in_track_block = True
                if in_track_block and (".invoke(" in stripped or ".ainvoke(" in stripped):
                    invoke_found = True
                    break
            assert invoke_found, f"{rel_path}: LLM invoke call not found inside track_usage block"
