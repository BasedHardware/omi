"""
Unit tests for LLM usage tracking.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Mock the database client to avoid needing GCP credentials
mock_db = MagicMock()
mock_client_module = MagicMock()
mock_client_module.db = mock_db
sys.modules["database._client"] = mock_client_module
sys.modules["stripe"] = MagicMock()

_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_firestore_module = types.ModuleType("google.cloud.firestore")
_google_firestore_module.Increment = lambda x: {"__increment": x}
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)

from langchain_core.outputs import Generation, LLMResult

from utils.llm import usage_tracker


def test_track_usage_context_sets_and_resets():
    assert usage_tracker.get_current_context() is None

    with usage_tracker.track_usage("user-1", usage_tracker.Features.CHAT):
        ctx = usage_tracker.get_current_context()
        assert ctx is not None
        assert ctx.uid == "user-1"
        assert ctx.feature == usage_tracker.Features.CHAT

    assert usage_tracker.get_current_context() is None


def test_set_usage_context_manual_reset():
    assert usage_tracker.get_current_context() is None

    token = usage_tracker.set_usage_context("user-2", usage_tracker.Features.RAG)
    try:
        ctx = usage_tracker.get_current_context()
        assert ctx is not None
        assert ctx.uid == "user-2"
        assert ctx.feature == usage_tracker.Features.RAG
    finally:
        usage_tracker.reset_usage_context(token)

    assert usage_tracker.get_current_context() is None


def test_get_usage_callback_singleton_uses_record_llm_usage():
    original_instance = usage_tracker._callback_instance
    original_record = usage_tracker.record_llm_usage
    usage_tracker._callback_instance = None
    record_mock = MagicMock()
    usage_tracker.record_llm_usage = record_mock

    try:
        callback1 = usage_tracker.get_usage_callback()
        callback2 = usage_tracker.get_usage_callback()
        assert callback1 is callback2

        token = usage_tracker.set_usage_context("user-2b", usage_tracker.Features.CHAT)
        try:
            result = LLMResult(
                generations=[[Generation(text="ok")]],
                llm_output={
                    "token_usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 11,
                        "model_name": "gpt-4.1-mini",
                    }
                },
            )
            callback1.on_llm_end(result)
        finally:
            usage_tracker.reset_usage_context(token)

        record_mock.assert_called_once_with("user-2b", "chat", "gpt-4.1-mini", 7, 11)
    finally:
        usage_tracker._callback_instance = original_instance
        usage_tracker.record_llm_usage = original_record


def test_llm_callback_flushes_immediately_skips_buffer():
    """When flush_fn is set, usage is written immediately and buffer is skipped."""
    usage_tracker.get_and_clear_buffer()
    flush_calls = []

    def flush_fn(uid, feature, model, input_tokens, output_tokens):
        flush_calls.append((uid, feature, model, input_tokens, output_tokens))

    callback = usage_tracker.LLMUsageCallback(flush_fn=flush_fn)
    token = usage_tracker.set_usage_context("user-3", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "model_name": "gpt-4.1-mini",
                }
            },
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    # When flush_fn is set, buffer is skipped to avoid unbounded growth
    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {}
    assert flush_calls == [("user-3", "chat", "gpt-4.1-mini", 12, 3)]


def test_llm_callback_uses_generation_info_model_when_missing():
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-4", usage_tracker.Features.RAG)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok", generation_info={"model_name": "fallback-model"})]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "model_name": "unknown",
                }
            },
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-4:rag:fallback-model": {"input_tokens": 1, "output_tokens": 2}}


def test_llm_callback_no_context_defaults_to_other():
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    result = LLMResult(
        generations=[[Generation(text="ok")]],
        llm_output={
            "token_usage": {
                "prompt_tokens": 4,
                "completion_tokens": 5,
                "model_name": "gpt-4.1-mini",
            }
        },
    )

    callback.on_llm_end(result)

    assert usage_tracker.get_and_clear_buffer() == {
        "unknown:other:gpt-4.1-mini": {"input_tokens": 4, "output_tokens": 5}
    }


def test_llm_callback_buffers_when_no_flush_fn():
    """When no flush_fn, usage is buffered instead of written immediately."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()  # No flush_fn
    token = usage_tracker.set_usage_context("user-5", usage_tracker.Features.CONVERSATION_PROCESSING)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 25,
                    "model_name": "gpt-4",
                }
            },
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-5:conversation_processing:gpt-4": {"input_tokens": 50, "output_tokens": 25}}


