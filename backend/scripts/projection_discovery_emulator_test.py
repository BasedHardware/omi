# LIFECYCLE: permanent
"""PL-606/607/608: projection discovery on old Firestore, Postgres and sim.

These are scheduling hints, never projection completion or privacy authority.
The same public Store queries must preserve owed work across clock selection,
pagination and rollback. Require OMI_REQUIRE_STORE_BACKENDS=all for full proof.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from testing.store_fixtures import store_backend  # noqa: F401

pytestmark = pytest.mark.integration
STATES = ('persisted', 'ready')
FOLLOWUP = 'projection_followup_due_at'
FINISH = 'projection_finish_due_at'


@pytest.fixture
def h(store_backend):  # noqa: F811
    store_backend.seed_user('owner')
    return store_backend


def put(h, key, *, state='ready', committed=1.0, followup=10.0, finish=-1.0):
    job = {
        'segment_id': key,
        'owner_id': h.uid('owner'),
        'owner_key': f'ok-{h.uid("owner")}',
        'state': 'result_ready',
        'capture_at': 1.0,
        'enqueued_at': 1.0,
        'privacy_generation': 0,
    }
    result = {
        **job,
        'projection_state': state,
        'committed_at': committed,
        'projection': {'state': state, 'receipt': f'synthetic-{key}'},
        'policy_id': 'synthetic-immutable-policy',
        'audio_uri': f'gs://synthetic-only/{key}',
        FINISH: finish,
    }
    if followup is not None:
        result[FOLLOWUP] = followup

    def commit(tx):
        tx.put('jobs', key, job)
        tx.put('results', key, result)

    h.store.run(commit)
    return result


def read(h, key):
    return h.store.run(lambda tx: tx.get('results', key))


@pytest.mark.parametrize('state', STATES)
def test_pl606_future_prefix_cannot_spend_due_followup_page(h, state):
    before = {f'old-{i}': put(h, f'old-{i}', state=state, committed=0.0, followup=1000.0) for i in range(5)}
    before['boundary'] = put(h, 'boundary', state=state, committed=5.0, followup=100.0)
    before['later'] = put(h, 'later', state=state, followup=100.001)
    before['legacy'] = put(h, 'legacy', state=state, followup=None)
    before['pending'] = put(h, 'pending', state='pending', followup=1.0)
    before['completed'] = put(h, 'completed', state='completed', followup=1.0)

    # Filtering after LIMIT would return only an old deferred row, hiding the
    # exact-boundary obligation.
    ids, _ = h.store.projection_page(1, states=STATES, followup_due_before=100.0)
    assert ids == ['boundary']
    assert h.store.projection_page(20, states=STATES, followup_due_before=100.001)[0] == ['boundary', 'later']
    assert 'legacy' in h.store.projection_page(20, states=STATES)[0]
    assert {key: read(h, key) for key in before} == before


@pytest.mark.parametrize('state', STATES)
def test_pl607_async_exclusion_belongs_only_to_finish_clock(h, state):
    before = {
        'async': put(h, 'async', state=state, followup=100.0, finish=-1.0),
        'sync': put(h, 'sync', state=state, followup=200.0, finish=80.0),
        'both': put(h, 'both', state=state, followup=100.0, finish=90.0),
    }
    assert h.store.projection_page(10, states=STATES, due_before=100.0, exclude_async=True)[0] == ['sync', 'both']
    # Passing the finish option must not filter the independent follow-up clock.
    for exclude_async in (False, True):
        assert h.store.projection_page(10, states=STATES, followup_due_before=100.0, exclude_async=exclude_async)[
            0
        ] == ['async', 'both']
    # Old readers/rollback still see retained async receipts as due.
    assert h.store.projection_page(10, states=STATES, due_before=100.0)[0] == ['async', 'sync', 'both']
    assert set(h.store.projection_page(10, states=STATES, exclude_async=True)[0]) == set(before)
    with pytest.raises(ValueError):
        h.store.projection_page(10, states=STATES, due_before=100.0, followup_due_before=100.0)
    assert {key: read(h, key) for key in before} == before


@pytest.mark.parametrize('limit', [1, 2])
@pytest.mark.parametrize('cursor_move', ['completed', 'deferred'])
def test_pl608_due_cursor_survives_source_move_and_future_tail(h, limit, cursor_move):
    for key in ('B', 'a', 'z', 'ä'):
        put(h, key, followup=10.0)
    put(h, 'future', followup=101.0)
    args = {'states': STATES, 'followup_due_before': 100.0}
    first, cursor = h.store.projection_page(limit, **args)
    expected = ['B', 'a', 'z', 'ä']
    assert first == expected[:limit] and cursor == (10.0, 1.0, first[-1])

    # The saved cursor consists of values, so the original row need not remain
    # in the query. A fresh caller resumes using just that cursor and cutoff.
    moved = read(h, first[-1])
    if cursor_move == 'completed':
        moved['projection_state'] = 'completed'
    else:
        moved[FOLLOWUP] = 200.0
    h.store.run(lambda tx: tx.put('results', first[-1], moved))
    put(h, 'behind', committed=0.0, followup=9.0)
    seen = list(first)
    for tick in range(6):
        # Newly due work belongs to the next fixed-cutoff pass. It cannot keep
        # this pass alive forever, or displace the remaining equal-clock rows.
        put(h, f'tail-{tick}', followup=101.0 + tick)
        page, cursor = h.store.projection_page(limit, after=cursor, **args)
        assert len(page) <= limit
        seen.extend(page)
        if cursor is None:
            break
    else:
        pytest.fail('fixed-cutoff discovery did not terminate')
    assert seen == expected
    wrapped = h.store.projection_page(20, **args)[0]
    assert wrapped == ['behind', *(key for key in expected if key != first[-1])]
    assert read(h, first[-1]) == moved
    # Advancing the cutoff eventually reaches work excluded from the old pass.
    assert 'future' in h.store.projection_page(20, states=STATES, followup_due_before=200.0)[0]
