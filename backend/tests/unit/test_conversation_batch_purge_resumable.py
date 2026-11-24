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
from unittest.mock import ANY, MagicMock

import pytest
from fastapi.testclient import TestClient

from database import batch_pipeline_conversation_purge as purge
from database import conversation_batch_purge_jobs as purge_jobs
from database import legal_holds
from database.batch_pipeline_privacy import privacy_owner_key
from utils.batch_pipeline import retention
from utils.conversations import deletion_batch_purge
from tests.unit.test_conversation_delete_gate_wait import (  # noqa: F401 - fixtures
    GATE_PATH,
    HOLD_PATH,
    UID,
    _gate_doc,
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
        monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda *args: 0)
        # Gate/segment fixtures own no WAL originals; WAL emulator tests cover real prefix discovery.
        monkeypatch.setattr(purge, 'conversation_objects', lambda *args, **kwargs: [])
        # Sync-ledger-linked segments per conversation id; empty unless a test names some.
        self.owed: dict[str, dict[str, set[str]]] = {}
        monkeypatch.setattr(
            purge,
            'owed_batch_segments',
            lambda _uid, cids, **kwargs: {ns: ids for cid in cids for ns, ids in self.owed.get(cid, {}).items()},
        )
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


def test_fallback_provenance_reaches_audio_and_source_receipt(owner, tombstone_db, armed, dispatch, fast_clock):
    plane = owner.plane()
    plane.add(
        'jobs',
        'fallback',
        conversation_id='independent-upload',
        source_conversation_ids=['independent-upload'],
        source_alias_fallback={'prior_dependencies': ['c1']},
        priority=1,
    )
    plane.add('artifacts', 'own-audio', segment_id='fallback', uri='gs://bucket/owners/own-audio')
    plane.add('projections', 'source-receipt', segment_id='fallback', source_conversation_ids=['independent-upload'])
    plane.add('projections', 'unrelated-receipt', segment_id='unrelated')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    assert plane.doc('jobs', 'fallback') is None
    assert plane.doc('artifacts', 'own-audio') is None
    assert plane.doc('projections', 'source-receipt') is None
    assert plane.doc('projections', 'unrelated-receipt') is not None
    assert plane.objects == ['gs://bucket/owners/own-audio']
    assert plane.erased == [('artifacts', 'own-audio'), ('jobs', 'fallback')]


def test_sync_ledger_segments_with_provisional_ids_are_erased(owner, tombstone_db, armed, dispatch, fast_clock):
    """A sync upload's rows carry its capture identity, not c1; the ledger names them."""
    plane = owner.plane()
    plane.owed = {'c1': {NS: {'upload-job', 'upload-result'}}}
    plane.add('jobs', 'upload-job', conversation_id='capture-identity', priority=1)
    plane.add('results', 'upload-job', conversation_id='capture-identity', segment_id='upload-job')
    plane.add('results', 'upload-result', conversation_id='capture-identity', segment_id='upload-result')
    plane.add('artifacts', 'upload-audio', segment_id='upload-result', uri='gs://bucket/owners/upload-audio')
    plane.add('results', 'other-upload', conversation_id='other-identity', segment_id='other-upload')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    assert plane.doc('jobs', 'upload-job') is None
    assert plane.doc('results', 'upload-result') == {'owner_key': KEY, 'projection_state': 'erased'}
    assert plane.doc('artifacts', 'upload-audio') is None
    assert plane.objects == ['gs://bucket/owners/upload-audio']
    assert plane.doc('results', 'other-upload')['conversation_id'] == 'other-identity'


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


def test_cold_copy_phase_runs_for_both_namespaces_with_shadow_disabled(
    owner, tombstone_db, armed, dispatch, fast_clock, monkeypatch
):
    owner.plane()
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'off')
    monkeypatch.delenv('JOBSTORE_SHADOW_NAMESPACES', raising=False)
    seen = []
    monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda namespace, uid: seen.append(namespace))
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    assert seen == list(purge.NAMESPACES)


def test_cold_copy_failure_cannot_checkpoint_the_shadow_phase_complete(
    owner, tombstone_db, armed, dispatch, fast_clock, monkeypatch
):
    owner.plane()
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')

    def unavailable(*args):
        raise RuntimeError('synthetic cold copy unavailable')

    monkeypatch.setattr(purge, 'purge_jobstore_owner', unavailable)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    with pytest.raises(RuntimeError, match='cold copy unavailable'):
        _run(armed, 1)
    assert _obligation(tombstone_db, 'c1')['last_outcome'] == 'failed'


# --- 5. a unit that loses its gate wait to a same-account peer hands off; any other blocker still fails ---


