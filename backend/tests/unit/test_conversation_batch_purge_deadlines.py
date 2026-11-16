"""Round 3 (#25124): a gate-held unit has a hard total deadline, and runs never start work past budget.

1. Inside a unit every Firestore/storage RPC is one attempt (no SDK retry) bounded
   by the time left; the gate document expires just after the unit's hard bound,
   so a failed release still frees foreground deletes inside their 20 s wait.
2. The run budget is checked before every unit, page read and discovery point
   read; an expiry mid-page replays that page from the previous checkpoint.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversation_batch_purge_jobs as purge_jobs
from database import legal_holds, rpc_deadline
from database.batch_pipeline_privacy import privacy_owner_key
from utils.batch_pipeline import retention
from utils.conversations import deletion_batch_purge
from tests.unit.test_conversation_batch_purge_resumable import (  # noqa: F401 - fixtures
    NS,
    _matching_artifacts,
    _run,
    owner,
)
from tests.unit.test_conversation_delete_gate_wait import (  # noqa: F401 - fixtures
    GATE_PATH,
    UID,
    _gate_doc,
    _obligation,
    _plane,
    armed,
    dispatch,
    fast_clock,
    gate_client,
    tombstone_db,
)


@pytest.fixture
def mono(monkeypatch):
    state = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(rpc_deadline, 'now', lambda: state.now)
    return state


# --- 1. hard RPC deadline at the SDK boundary ---


class _Gapic:
    def __init__(self):
        self.calls = []
        for name in ('get_document', 'commit', 'begin_transaction', 'rollback', 'run_query'):
            setattr(self, name, self._recorder(name))

    def _recorder(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, kwargs))
            return name

        return call


def test_bound_firestore_rpcs_are_one_attempt_bounded_by_the_time_left(mono):
    api = _Gapic()
    client = SimpleNamespace(_firestore_api=api)
    rpc_deadline.bind_firestore_client(client)
    rpc_deadline.bind_firestore_client(client)  # idempotent

    api.commit(request={})  # outside a unit: untouched
    assert api.calls[-1] == ('commit', {'request': {}})
    with rpc_deadline.rpc_deadline(mono.now + 5):
        mono.now += 2
        api.commit(request={})
        assert api.calls[-1][1] == {'request': {}, 'retry': None, 'timeout': 3}
        api.run_query(request={}, retry='caller-retry', timeout=60)  # callers cannot widen it
        assert api.calls[-1][1]['retry'] is None and api.calls[-1][1]['timeout'] == 3
        mono.now += 3
        with pytest.raises(rpc_deadline.RpcDeadlineExceeded):
            api.begin_transaction(request={})
        assert api.calls[-1][0] == 'run_query'  # not sent
        api.rollback(request={})  # rollback only releases locks: brief grace
        assert api.calls[-1][1]['timeout'] == rpc_deadline.ROLLBACK_GRACE_SECONDS


def test_bound_storage_session_caps_timeouts_and_refuses_past_the_deadline(mono):
    calls = []
    session = SimpleNamespace(request=lambda *args, **kwargs: calls.append(kwargs))
    client = SimpleNamespace(_http=session)
    rpc_deadline.bind_storage_client(client)
    session.request('DELETE', 'https://storage', timeout=60)
    assert calls[-1] == {'timeout': 60}
    with rpc_deadline.rpc_deadline(mono.now + 4):
        session.request('DELETE', 'https://storage', timeout=(60, 60))
        assert calls[-1] == {'timeout': (4, 4)}  # no max_allowed_time: it fires only after a response
        mono.now += 5
        with pytest.raises(rpc_deadline.RpcDeadlineExceeded):
            session.request('DELETE', 'https://storage')


def _object_uri(uid='synthetic-owner'):
    return f'gs://synthetic-bucket/batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key(uid)}/audio/a.enc#123'


def test_storage_delete_inside_a_unit_disables_the_120s_generation_retry(monkeypatch, mono):
    """Reviewer round-3 probe 2: timeout=5 alone kept DEFAULT_RETRY_IF_GENERATION_SPECIFIED (120 s)."""
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-bucket')
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value
    retention.delete_batch_object('synthetic-owner', _object_uri(), storage_client=client)
    assert blob.delete.call_args.kwargs == {'if_generation_match': 123}  # unchanged for ordinary callers
    retention.delete_batch_object('synthetic-owner', _object_uri(), timeout=5.0, storage_client=client)
    assert blob.delete.call_args.kwargs == {'if_generation_match': 123, 'timeout': 5.0, 'retry': None}
    with rpc_deadline.rpc_deadline(mono.now + 3):
        retention.delete_batch_object('synthetic-owner', _object_uri(), timeout=5.0, storage_client=client)
        assert blob.delete.call_args.kwargs == {'if_generation_match': 123, 'timeout': 3, 'retry': None}
        mono.now += 3
        blob.delete.reset_mock()
        with pytest.raises(rpc_deadline.RpcDeadlineExceeded):
            retention.delete_batch_object('synthetic-owner', _object_uri(), timeout=5.0, storage_client=client)
        blob.delete.assert_not_called()


def test_unit_gate_expires_so_a_lost_release_cannot_outlast_the_foreground_wait(
    monkeypatch, gate_client, fast_clock, mono
):
    real_finish = legal_holds.finish_destructive_operation
    outage = {'on': True}

    def release_never_lands(*args, **kwargs):
        if not outage['on']:
            return real_finish(*args, **kwargs)
        mono.now += 1.0
        raise RuntimeError('commit unavailable')

    monkeypatch.setattr(legal_holds, 'finish_destructive_operation', release_never_lands)
    started = mono.now
    with legal_holds.bounded_destructive_unit(UID):
        held = dict(gate_client.docs[GATE_PATH])
    # The release retried only within the unit's hold bound, then gave up.
    assert mono.now - started <= legal_holds.UNIT_HOLD_SECONDS + 1.0
    assert gate_client.docs[GATE_PATH]['state'] == 'running'
    expires_in = (held['expires_at'] - held['started_at']).total_seconds()
    assert expires_in == legal_holds.UNIT_EXPIRY_SECONDS
    # Past the expiry the stuck gate blocks nothing: a foreground delete acquires without waiting.
    gate_client.docs[GATE_PATH]['expires_at'] = legal_holds.datetime.now(legal_holds.timezone.utc)
    outage['on'] = False
    fast_clock.sleeps.clear()
    with legal_holds.destructive_operation_gate(UID, wait_seconds=20) as token:
        assert gate_client.docs[GATE_PATH]['token'] == token
    assert fast_clock.sleeps == []


def test_unit_body_past_its_deadline_sends_nothing_and_releases(gate_client, fast_clock, mono):
    api = _Gapic()
    client = rpc_deadline.bind_firestore_client(SimpleNamespace(_firestore_api=api))
    with pytest.raises(rpc_deadline.RpcDeadlineExceeded):
        with legal_holds.bounded_destructive_unit(UID):
            mono.now += legal_holds.UNIT_BODY_SECONDS  # e.g. a slow read consumed the body budget
            client._firestore_api.commit(request={'writes': ['erase']})
    assert api.calls == []
    assert gate_client.docs[GATE_PATH]['state'] == 'failed'


def test_unit_gate_carries_its_expiry_but_route_gates_do_not(gate_client, fast_clock):
    with legal_holds.bounded_destructive_unit(UID):
        assert gate_client.docs[GATE_PATH]['expires_at'] > gate_client.docs[GATE_PATH]['started_at']
    with legal_holds.destructive_operation_gate(UID):
        assert 'expires_at' not in gate_client.docs[GATE_PATH]


def test_malformed_gate_expiry_fails_closed(gate_client):
    gate_client.docs[GATE_PATH] = {**_gate_doc(), 'expires_at': 'soon'}
    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        with legal_holds.destructive_operation_gate(UID):
            pass


# --- 2. run budget before every unit and read batch ---


def test_page_started_near_the_budget_starts_no_unit_past_it_and_resume_erases_the_rest(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Reviewer round-3 probe 1: a 100-row page begun at 1199 s with 3.1 s rows ran to 1509 s."""
    elapsed = {'seconds': 0.0}
    unit_starts = []

    def page(namespace, table, after):
        if namespace == NS and table == 'artifacts' and after is None:
            elapsed['seconds'] = 1199.0

    def row_cost(seconds):
        elapsed['seconds'] += seconds

    plane = owner.plane(on_page=page, row_cost=3.1, sleep=row_cost)
    _matching_artifacts(plane, 100)
    real_unit = purge_jobs.RunProgress.unit

    def unit(self):
        unit_starts.append(elapsed['seconds'])
        return real_unit(self)

    monkeypatch.setattr(purge_jobs.RunProgress, 'unit', unit)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1, clock=lambda: elapsed['seconds']) == 'checkpointed'
    assert unit_starts and max(unit_starts) < purge_jobs.RUN_BUDGET_SECONDS
    assert len(plane.erased) < 100
    # The page's cursor was never advanced past unprocessed matches.
    saved = _obligation(tombstone_db, 'c1')['progress']
    assert saved['phase'] == 'dependents' and not saved.get('table') and saved.get('after') is None

    deletion_batch_purge.reconcile_conversation_batch_purges()
    elapsed['seconds'] = 0.0
    plane.on_page = None
    assert _run(armed, dispatch[-1][1], clock=lambda: 0.0) == 'purged'
    assert sorted(doc_id for _, doc_id in plane.erased) == [f'a{index:03d}' for index in range(100)]
    assert all(plane.doc('artifacts', f'a{index:03d}') is None for index in range(100))
    assert _obligation(tombstone_db, 'c1') is None


