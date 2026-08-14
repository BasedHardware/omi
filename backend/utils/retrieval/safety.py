"""
Safety guards for agentic chat system.

Prevents infinite loops, context overflow, and excessive tool usage.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import os
import time
import logging

logger = logging.getLogger(__name__)


def safe_isoformat(value: Any) -> Optional[str]:
    """Return a bounded ISO-like timestamp suitable for untrusted tool-source metadata."""
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    formatted = isoformat() if callable(isoformat) else value
    return str(formatted)[:80]


class SafetyGuardError(Exception):
    """Raised when a safety limit is exceeded."""

    pass


class AgentSafetyGuard:
    """
    Safety guard for ReAct agents to prevent:
    - Tool call loops (repeated calls with same parameters)
    - Excessive tool calls (max 25 per query)
    - Context overflow (max 500K tokens)
    - Suspicious parameter patterns
    """

    def __init__(self, max_tool_calls: int = 25, max_context_tokens: int = 500000):
        self.max_tool_calls = max_tool_calls
        self.max_context_tokens = max_context_tokens

        # Tracking
        self.tool_call_count = 0
        self.tool_call_history: List[Tuple[str, Dict[str, Any], float]] = []  # (tool_name, params, timestamp)
        self.estimated_tokens = 0
        self.start_time = time.time()

        # Loop detection window (check last N calls)
        self.loop_detection_window = 3

    def validate_tool_call(self, tool_name: str, params: Dict[str, Any]) -> None:
        """
        Validate a tool call before execution.

        Args:
            tool_name: Name of the tool being called
            params: Parameters for the tool call

        Raises:
            SafetyGuardError: If any safety limit is exceeded
        """
        # Check tool call limit
        if self.tool_call_count >= self.max_tool_calls:
            raise SafetyGuardError(
                "I'm having trouble finding all the information you need. "
                "Could you try asking a simpler question or breaking this into separate questions?"
            )

        # Check for tool call loops
        if self._is_loop_detected(tool_name, params):
            raise SafetyGuardError(
                "I seem to be stuck trying to answer your question. " "Could you rephrase it in a different way?"
            )

        # Record the call
        self.tool_call_count += 1
        self.tool_call_history.append((tool_name, params, time.time()))

        logger.info(f"🛡️ Safety Guard: Tool call {self.tool_call_count}/{self.max_tool_calls} - {tool_name}")

    def estimate_response_tokens(self, response: str) -> int:
        """
        Estimate token count for a response.
        Uses rough heuristic: ~4 characters per token for English text.

        Args:
            response: The response text

        Returns:
            Estimated token count
        """
        # Rough estimate: 1 token ≈ 4 characters
        return len(response) // 4

    def check_context_size(self, new_data: str) -> None:
        """
        Check if adding new data would exceed context limit.

        Args:
            new_data: The new data being added to context

        Raises:
            SafetyGuardError: If context limit would be exceeded
        """
        new_tokens = self.estimate_response_tokens(new_data)
        total_tokens = self.estimated_tokens + new_tokens

        if total_tokens > self.max_context_tokens:
            raise SafetyGuardError(
                "That's a lot of information to process at once! "
                "Could you narrow down your request? Try asking about a smaller time period or being more specific about what you're looking for."
            )

        self.estimated_tokens = total_tokens
        logger.info(
            f"🛡️ Safety Guard: Context size: {self.estimated_tokens}/{self.max_context_tokens} tokens (+{new_tokens})"
        )

    def _is_loop_detected(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """
        Detect if the same tool is being called repeatedly with similar parameters.

        Args:
            tool_name: Name of the tool
            params: Tool parameters

        Returns:
            True if a loop is detected
        """
        if len(self.tool_call_history) < self.loop_detection_window:
            return False

        # Check last N calls
        recent_calls = self.tool_call_history[-self.loop_detection_window :]

        # Count how many times this exact tool+params combination appears
        similar_count = 0
        for past_tool, past_params, _ in recent_calls:
            if past_tool == tool_name and self._params_similar(params, past_params):
                similar_count += 1

        # If more than half of recent calls are the same tool with similar params, it's likely a loop
        return similar_count >= (self.loop_detection_window // 2 + 1)

    def _params_similar(self, params1: Dict[str, Any], params2: Dict[str, Any], threshold: float = 0.8) -> bool:
        """
        Check if two parameter sets are similar (for loop detection).

        Args:
            params1: First parameter set
            params2: Second parameter set
            threshold: Similarity threshold (0-1)

        Returns:
            True if parameters are similar
        """
        # Get keys from both dicts
        all_keys = set(params1.keys()) | set(params2.keys())
        if not all_keys:
            return True

        # Count matching values
        matching = 0
        for key in all_keys:
            val1 = params1.get(key)
            val2 = params2.get(key)

            # Consider None and missing keys as equivalent
            if val1 is None and val2 is None:
                matching += 1
            elif val1 == val2:
                matching += 1

        # Calculate similarity ratio
        similarity = matching / len(all_keys)
        return similarity >= threshold

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current session.

        Returns:
            Dictionary with session statistics
        """
        elapsed = time.time() - self.start_time

        return {
            'tool_calls': self.tool_call_count,
            'max_tool_calls': self.max_tool_calls,
            'estimated_tokens': self.estimated_tokens,
            'max_context_tokens': self.max_context_tokens,
            'elapsed_seconds': elapsed,
            'tools_used': list(set(tool for tool, _, _ in self.tool_call_history)),
        }

    def should_warn_user(self) -> Optional[str]:
        """
        Check if user should be warned about approaching limits.

        Returns:
            Warning message if applicable, None otherwise
        """
        # Warn at 80% of limits
        if self.tool_call_count >= self.max_tool_calls * 0.8:
            logger.warning(
                f"🛡️ Safety Guard: Warning - Tool calls at {self.tool_call_count}/{self.max_tool_calls} (80% threshold)"
            )
            return "⚠️ I'm processing a lot of information. Your response might take a moment..."

        if self.estimated_tokens >= self.max_context_tokens * 0.8:
            logger.warning(
                f"🛡️ Safety Guard: Warning - Context size at {self.estimated_tokens}/{self.max_context_tokens} tokens (80% threshold)"
            )
            return "⚠️ Processing a large amount of data. Almost done..."

        return None