def test_buffer_accumulates_multiple_calls():
    """Buffer accumulates tokens from multiple LLM calls with same key."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-6", usage_tracker.Features.CHAT)
    try:
        # First call
        result1 = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "model_name": "gpt-4",
                }
            },
        )
        callback.on_llm_end(result1)

        # Second call - same user/feature/model
        result2 = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "model_name": "gpt-4",
                }
            },
        )
        callback.on_llm_end(result2)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-6:chat:gpt-4": {"input_tokens": 30, "output_tokens": 15}}


def test_buffer_separates_different_keys():
    """Buffer keeps separate entries for different user/feature/model combinations."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()

    # First: user-7, chat, gpt-4
    token1 = usage_tracker.set_usage_context("user-7", usage_tracker.Features.CHAT)
    try:
        result1 = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result1)
    finally:
        usage_tracker.reset_usage_context(token1)

    # Second: user-7, rag, gpt-4
    token2 = usage_tracker.set_usage_context("user-7", usage_tracker.Features.RAG)
    try:
        result2 = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 20, "completion_tokens": 10, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result2)
    finally:
        usage_tracker.reset_usage_context(token2)

    buffered = usage_tracker.get_and_clear_buffer()
    assert len(buffered) == 2
    assert buffered["user-7:chat:gpt-4"] == {"input_tokens": 10, "output_tokens": 5}
    assert buffered["user-7:rag:gpt-4"] == {"input_tokens": 20, "output_tokens": 10}


def test_get_and_clear_buffer_clears():
    """get_and_clear_buffer returns data and clears the buffer."""
    usage_tracker.get_and_clear_buffer()  # Start fresh
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-8", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 3, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    # First call should return data
    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-8:chat:gpt-4": {"input_tokens": 5, "output_tokens": 3}}

    # Second call should return empty
    buffered2 = usage_tracker.get_and_clear_buffer()
    assert buffered2 == {}


def test_llm_callback_skips_zero_tokens():
    """Callback does not buffer when both input and output tokens are zero."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-9", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {}


def test_llm_callback_records_nonzero_input_only():
    """Callback records when only input tokens are non-zero."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-10", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 0, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-10:chat:gpt-4": {"input_tokens": 10, "output_tokens": 0}}


def test_llm_callback_records_nonzero_output_only():
    """Callback records when only output tokens are non-zero."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-11", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"token_usage": {"prompt_tokens": 0, "completion_tokens": 15, "model_name": "gpt-4"}},
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-11:chat:gpt-4": {"input_tokens": 0, "output_tokens": 15}}


def test_llm_callback_handles_missing_llm_output():
    """Callback handles LLMResult with no llm_output (defaults to zero tokens)."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-12", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output=None,
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    # Zero tokens means nothing recorded
    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {}


def test_llm_callback_handles_missing_token_usage():
    """Callback handles LLMResult with llm_output but no token_usage key."""
    usage_tracker.get_and_clear_buffer()
    callback = usage_tracker.LLMUsageCallback()
    token = usage_tracker.set_usage_context("user-13", usage_tracker.Features.CHAT)
    try:
        result = LLMResult(
            generations=[[Generation(text="ok")]],
            llm_output={"some_other_key": "value"},
        )
        callback.on_llm_end(result)
    finally:
        usage_tracker.reset_usage_context(token)

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {}


def test_track_usage_context_resets_on_exception():
    """Context is properly reset even when an exception occurs."""
    usage_tracker.get_and_clear_buffer()

    class TestException(Exception):
        pass

    try:
        with usage_tracker.track_usage("user-14", usage_tracker.Features.CHAT):
            ctx = usage_tracker.get_current_context()
            assert ctx is not None
            raise TestException("test error")
    except TestException:
        pass

    # Context should be reset even after exception
    assert usage_tracker.get_current_context() is None


def test_features_constants_have_expected_values():
    """Verify Features class constants match expected string values."""
    assert usage_tracker.Features.CHAT == "chat"
    assert usage_tracker.Features.CONVERSATION_PROCESSING == "conversation_processing"
    assert usage_tracker.Features.RAG == "rag"
    assert usage_tracker.Features.NOTIFICATIONS == "notifications"
    assert usage_tracker.Features.APP_INTEGRATIONS == "app_integrations"
    assert usage_tracker.Features.GOALS == "goals"
    assert usage_tracker.Features.TRENDS == "trends"
    assert usage_tracker.Features.PERSONA == "persona"
    assert usage_tracker.Features.MEMORIES == "memories"
    assert usage_tracker.Features.TRANSCRIBE == "transcribe"
    assert usage_tracker.Features.OTHER == "other"


def test_usage_context_is_frozen():
    """UsageContext is immutable (frozen dataclass)."""
    ctx = usage_tracker.UsageContext(uid="user-15", feature="chat")
    try:
        ctx.uid = "different-user"
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass  # Expected - frozen dataclass
