"""Static-label v3 rollout and builder meters."""

from prometheus_client import Counter, Histogram, Gauge

RECONCILES = Counter('omi_conversations_v3_reconciles_total', 'Builder outcomes', ['outcome'])
BLOCKED = Counter(
    'omi_conversations_v3_blocked_total', 'Deterministic reconcile conflicts parked behind owner backoff', ['reason']
)
RACES = Counter(
    'omi_conversations_v3_races_total',
    'Retryable reconcile races answered with a coalesced follow-up wake instead of a task retry',
    ['reason'],
)
CREATED_DELIVERIES = Counter(
    'omi_conversations_v3_created_deliveries_total',
    'Conversation-created integration deliveries for derived conversations',
    ['outcome'],
)
ADOPTED = Counter('omi_conversations_v3_adopted_total', 'Existing derived rows adopted as a replanned prior')
PENDING_AGE = Histogram(
    'omi_conversations_v3_pending_age_seconds', 'Pending recording age', buckets=(60, 300, 600, 1800, 3600, 86400)
)
VISIBLE_LATENCY = Histogram(
    'omi_conversations_v3_first_speech_to_visible_seconds', 'First speech to visible projection'
)
SUMMARY_LATENCY = Histogram('omi_conversations_v3_end_to_summary_seconds', 'End to stored summary')
SUMMARY_WRITES = Counter('omi_conversations_v3_summary_writes_total', 'First writes and late rewrites', ['kind'])
MODEL_CALLS = Counter('omi_conversations_v3_model_calls_total', 'Metered model calls', ['kind'])
NON_V3 = Gauge(
    'omi_conversations_v3_active_pendant_users_legacy',
    'Daily active pendant users whose latest capture is not a recording',
)
EPISODE_CALLS = Counter(
    'omi_episode_endpoint_calls_total',
    'Episode calls during v3 migration',
    ['endpoint', 'app_channel', 'app_version', 'v3'],
)
EPISODE_COMPOSES = Counter('omi_episode_composes_total', 'Episode composition attempts', ['v3'])

UNCERTAIN_SHOWN = Counter(
    "omi_conversations_v3_uncertain_recognition_shown_total",
    "Committed windows shown because wearer recognition is uncertain",
)


TERMINAL_FAILURES = Counter(
    'omi_conversations_v3_terminal_failures_total', 'Committed v3 failure transitions', ['reason']
)


def terminal_failure(reason):
    TERMINAL_FAILURES.labels(
        reason if reason in {'outline', 'transcription', 'attempts_exhausted'} else 'processing'
    ).inc()
