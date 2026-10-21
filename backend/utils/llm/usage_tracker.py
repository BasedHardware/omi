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
from typing import Any, Protocol, Dict, Iterator, Mapping, Optional, cast

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from database.llm_usage import record_llm_usage
from utils.sync.repeat_work_metrics import record_llm_call

# Context variable for tracking current feature
_usage_context: contextvars.ContextVar[Optional["UsageContext"]] = contextvars.ContextVar(
    "llm_usage_context", default=None
)

# Thread-safe buffer for batching writes
_buffer_lock = threading.Lock()
_usage_buffer: Dict[str, Dict[str, int]] = {}

UsageContextToken = contextvars.Token[Optional["UsageContext"]]


@dataclass(frozen=True)
class UsageContext:
    """Context for LLM usage tracking."""

    uid: str
    feature: str
    surface: str | None = None
    turn_id: str | None = None


@dataclass
class UsageRecord:
    """A single usage record."""

    uid: str
    feature: str
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class UsageWriter(Protocol):
    """Usage sink accepting basic counts and optional chat cache/surface attribution."""

    def __call__(
        self,
        uid: str,
        feature: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        surface: str | None = None,
        turn_id: str | None = None,
    ) -> None: ...


class LLMUsageCallback(BaseCallbackHandler):
    """LangChain callback handler for tracking LLM token usage by feature."""

    def __init__(self, flush_fn: Optional[UsageWriter] = None) -> None:
        """
        Initialize the callback.

        Args:
            flush_fn: Optional function to call for each usage record.
                      Basic counts plus optional keyword-only cache/surface/turn attribution.
        """
        self._flush_fn = flush_fn

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        ctx = _usage_context.get()
        record_llm_call('failed', ctx.feature if ctx else 'other')

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM call ends. Records token usage."""
        ctx = _usage_context.get()
        record_llm_call('completed', ctx.feature if ctx else 'other')
        if not ctx:
            ctx = UsageContext(uid="unknown", feature=Features.OTHER)

        # Extract token usage from response
        token_usage: Mapping[str, object] = {}
        model = "unknown"
        llm_output = _mapping_or_empty(getattr(response, "llm_output", None))
        if llm_output:
            token_usage = _mapping_or_empty(llm_output.get("token_usage"))
            model = _string_or_default(llm_output.get("model_name") or token_usage.get("model_name"), model)

        input_tokens = _int_or_zero(token_usage.get("prompt_tokens"))
        output_tokens = _int_or_zero(token_usage.get("completion_tokens"))

        cache_read = _int_or_zero(_mapping_or_empty(token_usage.get('prompt_tokens_details')).get('cached_tokens'))
        cache_write = _int_or_zero(
            _mapping_or_empty(token_usage.get('prompt_tokens_details')).get('cache_write_tokens')
        )
        for group in response.generations or []:
            for generation in group:
                message = getattr(generation, 'message', None)
                raw = _mapping_or_empty(
                    _mapping_or_empty(getattr(message, 'response_metadata', {})).get('omi_token_usage')
                )
                usage = _mapping_or_empty(getattr(message, 'usage_metadata', {}))
                if raw and not token_usage:
                    input_tokens = _int_or_zero(raw.get('prompt_tokens'))
                    output_tokens = _int_or_zero(raw.get('completion_tokens'))
                    details = _mapping_or_empty(raw.get('prompt_tokens_details'))
                    cache_read = _int_or_zero(details.get('cached_tokens'))
                    cache_write = _int_or_zero(details.get('cache_write_tokens'))
                elif usage and not token_usage:
                    input_tokens = _int_or_zero(usage.get('input_tokens'))
                    output_tokens = _int_or_zero(usage.get('output_tokens'))
                    details = _mapping_or_empty(usage.get('input_token_details'))
                    cache_read = sum(_int_or_zero(v) for k, v in details.items() if k.endswith('cache_read'))
                    cache_write = sum(
                        _int_or_zero(v) for k, v in details.items() if k.endswith(('cache_creation', 'cache_write'))
                    )

        # Also try to get model from response metadata
        if model == "unknown" and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    metadata = _mapping_or_empty(getattr(getattr(gen, 'message', None), 'response_metadata', {}))
                    model = _string_or_default(metadata.get('model_name'), model)
                    if hasattr(gen, "generation_info") and gen.generation_info:
                        generation_info = cast(Mapping[str, object], gen.generation_info)
                        model = _string_or_default(generation_info.get("model_name"), model)
                        break

        if input_tokens > 0 or output_tokens > 0:
            if self._flush_fn:
                # Write immediately - skip buffering to avoid unbounded growth
                if ctx.feature == 'chat_agent':
                    from utils.messaging.metrics import CHAT_TOKENS

                    surface = ctx.surface if ctx.surface in {'app', 'telegram', 'imessage'} else 'other'
                    for kind, value in [
                        ('input', input_tokens),
                        ('cache_read', cache_read),
                        ('cache_write', cache_write),
                    ]:
                        CHAT_TOKENS.labels(surface, kind).inc(max(0, value))
                    self._flush_fn(
                        ctx.uid,
                        ctx.feature,
                        model,
                        input_tokens,
                        output_tokens,
                        cache_read_tokens=cache_read,
                        cache_write_tokens=cache_write,
                        surface=surface,
                        turn_id=ctx.turn_id,
                    )
                else:
                    self._flush_fn(ctx.uid, ctx.feature, model, input_tokens, output_tokens)
            else:
                # Buffer for batch writing when no flush_fn provided
                _buffer_usage(ctx.uid, ctx.feature, model, input_tokens, output_tokens)


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _string_or_default(value: object, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _int_or_zero(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _buffer_usage(uid: str, feature: str, model: str, input_tokens: int, output_tokens: int) -> None:
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
def track_usage(uid: str, feature: str) -> Iterator[UsageContext]:
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


def set_usage_context(
    uid: str, feature: str, *, surface: str | None = None, turn_id: str | None = None
) -> UsageContextToken:
    """
    Set the usage context manually (for cases where context manager isn't suitable).

    Returns a token that should be used with reset_usage_context().
    """
    ctx = UsageContext(uid=uid, feature=feature, surface=surface, turn_id=turn_id)
    return _usage_context.set(ctx)


def reset_usage_context(token: UsageContextToken) -> None:
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

    PROACTIVE_NOTIFICATION = "proactive_notification"
    FOLLOWUP = "followup"
    OPENGLASS = "openglass"
    APP_GENERATOR = "app_generator"
    ONBOARDING = "onboarding"
    SCREEN_FRAME_JUDGE = "screen_frame_judge"

    # Conversation processing sub-features (granular cost tracking)
    CONVERSATION_DISCARD = "conv_discard"
    CONVERSATION_STRUCTURE = "conv_structure"
    CONVERSATION_ACTION_ITEMS = "conv_action_items"
    WAKE_WORD_ADJUDICATION = "wake_word_adjudication"
    CONVERSATION_FOLDER = "conv_folder"
    CONVERSATION_APPS = "conv_apps"
