"""Bounded migration telemetry. No user, episode or exception-string labels."""

from prometheus_client import Counter, Histogram, Gauge

from utils.episodes.metrics import reuse_or_create, bounded_label
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
DRIFT_OUTCOMES = frozenset({'match', 'mismatch', 'missing_legacy', 'missing_view'})
DRAIN_OUTCOMES = frozenset({'drained', 'error', 'lost_lease'})
SWEEP_OUTCOMES = frozenset({'redriven', 'error'})
DRIFT = reuse_or_create(
    Counter, 'omi_episode_view_drift_total', 'Legacy vs log projection digests.', ['field', 'outcome']
)
COMPARE_SKIPPED = reuse_or_create(
    Counter, 'omi_episode_view_compare_skipped_total', 'Comparisons deferred until an aligned watermark.', ['reason']
)
SWEEP_OBSERVED = reuse_or_create(
    Gauge, 'omi_episode_drain_sweep_observed_at_seconds', 'Last successful bounded sweep.', []
)
DRAIN = reuse_or_create(Counter, 'omi_episode_drain_total', 'Drain attempts by bounded outcome.', ['outcome'])
SWEEP = reuse_or_create(Counter, 'omi_episode_drain_sweep_total', 'Bounded sweep outcomes.', ['outcome'])
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

# Alert inputs exist at zero before the first failure instead of appearing only
# with an inaugural nonzero sample, which increase() cannot compare to zero.
for _field in FIELDS:
    for _outcome in DRIFT_OUTCOMES:
        DRIFT.labels(field=_field, outcome=bounded_label(_outcome, DRIFT_OUTCOMES))
for _phase in ('queued', 'running', 'retrying'):
    OVERDUE.labels(phase=_phase)
for _outcome in DRAIN_OUTCOMES:
    DRAIN.labels(outcome=bounded_label(_outcome, DRAIN_OUTCOMES))
for _outcome in SWEEP_OUTCOMES:
    SWEEP.labels(outcome=bounded_label(_outcome, SWEEP_OUTCOMES))


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
    for key in ('member_activity', 'parallel_content_spans'):
        result[key] = result[key] or {}
    home = result.get('home_row')
    if isinstance(home, dict):
        home = {key: value for key, value in home.items() if key != 'state_updated_at'}
        home['conversation_ids'] = sorted(home.get('conversation_ids') or [])
        home['members'] = sorted(home.get('members') or [], key=lambda member: member['id'])
        result['home_row'] = home
    result['content_hash'] = digest({key: row.get(key) or ('' if key in {'title', 'lede'} else []) for key in CONTENT})
    return result


def differences(legacy, view):
    left, right = comparable(legacy), comparable(view)
    if left is None and right is None:
        return {field: 'match' for field in FIELDS}
    if left is None or right is None:
        return {field: 'missing_legacy' if left is None else 'missing_view' for field in FIELDS}
    return {field: 'match' if digest(left[field]) == digest(right[field]) else 'mismatch' for field in FIELDS}


def compare(legacy, view, *, reread=None):
    outcomes = differences(legacy, view)
    if reread and any(value != 'match' for value in outcomes.values()):
        legacy = reread()
        outcomes = differences(legacy, view)
    for field, outcome in outcomes.items():
        DRIFT.labels(field=field, outcome=bounded_label(outcome, DRIFT_OUTCOMES)).inc()
    return outcomes
