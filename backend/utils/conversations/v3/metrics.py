"""Static-label v3 rollout and builder meters."""

import logging
from collections.abc import Callable
from contextlib import contextmanager
from threading import Lock

from prometheus_client import Counter, Histogram, Gauge

from database.firestore_write_probe import count_committed_writes, probe_enabled, probe_installed

logger = logging.getLogger(__name__)
_metric_warning_lock = Lock()
_metric_warning_logged = False


def safe_metric(fn: Callable[[], None]) -> None:
    """Treat telemetry as best effort, including its own warning log."""
    global _metric_warning_logged
    try:
        fn()
    except Exception as error:
        with _metric_warning_lock:
            if _metric_warning_logged:
                return
            _metric_warning_logged = True
        try:
            logger.warning('v3 reconcile telemetry failed exception_type=%s', type(error).__name__)
        except Exception:
            pass


RECONCILES = Counter('omi_conversations_v3_reconciles_total', 'Builder and processing outcomes', ['outcome'])
BLOCKED = Counter(
    'omi_conversations_v3_blocked_total', 'Deterministic reconcile conflicts parked behind owner backoff', ['reason']
)
RACES = Counter(
    'omi_conversations_v3_races_total',
    'Retryable reconcile outcomes answered with a coalesced wake or a task retry',
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

FINISH_NO_POINTER = Counter(
    'omi_conversations_v3_finish_no_pointer_total',
    'No-pointer Finish API outcomes, whole-record batch resolution, and first settlement',
    ['outcome'],
)
for outcome in (
    'cut',
    'already_cut',
    'already_empty',
    'resolved_empty',
    'requested',
    'already_requested',
    'request_conflict',
    'no_live_window',
    'disabled',
    'owner_not_enabled',
    'recording_lookup_capped',
    'window_lookup_capped',
    'recording_ambiguous',
    'recording_ineligible',
    'recording_requested',
    'recording_cut',
    'named_recording_cut',
    'named_recording_requested',
    'newer_recording_cut',
    'newer_recording_requested',
    'newer_already_cut',
    'newer_already_requested',
    'newer_already_empty',
    'newer_resolved_empty',
    'newer_consumed',
    'newer_recording_ineligible',
    'newer_batch_unavailable',
    'newer_batch_disabled',
    'newer_dual_cut',
    'newer_dual_requested',
    'newer_dual_consumed',
    'newer_dual_already_cut',
    'newer_dual_already_requested',
    'newer_dual_already_empty',
    'newer_dual_resolved_empty',
    'named_not_finishable',
    'named_superseded',
    'already_visible',
    'no_recording',
    'batch_disabled',
    'batch_unavailable',
    'consumed',
    'whole_record_consumed',
    'whole_record_resolved_empty',
    'whole_record_redirected',
    'settled',
):
    FINISH_NO_POINTER.labels(outcome)

BATCH_MANUAL_END = Counter(
    'omi_conversations_v3_batch_manual_end_total',
    'Manual-end requests of audio-only v3 recordings at record admission, by what admission did with them',
    ['outcome'],
)
for outcome in ('promoted', 'fast_finish', 'multi_unit_deferred', 'not_promoted', 'error'):
    BATCH_MANUAL_END.labels(outcome)

FINISH_HELD = Counter(
    'omi_conversations_v3_finish_held_total',
    'Builder passes that kept a manual-end cut open while its own or a preceding batch transcript was pending',
)

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


AUDIO_PURGES = Counter(
    'omi_conversations_v3_audio_purges_total',
    'Released-recording audio purge steps: custody invalidated, held, intake purge pending or failed, audio erased',
    ['outcome'],
)
for outcome in ('custody_invalidated', 'held', 'intakes_pending', 'intakes_failed', 'erased'):
    AUDIO_PURGES.labels(outcome)


PROJECTION_ROWS = Histogram(
    'omi_conversations_v3_projection_rows',
    'Distinct conversation rows written or skipped per completed projection or pending mark, for nonzero outcomes',
    ['caller', 'outcome'],
    buckets=(0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 90, 130),
)


def projection_writes(caller, written, skipped):
    if written:
        safe_metric(lambda: PROJECTION_ROWS.labels(caller, 'written').observe(written))
    if skipped:
        safe_metric(lambda: PROJECTION_ROWS.labels(caller, 'skipped').observe(skipped))


EQUALITY_UNAVAILABLE = Counter(
    'omi_conversations_v3_equality_unavailable_total',
    'Comparisons that could not establish equality and fell back to a write',
)


RECONCILE_BILLED_WRITES = Histogram(
    'omi_conversations_v3_reconcile_billed_writes',
    'Confirmed Firestore writes per builder pass chain including leases and commit-hook writes',
    ['caller'],
    buckets=(0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 90, 130),
)


RECONCILE_PROBE_MISSING = Counter(
    'omi_conversations_v3_reconcile_probe_missing_total',
    'Builder pass chains without an installed Firestore write probe when enabled',
)


@contextmanager
def measure_reconcile_writes(caller):
    if not probe_enabled():
        yield
        return
    if not probe_installed():
        safe_metric(lambda: RECONCILE_PROBE_MISSING.inc())
        yield
        return
    with count_committed_writes() as writes:
        try:
            yield
        finally:
            safe_metric(lambda: RECONCILE_BILLED_WRITES.labels(caller).observe(writes.total))
