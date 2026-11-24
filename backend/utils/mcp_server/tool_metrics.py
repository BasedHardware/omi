"""Unsampled Prometheus metrics for hosted MCP tool calls.

PostHog's ``MCP Tool Call`` event is sampled per user and carries no response
size, so it cannot answer "which tools fail, how slow are they, how big are
their answers, how often are reads cut short" for every call. These series can.

Every label is bounded: ``tool`` is allowlisted to the registry (else
``unknown``), ``client`` is the analytics client family, ``outcome`` and
``error_category`` are closed sets. No uid, query, id or payload is a label.
"""

import logging
from typing import Any, Mapping, Optional

from prometheus_client import REGISTRY, Counter, Histogram

from utils.mcp_analytics import mcp_client_family, mcp_tool_enum

logger = logging.getLogger(__name__)

_OUTCOMES = frozenset({'success', 'error'})
# ``capped`` (daily cap or usage budget reached) is metrics-only; the rest match the PostHog event.
_ERROR_CATEGORIES = frozenset({'none', 'authorization_denied', 'validation', 'unknown_tool', 'internal', 'capped'})
DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 60.0, 120.0)
RESPONSE_CHAR_BUCKETS = (1_000, 4_000, 16_000, 32_000, 64_000, 100_000, 120_000, 250_000)


def _registered(name: str, kind: type, labels: list, factory):
    """Module-reload-safe: isolated test loads reuse the one registered collector of the same shape."""
    existing = getattr(REGISTRY, '_names_to_collectors', {}).get(name)
    if existing is None:
        return factory()
    if not isinstance(existing, kind) or list(getattr(existing, '_labelnames', ())) != labels:
        raise ValueError(f'{name} already registered with a different shape')
    return existing


MCP_TOOL_CALLS_TOTAL: Counter = _registered(
    'omi_mcp_tool_calls_total',
    Counter,
    ['tool', 'client', 'outcome', 'error_category'],
    lambda: Counter(
        'omi_mcp_tool_calls',
        'Hosted MCP tools/call requests by tool, client family, outcome and error category',
        ['tool', 'client', 'outcome', 'error_category'],
    ),
)
MCP_TOOL_DURATION_SECONDS: Histogram = _registered(
    'omi_mcp_tool_duration_seconds',
    Histogram,
    ['tool'],
    lambda: Histogram(
        'omi_mcp_tool_duration_seconds',
        'Hosted MCP tools/call wall time from admission to result, by tool',
        ['tool'],
        buckets=DURATION_BUCKETS,
    ),
)
MCP_TOOL_RESPONSE_CHARS: Histogram = _registered(
    'omi_mcp_tool_response_chars',
    Histogram,
    ['tool'],
    lambda: Histogram(
        'omi_mcp_tool_response_chars',
        'Compact JSON characters in a successful hosted MCP tool result, by tool',
        ['tool'],
        buckets=RESPONSE_CHAR_BUCKETS,
    ),
)
MCP_TOOL_TRUNCATED_TOTAL: Counter = _registered(
    'omi_mcp_tool_truncated_results_total',
    Counter,
    ['tool'],
    lambda: Counter(
        'omi_mcp_tool_truncated_results',
        'Successful hosted MCP tool results that reported truncated=true (more to page), by tool',
        ['tool'],
    ),
)
MCP_MEMORY_WINDOW_END_TOTAL: Counter = _registered(
    'omi_mcp_memory_window_end_total',
    Counter,
    ['tool'],
    lambda: Counter(
        'omi_mcp_memory_window_end',
        'Memory list pages that ended a full bounded source window with no pageable continuation; '
        'the client may be missing older eligible memories',
        ['tool'],
    ),
)


def record_tool_call(
    tool_name: Any,
    *,
    auth_type: Any,
    client_id: Optional[str],
    outcome: str,
    error_category: str,
    duration_ms: float,
) -> None:
    try:
        tool = mcp_tool_enum(tool_name)
        MCP_TOOL_CALLS_TOTAL.labels(
            tool,
            mcp_client_family(auth_type, client_id),
            outcome if outcome in _OUTCOMES else 'error',
            error_category if error_category in _ERROR_CATEGORIES else 'internal',
        ).inc()
        if duration_ms > 0:
            # Argument and envelope failures never reached a handler; they would drag latency toward zero.
            MCP_TOOL_DURATION_SECONDS.labels(tool).observe(float(duration_ms) / 1_000)
    except Exception as exc:  # noqa: BLE001 - telemetry must never fail a tool call
        logger.warning('mcp tool metric failed error=%s', type(exc).__name__)


def record_tool_result(tool_name: Any, result: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    """Size and truncation of a successful result, from the text content already serialized."""
    try:
        tool = mcp_tool_enum(tool_name)
        content = payload.get('content') or []
        text = content[0].get('text') if content and isinstance(content[0], Mapping) else None
        if isinstance(text, str):
            MCP_TOOL_RESPONSE_CHARS.labels(tool).observe(len(text))
        if result.get('truncated') is True:
            MCP_TOOL_TRUNCATED_TOTAL.labels(tool).inc()
        # A full bounded window with no continuation is the exact state that
        # used to advertise a dangling has_more: the client cannot page further
        # and global coverage is unknown, so it may be missing older memories.
        window_limit = result.get('source_window_limit')
        if (
            isinstance(window_limit, int)
            and result.get('has_more') is False
            and result.get('scan_truncated') is True
            and result.get('scanned_count') == window_limit
        ):
            MCP_MEMORY_WINDOW_END_TOTAL.labels(tool).inc()
    except Exception as exc:  # noqa: BLE001 - telemetry must never fail a tool call
        logger.warning('mcp tool result metric failed error=%s', type(exc).__name__)
