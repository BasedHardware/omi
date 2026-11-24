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
WINDOW_CAP_CUTS = Counter(
    'omi_conversations_v3_window_cap_cuts_total', 'Cap boundaries that created a successor in a live projection'
)
ADOPTED = Counter('omi_conversations_v3_adopted_total', 'Existing derived rows adopted as a replanned prior')
PENDING_AGE = Histogram(
    'omi_conversations_v3_pending_age_seconds', 'Pending recording age', buckets=(60, 300, 600, 1800, 3600, 86400)
)
VISIBLE_LATENCY = Histogram(
    'omi_conversations_v3_first_speech_to_visible_seconds', 'First speech to visible projection'
)
MANUAL_END_HOME = Counter(
    'omi_conversations_v3_manual_end_home_total',
    'First successful processing settlement of each live derived manual-end row, by Home visibility and kind',
    ['visibility', 'kind'],
)
MANUAL_END_KINDS = ('conversation', 'media', 'background', 'other')
for outcome in ('visible', 'hidden'):
    for kind in MANUAL_END_KINDS:
        MANUAL_END_HOME.labels(outcome, kind)

BATCH_MANUAL_END = Counter(
    'omi_conversations_v3_batch_manual_end_total',
    'Manual-end requests of audio-only v3 recordings at record admission, by what admission did with them',
    ['outcome'],
)
for outcome in ('promoted', 'fast_finish', 'multi_unit_deferred', 'not_promoted', 'error'):
    BATCH_MANUAL_END.labels(outcome)

SUMMARY_LATENCY = Histogram('omi_conversations_v3_end_to_summary_seconds', 'End to stored summary')
SUMMARY_WRITES = Counter('omi_conversations_v3_summary_writes_total', 'First writes and late rewrites', ['kind'])
WORD_FLOOR_COMPLETIONS = Counter(
    'omi_conversations_v3_word_floor_completions_total',
    'First automatic v3 processing settlements containing Han, kana, Hangul or Thai letters',
    ['method', 'floor'],
)
# Initialize each series so a later first occurrence has a zero baseline.
for method in ('legacy', 'script_aware'):
    for floor in ('below', 'met'):
        WORD_FLOOR_COMPLETIONS.labels(method, floor)

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


def observe_word_floor(legacy_below: bool, script_aware_below: bool) -> None:
    for method, below in (('legacy', legacy_below), ('script_aware', script_aware_below)):
        WORD_FLOOR_COMPLETIONS.labels(method, 'below' if below else 'met').inc()
