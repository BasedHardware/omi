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


def test_llm_callback_buffers_and_flushes():
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

    buffered = usage_tracker.get_and_clear_buffer()
    assert buffered == {"user-3:chat:gpt-4.1-mini": {"input_tokens": 12, "output_tokens": 3}}
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


def test_llm_callback_no_context_noop():
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

    assert usage_tracker.get_and_clear_buffer() == {}