def test_unit_losing_its_gate_wait_to_a_same_account_peer_hands_off_busy_and_resumes(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Prod 2026-11-12..15: one account's purges, erasures and deletes queue on its gate; a unit that waited
    out its 30 s raised DestructiveOperationInProgress and the task answered 500 (1,293 times)."""
    plane = owner.plane()
    _matching_artifacts(plane, 2)
    gate_client.docs[GATE_PATH] = _gate_doc()  # a same-kind peer that outlasts the unit's wait
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'busy'
    assert sum(fast_clock.sleeps) == pytest.approx(purge_jobs.UNIT_GATE_WAIT_SECONDS)
    # Nothing was erased without the gate, the peer keeps it, and the run's scan position is saved.
    assert plane.erased == [] and plane.objects == []
    assert gate_client.docs[GATE_PATH]['token'] == 'peer'
    row = _obligation(tombstone_db, 'c1')
    assert row['last_outcome'] == 'busy' and row['lease_until'] is None and row['run_token'] is None
    assert row['progress'] and row['attempts'] == 0
    assert row['due_at'] <= purge_jobs._now() + purge_jobs.timedelta(seconds=purge_jobs.BUSY_RETRY_SECONDS + 1)

    gate_client.docs.pop(GATE_PATH)  # the peer finished
    _redrive(tombstone_db, armed, purge_jobs.BUSY_RETRY_SECONDS + 1)
    assert dispatch[-1] == (armed, 2)
    assert _run(armed, 2) == 'purged'
    assert plane.doc('artifacts', 'a000') is None and plane.doc('artifacts', 'a001') is None
    assert _obligation(tombstone_db, 'c1') is None


@pytest.mark.parametrize('kind', ['account_deletion', 'retention_cleanup', 'audio_conversation_deletion'])
def test_unit_blocked_by_another_destructive_kind_still_fails_the_run(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock, kind
):
    """An account wipe (or any other kind) is never a peer: the purge yields to it and the task retries."""
    plane = owner.plane()
    _matching_artifacts(plane, 1)
    gate_client.docs[GATE_PATH] = _gate_doc(kind=kind)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _run(armed, 1)
    assert fast_clock.sleeps == [] and plane.erased == [] and plane.objects == []
    row = _obligation(tombstone_db, 'c1')
    assert row['last_outcome'] == 'failed' and row['lease_until'] is None


def test_legacy_rearm_behind_cursor_preserves_obligation_and_restarts_discovery(
    monkeypatch, owner, tombstone_db, armed, dispatch, fast_clock
):
    plane = owner.plane()
    plane.add('results', 'original', conversation_id='c1', segment_id='original')
    rearmed = []

    def rearm_after_namespace(namespace, uid):
        if not rearmed:
            tombstone_db.docs[f'{purge_jobs.COLLECTION}/{armed}'].update(purge_jobs.arm_fields(UID, 'c1'))
            plane.add('results', 'behind-cursor', conversation_id='c1', segment_id='behind-cursor')
            rearmed.append(True)
        return 0

    monkeypatch.setattr(purge, 'purge_jobstore_owner', rearm_after_namespace)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'superseded'
    row = _obligation(tombstone_db, 'c1')
    assert row['last_outcome'] == 'rearmed' and row['progress'] == {}
    assert row['lease_until'] is None and row['run_token'] is None
    assert plane.doc('results', 'behind-cursor')['conversation_id'] == 'c1'
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert dispatch[-1] == (armed, 2)
    assert _run(armed, 2) == 'purged'
    assert plane.doc('results', 'behind-cursor')['projection_state'] == 'erased'
    assert _obligation(tombstone_db, 'c1') is None


@pytest.mark.parametrize('parked', [False, True])
def test_pending_upload_keeps_purge_and_segment_link_until_replay(
    monkeypatch, owner, tombstone_db, armed, dispatch, fast_clock, parked
):
    plane = owner.plane()
    plane.add('jobs', 's1', conversation_id='c1', priority=1)
    plane.add('artifacts', 'a1', segment_id='s1', owner_id=UID, owner_key='parked' if parked else KEY)
    original = plane.erase_artifact

    def erase(uid, namespace, snapshot, data, delete_uri, fence=None, client=None):
        if not data.get('erasure_requested'):
            plane.doc('artifacts', 'a1').update(owner_key=KEY, erasure_requested=True)
            return True
        return original(uid, namespace, snapshot, data, delete_uri, fence=fence, client=client)

    monkeypatch.setattr(purge, '_erase_artifact', erase)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'artifact_pending'
    assert plane.doc('jobs', 's1') is not None
    assert plane.doc('artifacts', 'a1') is not None
    assert _obligation(tombstone_db, 'c1') is not None

    _advance(tombstone_db, armed, purge_jobs.ARTIFACT_RETRY_SECONDS + 1)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 2) == 'purged'
    assert plane.doc('artifacts', 'a1') is None
    assert _obligation(tombstone_db, 'c1') is None


def test_resumed_cursor_past_discovery_still_erases_ledger_owed_rows(owner, tombstone_db, armed, dispatch, fast_clock):
    """A run checkpointed past discovery (pre-upgrade, or before the last sibling's tombstone) never saw them."""
    plane = owner.plane()
    plane.add('jobs', 'upload-job', conversation_id='capture-identity', priority=1)
    plane.add('results', 'upload-job', conversation_id='capture-identity', segment_id='upload-job')
    plane.add('artifacts', 'upload-audio', segment_id='upload-job', uri='gs://bucket/owners/upload-audio')
    plane.add('results', 'other-upload', conversation_id='other-identity', segment_id='other-upload')
    row = _obligation(tombstone_db, 'c1')
    row['progress'] = {'ns': len(purge.NAMESPACES), 'phase': 'discover'}
    row['progress_arm'] = {'armed_at': row['armed_at'], 'arm_revision': row['arm_revision']}
    plane.owed = {'c1': {NS: {'upload-job', 'already-erased'}}}
    plane.add('results', 'already-erased', projection_state='erased')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    assert plane.doc('jobs', 'upload-job') is None
    assert plane.doc('artifacts', 'upload-audio') is None
    assert plane.objects == ['gs://bucket/owners/upload-audio']
    assert plane.doc('results', 'other-upload')['conversation_id'] == 'other-identity'


# --- durable audio erasure obligation (SCA-1819): every delete owes its audio until it is gone ---


@pytest.fixture
def audio_job(monkeypatch, tombstone_db):
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda uid: None)
    tombstone_db.docs[f'users/{UID}/deleted_conversations/c1'] = {'conversation_id': 'c1'}
    purge_jobs.arm_audio_erasure(UID, 'c1', ['donor', 'c1'])
    return purge_jobs.audio_job_id(UID, 'c1')


def _audio_row(client):
    return client.docs.get(f'{purge_jobs.AUDIO_COLLECTION}/{purge_jobs.audio_job_id(UID, "c1")}')


def _audio_generation(client, job):
    row = _audio_row(client)
    for field in ('due_at', 'lease_until'):
        if row.get(field) is not None:
            row[field] = row[field] - purge_jobs.timedelta(days=1)
    claim = purge_jobs.claim_dispatch(job, collection=purge_jobs.AUDIO_COLLECTION)
    assert claim is not None
    return claim[0]


def test_storage_hold_is_reported_on_the_obligation_and_retried(tombstone_db, audio_job):
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked

    calls = []

    def erase(uid, cid, sources, *, staging, settled, **_):
        calls.append((uid, cid, sources))
        if len(calls) == 1:
            raise StoragePrefixPurgeBlocked({('syncing', 'syncing/uid1/job/1.bin', 1): 'objectUnderActiveHold'})

    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'storage_held'
    )
    row = _audio_row(tombstone_db)
    assert row['last_outcome'] == 'held' and row['last_reason'] == 'storage_hold' and row['blocked_objects'] == 1
    assert row['due_at'] > purge_jobs._now() + purge_jobs.timedelta(minutes=50)  # rechecked, never dropped
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert calls == [(UID, 'c1', ['donor'])] * 2
    assert _audio_row(tombstone_db) is None


