"""
LLM Usage Tracker - Feature-level token usage tracking.

Uses LangChain callbacks and contextvars to track which features consume LLM tokens.
"""

from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from database.llm_usage import record_llm_usage

# Context variable for tracking current feature
_usage_context: contextvars.ContextVar[Optional["UsageContext"]] = contextvars.ContextVar(
    "llm_usage_context", default=None
)

# Thread-safe buffer for batching writes
_buffer_lock = threading.Lock()
_usage_buffer: Dict[str, Dict[str, int]] = {}


@dataclass(frozen=True)
class UsageContext:
    """Context for LLM usage tracking."""

    uid: str
    feature: str


@dataclass
class UsageRecord:
    """A single usage record."""

    uid: str
    feature: str
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LLMUsageCallback(BaseCallbackHandler):
    """LangChain callback handler for tracking LLM token usage by feature."""

    def __init__(self, flush_fn: Optional[Callable[[str, str, str, int, int], None]] = None):
        """
        Initialize the callback.

        Args:
            flush_fn: Optional function to call for each usage record.
                      Signature: (uid, feature, model, input_tokens, output_tokens) -> None
        """
        self._flush_fn = flush_fn

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM call ends. Records token usage."""
        ctx = _usage_context.get()
        if not ctx:
            ctx = UsageContext(uid="unknown", feature=Features.OTHER)

        # Extract token usage from response
        token_usage = {}
        model = "unknown"
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            model = response.llm_output.get("model_name") or token_usage.get("model_name", model)

        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)

        # Also try to get model from response metadata
        if model == "unknown" and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, "generation_info") and gen.generation_info:
                        model = gen.generation_info.get("model_name", model)
                        break

        if input_tokens > 0 or output_tokens > 0:
            if self._flush_fn:
                # Write immediately - skip buffering to avoid unbounded growth
                self._flush_fn(ctx.uid, ctx.feature, model, input_tokens, output_tokens)
            else:
                # Buffer for batch writing when no flush_fn provided
                _buffer_usage(ctx.uid, ctx.feature, model, input_tokens, output_tokens)


def _buffer_usage(uid: str, feature: str, model: str, input_tokens: int, output_tokens: int):
    """Buffer usage data for batch writing."""
    key = f"{uid}:{feature}:{model}"
    with _buffer_lock:
        if key not in _usage_buffer:
            _usage_buffer[key] = {"input_tokens": 0, "output_tokens": 0}
        _usage_buffer[key]["input_tokens"] += input_tokens
        _usage_buffer[key]["output_tokens"] += output_tokens


def get_and_clear_buffer() -> Dict[str, Dict[str, int]]:
    """Get buffered usage data and clear the buffer."""
    with _buffer_lock:
        data = _usage_buffer.copy()
        _usage_buffer.clear()
        return data


@contextmanager
def track_usage(uid: str, feature: str):
    """
    Context manager to track LLM usage for a specific feature.

    Usage:
        with track_usage(uid, "chat"):
            response = llm.invoke(prompt)

    Args:
        uid: User ID
        feature: Feature name (e.g., "chat", "conversation_processing", "rag")
    """
    ctx = UsageContext(uid=uid, feature=feature)
    token = _usage_context.set(ctx)
    try:
        yield ctx
    finally:
        _usage_context.reset(token)


def set_usage_context(uid: str, feature: str) -> contextvars.Token:
    """
    Set the usage context manually (for cases where context manager isn't suitable).

    Returns a token that should be used with reset_usage_context().
    """
    ctx = UsageContext(uid=uid, feature=feature)
    return _usage_context.set(ctx)


def reset_usage_context(token: contextvars.Token):
    """Reset the usage context using the token from set_usage_context()."""
    _usage_context.reset(token)


def get_current_context() -> Optional[UsageContext]:
    """Get the current usage context, if any."""
    return _usage_context.get()


# Singleton callback instance
_callback_instance: Optional[LLMUsageCallback] = None


def get_usage_callback() -> LLMUsageCallback:
    """Get the singleton usage callback instance."""
    global _callback_instance
    if _callback_instance is None:
        _callback_instance = LLMUsageCallback(flush_fn=record_llm_usage)
    return _callback_instance


# Feature constants for consistency
class Features:
    CHAT = "chat"
    CONVERSATION_PROCESSING = "conversation_processing"
    RAG = "rag"
    NOTIFICATIONS = "notifications"
    APP_INTEGRATIONS = "app_integrations"
    GOALS = "goals"
    TRENDS = "trends"
    PERSONA = "persona"
    MEMORIES = "memories"
    TRANSCRIBE = "transcribe"
    REALTIME_INTEGRATIONS = "realtime_integrations"
    DAILY_SUMMARY = "daily_summary"
    SUBSCRIPTION_NOTIFICATION = "subscription_notification"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    OTHER = "other"

    # Conversation processing sub-features (granular cost tracking)
    CONVERSATION_DISCARD = "conv_discard"
    CONVERSATION_STRUCTURE = "conv_structure"
    CONVERSATION_ACTION_ITEMS = "conv_action_items"
    CONVERSATION_FOLDER = "conv_folder"
    CONVERSATION_APPS = "conv_apps"
