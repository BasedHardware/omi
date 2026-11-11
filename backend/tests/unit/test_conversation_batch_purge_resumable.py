"""Round 2 (#25124): the background conversation batch purge is resumable, fenced and gate-bounded.

1. Segment ids are persisted before anything is erased, dependents go before
   their job/result binding, so a hold or crash between them cannot strand an
   artifact that carries only a segment id.
2. Every unit and checkpoint proves run ownership; a superseded or expired run
   stops, and a run hands off before the task deadline and resumes past an
   unmatched prefix.
3. Each account-gate hold is bounded; a foreground delete that arrives while a
   large purge runs still gets 204.
4. Unknown consumer readiness records a degraded fallback.
"""

from __future__ import annotations

import contextvars
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from database import batch_pipeline_conversation_purge as purge
from database import conversation_batch_purge_jobs as purge_jobs
from database import legal_holds
from database.batch_pipeline_privacy import privacy_owner_key
from utils.batch_pipeline import retention
from utils.conversations import deletion_batch_purge
from tests.unit.test_conversation_delete_gate_wait import (  # noqa: F401 - fixtures
    HOLD_PATH,
    UID,
    _advance,
    _obligation,
    _plane,
    _route_app,
    _segments,
    armed,
    dispatch,
    fast_clock,
    gate_client,
    tombstone_db,
)

NS = 'batch_pipeline_prod'
KEY = privacy_owner_key(UID)


class _Snap:
    def __init__(self, client, path):
        self._client, self.path = client, path
        self.id = path.rsplit('/', 1)[-1]
        self.reference = client.collection(path.rsplit('/', 1)[0]).document(self.id)
        self._data = dict(client.docs.get(path) or {})
        self.exists = path in client.docs

    def to_dict(self):
        return dict(self._data)


class BatchPlane:
    """Batch rows in the shared fake client; erasure helpers mutate it and record what they did."""

    def __init__(self, monkeypatch, client, *, on_page=None, row_cost=0.0, sleep=time.sleep):
        self.client, self.on_page, self.row_cost, self.sleep = client, on_page, row_cost, sleep
        self.reads, self.objects, self.erased = [], [], []
        monkeypatch.setattr(purge, 'get_data_plane_firestore_client', lambda: client)
        monkeypatch.setattr(purge, '_cursor', lambda _client, _ns, _table, after: after)
        monkeypatch.setattr(purge.queries, 'owner_documents', self.owner_documents)
        monkeypatch.setattr(purge.queries, 'artifacts_by_owner_id', self.parked)
        monkeypatch.setattr(purge, '_erase_artifact', self.erase_artifact)
        monkeypatch.setattr(purge, '_erase_result', self.erase_result)
        monkeypatch.setattr(purge, '_delete_job', self.delete_job)
        monkeypatch.setattr(purge, 'mirror_refresh', lambda *a: None)
        monkeypatch.setattr(purge, '_shadow_mode', lambda: False)
        from tests.unit.test_conversation_delete_gate_wait import _Transaction

        monkeypatch.setattr(purge, '_in_transaction', lambda _client, body: body(_Transaction(client)))
        self.fenced = 0
        monkeypatch.setattr(
            retention,
            'delete_batch_object',
            lambda uid, uri, timeout=None, storage_client=None: self.objects.append(uri),
        )
        from utils.other import local_storage

        monkeypatch.setattr(local_storage, 'create_storage_client', MagicMock)

    def add(self, table, doc_id, **data):
        self.client.docs[f'{NS}_{table}/{doc_id}'] = {'owner_key': KEY, 'owner_id': UID, **data}

    def doc(self, table, doc_id):
        return self.client.docs.get(f'{NS}_{table}/{doc_id}')

    def _rows(self, namespace, table, keep, after):
        prefix = f'{namespace}_{table}/'
        ids = sorted(
            path[len(prefix) :] for path, row in self.client.docs.items() if path.startswith(prefix) and keep(row)
        )
        ids = [doc_id for doc_id in ids if after is None or doc_id > after][:100]
        return [_Snap(self.client, f'{prefix}{doc_id}') for doc_id in ids]

    def owner_documents(self, _client, namespace, table, key, *, after=None):
        self.reads.append((namespace, table, after))
        if self.on_page:
            self.on_page(namespace, table, after)
        return self._rows(namespace, table, lambda row: row.get('owner_key') == key, after)

    def parked(self, _client, namespace, uid, *, after=None):
        return self._rows(namespace, 'artifacts', lambda row: row.get('owner_id') == uid, after)

    def _cost(self):
        if self.row_cost:
            self.sleep(self.row_cost)

    def _fence(self, fence):
        if fence is not None:
            fence(None)  # the real fence reads the gate/hold documents; fakes ignore transactions
            self.fenced += 1

    def erase_artifact(self, uid, namespace, snapshot, data, delete_uri, fence=None, client=None):
        self._cost()
        if data.get('uri'):
            delete_uri(uid, data['uri'])
        self._fence(fence)
        self.client.docs.pop(f'{namespace}_artifacts/{snapshot.id}', None)
        self.erased.append(('artifacts', snapshot.id))

    def _erase_result_doc(self, namespace, segment_id):
        path = f'{namespace}_results/{segment_id}'
        if path in self.client.docs:
            row = self.client.docs[path]
            self.client.docs[path] = {'owner_key': row.get('owner_key'), 'projection_state': 'erased'}

    def erase_result(self, _client, namespace, snapshot, fence=None):
        self._cost()
        self._fence(fence)
        self._erase_result_doc(namespace, snapshot.id)
        self.erased.append(('results', snapshot.id))

    def delete_job(self, _client, namespace, snapshot, *, retain_ordering, fence=None):
        self._cost()
        self._fence(fence)
        self.client.docs.pop(f'{namespace}_jobs/{snapshot.id}', None)
        self._erase_result_doc(namespace, snapshot.id)
        self.erased.append(('jobs', snapshot.id))