def test_retry_after_the_primary_row_is_gone_still_finishes_the_audio(tombstone_db, audio_job):
    # Only the tombstone and the obligation remain: the route would answer ``already_deleted``.
    assert not any(path.startswith(f'users/{UID}/conversations/') for path in tombstone_db.docs)
    erase = MagicMock()
    generation = _audio_generation(tombstone_db, audio_job)
    assert purge_jobs.run_audio_erasure_job(audio_job, generation, erase=erase) == 'erased'
    erase.assert_called_once_with(UID, 'c1', ['donor'], staging={}, settled=[], deleted_siblings=[], ledger=ANY)
    assert _audio_row(tombstone_db) is None


def test_ledger_read_failure_is_retried_not_dropped(tombstone_db, audio_job):
    erase = MagicMock(side_effect=[RuntimeError('ledger unavailable'), None])
    with pytest.raises(RuntimeError, match='ledger unavailable'):
        purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase)
    row = _audio_row(tombstone_db)
    assert row['last_outcome'] == 'failed' and row['last_reason'] == 'RuntimeError'
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert _audio_row(tombstone_db) is None


def test_reconciler_dispatches_audio_erasures_by_their_own_kind(monkeypatch, tombstone_db, audio_job):
    sent = []
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    monkeypatch.setattr(
        deletion_batch_purge, 'enqueue_conversation_batch_purge', lambda job, gen, **kind: sent.append((job, gen, kind))
    )
    from tests.unit.test_conversation_delete_gate_wait import _due

    monkeypatch.setattr(
        purge_jobs,
        'due_jobs',
        lambda **kwargs: _due(kwargs.get('now'), kwargs.get('collection', purge_jobs.COLLECTION), kwargs.get('limit')),
    )
    counts = deletion_batch_purge.reconcile_conversation_batch_purges()
    assert sent == [(audio_job, 1, {'audio': True})]
    assert counts['audio_erasures_dispatched'] == 1


