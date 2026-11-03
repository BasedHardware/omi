"""Content-free, bounded channel operational metrics."""

from prometheus_client import Counter, Histogram

TURNS = Counter('omi_messaging_turns_total', 'Completed channel inbox turns', ['channel', 'outcome'])
FAILURES = Counter('omi_messaging_failures_total', 'Channel failures', ['channel', 'reason'])
HTTP = Counter('omi_messaging_provider_http_total', 'Provider responses', ['provider', 'status'])
LATENCY = Histogram(
    'omi_messaging_turn_seconds', 'Channel worker latency', ['channel'], buckets=(1, 5, 15, 30, 60, 120, 180)
)
QUEUE_AGE = Histogram(
    'omi_messaging_queue_age_seconds', 'Age of claimed inbound', ['channel'], buckets=(1, 5, 30, 60, 300, 900, 1800)
)

CHAT_TOKENS = Counter(
    'omi_chat_agent_tokens_total', 'Provider-reported chat input and cache tokens', ['surface', 'kind']
)

# Outcomes, including successful/missing continuity, supply the denominator.
# Fail-open events still use the shared omi_fallback_total authority.
CONTEXT_TURNS = Counter('omi_chat_context_turns_total', 'Shaped context preparation', ['surface', 'outcome'])
CONTEXT_READS = Histogram(
    'omi_chat_context_read_seconds',
    'Optional shaped context operation latency including executor admission',
    ['surface', 'phase'],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.3, 1, 5, 60),
)
CONTEXT_SETUP_OVERLAP = Histogram(
    'omi_chat_context_setup_overlap_seconds',
    'Time available for prefetched context before the model mount consumes ready results',
    ['surface'],
    buckets=(0.01, 0.05, 0.1, 0.15, 0.3, 0.5, 1, 2, 5, 10, 25),
)
