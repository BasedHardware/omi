"""Dark finish-backoff lever: identical output, no reads when a walk changed nothing.

The lever (``BATCH_PROJECTION_FINISH_BACKOFF_ENABLED``) is off by default. Off,
the finish page is exactly the legacy page. Clock writes are unconditional. On,
a no-change walk stamps a durable next-attempt clock and the page filters on it,
which is what removes the projection replay reads. Any state move clears the
clock in the same write, so no obligation waits on it, and the ``pending``
assignment page is never filtered, so new work is never delayed.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from google.cloud import firestore
import pytest

from database.batch_pipeline_projection import ProjectionBlocked, ProjectionStore
from database.batch_pipeline_projection_finish import (
    PROJECTION_FINISH_DUE_FIELD,
    PROJECTION_FINISH_STEP_FIELD,
    projection_finish_entry_fields,
    projection_finish_state_fields,
)
from database.batch_pipeline_store import projection_page
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain, projector_for
from tests.unit.test_batch_pipeline_sweep_owner_chain import Recording

LEVER = 'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED'
SWITCHES = (
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED',
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED',
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def claim(*_):
        yield True

    from utils.batch_pipeline import projection, projection_followup

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    for name in (*SWITCHES, 'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', LEVER):
        monkeypatch.delenv(name, raising=False)


def finish_log(*, persisted=2):
    """Synchronous-policy rows already persisted, so only the finish page sees them."""
    log = ResultLog(async_projection=False)
    ids = chain(log, BURST, 'a', persisted)
    for sid in ids:
        log.results[sid]['projection_state'] = 'persisted'
        log.results[sid][PROJECTION_FINISH_DUE_FIELD] = 1.0
        log.results[sid]['projection'] = {'state': 'persisted', 'conversation_id': None, 'enrichment_required': False}
    return log, ids


def silent_projector(log, now=1000.0):
    log.projection_finish_backfill_complete = Mock(return_value=True)
    projector = projector_for(log)
    projector.clock = lambda: now
    # The walk changes nothing: this is the replay A-1 bounds.
    projector._finish = Mock(return_value=None)
    return projector


def test_flag_off_uses_legacy_page_without_deferral_or_marker_reads():
    log, ids = finish_log()
    projector = silent_projector(log)
    recorder = Recording(log)
    projector.store = recorder
    projector.finish_discovery.store = recorder
    counts = projector.sweep(limit=10)
    pages = [call for call in recorder.calls if call[0] == 'projection_page']
    # The exact legacy call: the finish page passes no clock filter at all.
    finish = [dict(call[2]) for call in pages if dict(call[2])['states'] == ('persisted', 'ready')]
    assert finish and all('due_before' not in page for page in finish)
    assert counts == {'completed': 0, 'waiting': len(ids), 'blocked': 0, 'error': 0}
    for sid in ids:
        assert log.results[sid][PROJECTION_FINISH_DUE_FIELD] == 1.0
        assert PROJECTION_FINISH_STEP_FIELD not in log.results[sid]
    assert [call for call in recorder.calls if call[0] == 'defer_finish'] == []
    assert projection_finish_state_fields('ready', 5.0)[PROJECTION_FINISH_DUE_FIELD] == 5.0
    log.projection_finish_backfill_complete.assert_not_called()


def test_no_change_walk_defers_60_then_300_then_900_and_caps(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    now = [1000.0]
    projector = silent_projector(log)
    projector.clock = lambda: now[0]
    row = log.results[ids[0]]

    expected = [60.0, 300.0, 900.0, 900.0]
    for tick, delay in enumerate(expected):
        now[0] = 1000.0 + tick * 1000
        projector.sweep(limit=10)
        assert row[PROJECTION_FINISH_DUE_FIELD] == now[0] + delay
        assert row[PROJECTION_FINISH_STEP_FIELD] == min(tick, 2)


def test_a_deferred_row_leaves_the_page_until_its_clock_passes(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    now = [1000.0]
    projector = silent_projector(log)
    projector.clock = lambda: now[0]
    projector.sweep(limit=10)
    # One tick later every stamped row is still deferred: the page reads nothing.
    now[0] += 10
    recorder = Recording(log)
    projector.store = recorder
    projector.finish_discovery.store = recorder
    counts = projector.sweep(limit=10)
    assert counts == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
    # Past the 60 s delay the same rows are due again.
    now[0] += 60
    counts = projector.sweep(limit=10)
    assert counts['waiting'] == len(ids)


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_a_state_change_clears_both_fields_in_the_same_write(monkeypatch, enabled):
    from tests.unit.test_batch_pipeline_quarantine import projection_fixture

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client, store, binding = projection_fixture()
    row = ('batch_pipeline_dev_results', 'good')
    client.rows[row]['projection_state'] = 'persisted'
    client.rows[row][PROJECTION_FINISH_DUE_FIELD] = 9.0
    client.rows[row][PROJECTION_FINISH_STEP_FIELD] = 1
    monkeypatch.setenv(LEVER, enabled)
    assert projection_finish_state_fields('ready', 5.0) == {
        PROJECTION_FINISH_DUE_FIELD: 5.0,
        PROJECTION_FINISH_STEP_FIELD: 0,
    }
    assert projection_finish_state_fields('completed', 5.0) == {
        PROJECTION_FINISH_DUE_FIELD: firestore.DELETE_FIELD,
        PROJECTION_FINISH_STEP_FIELD: firestore.DELETE_FIELD,
    }
    assert store.hold_for_quarantine('good', binding, 100)
    assert client.rows[row]['projection_state'] == 'ready'
    patches = [dict(patch) for _path, patch in client.transactions[-1].updates]
    assert any(PROJECTION_FINISH_DUE_FIELD in patch for patch in patches)
    assert any(PROJECTION_FINISH_STEP_FIELD in patch for patch in patches)
    # Entering a finish state stamps the clock as due now, so the filtered page
    # still sees a row that the lever did not survey.
    receipt = store.ready('good', binding, 200)
    assert receipt['state'] == 'ready'
    patches = [dict(patch) for _path, patch in client.transactions[-1].updates]
    stamped = [patch for patch in patches if patch.get(PROJECTION_FINISH_DUE_FIELD) == 200.0]
    assert stamped and stamped[0][PROJECTION_FINISH_STEP_FIELD] == 0
    # A clearing transition writes DELETE_FIELD, not a fresh timestamp.
    ledger = client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]
    ledger['status'] = 'completed'
    ledger['result'] = {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'}
    store.acknowledge('good', binding, 300)
    patches = [dict(patch) for _path, patch in client.transactions[-1].updates]
    cleared = [patch for patch in patches if patch.get(PROJECTION_FINISH_DUE_FIELD) is firestore.DELETE_FIELD]
    assert cleared and cleared[0][PROJECTION_FINISH_STEP_FIELD] is firestore.DELETE_FIELD
    # Off, writers still stamp the clock for later filtered discovery.
    monkeypatch.setenv(LEVER, 'false')
    assert projection_finish_state_fields('ready', 5.0)[PROJECTION_FINISH_DUE_FIELD] == 5.0


def test_defer_finish_fence_refuses_a_row_that_moved_on():
    rows = {
        ('batch_pipeline_dev_results', 'good'): {
            'projection_state': 'ready',
            'committed_at': 1.0,
        }
    }
    client = StrictFirestore(rows)
    store = ProjectionStore(SimpleNamespace(client=client, namespace='batch_pipeline_dev'))
    # The sweep read ``persisted``; by the fence the row is ``ready``.
    assert store.defer_finish('good', 'persisted', 1000.0) is False
    row = client.rows[('batch_pipeline_dev_results', 'good')]
    assert PROJECTION_FINISH_DUE_FIELD not in row
    # The unchanged case stamps the clock and the escalation step.
    assert store.defer_finish('good', 'ready', 1000.0) is True
    assert row[PROJECTION_FINISH_DUE_FIELD] == 1060.0
    assert row[PROJECTION_FINISH_STEP_FIELD] == 0
    assert store.defer_finish('good', 'ready', 2000.0) is True
    assert row[PROJECTION_FINISH_DUE_FIELD] == 2300.0


def test_assignment_page_is_never_filtered_by_the_clock():
    log, _ids = finish_log()
    log.commit(BURST, 'b', 'pending-0', ['pending-0'])
    log.results['pending-0'][PROJECTION_FINISH_DUE_FIELD] = 1e12
    projector = silent_projector(log)
    recorder = Recording(log)
    projector.store = recorder
    projector.assignment_discovery.store = recorder
    projector.finish_discovery.store = recorder
    projector.sweep(limit=10)
    assignment = [dict(call[2]) for call in recorder.calls if call[0] == 'projection_page']
    pending = [page for page in assignment if page['states'] == ('pending',)]
    assert pending and all('due_before' not in page for page in pending)


def test_replay_still_completes_and_is_counted_not_lost(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    # Already-projected rows keep their receipt: the walk replays and counts them.
    calls = []
    projector = silent_projector(log)
    projector._finish = Mock(side_effect=lambda sid, *_a: calls.append(sid))
    counts = projector.sweep(limit=10)
    assert calls == ids
    assert counts['waiting'] == len(ids)


def test_same_output_with_the_flag_on_and_off():
    """Parity: the filtered tick walks the same rows in the same order."""
    outcomes = []
    for enabled in (False, True):
        log, ids = finish_log(persisted=3)
        now = [1000.0]
        projector = silent_projector(log)
        projector.clock = lambda: now[0]
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv(LEVER, 'true' if enabled else 'false')
        try:
            # Both ticks filter immediately once the shared marker exists.
            projector.sweep(limit=10)
            now[0] += 60
            projector._finish.reset_mock()
            recorder = Recording(log)
            projector.store = recorder
            projector.finish_discovery.store = recorder
            counts = projector.sweep(limit=10)
            walked = [call.args[0] for call in projector._finish.call_args_list]
            pages = [
                dict(call[2])
                for call in recorder.calls
                if call[0] == 'projection_page' and dict(call[2])['states'] == ('persisted', 'ready')
            ]
        finally:
            monkeypatch.undo()
        outcomes.append((counts, walked, ids, pages))
    assert outcomes[0][:3] == outcomes[1][:3]
    assert outcomes[0][0] == {'completed': 0, 'waiting': 3, 'blocked': 0, 'error': 0}
    # Off never filters; on filters immediately after reading the shared marker.
    assert all('due_before' not in page for page in outcomes[0][3])
    assert any(page.get('due_before') is not None for page in outcomes[1][3])


def test_a_blocked_row_is_deferred_and_revisited_when_due(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log(persisted=2)
    now = [1000.0]
    projector = silent_projector(log)
    projector.clock = lambda: now[0]
    blocked = ids[0]

    def finish(sid, *_args):
        if sid == blocked:
            raise ProjectionBlocked('synthetic block')
        return None

    projector._finish = Mock(side_effect=finish)
    counts = projector.sweep(limit=10)
    assert counts['blocked'] == 1
    # A blocked row keeps its durable retry clock.
    assert log.results[blocked][PROJECTION_FINISH_DUE_FIELD] == 1060.0
    now[0] += 60
    projector._finish = Mock(return_value=None)
    projector.sweep(limit=10)
    assert blocked in [call.args[0] for call in projector._finish.call_args_list]


def test_kill_switch_flip_restores_the_legacy_page_on_the_next_tick(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    now = [1000.0]
    projector = silent_projector(log)
    projector.clock = lambda: now[0]
    projector.sweep(limit=10)
    assert all(PROJECTION_FINISH_DUE_FIELD in log.results[sid] for sid in ids)
    # Flip the switch off mid-run: the next tick is the unfiltered legacy page.
    monkeypatch.setenv(LEVER, 'false')
    now[0] += 1
    counts = projector.sweep(limit=10)
    assert counts['waiting'] == len(ids)
    recorder = Recording(log)
    projector.store = recorder
    projector.finish_discovery.store = recorder
    projector.sweep(limit=10)
    finish = [
        dict(call[2])
        for call in recorder.calls
        if call[0] == 'projection_page' and dict(call[2])['states'] == ('persisted', 'ready')
    ]
    assert finish and all('due_before' not in page for page in finish)


def test_projection_page_due_cursor_and_seed_shapes():
    class Query:
        def __init__(self):
            self.calls = []

        def where(self, field, op, value):
            self.calls.append(('where', field, op, value))
            return self

        def order_by(self, field):
            self.calls.append(('order_by', field))
            return self

        def start_at(self, values):
            self.calls.append(('start_at', dict(values)))
            return self

        def start_after(self, values):
            self.calls.append(('start_after', dict(values)))
            return self

        def limit(self, size):
            self.calls.append(('limit', size))
            return self

        def stream(self):
            return []

    class Collection(Query):
        def document(self, key):
            return ('doc', key)

    class Client:
        def __init__(self):
            self.collection_query = Collection()

        def collection(self, name):
            return self.collection_query

    client = Client()
    projection_page(client, 'batch_pipeline_dev', 200, states=('persisted', 'ready'), due_before=50.0, after=(40.0,))
    calls = client.collection_query.calls
    assert ('where', PROJECTION_FINISH_DUE_FIELD, '<=', 50.0) in calls
    # The range field leads the ordering, then the committed log and the key.
    ordered = [call[1] for call in calls if call[0] == 'order_by']
    assert ordered == [PROJECTION_FINISH_DUE_FIELD, 'committed_at', '__name__']
    assert ('start_at', {PROJECTION_FINISH_DUE_FIELD: 40.0}) in calls

    client = Client()
    projection_page(client, 'batch_pipeline_dev', 200, after=(40.0, 7.0, 'k'), due_before=50.0)
    assert (
        'start_after',
        {PROJECTION_FINISH_DUE_FIELD: 40.0, 'committed_at': 7.0, '__name__': ('doc', 'k')},
    ) in client.collection_query.calls


def test_the_finish_index_is_declared_for_both_namespaces():
    from database.firestore_index_registry import firebase_index_manifest

    fields = [
        index['fields']
        for index in firebase_index_manifest()['indexes']
        if index['collectionGroup'] in ('batch_pipeline_prod_results', 'batch_pipeline_dev_results')
        and any(field['fieldPath'] == PROJECTION_FINISH_DUE_FIELD for field in index['fields'])
    ]
    assert len(fields) == 2
    for index_fields in fields:
        assert [field['fieldPath'] for field in index_fields] == [
            'projection_state',
            PROJECTION_FINISH_DUE_FIELD,
            'committed_at',
            '__name__',
        ]


def test_missing_marker_uses_legacy_without_stamp_transactions(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    projector = silent_projector(log)
    log.projection_finish_backfill_complete.return_value = False
    log.defer_finish = Mock()
    projector.finish_backoff.monotonic = Mock(return_value=10.0)
    for _ in range(3):
        assert projector.sweep(limit=10)['waiting'] == len(ids)
    log.defer_finish.assert_not_called()
    assert log.projection_finish_backfill_complete.call_count == 1
    # The maintenance pass finishes; the next bounded check switches queries.
    log.projection_finish_backfill_complete.return_value = True
    projector.finish_backoff.monotonic.return_value = 70.0
    projector.sweep(limit=10)
    assert projector.finish_discovery.due_mode is True
    assert log.defer_finish.call_count == len(ids)


def test_new_replicas_and_reenable_trust_shared_completion(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log()
    first = silent_projector(log)
    first.sweep(limit=10)
    second = silent_projector(log)
    assert second.sweep(limit=10)['waiting'] == 0
    assert second.finish_discovery.due_mode is True
    monkeypatch.setenv(LEVER, 'false')
    second.sweep(limit=10)
    monkeypatch.setenv(LEVER, 'true')
    assert second.sweep(limit=10)['waiting'] == 0
    assert log.projection_finish_backfill_complete.call_count == 1


def test_flag_off_writer_fields_remain_discoverable_on_listen_host(monkeypatch):
    monkeypatch.setenv(LEVER, 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    for state in ('persisted', 'ready'):
        assert projection_finish_entry_fields(state, 123.0) == {
            PROJECTION_FINISH_DUE_FIELD: 123.0,
            PROJECTION_FINISH_STEP_FIELD: 0,
        }
        assert projection_finish_state_fields(state, 123.0) == projection_finish_entry_fields(state, 123.0)


def test_defer_failure_keeps_existing_clock_due(monkeypatch):
    monkeypatch.setenv(LEVER, 'true')
    log, ids = finish_log(persisted=1)
    projector = silent_projector(log)
    real = log.defer_finish
    log.defer_finish = Mock(side_effect=RuntimeError('synthetic failure'))
    projector.sweep(limit=10)
    assert log.results[ids[0]][PROJECTION_FINISH_DUE_FIELD] == 1.0
    log.defer_finish = real
    assert projector.sweep(limit=10)['waiting'] == 1
    assert log.results[ids[0]][PROJECTION_FINISH_DUE_FIELD] == 1060.0