def test_staging_still_in_use_stays_owed_past_the_window_and_is_escalated_not_dropped(tombstone_db, audio_job):
    from database.sync_ledger_sources import StagingInFlight

    erase = MagicMock(side_effect=[StagingInFlight(1), StagingInFlight(1), None])
    generation = _audio_generation(tombstone_db, audio_job)
    assert purge_jobs.run_audio_erasure_job(audio_job, generation, erase=erase) == 'staging_in_flight'
    assert _audio_row(tombstone_db)['last_reason'] == 'staging_in_flight'
    later = purge_jobs._now() + purge_jobs.timedelta(seconds=purge_jobs.AUDIO_STAGING_PENDING_MAX_SECONDS + 1)
    generation = _audio_generation(tombstone_db, audio_job)
    assert purge_jobs.run_audio_erasure_job(audio_job, generation, erase=erase, now=later) == 'staging_unsettled'
    row = _audio_row(tombstone_db)
    # Staging is retained and its bucket has no lifecycle delete: the obligation stays, rechecked daily.
    assert row['last_outcome'] == 'held' and row['last_reason'] == 'staging_unsettled'
    assert row['due_at'] > purge_jobs._now() + purge_jobs.timedelta(hours=23)
    # Discharged only once the staging is actually erased.
    generation = _audio_generation(tombstone_db, audio_job)
    assert purge_jobs.run_audio_erasure_job(audio_job, generation, erase=erase, now=later) == 'erased'
    assert _audio_row(tombstone_db) is None


def test_legal_hold_and_account_wipe_stop_the_audio_erasure(monkeypatch, tombstone_db, audio_job):
    erase = MagicMock()

    def held(uid):
        raise legal_holds.LegalHoldActive('held')

    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', held)
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'held'
    )
    assert _audio_row(tombstone_db)['last_reason'] == 'legal_hold'
    tombstone_db.docs.pop(f'users/{UID}/deleted_conversations/c1')  # an account wipe removed the subtree
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'no_tombstone'
    )
    erase.assert_not_called()
    assert _audio_row(tombstone_db) is None


def test_rearm_during_a_run_is_erased_again_not_completed(tombstone_db, audio_job):
    def erase(uid, cid, sources, *, staging, settled, **_):
        purge_jobs.arm_audio_erasure(UID, 'c1', ['late-donor'])  # a retried delete re-arms meanwhile

    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'superseded'
    )
    row = _audio_row(tombstone_db)
    assert row['audio_source_ids'] == ['donor', 'late-donor']
    assert row['last_outcome'] == 'checkpointed' and row['last_reason'] == 'rearmed'


def test_kill_switch_off_holds_armed_audio_obligations_and_they_resume_when_on(monkeypatch, tombstone_db, audio_job):
    sent = []
    monkeypatch.setattr(deletion_batch_purge, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_consumer_ready', lambda: True)
    monkeypatch.setattr(deletion_batch_purge, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
    monkeypatch.setattr(
        deletion_batch_purge, 'enqueue_conversation_batch_purge', lambda job, gen, **kind: sent.append((job, gen, kind))
    )
    from tests.unit.test_conversation_delete_gate_wait import _due

    monkeypatch.setattr(
        purge_jobs,
        'due_jobs',
        lambda **kwargs: _due(kwargs.get('now'), kwargs.get('collection', purge_jobs.COLLECTION), kwargs.get('limit')),
    )
    monkeypatch.setenv(deletion_batch_purge.AUDIO_ERASURE_SWITCH, 'off')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert sent == []  # not dispatched while off
    # A task already in flight when the switch went off holds the obligation instead of erasing.
    erase = MagicMock()
    generation = _audio_generation(tombstone_db, audio_job)
    outcome = purge_jobs.run_audio_erasure_job(
        audio_job, generation, erase=erase, enabled=deletion_batch_purge.durable_audio_erasure
    )
    assert outcome == 'switched_off'
    erase.assert_not_called()
    assert _audio_row(tombstone_db)['last_reason'] == 'switched_off'
    monkeypatch.setenv(deletion_batch_purge.AUDIO_ERASURE_SWITCH, 'true')
    _audio_row(tombstone_db)['due_at'] -= purge_jobs.timedelta(days=1)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert [kind for _job, _gen, kind in sent] == [{'audio': True}]


def test_visible_conversation_row_waits_instead_of_losing_its_audio(tombstone_db, audio_job):
    """A delete that failed after arming (503) leaves the row visible: its audio must not go."""
    tombstone_db.docs[f'users/{UID}/conversations/c1'] = {'status': 'completed'}
    erase = MagicMock()
    generation = _audio_generation(tombstone_db, audio_job)
    assert purge_jobs.run_audio_erasure_job(audio_job, generation, erase=erase) == 'conversation_row_live'
    erase.assert_not_called()
    row = _audio_row(tombstone_db)
    assert row['last_reason'] == 'conversation_row_live'
    assert row['due_at'] <= purge_jobs._now() + purge_jobs.timedelta(
        seconds=purge_jobs.AUDIO_ROW_LIVE_RETRY_SECONDS + 5
    )
    tombstone_db.docs[f'users/{UID}/conversations/c1'] = {'deleted': True}  # hidden: erasure proceeds
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )


def test_staging_kept_for_a_live_sibling_stays_owed_until_that_sibling_is_deleted(tombstone_db, audio_job, caplog):
    caplog.set_level('INFO', logger=purge_jobs.logger.name)
    erase = MagicMock(side_effect=[{'shared_live': 1}, {'shared_live': 0}])
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_kept_for_live_sibling'
    )
    assert 'last_reason=staging_kept_for_live_sibling' in caplog.text and 'shared_live=1' in caplog.text
    row = _audio_row(tombstone_db)
    # Never discharged while the recorded prefix is kept: the ledger linking it to the sibling expires.
    assert row['last_reason'] == 'staging_kept_for_live_sibling' and row['shared_live'] == 1
    assert row['due_at'] > purge_jobs._now() + purge_jobs.timedelta(hours=23)
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert _audio_row(tombstone_db) is None


