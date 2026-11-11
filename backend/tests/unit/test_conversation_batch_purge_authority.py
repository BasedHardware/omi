"""Round 4 (#25124): authority, not a timer, decides when an erasure may still happen.

1. A remote (object) erasure keeps the account gate held, past its expiry,
   until its outcome is known; an unknown outcome fails closed and the next run
   settles it under the same gate token. Firestore erasures re-prove the unit's
   token and the absence of a hold inside their own transaction.
2. Segment binding reads check the run budget one by one, and every RPC of a
   run is bounded by the run deadline.
"""

from __future__ import annotations

import contextvars
from types import SimpleNamespace

import pytest
import requests

from database import conversation_batch_purge_jobs as purge_jobs
from database import legal_holds, rpc_deadline
from utils.conversations import deletion_batch_purge
from tests.unit.test_conversation_batch_purge_resumable import NS, _run, owner  # noqa: F401 - fixtures
from tests.unit.test_conversation_delete_gate_wait import (  # noqa: F401 - fixtures
    GATE_PATH,
    HOLD_PATH,
    UID,
    _obligation,
    _plane,
    _Transaction,
    armed,
    dispatch,
    fast_clock,
    gate_client,
    tombstone_db,
)


def _expire(gate_client):
    gate_client.docs[GATE_PATH]['expires_at'] = legal_holds.datetime.now(legal_holds.timezone.utc)


def _hold(gate_client, active=True):
    legal_holds._place_legal_hold_transaction.to_wrap(
        gate_client.transaction(), gate_client, UID, 'admin', active, legal_holds.datetime.now(legal_holds.timezone.utc)
    )


def _foreground_acquires(gate_client):
    """A fresh-context fail-fast acquisition: True when a foreground delete could take the gate now."""

    def attempt():
        try:
            with legal_holds.destructive_operation_gate(UID):
                return True
        except legal_holds.DestructiveOperationInProgress:
            return False

    return contextvars.Context().run(attempt)


# --- 1. remote erasure holds authority until its outcome is known ---


def test_in_flight_remote_erasure_keeps_the_gate_past_expiry_against_takeover_and_holds(gate_client, fast_clock):
    """Reviewer round-4 probe: an expired unit gate was taken over and a hold committed mid-delete."""
    seen = {}

    def slow_remote_delete():
        _expire(gate_client)  # the unit's 10 s expiry passes while the request is still out
        seen['takeover'] = _foreground_acquires(gate_client)
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            _hold(gate_client)  # the hold writer cannot overtake an unresolved erasure
        seen['hold_during_erase'] = gate_client.docs.get(HOLD_PATH)
        return 'deleted'

    with legal_holds.bounded_destructive_unit(UID) as authority:
        assert authority.remote(slow_remote_delete, target='gs://bucket/owners/a') == 'deleted'
        assert gate_client.docs[GATE_PATH]['remote_inflight'] is False  # outcome known: mark cleared
    assert seen == {'takeover': False, 'hold_during_erase': None}
    # Once resolved, the expired gate no longer blocks: authority can transfer, and the hold can land.
    _expire(gate_client)
    assert _foreground_acquires(gate_client) is True
    _hold(gate_client)
    assert gate_client.docs[HOLD_PATH]['active'] is True


def test_firestore_erasure_after_takeover_or_hold_fails_inside_its_own_transaction(gate_client, fast_clock):
    with legal_holds.bounded_destructive_unit(UID) as authority:
        authority.fence(_Transaction(gate_client))  # ours, no hold: allowed
        token = gate_client.docs[GATE_PATH]['token']
        gate_client.docs[GATE_PATH]['token'] = 'successor'  # the gate changed hands
        with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
            authority.fence(_Transaction(gate_client))
        gate_client.docs[GATE_PATH]['token'] = token
        gate_client.docs[HOLD_PATH] = {
            'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION,
            'issuer': 'admin',
            'active': True,
        }
        with pytest.raises(legal_holds.LegalHoldActive):
            authority.fence(_Transaction(gate_client))
        gate_client.docs.pop(HOLD_PATH)


def test_remote_erasure_is_not_sent_once_the_gate_is_lost(gate_client, fast_clock):
    sent = []
    with legal_holds.bounded_destructive_unit(UID) as authority:
        gate_client.docs[GATE_PATH]['token'] = 'successor'
        with pytest.raises(legal_holds.DestructiveGateTakeover):
            authority.remote(lambda: sent.append(True), target='gs://bucket/owners/a')
    assert sent == []