@pytest.fixture
def owner(monkeypatch, tombstone_db, gate_client):
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', legal_holds.assert_account_deletion_permitted)
    return SimpleNamespace(plane=lambda **kwargs: BatchPlane(monkeypatch, tombstone_db, **kwargs))


def _place_hold(gate_client, active=True):
    legal_holds._place_legal_hold_transaction.to_wrap(
        gate_client.transaction(), gate_client, UID, 'admin', active, legal_holds.datetime.now(legal_holds.timezone.utc)
    )


def _run(armed, generation, **kwargs):
    kwargs.setdefault('sleep', lambda seconds: None)
    return purge_jobs.run_job(armed, generation, **kwargs)


def _redrive(tombstone_db, armed, seconds=purge_jobs.HOLD_RECHECK_SECONDS + 1):
    _advance(tombstone_db, armed, seconds)
    deletion_batch_purge.reconcile_conversation_batch_purges()


# --- 1. durable segment work: dependents before their binding, resume never strands an artifact ---


def test_hold_before_the_artifact_unit_then_resume_erases_the_segment_only_artifact(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Reviewer round-2 probe: result r1 is the only link from artifact a1 (no conversation ids) to c1."""
    held = []

    def hold_when_artifacts_are_read(namespace, table, after):
        if table == 'artifacts' and not held:
            _place_hold(gate_client)
            held.append(True)

    plane = owner.plane(on_page=hold_when_artifacts_are_read)
    plane.add('results', 'r1', conversation_id='c1', segment_id='r1')
    plane.add('artifacts', 'a1', segment_id='r1', conversation_ids=[], uri='gs://bucket/owners/a1', kind='audio')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'held'
    # Nothing destructive ran after the hold, and the link plus its durable record survive.
    assert plane.erased == [] and plane.objects == []
    assert plane.doc('results', 'r1')['conversation_id'] == 'c1'
    assert [row['segment_id'] for row in _segments(tombstone_db, armed, NS)] == ['r1']

    _place_hold(gate_client, active=False)
    _redrive(tombstone_db, armed)
    assert dispatch[-1] == (armed, 2)
    assert _run(armed, 2) == 'purged'
    assert plane.doc('artifacts', 'a1') is None and plane.objects == ['gs://bucket/owners/a1']
    assert plane.doc('results', 'r1') == {'owner_key': KEY, 'projection_state': 'erased'}
    # Dependents are erased before the binding that links them.
    assert plane.erased == [('artifacts', 'a1'), ('results', 'r1')]
    assert _segments(tombstone_db, armed, NS) == [] and _obligation(tombstone_db, 'c1') is None


def test_crash_between_dependents_and_bindings_resumes_from_the_segment_records(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    plane = owner.plane()
    plane.add('jobs', 'j1', conversation_id='c1', priority=1)
    plane.add('results', 'j1', conversation_id='c1', segment_id='j1')
    plane.add('intakes', 'i1', segment_ids=['j1'])
    real_delete_job = plane.delete_job
    crashes = []

    def crash_once(*args, **kwargs):
        if not crashes:
            crashes.append(True)
            raise RuntimeError('instance lost mid-unit')
        real_delete_job(*args, **kwargs)

    plane.delete_job = crash_once
    purge.__dict__['_delete_job'] = crash_once
    deletion_batch_purge.reconcile_conversation_batch_purges()
    with pytest.raises(RuntimeError):
        _run(armed, 1)
    assert plane.doc('intakes', 'i1') is None  # dependent already gone
    assert plane.doc('jobs', 'j1') is not None  # binding kept ...
    assert [row['segment_id'] for row in _segments(tombstone_db, armed, NS)] == ['j1']  # ... and recorded
    assert _obligation(tombstone_db, 'c1')['progress']['phase'] == 'segments'
    reads_before = len(plane.reads)

    _redrive(tombstone_db, armed, purge_jobs.REDRIVE_SECONDS + 1)
    assert _run(armed, dispatch[-1][1]) == 'purged'
    assert plane.doc('jobs', 'j1') is None
    # The resumed run re-scanned nothing it had finished: dependents are not re-read.
    assert all(
        table not in {'artifacts', 'intakes'} for namespace, table, _ in plane.reads[reads_before:] if namespace == NS
    )
    assert _obligation(tombstone_db, 'c1') is None


def test_completion_is_refused_while_segment_work_is_still_recorded(monkeypatch, tombstone_db, armed, dispatch):
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda *a, **k: None)
    monkeypatch.setattr(purge, 'purge_conversation', lambda *a, **k: 0)
    tombstone_db.docs[f'{purge_jobs.COLLECTION}/{armed}/{purge_jobs.SEGMENTS}/x'] = {
        'namespace': NS,
        'segment_id': 's1',
    }
    deletion_batch_purge.reconcile_conversation_batch_purges()
    with pytest.raises(RuntimeError, match='segment erasure still recorded'):
        _run(armed, 1)
    assert _obligation(tombstone_db, 'c1')['last_outcome'] == 'failed'


# --- 2. run ownership is fenced; runs hand off before the deadline and resume past the prefix ---


def _matching_artifacts(plane, count):
    for index in range(count):
        plane.add('artifacts', f'a{index:03d}', conversation_ids=['c1'], uri=f'gs://bucket/owners/a{index:03d}')


def test_superseded_generation_stops_before_its_next_erasure(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Reviewer round-2 probe 1: generation 1's lease expires mid-scan and generation 2 finishes."""
    clock = {'now': purge_jobs._now()}
    monkeypatch.setattr(purge_jobs, '_now', lambda: clock['now'])
    outcomes, fired = [], []

    def expire_and_take_over(namespace, table, after):
        if table == 'artifacts' and after == 'a099' and not fired:
            fired.append(True)
            # Past the lease and the dispatch's redrive time: the reconciler may hand out generation 2.
            clock['now'] += purge_jobs.timedelta(seconds=max(purge_jobs.LEASE_SECONDS, purge_jobs.REDRIVE_SECONDS) + 1)
            deletion_batch_purge.reconcile_conversation_batch_purges()
            assert dispatch[-1] == (armed, 2)
            outcomes.append(contextvars.Context().run(_run, armed, 2))

    plane = owner.plane(on_page=expire_and_take_over)
    _matching_artifacts(plane, 101)  # two pages
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'superseded'
    assert outcomes == ['purged']
    # a100 was erased exactly once, by generation 2; generation 1 stopped at its next unit.
    assert [row for row in plane.erased if row[1] == 'a100'] == [('artifacts', 'a100')]
    assert _obligation(tombstone_db, 'c1') is None


def test_same_generation_retry_after_lease_expiry_takes_over_and_the_old_run_stops(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    clock = {'now': purge_jobs._now()}
    monkeypatch.setattr(purge_jobs, '_now', lambda: clock['now'])
    outcomes, fired = [], []

    def queue_retry(namespace, table, after):
        if table == 'artifacts' and after == 'a099' and not fired:
            fired.append(True)
            clock['now'] += purge_jobs.timedelta(seconds=purge_jobs.LEASE_SECONDS + 1)
            outcomes.append(contextvars.Context().run(_run, armed, 1))  # Cloud Tasks redelivers generation 1

    plane = owner.plane(on_page=queue_retry)
    _matching_artifacts(plane, 101)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'superseded'
    assert outcomes == ['purged']
    assert sum(1 for row in plane.erased if row[1] == 'a100') == 1


def test_duplicate_delivery_while_the_lease_is_live_does_not_overlap(owner, tombstone_db, gate_client, armed, dispatch):
    outcomes, fired = [], []

    def duplicate(namespace, table, after):
        if not fired:
            fired.append(True)
            outcomes.append(contextvars.Context().run(_run, armed, 1))

    owner.plane(on_page=duplicate)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    assert outcomes == ['in_progress']


def test_run_hands_off_before_the_deadline_and_resumes_past_an_unmatched_prefix(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    elapsed = {'seconds': 0.0}

    def slow_page(namespace, table, after):
        elapsed['seconds'] += 400.0  # each page read costs 400 s of the 1200 s run budget

    plane = owner.plane(on_page=slow_page)
    for index in range(350):
        plane.add('results', f'p{index:03d}', conversation_id='other', segment_id=f'p{index:03d}')
    plane.add('results', 'q000', conversation_id='c1', segment_id='q000')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1, clock=lambda: elapsed['seconds']) == 'checkpointed'
    row = _obligation(tombstone_db, 'c1')
    assert row['last_outcome'] == 'checkpointed' and row['attempts'] == 0 and row['lease_until'] is None
    assert row['progress'] == {'ns': 0, 'phase': 'discover', 'table': 1, 'after': 'p199'}
    assert row['due_at'] <= purge_jobs._now()  # handed off at once
    reads_before = len(plane.reads)

    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch[-1] == (armed, 2)
    elapsed['seconds'] = 0.0
    assert _run(armed, 2, clock=lambda: 0.0) == 'purged'
    assert plane.reads[reads_before] == (NS, 'results', 'p199')  # resumed past the scanned prefix
    assert plane.doc('results', 'q000') == {'owner_key': KEY, 'projection_state': 'erased'}
    assert _obligation(tombstone_db, 'c1') is None


# --- 3. bounded account-gate holds ---


class _Units:
    def __init__(self, clock):
        self.clock, self.sizes, self._current = clock, [], None

    def expired(self):
        return False

    def unit(self):
        units = self

        class Unit:
            def __enter__(self):
                units.sizes.append(0)

            def __exit__(self, *exc):
                return False

        return Unit()


def test_units_stop_at_the_row_cap_and_the_time_budget():
    clock = {'now': 0.0}
    units = _Units(clock)

    def erase(_row, _authority):
        units.sizes[-1] += 1

    assert purge._in_units(units, list(range(25)), erase, lambda: clock['now'], lambda: None) == 25
    assert units.sizes == [10, 10, 5]

    units.sizes.clear()

    def slow_erase(_row, _authority):
        units.sizes[-1] += 1
        clock['now'] += 0.6

    purge._in_units(units, list(range(7)), slow_erase, lambda: clock['now'], lambda: None)
    assert units.sizes == [3, 3, 1]  # 0.0, 0.6, 1.2 start; 1.8 >= 1.5 stops the unit


def test_foreground_delete_gets_204_while_a_full_page_purge_runs(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch
):
    """Real threads and real waiting: a 100-row matching page at 0.3 s per row (30 s of work)."""
    plane = owner.plane(row_cost=0.3)
    _matching_artifacts(plane, 100)
    holds = []
    real_unit = purge_jobs.RunProgress.unit

    def timed_unit(self):
        context = real_unit(self)

        class Timed:
            def __enter__(self):
                authority = context.__enter__()
                self.started = time.monotonic()
                return authority

            def __exit__(self, *exc):
                holds.append(time.monotonic() - self.started)
                return context.__exit__(*exc)

        return Timed()

    monkeypatch.setattr(purge_jobs.RunProgress, 'unit', timed_unit)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    background = {}
    worker = threading.Thread(target=lambda: background.setdefault('outcome', purge_jobs.run_job(armed, 1)))
    worker.start()
    time.sleep(1.0)  # the purge is mid-unit
    app = _route_app(monkeypatch, MagicMock())
    with TestClient(app) as client:
        started = time.monotonic()
        response = client.delete('/v1/conversations/c-foreground?cascade=true')
        waited = time.monotonic() - started
    assert response.status_code == 204
    assert waited < 3.0
    # Stop the background run: supersede it, and it must stop at its next unit.
    tombstone_db.docs[f'{purge_jobs.COLLECTION}/{armed}']['run_token'] = 'taken-over'
    worker.join(timeout=10)
    assert background['outcome'] == 'superseded'
    assert holds and max(holds) < purge.UNIT_BUDGET_SECONDS + plane.row_cost + 0.2


# --- 4. unknown readiness is a recorded fail-open ---


@pytest.mark.parametrize('ready,expected', [(None, 1), (True, 0), (False, 0)])
def test_unknown_consumer_readiness_records_a_degraded_fallback(
    monkeypatch, tombstone_db, armed, dispatch, ready, expected
):
    recorder = MagicMock()
    monkeypatch.setattr(deletion_batch_purge, 'record_fallback', recorder)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: ready)
    result = deletion_batch_purge.reconcile_conversation_batch_purges()
    assert recorder.call_count == expected
    if expected:
        assert recorder.call_args.kwargs['outcome'] == 'degraded'
        assert result['dispatched'] == 1