def _fake_ledger(monkeypatch, client):
    """The dev-stage sync content ledger in the shared fake client, queryable like Firestore."""
    from database import sync_ledger_sources as sources

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    path = f'users/{UID}/sync_content_ledger_dev'

    class _Query:
        def __init__(self, field, op, value):
            self.field, self.op, self.value = field, op, value

        def stream(self):
            for doc_path, row in sorted(client.docs.items()):
                if not doc_path.startswith(path + '/') or doc_path.count('/') != path.count('/') + 1:
                    continue
                value = row
                for part in self.field.split('.'):
                    value = (value or {}).get(part) if isinstance(value, dict) else None
                hit = value == self.value if self.op == '==' else bool(set(value or []) & set(self.value))
                if hit:
                    yield SimpleNamespace(id=doc_path.rsplit('/', 1)[-1], to_dict=lambda row=row: dict(row))

    def ledger_ref(uid, _client):
        collection = client.collection('users').document(uid).collection('sync_content_ledger_dev')
        collection.where = lambda *, filter: _Query(filter.field_path, filter.op_string, filter.value)
        return collection

    monkeypatch.setattr(sources, '_ledger', ledger_ref)
    monkeypatch.setattr(sources, '_client', lambda _client: client)
    return path


def test_obligation_runs_before_donor_tombstones_and_still_erases_the_donor_upload(
    monkeypatch, tombstone_db, audio_job
):
    """F2 race: the reconciler can run the obligation before the cascade tombstones merge donors."""
    from database import sync_ledger_sources as sources

    ledger = _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'{ledger}/donor-upload'] = {
        'job_id': 'job-donor',
        'status': 'completed',
        'result': {'new_memories': ['donor'], 'updated_memories': []},
    }
    tombstone_db.docs[f'users/{UID}/conversations/donor'] = {'deleted': True}  # absorbed, tombstone not yet written
    erased = []

    def erase(uid, cid, donors, *, staging, settled, **_):
        plan = sources.staging_plan(uid, [cid, *donors], recorded=staging, settled=settled)
        erased.extend(plan.erasable)
        return {'shared_live': len(plan.shared_live)}

    purge_jobs.arm_audio_erasure(UID, 'c1', ['donor'])
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert erased == ['job-donor']


def test_recorded_staging_outlives_the_ledger_and_keeps_the_obligation_owed(monkeypatch, tombstone_db, audio_job):
    """A held obligation can outlive the 45-day ledger: the prefix recorded on its first run stays owed."""
    from database import sync_ledger_sources as sources
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked

    ledger = _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'{ledger}/upload'] = {
        'job_id': 'job-x',
        'status': 'completed',
        'result': {'new_memories': ['c1', 'sibling'], 'updated_memories': []},
    }
    plans = []

    def erase(uid, cid, donors, *, staging, settled, **_):
        plan = sources.staging_plan(uid, [cid, *donors], recorded=staging, settled=settled)
        plans.append(plan)
        if len(plans) == 1:
            raise StoragePrefixPurgeBlocked({('syncing', 'syncing/uid1/job-x/1.bin', 1): 'objectUnderActiveHold'})
        return {'shared_live': len(plan.shared_live)}

    # First run (sibling already deleted): the job and its fed conversations are recorded, then a hold stops it.
    tombstone_db.docs[f'users/{UID}/deleted_conversations/sibling'] = {}
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'storage_held'
    )
    assert _audio_row(tombstone_db)['staging_sources'] == {'job-x': ['c1', 'sibling']}
    # The ledger row expires while the obligation is held.
    tombstone_db.docs.pop(f'{ledger}/upload')
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert plans[-1].erasable == ('job-x',)