# ---------------------------------------------------------------------------
# Oversized chat-input guard.
#
# An extremely long chat message (or a long conversation history) can exceed the chat model's
# context window. When that happens the Anthropic call raises an input-too-long error which the
# agent loop swallows into a streamed text chunk without a terminal ``done:`` frame, so the mobile
# client never finalizes a reply and the user sees "no response" (or a generic error). The decision
# logic below is kept pure and import-light (the token counter is injected) so it can be unit-tested
# without the heavy chat/LLM stack: trim the oldest turns to fit the budget and, when the newest
# turn alone is too large, return a clear message through the normal streaming contract instead of
# calling the model with input that cannot fit.
# ---------------------------------------------------------------------------


def _int_from_env(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back to ``default``."""
    try:
        value = int(os.environ.get(name, ''))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# 120k tokens is ~90k words of conversation — far beyond any legitimate mobile chat, so real
# usage is never rejected, only pathological paste-dumps. This is an abuse cap, not a
# context-window cap, and it is deliberately not derived from any model's window: `chat_agent`
# is routed per deployment and both providers it can reach have windows far above this, so the
# system prompt, tool schemas, accumulated tool results and the reply all fit with room to
# spare. Re-deriving it from whatever model is current raises the ceiling on what a single
# request can cost, which is the reason to keep it low and provider-independent.
#
# The counter is tiktoken, so it is exact only for the OpenAI route and undercounts on the
# Anthropic one — a conversation measured at the cap is somewhat larger in the tokens actually
# billed there. That error is in the safe direction (the guard trips earlier than the nominal
# limit) and stays safe only while the cap sits far below the real window.
MAX_CHAT_INPUT_TOKENS = _int_from_env('MAX_CHAT_INPUT_TOKENS', 120_000)

# Delivered to the user (and persisted) when the newest message alone is over the budget. Sent
# through the same streaming/done: contract as any normal reply so the client renders it in-line.
INPUT_TOO_LONG_MESSAGE = (
    "That message is too long for me to process in one go. "
    "Please shorten it or split it into a few smaller messages and send again."
)


def message_text(content: Any) -> str:
    """Best-effort plain text of a message's content.

    Handles a plain string, an Anthropic-style list of content blocks (dicts with a ``text``
    field, e.g. ``{"type": "text", "text": ...}``), or a bare list of strings. Non-text blocks
    (images, tool results) contribute nothing to the text token estimate.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get('text')
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def fit_within_budget(
    items: Sequence[Any],
    text_of: Callable[[Any], str],
    counter: Callable[[str], int],
    limit: int = MAX_CHAT_INPUT_TOKENS,
) -> Tuple[list, bool]:
    """Trim the oldest items so the cumulative token estimate fits within ``limit``.

    Keeps the most recent items and always preserves the final (current) item. ``text_of`` maps
    an item to its text and ``counter`` estimates that text's token count.

    Returns ``(kept_items, newest_exceeds_limit)``. When the newest item alone is over ``limit``
    the input cannot fit the context window, so this returns ``([], True)`` and the caller should
    reject with a clear message rather than call the model. Otherwise ``newest_exceeds_limit`` is
    ``False`` and ``kept_items`` is the trimmed, in-order list to send.
    """
    items = list(items)
    if not items:
        return items, False

    if counter(text_of(items[-1])) > limit:
        return [], True

    kept: list = []
    total = 0
    for item in reversed(items):
        tokens = counter(text_of(item))
        if kept and total + tokens > limit:
            break
        kept.append(item)
        total += tokens
    kept.reverse()
    return kept, False


# Matched on class name, not type, so this stays import-light and still covers the raw httpx
# exceptions that escape the SDK once the response body is already streaming.
TRANSIENT_PROVIDER_ERROR_NAMES = frozenset(
    {
        'APIConnectionError',
        'APITimeoutError',
        'ConnectError',
        'ConnectTimeout',
        'InternalServerError',
        'PoolTimeout',
        'ReadError',
        'ReadTimeout',
        'RemoteProtocolError',
        'WriteError',
        'WriteTimeout',
    }
)

# 429 is deliberately absent: a rate limit does not clear within one turn's budget.
TRANSIENT_PROVIDER_STATUS_CODES = frozenset({500, 502, 503, 504, 529})

_TIMEOUT_ERROR_NAMES = frozenset({'APITimeoutError', 'ConnectTimeout', 'PoolTimeout', 'ReadTimeout', 'WriteTimeout'})


def _provider_status_code(error: BaseException) -> Optional[int]:
    """HTTP status carried by a provider exception, if it has one."""
    status_code = getattr(error, 'status_code', None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(error, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int):
        return response_status
    return None


def is_transient_provider_error(error: BaseException) -> bool:
    """Whether ``error`` is a transport-class provider failure worth re-issuing.

    A status-carrying error is judged by its status alone: a 4xx describes the request we just
    sent, so repeating it cannot help.
    """
    status_code = _provider_status_code(error)
    if status_code is not None:
        return status_code in TRANSIENT_PROVIDER_STATUS_CODES
    return type(error).__name__ in TRANSIENT_PROVIDER_ERROR_NAMES


def provider_fallback_reason(error: BaseException) -> str:
    """Map a provider exception onto the bounded ``record_fallback`` reason set."""
    status_code = _provider_status_code(error)
    if status_code is not None:
        if 500 <= status_code < 600:
            return 'provider_5xx'
        if status_code == 429:
            return 'provider_429'
        return 'other'
    return 'timeout' if type(error).__name__ in _TIMEOUT_ERROR_NAMES else 'other'


def should_retry_provider_error(
    error: BaseException,
    *,
    attempts_made: int,
    max_attempts: int,
    text_already_streamed: bool,
    seconds_remaining: float,
    min_headroom_seconds: float,
) -> bool:
    """Whether the agent's streaming model call may be re-issued after ``error``.

    Safe only while nothing from this attempt has reached the user: streamed text cannot be
    un-sent, and tool calls run after a stream closes cleanly, so a failed attempt leaves
    nothing to undo. A retry with less than ``min_headroom_seconds`` of the request budget left
    would be cancelled mid-flight, so it is not started.
    """
    if text_already_streamed:
        return False
    if attempts_made >= max_attempts:
        return False
    if seconds_remaining < min_headroom_seconds:
        return False
    return is_transient_provider_error(error)
