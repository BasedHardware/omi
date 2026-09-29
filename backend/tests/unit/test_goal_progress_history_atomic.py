"""History is a projection committed by the goal journal, never by its caller.

The shared strict fixture guards transactional read/write ordering. Real rollback
and interleaved-writer proofs live in test_goal_progress_history_emulator.py.
"""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from database import goals
from models.goal import GoalMetric, GoalProgressEventCreate, GoalProgressEventKind, GoalType
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

GOAL_PATH = ('users', 'u1', 'goals', 'g1')


@pytest.fixture
def store(monkeypatch):
    now = datetime(2026, 9, 27, 2, 30, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(goals, 'datetime', FrozenDatetime)
    original_get = StrictFirestoreDocument.get

    def get_with_identity(reference, *args, **kwargs):
        snapshot = original_get(reference, *args, **kwargs)
        snapshot.id = reference.path[-1]
        snapshot.reference = reference
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get_with_identity)
    return StrictFirestore(
        {('users', 'u1'): {'time_zone': 'America/Los_Angeles'}, GOAL_PATH: {'id': 'g1', 'title': 'Books'}}
    )


def append(store, key='one', value=7, generation=0):
    return goals.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(
            kind=GoalProgressEventKind.metric_update,
            summary='Books read',
            metric=GoalMetric(type=GoalType.numeric, current=value, target=20),
        ),
        idempotency_key=key,
        account_generation=generation,
        firestore_client=store,
    )


@pytest.mark.parametrize(
    'zone,day', [('America/Los_Angeles', '2026-09-26'), ('Asia/Tokyo', '2026-09-27'), (None, '2026-09-27')]
)
def test_metric_event_commits_history_with_goal_and_journal(store, zone, day):
    store.rows[('users', 'u1')]['time_zone'] = zone
    event = append(store)
    transaction = store.transactions[-1]
    assert len(transaction.creates) == 1
    assert len(transaction.updates) == 1
    assert transaction.sets == [
        ((*GOAL_PATH, 'goal_history', day), {'date': day, 'value': 7, 'recorded_at': event.created_at})
    ]
    assert store.rows[GOAL_PATH]['current_value'] == 7


def test_metricless_event_leaves_existing_history_and_metric_unchanged(store):
    append(store)
    before = deepcopy(store.rows)
    event = goals.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(kind=GoalProgressEventKind.evidence, summary='Started reading'),
        idempotency_key='note',
        account_generation=0,
        firestore_client=store,
    )
    assert event.sequence == 2
    assert store.transactions[-1].sets == []
    assert store.rows[GOAL_PATH]['metric'] == before[GOAL_PATH]['metric']
    assert store.rows[(*GOAL_PATH, 'goal_history', '2026-09-26')] == before[(*GOAL_PATH, 'goal_history', '2026-09-26')]


def test_replay_after_newer_event_performs_no_writes(store):
    original = append(store)
    append(store, key='two', value=8)
    before = deepcopy(store.rows)
    assert append(store) == original
    assert store.rows == before
    assert store.transactions[-1].sets == []
    assert store.transactions[-1].updates == []
    assert store.transactions[-1].creates == []


@pytest.mark.parametrize('failure', ['conflicting_key', 'stale_generation', 'missing_goal'])
def test_rejected_event_leaves_all_projections_unchanged(store, failure):
    append(store)
    if failure == 'missing_goal':
        del store.rows[GOAL_PATH]
    before = deepcopy(store.rows)
    with pytest.raises(goals.GoalStoreError):
        append(
            store, value=9 if failure == 'conflicting_key' else 7, generation=1 if failure == 'stale_generation' else 0
        )
    assert store.rows == before