def test_recorded_live_sibling_still_protects_its_staging_after_the_ledger_expires(monkeypatch, tombstone_db):
    from database import sync_ledger_sources as sources

    _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'users/{UID}/conversations/sibling'] = {'status': 'completed'}
    plan = sources.staging_plan(UID, ['c1'], recorded={'job-x': ['c1', 'sibling']})
    assert plan.shared_live == ('job-x',) and not plan.erasable
    tombstone_db.docs[f'users/{UID}/deleted_conversations/sibling'] = {}
    assert sources.staging_plan(UID, ['c1'], recorded={'job-x': ['c1', 'sibling']}).in_flight == ('job-x',)
    assert sources.staging_plan(UID, ['c1'], recorded={'job-x': ['c1', 'sibling']}, settled=['job-x']).erasable == (
        'job-x',
    )


def test_audio_gate_contention_is_busy_not_failure(monkeypatch, tombstone_db, audio_job):
    kinds = []

    def busy_with_peer(error, uid, *, kind, **kwargs):
        kinds.append(kind)
        return kind == purge_jobs.AUDIO_GATE_KIND

    monkeypatch.setattr(legal_holds, 'gate_busy_with_peer', busy_with_peer)
    erase = MagicMock(side_effect=RuntimeError('audio gate held by a peer'))
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'busy'
    )
    assert kinds == [purge_jobs.AUDIO_GATE_KIND]
    assert _audio_row(tombstone_db)['last_outcome'] == 'busy'


def _ledger_erase(sources, plans, *, block_first=False):
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked
    from database.sync_ledger_sources import StagingInFlight

    def erase(uid, cid, donors, *, staging, settled, **_):
        plan = sources.staging_plan(uid, [cid, *donors], recorded=staging, settled=settled)
        plans.append(plan)
        if plan.in_flight:
            raise StagingInFlight(len(plan.in_flight))
        return {'shared_live': len(plan.shared_live)}

    return erase


def test_sibling_fed_after_the_first_record_survives_the_ledger_ttl(monkeypatch, tombstone_db, audio_job):
    from database import sync_ledger_sources as sources

    ledger = _fake_ledger(monkeypatch, tombstone_db)
    upload = f'{ledger}/upload'
    tombstone_db.docs[upload] = {
        'job_id': 'job-x',
        'status': 'processing',
        'result': {'new_memories': ['c1'], 'updated_memories': []},
    }
    plans = []
    erase = _ledger_erase(sources, plans)
    # First run: still processing, only c1 known; held in flight.
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_in_flight'
    )
    assert _audio_row(tombstone_db)['staging_sources'] == {'job-x': ['c1']}
    # The upload then feeds a new, live conversation and completes.
    tombstone_db.docs[upload] = {
        'job_id': 'job-x',
        'status': 'completed',
        'result': {'new_memories': ['c1', 'late'], 'updated_memories': []},
    }
    tombstone_db.docs[f'users/{UID}/conversations/late'] = {'status': 'completed'}
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_kept_for_live_sibling'
    )
    row = _audio_row(tombstone_db)
    assert row['staging_sources'] == {'job-x': ['c1', 'late']} and row['staging_settled'] == ['job-x']
    # The ledger row expires; the recorded live sibling still protects the staging.
    tombstone_db.docs.pop(upload)
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_kept_for_live_sibling'
    )
    assert plans[-1].shared_live == ('job-x',) and not plans[-1].erasable


def test_unsettled_recorded_job_is_held_after_its_ledger_expires(monkeypatch, tombstone_db, audio_job):
    from database import sync_ledger_sources as sources

    ledger = _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'{ledger}/upload'] = {
        'job_id': 'job-x',
        'status': 'processing',
        'result': {'new_memories': ['c1'], 'updated_memories': []},
    }
    plans = []
    erase = _ledger_erase(sources, plans)
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_in_flight'
    )
    tombstone_db.docs.pop(f'{ledger}/upload')
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_in_flight'
    )
    assert plans[-1].in_flight == ('job-x',) and not plans[-1].erasable
    assert _audio_row(tombstone_db) is not None


def test_deliberate_holds_reset_attempts_but_failures_keep_counting(tombstone_db, audio_job):
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked

    blocked = StoragePrefixPurgeBlocked({('b', 'o', 1): 'objectUnderActiveHold'})
    erase = MagicMock(side_effect=[blocked] * 9 + [RuntimeError('ledger unavailable')])
    for _ in range(9):
        purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase)
        assert _audio_row(tombstone_db)['attempts'] == 0  # never reaches the stuck-obligation alert
    with pytest.raises(RuntimeError):
        purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase)
    assert _audio_row(tombstone_db)['attempts'] == 1  # a real failure still counts toward the alert


