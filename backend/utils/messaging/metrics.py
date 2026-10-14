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