def test_discovery_expiry_mid_page_replays_the_page_and_finds_every_segment(
    owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    elapsed = {'seconds': 0.0, 'reads': 0}
    plane = owner.plane()
    for index in range(160):  # two discovery pages
        plane.add('jobs', f'j{index:03d}', conversation_id='c1', priority=1)
    real_collection = tombstone_db.collection

    def costly_collection(name):
        if name == f'{NS}_results':
            elapsed['reads'] += 1
            elapsed['seconds'] += 10.0  # each job's result point read costs 10 s of budget
        return real_collection(name)

    tombstone_db.collection = costly_collection
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1, clock=lambda: elapsed['seconds']) == 'checkpointed'
    # Page one (1000 s) was saved; page two stopped at the budget, mid-page, unsaved.
    assert 100 < elapsed['reads'] < 160
    progress = _obligation(tombstone_db, 'c1')['progress']
    assert progress['phase'] == 'discover' and progress['after'] == 'j099'
    tombstone_db.collection = real_collection

    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, dispatch[-1][1], clock=lambda: 0.0) == 'purged'
    assert all(plane.doc('jobs', f'j{index:03d}') is None for index in range(160))
    assert _obligation(tombstone_db, 'c1') is None


def test_every_run_saves_a_step_before_honouring_its_budget(owner, tombstone_db, gate_client, armed, dispatch):
    plane = owner.plane()
    plane.add('results', 'r1', conversation_id='c1', segment_id='r1')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    outcomes = []
    for _ in range(40):  # zero budget: one saved step per run, never a no-progress loop
        outcomes.append(_run(armed, dispatch[-1][1], budget_seconds=0))
        if outcomes[-1] == 'purged':
            break
        deletion_batch_purge.reconcile_conversation_batch_purges()
    assert outcomes[-1] == 'purged' and outcomes.count('checkpointed') >= 3
    assert plane.doc('results', 'r1') == {'owner_key': privacy_owner_key(UID), 'projection_state': 'erased'}