def test_a_new_outcome_clears_detail_fields_it_does_not_set(tombstone_db, audio_job):
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked
    from google.cloud import firestore

    erase = MagicMock(
        side_effect=[
            StoragePrefixPurgeBlocked({('b', 'o', 1): 'objectUnderActiveHold'}, unverified=2),
            RuntimeError('x'),
        ]
    )
    purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase)
    assert _audio_row(tombstone_db)['blocked_objects'] == 1
    with pytest.raises(RuntimeError):
        purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase)
    row = _audio_row(tombstone_db)
    assert row['last_reason'] == 'RuntimeError'
    assert row['blocked_objects'] is firestore.DELETE_FIELD and row['unverified'] is firestore.DELETE_FIELD


def test_more_than_500_owed_segments_are_journaled_in_bounded_chunks(
    monkeypatch, owner, tombstone_db, armed, dispatch, fast_clock
):
    """One Firestore transaction holds at most 500 writes: a big upload's owed ids must not fail forever."""
    plane = owner.plane()
    ids = {f'seg-{i:04d}' for i in range(520)}
    for segment_id in ids:
        plane.add('jobs', segment_id, conversation_id='capture-identity', priority=1)
    row = _obligation(tombstone_db, 'c1')
    row['progress'] = {'ns': len(purge.NAMESPACES), 'phase': 'discover'}  # cursor past discovery
    row['progress_arm'] = {'armed_at': row['armed_at'], 'arm_revision': row['arm_revision']}
    plane.owed = {'c1': {NS: set(ids)}}
    sizes, positions = [], []
    checkpoint = purge_jobs.RunProgress.checkpoint

    def bounded(self, position, *, add_segments=None):
        if add_segments is not None:
            sizes.append(len(list(add_segments[1])))
        else:
            positions.append(dict(position))
        return checkpoint(self, position, add_segments=add_segments)

    monkeypatch.setattr(purge_jobs.RunProgress, 'checkpoint', bounded)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    outcome = _run(armed, 1)
    while outcome == 'checkpointed':
        _advance(tombstone_db, armed, 1)
        deletion_batch_purge.reconcile_conversation_batch_purges()
        outcome = _run(armed, int(_obligation(tombstone_db, 'c1')['generation']))
    assert outcome == 'purged'
    journaled = [size for size in sizes if size]
    assert sum(journaled[:2]) == 520 and max(journaled) <= purge.OWED_JOURNAL_CHUNK
    # The rewind was persisted before the first chunk, so a crash between chunks resumes at dependents.
    assert positions[0] == {'ns': 0, 'phase': 'dependents'}
    assert not any(plane.doc('jobs', segment_id) for segment_id in ids)


def test_a_legal_hold_pass_still_records_the_ledger_before_it_expires(monkeypatch, tombstone_db, audio_job):
    from database import sync_ledger_sources as sources  # noqa: F401 - _fake_ledger patches it

    ledger = _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'{ledger}/upload'] = {
        'job_id': 'job-x',
        'status': 'processing',
        'result': {'new_memories': ['c1'], 'updated_memories': []},
    }

    def held(uid):
        raise legal_holds.LegalHoldActive('held')

    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', held)
    erase = MagicMock()
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'held'
    )
    # The upload completes and feeds a sibling while the hold lasts; the next held pass records both.
    tombstone_db.docs[f'{ledger}/upload'] = {
        'job_id': 'job-x',
        'status': 'completed',
        'result': {'new_memories': ['c1', 'late'], 'updated_memories': []},
    }
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'held'
    )
    row = _audio_row(tombstone_db)
    assert row['staging_sources'] == {'job-x': ['c1', 'late']} and row['staging_settled'] == ['job-x']
    erase.assert_not_called()


def test_visible_row_backs_off_to_hourly_then_daily_and_counts_toward_the_alert(tombstone_db, audio_job):
    tombstone_db.docs[f'users/{UID}/conversations/c1'] = {'status': 'completed'}
    erase = MagicMock()
    start = purge_jobs._now()
    waits = []
    for hours in (0, 0, 0, 0, 0, 0):
        assert purge_jobs.run_audio_erasure_job(
            audio_job, _audio_generation(tombstone_db, audio_job), erase=erase, now=start
        ) == ('conversation_row_live')
        row = _audio_row(tombstone_db)
        waits.append(round((row['due_at'] - purge_jobs._now()).total_seconds() / 60))
        assert row['attempts'] == 0
    assert waits == [5, 10, 20, 40, 60, 60]
    later = start + purge_jobs.timedelta(hours=25)
    purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase, now=later)
    row = _audio_row(tombstone_db)
    assert row['due_at'] > purge_jobs._now() + purge_jobs.timedelta(hours=23)  # daily
    assert row['attempts'] >= 1  # past a day it counts toward the stuck-obligation alert
    assert row['row_live_since'] == start
    erase.assert_not_called()