def test_unknown_remote_outcome_fails_closed_then_the_next_run_settles_it(gate_client, fast_clock):
    attempts = []

    def no_response():
        attempts.append(True)
        raise requests.exceptions.ReadTimeout('no response')

    with pytest.raises(requests.exceptions.ReadTimeout):
        with legal_holds.bounded_destructive_unit(UID) as authority:
            authority.remote(no_response, target='gs://bucket/owners/a#7')
    assert len(attempts) == 1 + legal_holds.UNIT_REMOTE_RESOLVE_ATTEMPTS
    gate = gate_client.docs[GATE_PATH]
    assert (
        gate['state'] == 'running'
        and gate['remote_inflight'] is True
        and gate['remote_target'] == 'gs://bucket/owners/a#7'
    )
    _expire(gate_client)
    assert _foreground_acquires(gate_client) is False  # fail closed: the erasure may still land
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _hold(gate_client)

    # The obligation's next run settles it under the same token once the same delete answers definitively.
    gate['remote_inflight_at'] = gate['remote_inflight_at'] - legal_holds.timedelta(
        seconds=legal_holds.UNIT_REMOTE_STUCK_SECONDS + 1
    )
    progress = SimpleNamespace(uid=UID)
    resolved = []
    purge_jobs.RunProgress.settle_stuck(progress, lambda target: resolved.append(target) or True)
    assert resolved == ['gs://bucket/owners/a#7']
    assert gate_client.docs[GATE_PATH]['state'] == 'failed'
    assert _foreground_acquires(gate_client) is True


def test_stuck_gate_is_not_settled_without_a_definitive_answer(gate_client, fast_clock):
    with pytest.raises(requests.exceptions.ConnectionError):
        with legal_holds.bounded_destructive_unit(UID) as authority:
            authority.remote(lambda: (_ for _ in ()).throw(requests.exceptions.ConnectionError('reset')))
    gate = gate_client.docs[GATE_PATH]
    gate['remote_target'] = 'gs://bucket/owners/a'
    gate['remote_inflight_at'] -= legal_holds.timedelta(seconds=legal_holds.UNIT_REMOTE_STUCK_SECONDS + 1)
    purge_jobs.RunProgress.settle_stuck(SimpleNamespace(uid=UID), lambda target: False)
    assert gate_client.docs[GATE_PATH]['state'] == 'running'


class _HttpError(Exception):
    code = 503
    response = object()


@pytest.mark.parametrize(
    'error,known',
    [
        (_HttpError(), True),  # the server answered: that request is finished
        (rpc_deadline.RpcDeadlineExceeded('not sent'), True),
        (ValueError('foreign uri'), True),
        (requests.exceptions.ReadTimeout('no response'), False),
        (requests.exceptions.ConnectionError('reset'), False),
        (TimeoutError('socket'), False),
    ],
)
def test_remote_outcome_is_known_only_with_a_response_or_when_never_sent(error, known):
    assert legal_holds.remote_outcome_known(error) is known


# --- 2. segment binding reads and out-of-unit RPCs are bounded by the run ---


