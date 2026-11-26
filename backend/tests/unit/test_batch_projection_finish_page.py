"""Projection finish discovery and async classification regression coverage."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from google.cloud import firestore
import pytest

from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_finish import (
    PROJECTION_FINISH_DUE_FIELD,
    PROJECTION_FINISH_STEP_FIELD,
    projection_finish_entry_fields,
    projection_finish_state_fields,
)
from database.batch_pipeline_store import projection_page
from database.batch_pipeline_projection_followup_clock import DUE_FIELD as FOLLOWUP_DUE
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain, projector_for
from tests.unit.test_batch_pipeline_sweep_owner_chain import Recording

from contextlib import contextmanager
from utils.batch_pipeline import projection, projection_followup
from tests.unit.test_batch_pipeline_quarantine import projection_fixture
from database.firestore_index_registry import firebase_index_manifest
import math
import asyncio
from unittest.mock import AsyncMock
from utils.batch_pipeline.serving import Serving
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.metrics import PROJECTION_FINISH_CLASSIFIED, PROJECTION_FINISH_CLASSIFICATION_FAILURES
from google.api_core.exceptions import Aborted
from database.firestore_transaction_retry import FirestoreContentionExhausted
from config.batch_pipeline import projection_finish_classify_page_limit
from config.policy import ProjectionPolicy
from concurrent.futures import ThreadPoolExecutor
import threading

SWITCHES = (
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED',
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED',
)


@pytest.mark.parametrize('state', ['persisted', 'ready'])
@pytest.mark.parametrize('fields', [projection_finish_state_fields, projection_finish_entry_fields])
def test_async_state_move_stamps_independent_followup_clock(state, fields):
    assert fields(state, 123.0, async_projection=True) == {
        PROJECTION_FINISH_DUE_FIELD: -1.0,
        PROJECTION_FINISH_STEP_FIELD: 0,
        FOLLOWUP_DUE: 123.0,
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch):

    @contextmanager
    def claim(*_):
        yield True

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'false')
    for name in (*SWITCHES, 'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED'):
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


def test_legacy_finish_page_replays_without_marker_reads():
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
    assert projection_finish_state_fields('ready', 5.0)[PROJECTION_FINISH_DUE_FIELD] == 5.0
    log.projection_finish_backfill_complete.assert_not_called()


def test_a_state_change_clears_both_fields_in_the_same_write(monkeypatch):

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client, store, binding = projection_fixture()
    row = ('batch_pipeline_dev_results', 'good')
    client.rows[row]['projection_state'] = 'persisted'
    client.rows[row][PROJECTION_FINISH_DUE_FIELD] = 9.0
    client.rows[row][PROJECTION_FINISH_STEP_FIELD] = 1
    assert projection_finish_state_fields('ready', 5.0) == {
        PROJECTION_FINISH_DUE_FIELD: 5.0,
        PROJECTION_FINISH_STEP_FIELD: 0,
        FOLLOWUP_DUE: 5.0,
    }
    assert projection_finish_state_fields('completed', 5.0) == {
        PROJECTION_FINISH_DUE_FIELD: firestore.DELETE_FIELD,
        PROJECTION_FINISH_STEP_FIELD: firestore.DELETE_FIELD,
        FOLLOWUP_DUE: firestore.DELETE_FIELD,
    }
    assert store.hold_for_quarantine('good', binding, 100)
    assert client.rows[row]['projection_state'] == 'ready'
    patches = [dict(patch) for _path, patch in client.transactions[-1].updates]
    assert any(PROJECTION_FINISH_DUE_FIELD in patch for patch in patches)
    assert any(PROJECTION_FINISH_STEP_FIELD in patch for patch in patches)
    # Entering a finish state stamps the clock as due now, so the filtered page
    # can see the row.
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


def test_synchronous_replay_is_counted():
    log, ids = finish_log()
    # Already-projected rows keep their receipt: the walk replays and counts them.
    calls = []
    projector = silent_projector(log)
    projector._finish = Mock(side_effect=lambda sid, *_a: calls.append(sid))
    counts = projector.sweep(limit=10)
    assert calls == ids
    assert counts['waiting'] == len(ids)


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


def test_missing_marker_uses_legacy_finish_page(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = finish_log()
    projector = silent_projector(log)
    log.projection_finish_backfill_complete.return_value = False
    projector.finish_page.monotonic = Mock(return_value=10.0)
    for _ in range(3):
        assert projector.sweep(limit=10)['waiting'] == len(ids)
    assert log.projection_finish_backfill_complete.call_count == 1
    # The maintenance pass finishes; the next bounded check switches queries.
    log.projection_finish_backfill_complete.return_value = True
    projector.finish_page.monotonic.return_value = 70.0
    projector.sweep(limit=10)
    assert projector.finish_discovery.due_mode is True


def test_new_replicas_and_reenable_trust_shared_completion(monkeypatch):
    flag = 'BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED'
    monkeypatch.setenv(flag, 'true')
    log, ids = finish_log()
    first = silent_projector(log)
    assert first.sweep(limit=10)['waiting'] == len(ids)
    second = projector_for(log)
    second._finish = Mock(return_value=None)
    assert second.sweep(limit=10)['waiting'] == len(ids)
    assert second.finish_discovery.due_mode is True
    monkeypatch.setenv(flag, 'false')
    second.sweep(limit=10)
    monkeypatch.setenv(flag, 'true')
    assert second.sweep(limit=10)['waiting'] == len(ids)
    assert log.projection_finish_backfill_complete.call_count == 2


def test_writer_fields_remain_discoverable_on_listen_host(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    for state in ('persisted', 'ready'):
        assert projection_finish_entry_fields(state, 123.0) == {
            PROJECTION_FINISH_DUE_FIELD: 123.0,
            PROJECTION_FINISH_STEP_FIELD: 0,
            FOLLOWUP_DUE: 123.0,
        }
        assert projection_finish_state_fields(state, 123.0) == projection_finish_entry_fields(state, 123.0)


@pytest.mark.parametrize('rows', [1, 200])
def test_async_only_finish_page_has_constant_reads_and_keeps_drain_awake(monkeypatch, rows):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log = ResultLog()
    for n in range(rows):
        sid = f'async-{n}'
        log.commit(f'owner-{n}', sid, sid, [sid], state='persisted')
        log.results[sid][PROJECTION_FINISH_DUE_FIELD] = -1.0
    projector = silent_projector(log)
    recorder = Recording(log)
    projector.store = recorder
    projector.finish_discovery.store = recorder
    for _ in range(3):
        recorder.calls.clear()
        counts = projector.sweep(limit=200)
        assert counts == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
        assert projector.has_async_followups
        assert not [c for c in recorder.calls if c[0] in {'read', 'retire_async_finish'}]
        probes = [
            dict(c[2])
            for c in recorder.calls
            if c[0] == 'projection_page' and dict(c[2]).get('states') == ('persisted', 'ready')
        ]
        assert len(probes) == 2
        assert probes[0]['limit'] == 1
        assert probes[1]['exclude_async'] is True


def test_legacy_async_rows_are_classified_once_and_rollback_sees_them(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = finish_log()
    for sid in ids:
        log.jobs[sid]['policy_parts']['projection'] = {**log.policy, 'async_projection': True}
    projector = silent_projector(log)
    log.read = Mock(wraps=log.read)
    projector.sweep()
    assert log.read.call_count == len(ids)
    assert all(log.results[sid][PROJECTION_FINISH_DUE_FIELD] == -1.0 for sid in ids)
    log.read.reset_mock()
    projector.sweep()
    log.read.assert_not_called()
    assert projector.has_async_followups
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'false')
    projector.sweep()
    assert log.read.call_count == len(ids)
    assert projector.has_async_followups


def test_mixed_finish_page_keeps_sync_behavior(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = finish_log()
    async_sid = ids[0]
    log.jobs[async_sid]['policy_parts']['projection'] = {**log.policy, 'async_projection': True}
    log.results[async_sid][PROJECTION_FINISH_DUE_FIELD] = -1.0
    projector = silent_projector(log)
    counts = projector.sweep()
    assert counts == {'completed': 0, 'waiting': 1, 'blocked': 0, 'error': 0}
    assert [c.args[0] for c in projector._finish.call_args_list] == ids[1:]
    assert projector.has_async_followups


@pytest.mark.parametrize(
    'state,async_policy,retired',
    [
        ('persisted', True, True),
        ('ready', True, True),
        ('pending', True, False),
        ('completed', True, False),
        ('ready', False, False),
        ('ready', None, False),
    ],
)
def test_async_retirement_fences_pinned_policy_and_state(state, async_policy, retired):
    job = {} if async_policy is None else {'policy_parts': {'projection': {'async_projection': async_policy}}}
    client = StrictFirestore(
        {
            ('batch_pipeline_dev_jobs', 'row'): job,
            ('batch_pipeline_dev_results', 'row'): {'projection_state': state, PROJECTION_FINISH_DUE_FIELD: 12.0},
        }
    )
    store = ProjectionStore(SimpleNamespace(client=client, namespace='batch_pipeline_dev'))
    assert store.retire_async_finish('row') is retired
    row = client.rows[('batch_pipeline_dev_results', 'row')]
    assert row['projection_state'] == state
    assert row[PROJECTION_FINISH_DUE_FIELD] == (-1.0 if retired else 12.0)


def test_new_async_state_writes_exclude_without_backfill_or_policy_reads():
    for state in ('persisted', 'ready'):
        assert projection_finish_state_fields(state, 12.0, async_projection=True)[PROJECTION_FINISH_DUE_FIELD] == -1.0
        assert projection_finish_state_fields(state, 12.0)[PROJECTION_FINISH_DUE_FIELD] == 12.0


@pytest.mark.parametrize('stripe', [0, 2048])
def test_sync_finish_with_backoff_off_seeds_a_finite_cursor(monkeypatch, stripe):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'on')
    log, ids = finish_log()
    projector = silent_projector(log)
    projector.finish_discovery.stripe = stripe
    original = log.projection_page
    cursors = []

    def page(*args, **kwargs):
        after = kwargs.get('after')
        if after is not None:
            cursors.append(after)
        return original(*args, **kwargs)

    log.projection_page = page
    projector.sweep()
    assert all(math.isfinite(cursor[0]) for cursor in cursors)
    assert [call.args[0] for call in projector._finish.call_args_list] == ids


def test_missing_marker_does_not_reclassify_an_already_excluded_row(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log = ResultLog()
    log.commit('owner', 'a', 'row', ['row'], state='persisted')
    log.results['row'][PROJECTION_FINISH_DUE_FIELD] = -1.0
    log.retire_async_finish = Mock(side_effect=AssertionError('already classified'))
    projector = projector_for(log)
    projector.sweep()
    projector.sweep()
    log.retire_async_finish.assert_not_called()
    assert projector.has_async_followups


def test_sync_only_finish_page_never_wakes_followup_candidate_discovery(monkeypatch):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = finish_log(persisted=100)
    projector = silent_projector(log)
    projector.start_followups = AsyncMock(side_effect=AssertionError('sync-only discovery'))
    projector.sweep(limit=200)
    assert projector._finish.call_count == len(ids)
    assert not projector.has_async_followups
    service = Serving(MemoryStore(), projector=projector)
    service.reconcile = lambda **_: []
    asyncio.run(service.reconcile_async())
    projector.start_followups.assert_not_awaited()


def legacy_async_log(rows=20):
    log, ids = finish_log(persisted=rows)
    for sid in ids:
        log.jobs[sid]['policy_parts']['projection'] = {**log.policy, 'async_projection': True}
    return log, ids


@pytest.mark.parametrize('limit', [0, 1, 4, 16])
def test_classification_budget_counts_only_successful_updates(monkeypatch, limit):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', str(limit))
    log, ids = legacy_async_log()
    projector = silent_projector(log)
    log.retire_async_finish = Mock(wraps=log.retire_async_finish)
    successes = PROJECTION_FINISH_CLASSIFIED._value.get()
    failures = PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get()
    counts = projector.sweep(limit=100)
    assert log.retire_async_finish.call_count == limit
    assert sum(log.results[sid][PROJECTION_FINISH_DUE_FIELD] == -1.0 for sid in ids) == limit
    assert PROJECTION_FINISH_CLASSIFIED._value.get() - successes == limit
    assert PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get() == failures
    assert counts['error'] == 0
    assert projector.has_async_followups  # Including paused classification.


def test_repeated_pages_do_not_refill_budget_until_after_last_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', '4')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, _ids = legacy_async_log()
    projector = silent_projector(log)
    now = [100.0]
    projector.finish_page.monotonic = lambda: now[0]
    retire = log.retire_async_finish

    def delayed(sid):
        now[0] += 1.0  # Include time spent inside each transaction in the cooldown.
        return retire(sid)

    log.retire_async_finish = Mock(side_effect=delayed)
    projector.sweep(limit=100)
    assert log.retire_async_finish.call_count == 4
    assert projector.finish_page.classify_after == 124.0
    for tick in [104.0, 110.0, 123.99]:
        now[0] = tick
        projector.sweep(limit=100)
        assert log.retire_async_finish.call_count == 4
        assert projector.has_async_followups
    now[0] = 124.0
    projector.sweep(limit=100)
    assert log.retire_async_finish.call_count == 8


@pytest.mark.parametrize('kind', ['abort', 'contention', 'failure'])
def test_classification_failures_are_counted_without_sweep_errors(monkeypatch, caplog, kind):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', '4')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = legacy_async_log(rows=6)
    projector = silent_projector(log)
    now = [100.0]
    projector.finish_page.monotonic = lambda: now[0]
    real = log.retire_async_finish
    error = {
        'abort': Aborted('synthetic'),
        'contention': FirestoreContentionExhausted('synthetic'),
        'failure': RuntimeError('synthetic'),
    }[kind]
    log.retire_async_finish = Mock(side_effect=error)
    successes = PROJECTION_FINISH_CLASSIFIED._value.get()
    failures = PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get()
    counts = projector.sweep(limit=100)
    assert counts == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
    assert 'outcome=error' not in caplog.text
    assert log.retire_async_finish.call_count == 4  # Failures consume budget too.
    assert PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get() - failures == 4
    assert PROJECTION_FINISH_CLASSIFIED._value.get() == successes
    assert all(log.results[sid][PROJECTION_FINISH_DUE_FIELD] == 1.0 for sid in ids)
    assert projector.has_async_followups
    # Cooldown expires and the unchanged row can classify on a later page.
    now[0] = 121.0
    log.retire_async_finish.side_effect = real
    projector.sweep(limit=100)
    assert PROJECTION_FINISH_CLASSIFIED._value.get() - successes == 4
    assert projector.has_async_followups


def test_classification_fence_noop_is_neither_success_nor_failure(monkeypatch):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, _ids = legacy_async_log(rows=2)
    projector = silent_projector(log)
    log.retire_async_finish = Mock(return_value=False)
    successes = PROJECTION_FINISH_CLASSIFIED._value.get()
    failures = PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get()
    projector.sweep()
    assert log.retire_async_finish.call_count == 2
    assert PROJECTION_FINISH_CLASSIFIED._value.get() == successes
    assert PROJECTION_FINISH_CLASSIFICATION_FAILURES._value.get() == failures


@pytest.mark.parametrize('value,expected', [(None, 8), ('0', 0), ('16', 16), ('-1', 8), ('17', 8), ('bad', 8)])
def test_classification_page_limit_setting(monkeypatch, value, expected):

    if value is None:
        monkeypatch.delenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', raising=False)
    else:
        monkeypatch.setenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', value)
    assert projection_finish_classify_page_limit() == expected


def test_overlapping_pages_keep_individual_caps_and_share_process_budget(monkeypatch):

    monkeypatch.setenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', '4')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, _ids = legacy_async_log()
    projector = silent_projector(log)
    projector.finish_discovery.next = Mock(return_value=[])
    budget = projector.finish_page
    now = [100.0]
    budget.monotonic = lambda: now[0]
    old_spent, new_started, old_done = threading.Event(), threading.Event(), threading.Event()
    log.retire_async_finish = Mock(return_value=True)

    def old_page():
        budget.page(100)
        for n in range(4):
            budget.observed_async(f'old-{n}', {PROJECTION_FINISH_DUE_FIELD: 1.0})
        old_spent.set()
        assert new_started.wait(5)
        # A later page's refill must not restore this page's exhausted cap.
        budget.observed_async('old-extra', {PROJECTION_FINISH_DUE_FIELD: 1.0})
        old_done.set()

    def new_page():
        assert old_spent.wait(5)
        # Still in the cooldown: no additional per-process work is admitted.
        budget.page(100)
        budget.observed_async('too-soon', {PROJECTION_FINISH_DUE_FIELD: 1.0})
        now[0] = 121.0
        budget.page(100)
        budget.observed_async('new-0', {PROJECTION_FINISH_DUE_FIELD: 1.0})
        new_started.set()
        assert old_done.wait(5)
        for n in range(1, 4):
            budget.observed_async(f'new-{n}', {PROJECTION_FINISH_DUE_FIELD: 1.0})

    with ThreadPoolExecutor(max_workers=2) as pool:
        old, new = pool.submit(old_page), pool.submit(new_page)
        old.result(timeout=10)
        new.result(timeout=10)
    assert [call.args[0] for call in log.retire_async_finish.call_args_list] == [
        *[f'old-{n}' for n in range(4)],
        *[f'new-{n}' for n in range(4)],
    ]


def test_default_classification_budget_stops_at_eight(monkeypatch):
    monkeypatch.delenv('BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT', raising=False)
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    log, ids = legacy_async_log(rows=25)
    projector = silent_projector(log)
    log.retire_async_finish = Mock(wraps=log.retire_async_finish)
    projector.sweep(limit=100)
    assert log.retire_async_finish.call_count == 8
    assert sum(log.results[sid][PROJECTION_FINISH_DUE_FIELD] == -1.0 for sid in ids) == 8


@pytest.mark.parametrize('group_ready', [False, True])
@pytest.mark.parametrize('async_projection', [False, True])
def test_held_ready_settlement_keeps_pinned_finish_policy(monkeypatch, group_ready, async_projection):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', str(group_ready).lower())
    client, store, binding = projection_fixture()
    client.rows[('batch_pipeline_dev_jobs', 'good')]['policy_parts']['projection'] = ProjectionPolicy(
        async_projection=async_projection
    ).to_dict()
    entry = client.rows[('batch_pipeline_dev_results', 'good')]
    entry[PROJECTION_FINISH_DUE_FIELD] = -1.0 if async_projection else 1.0
    receipt = deepcopy(entry['projection'])
    for now in (100.0, 101.0):
        assert store.hold_for_quarantine('good', binding, now)
        assert entry[PROJECTION_FINISH_DUE_FIELD] == (-1.0 if async_projection else now)
        assert entry[FOLLOWUP_DUE] == now
        assert entry['projection'] == receipt