def test_sync_conversation_with_nothing_traceable_logs_the_accepted_retention(monkeypatch, tombstone_db, caplog):
    caplog.set_level('INFO', logger=purge_jobs.logger.name)
    monkeypatch.setattr(purge_jobs, 'assert_account_deletion_permitted', lambda uid: None)
    _fake_ledger(monkeypatch, tombstone_db)
    tombstone_db.docs[f'users/{UID}/deleted_conversations/c1'] = {'conversation_id': 'c1'}
    purge_jobs.arm_audio_erasure(UID, 'c1', [], sync_sourced=True)
    job = purge_jobs.audio_job_id(UID, 'c1')
    assert purge_jobs.run_audio_erasure_job(job, _audio_generation(tombstone_db, job), erase=MagicMock()) == 'erased'
    assert 'outcome=staging_undiscoverable_after_ledger_ttl' in caplog.text


def test_completed_delete_marker_erases_whatever_the_row_looks_like(tombstone_db, audio_job):
    """The arming request marks the obligation once it deleted the row: the runner gates on that."""
    tombstone_db.docs[f'users/{UID}/conversations/c1'] = {'status': 'completed'}  # e.g. a straggling write
    erase = MagicMock(return_value={'shared_live': 0})
    purge_jobs.mark_audio_delete_completed(UID, 'c1')
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    erase.assert_called_once()
    assert _audio_row(tombstone_db) is None


def test_ordinary_delete_order_arm_then_row_gone_then_marker_is_erased(tombstone_db, audio_job):
    """A run between arming and the row delete holds; the marker redrives it at once and it erases."""
    tombstone_db.docs[f'users/{UID}/conversations/c1'] = {'status': 'completed'}
    erase = MagicMock(return_value={'shared_live': 0})
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'conversation_row_live'
    )
    assert _audio_row(tombstone_db)['due_at'] > purge_jobs._now() + purge_jobs.timedelta(minutes=4)
    tombstone_db.docs.pop(f'users/{UID}/conversations/c1')
    purge_jobs.mark_audio_delete_completed(UID, 'c1')
    assert _audio_row(tombstone_db)['due_at'] <= purge_jobs._now()  # due now, not after the backoff
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )


def test_marker_landing_while_a_run_holds_for_the_row_makes_it_due_now(tombstone_db, audio_job):
    generation = _audio_generation(tombstone_db, audio_job)
    claim, _row, token = purge_jobs.begin_run(audio_job, generation, collection=purge_jobs.AUDIO_COLLECTION)
    assert claim == 'run'
    purge_jobs.mark_audio_delete_completed(UID, 'c1')  # the request finished while the run read the row
    purge_jobs.finish_run(
        audio_job,
        generation,
        token,
        'held',
        collection=purge_jobs.AUDIO_COLLECTION,
        detail={'last_reason': 'conversation_row_live'},
        retry_after=purge_jobs.AUDIO_ROW_LIVE_RETRY_SECONDS,
    )
    assert _audio_row(tombstone_db)['due_at'] <= purge_jobs._now()


def test_siblings_over_the_per_pass_cap_are_recorded_and_continued(tombstone_db, audio_job):
    calls = []
    summaries = [
        {'shared_live': 0, 'unchecked_siblings': 1, 'deleted_siblings': ['s0', 's1']},
        {'shared_live': 0, 'deleted_siblings': ['s0', 's1', 's2']},
    ]

    def erase(uid, cid, donors, *, staging, settled, deleted_siblings, **_):
        calls.append(list(deleted_siblings))
        return summaries[len(calls) - 1]

    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'staging_siblings_pending'
    )
    row = _audio_row(tombstone_db)
    assert row['last_reason'] == 'staging_siblings_pending' and row['unchecked_siblings'] == 1
    assert row['staging_deleted_siblings'] == ['s0', 's1'] and row['attempts'] == 0
    assert row['due_at'] <= purge_jobs._now() + purge_jobs.timedelta(
        seconds=purge_jobs.AUDIO_SIBLINGS_PENDING_RETRY_SECONDS + 5
    )
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert calls == [[], ['s0', 's1']]


def test_marker_after_the_obligation_was_discharged_recreates_nothing(tombstone_db, audio_job):
    erase = MagicMock(return_value={'shared_live': 0})
    assert purge_jobs.run_audio_erasure_job(audio_job, _audio_generation(tombstone_db, audio_job), erase=erase) == (
        'erased'
    )
    assert _audio_row(tombstone_db) is None
    purge_jobs.mark_audio_delete_completed(UID, 'c1')  # the request's marker lands after the runner discharged it
    assert _audio_row(tombstone_db) is None
