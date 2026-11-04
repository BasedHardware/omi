"""Bounded migration telemetry. No user, episode or exception-string labels."""

from prometheus_client import Counter, Histogram, Gauge

from utils.episodes.metrics import reuse_or_create
from utils.episodes.log.codec import digest

FIELDS = (
    'status',
    'close_reason',
    'started_at',
    'recorded_end',
    'last_activity_at',
    'conversation_ids',
    'discarded_conversation_ids',
    'duplicate_conversation_ids',
    'recovered_conversation_ids',
    'recorded_members',
    'member_activity',
    'recorded_merged_into',
    'sources',
    'parallel_content_spans',
    'composed_fingerprint',
    'wrap_up_requested_at',
    'closing_conversation_id',
    'content_hash',
    'home_row',
)
CONTENT = ('title', 'bullets', 'lede', 'follow_ups', 'people', 'open_questions', 'provisional_items', 'moments')
DRIFT = reuse_or_create(
    Counter, 'omi_episode_view_drift_total', 'Legacy vs log projection digests.', ['field', 'outcome']
)
SWEEP_OBSERVED = reuse_or_create(
    Gauge, 'omi_episode_drain_sweep_observed_at_seconds', 'Last successful bounded sweep.', []
)
DRAIN = reuse_or_create(Counter, 'omi_episode_drain_total', 'Drain attempts by bounded outcome.', ['outcome'])
SECONDS = reuse_or_create(
    Histogram,
    'omi_episode_drain_seconds',
    'Drain wall time.',
    ['outcome'],
    buckets=(0.1, 1, 5, 15, 30, 60, 120, 300, 600),
)
DWELL = reuse_or_create(
    Histogram,
    'omi_episode_drain_dwell_seconds',
    'Automatic phase dwell at exit/observation.',
    ['phase'],
    buckets=(1, 30, 60, 180, 300, 600, 900, 1500, 1800, 3600),
)
OVERDUE = reuse_or_create(Counter, 'omi_episode_drain_deadline_total', 'Automatic phase deadline breaches.', ['phase'])


def observe_state(state, phase, now):
    if phase not in {'queued', 'running', 'retrying'}:
        return
    entered = state.get(f'{phase}_entered_at')
    deadline = state.get({'queued': 'queued_deadline_at', 'running': 'lease_until', 'retrying': 'retry_at'}[phase])
    if entered:
        DWELL.labels(phase=phase).observe(max(0, (now - entered).total_seconds()))
    if deadline and now > deadline:
        OVERDUE.labels(phase=phase).inc()


def comparable(row):
    if row is None:
        return None
    result = {key: row.get(key) for key in FIELDS}
    for key in (
        'conversation_ids',
        'discarded_conversation_ids',
        'duplicate_conversation_ids',
        'recovered_conversation_ids',
        'sources',
    ):
        result[key] = sorted(result[key] or [])
    result['content_hash'] = digest({key: row.get(key) for key in CONTENT})
    return result


def differences(legacy, view):
    left, right = comparable(legacy), comparable(view)
    if left is None or right is None:
        return {field: 'missing_legacy' if left is None else 'missing_view' for field in FIELDS}
    return {field: 'match' if digest(left[field]) == digest(right[field]) else 'mismatch' for field in FIELDS}


def compare(legacy, view, *, reread=None):
    outcomes = differences(legacy, view)
    if reread and any(value != 'match' for value in outcomes.values()):
        legacy = reread()
        outcomes = differences(legacy, view)
    for field, outcome in outcomes.items():
        DRIFT.labels(field=field, outcome=outcome).inc()
    return outcomes