def test_segment_binding_reads_stop_at_the_budget_not_after_the_whole_chunk(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Reviewer round-4 probe: entered at 1199 s with 20 s reads, the 20-read prefetch ran to 1599 s."""
    elapsed, read_starts = {'seconds': 0.0}, []
    plane = owner.plane()
    for index in range(10):
        segment = f's{index:03d}'
        plane.add('results', segment, conversation_id='c1', segment_id=segment)
    real_pending = purge_jobs.RunProgress.pending_segments

    def pending(self, namespace, limit):
        elapsed['seconds'] = 1199.0
        return real_pending(self, namespace, limit)

    monkeypatch.setattr(purge_jobs.RunProgress, 'pending_segments', pending)
    ref_type = type(tombstone_db.collection('x').document('x'))
    real_get = ref_type.get

    def costly_get(ref, *args, **kwargs):
        if ref.path.startswith((f'{NS}_jobs/', f'{NS}_results/')):
            read_starts.append(elapsed['seconds'])
            elapsed['seconds'] += 20.0
        return real_get(ref, *args, **kwargs)

    monkeypatch.setattr(ref_type, 'get', costly_get)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1, clock=lambda: elapsed['seconds']) == 'checkpointed'
    assert read_starts and max(read_starts) < purge_jobs.RUN_BUDGET_SECONDS  # no read starts past the budget
    assert elapsed['seconds'] < purge_jobs.RUN_BUDGET_SECONDS + 20.0 + 1
    assert len(_obligation(tombstone_db, 'c1')) and plane.doc('results', 's000')['conversation_id'] == 'c1'

    monkeypatch.setattr(purge_jobs.RunProgress, 'pending_segments', real_pending)
    monkeypatch.setattr(ref_type, 'get', real_get)
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, dispatch[-1][1], clock=lambda: 0.0) == 'purged'
    assert all(plane.doc('results', f's{index:03d}').get('projection_state') == 'erased' for index in range(10))


def test_every_rpc_of_a_run_is_bounded_by_the_run_deadline(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch
):
    seen = []
    real_checkpoint = purge_jobs.RunProgress.checkpoint

    def checkpoint(self, *args, **kwargs):
        seen.append(rpc_deadline.remaining())
        return real_checkpoint(self, *args, **kwargs)

    monkeypatch.setattr(purge_jobs.RunProgress, 'checkpoint', checkpoint)
    owner.plane().add('results', 'r1', conversation_id='c1', segment_id='r1')
    deletion_batch_purge.reconcile_conversation_batch_purges()
    assert _run(armed, 1) == 'purged'
    budget = purge_jobs.RUN_BUDGET_SECONDS + purge_jobs.RUN_FINALIZE_SECONDS
    assert seen and all(left is not None and 0 < left <= budget for left in seen)
    assert budget < 1500  # inside the Cloud Tasks dispatch deadline / handler timeout


# --- round 5 ---


class _Http503(Exception):
    code = 503
    response = object()


class _Http412(Exception):
    code = 412
    response = object()


def test_a_retry_503_does_not_settle_an_unanswered_delete(gate_client, fast_clock):
    """Round-5 item 1: the earlier request had no response; a later 503 proves nothing about it."""
    calls = []

    def first_unanswered_then_503():
        calls.append(True)
        if len(calls) == 1:
            raise requests.exceptions.ReadTimeout('no response')
        raise _Http503('unavailable')

    with pytest.raises(requests.exceptions.ReadTimeout):
        with legal_holds.bounded_destructive_unit(UID) as authority:
            authority.remote(first_unanswered_then_503, target='gs://bucket/owners/a#7')
    gate = gate_client.docs[GATE_PATH]
    assert gate['state'] == 'running' and gate['remote_inflight'] is True  # not released on a 503
    assert _foreground_acquires(gate_client) is False
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _hold(gate_client)
    # Only proof that the pinned generation is gone settles it: deleted/absent now, or 412.
    assert legal_holds.settles_unknown_erasure(lambda: (_ for _ in ()).throw(_Http503('unavailable'))) is False
    assert legal_holds.settles_unknown_erasure(lambda: None) is True
    assert legal_holds.settles_unknown_erasure(lambda: (_ for _ in ()).throw(_Http412('not that generation'))) is True


def test_unresolved_remote_gate_blocks_past_the_stale_bound_and_reports_it(gate_client, fast_clock, caplog):
    """Round-5 item 2: the 6 h stale takeover must not apply while an erasure is unresolved."""
    old = legal_holds.datetime.now(legal_holds.timezone.utc) - legal_holds.timedelta(hours=7)
    gate_client.docs[GATE_PATH] = {
        'schema_version': legal_holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': 'explicit_memory_deletion',
        'token': 'unresolved-request',
        'state': 'running',
        'started_at': old,
        'finished_at': None,
        'expires_at': old + legal_holds.timedelta(seconds=10),
        'remote_inflight': True,
        'remote_inflight_at': old,
        'remote_target': 'gs://bucket/owners/a#7',
    }
    with caplog.at_level('ERROR', logger='database.legal_holds'):
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            _hold(gate_client)
        assert _foreground_acquires(gate_client) is False
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            with legal_holds.destructive_operation_gate(UID, kind='account_deletion'):
                pass
    assert 'event=destructive_gate_remote_unresolved' in caplog.text
    # An ordinary abandoned gate still goes stale as before.
    gate_client.docs[GATE_PATH]['remote_inflight'] = False
    assert _foreground_acquires(gate_client) is True


def test_admission_is_inside_the_run_deadline_and_debited_from_the_budget(
    monkeypatch, owner, tombstone_db, gate_client, armed, dispatch, fast_clock
):
    """Round-5 item 3: begin_run ran with no deadline, and its time was not charged to the budget."""
    from database import batch_pipeline_conversation_purge as purge

    elapsed, seen = {'seconds': 0.0}, {}
    owner.plane()
    deletion_batch_purge.reconcile_conversation_batch_purges()
    monkeypatch.setattr(rpc_deadline, 'now', lambda: elapsed['seconds'])
    real_begin = purge_jobs.begin_run

    def slow_admission(*args, **kwargs):
        seen['admission_deadline'] = rpc_deadline.current()
        result = real_begin(*args, **kwargs)
        elapsed['seconds'] += 301.0  # SDK/transaction retries before the claim lands
        return result

    def body(uid, conversation_id, progress, **kwargs):
        seen['run_deadline'] = rpc_deadline.current()
        progress.checkpoint({'ns': 0, 'phase': 'discover', 'table': 0, 'after': None})
        elapsed['seconds'] += purge_jobs.RUN_BUDGET_SECONDS - 301.0
        seen['expired_at_budget_from_entry'] = progress.expired()
        raise purge.PurgeCheckpointed()

    monkeypatch.setattr(purge_jobs, 'begin_run', slow_admission)
    monkeypatch.setattr(purge, 'purge_conversation', body)
    assert _run(armed, 1, clock=lambda: elapsed['seconds']) == 'checkpointed'
    limit = purge_jobs.RUN_BUDGET_SECONDS + purge_jobs.RUN_FINALIZE_SECONDS
    assert seen['admission_deadline'] == limit  # admission is bounded from entry
    assert seen['run_deadline'] == limit  # not reset after admission
    assert seen['expired_at_budget_from_entry'] is True  # admission time was debited
