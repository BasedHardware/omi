"""Durable sync dead-letter ledger and its Redis terminal-publish fence.

``sync_dead_letters/{job_id}`` records bounded diagnosis for terminal backfill
failures. The pending record must exist *before* Redis publishes
``failed``/``partial_failure``, confirmation flips it to ``dead_letter`` once,
the status poll refuses terminal backfill answers without a record, and the
terminal-delivery path confirms before ACK/cleanup. Client compatibility: the
app only ever sees the existing ``failed``/``partial_failure`` statuses and
only ACKs ``completed`` — verified here against the Dart terminal policy.
"""

from __future__ import annotations

import asyncio
import json
import time
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

import pytest

import database.sync_dead_letters as ledger
import database.sync_jobs as sync_jobs
import routers.sync as sync_router
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class _Snapshot:
    def __init__(self, data):
        self._data = deepcopy(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return deepcopy(self._data)


class _DocRef:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, transaction=None):
        return _Snapshot(self.db.rows.get(self.path))

    def set(self, data, merge=False):
        row = self.db.rows.setdefault(self.path, {}) if merge else {}
        row.update(deepcopy(data))
        self.db.rows[self.path] = row


class _Collection:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def document(self, name):
        return _DocRef(self.db, (*self.path, name))


class _Transaction:
    def __init__(self, db):
        self.db = db

    def set(self, doc, data, merge=False):
        doc.set(data, merge=merge)

    def update(self, doc, patch):
        doc.db.rows.setdefault(doc.path, {}).update(deepcopy(patch))


class _FakeFirestore:
    def __init__(self):
        self.rows: dict[tuple, dict] = {}

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

    def doc(self, job_id):
        return self.rows.get((ledger.DEAD_LETTERS_COLLECTION, job_id))


@pytest.fixture(autouse=True)
def _transactional_passthrough(monkeypatch):
    monkeypatch.setattr(ledger.firestore, 'transactional', lambda function: function)


@pytest.fixture
def firestore():
    return _FakeFirestore()


def test_pending_record_has_exact_bounded_schema(firestore):
    record = ledger.record_dead_letter_pending(
        job_id='job-1',
        uid='u1',
        conversation_id='conv-9',
        failure_code='stt_failed',
        firestore_client=firestore,
    )

    doc = firestore.doc('job-1')
    assert doc == record
    assert doc['uid'] == 'u1'
    assert doc['job_id'] == 'job-1'
    assert doc['conversation_id'] == 'conv-9'
    assert doc['lane'] == 'backfill'
    assert doc['status'] == 'pending'
    assert doc['failure_code'] == 'stt_failed'
    assert doc['attempt_count'] == 1
    assert 'created_at' in doc
    assert 'dead_lettered_at' not in doc
    assert not ({'error', 'errors', 'transcript', 'audio', 'file', 'path'} & set(doc))


def test_pending_record_is_idempotent_and_counts_attempts(firestore):
    first = ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)
    second = ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)

    assert second['attempt_count'] == 2
    assert second['created_at'] == first['created_at']
    assert 'conversation_id' not in second


def test_failure_code_maps_to_the_closed_vocabulary():
    assert ledger.dead_letter_failure_code('speaker_embedding_unconfigured') == 'speaker_embedding_unconfigured'
    assert ledger.dead_letter_failure_code('speaker_embedding_failed') == 'speaker_embedding_failed'
    assert ledger.dead_letter_failure_code('typesense_projection_failed') == 'typesense_projection_failed'
    assert ledger.dead_letter_failure_code('stt_failed') == 'stt_failed'
    assert ledger.dead_letter_failure_code('llm_failed') == 'llm_failed'
    assert ledger.dead_letter_failure_code('empty_structured_guard') == 'empty_structured_guard'
    assert ledger.dead_letter_failure_code('sync_decode_failed') == 'unknown'
    assert ledger.dead_letter_failure_code('SomeException: raw trace /tmp/a.wav') == 'unknown'
    assert ledger.dead_letter_failure_code(None) == 'unknown'


def test_confirm_flips_pending_once_and_emits_the_event(firestore, capsys):
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', failure_code='llm_failed', firestore_client=firestore)

    confirmed = ledger.confirm_dead_letter('job-1', firestore_client=firestore)
    assert confirmed['status'] == 'dead_letter'
    assert confirmed['dead_lettered_at']
    (event,) = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert event == {
        'event': 'sync_backfill_dead_letter',
        'job_id': 'job-1',
        'uid': 'u1',
        'failure_code': 'llm_failed',
        'outcome': 'confirmed',
    }

    again = ledger.confirm_dead_letter('job-1', firestore_client=firestore)
    assert again['status'] == 'dead_letter'
    assert capsys.readouterr().out == ''


def test_confirm_missing_doc_returns_none(firestore, capsys):
    assert ledger.confirm_dead_letter('missing', firestore_client=firestore) is None
    assert capsys.readouterr().out == ''


def test_ensure_confirms_pending_and_self_heals_missing(firestore, capsys):
    confirmed = ledger.ensure_dead_letter_confirmed(
        'job-9', uid='u1', failure_code='empty_structured_guard', firestore_client=firestore
    )
    assert confirmed['status'] == 'dead_letter'
    doc = firestore.doc('job-9')
    assert doc['attempt_count'] == 1
    assert 'sync_backfill_dead_letter' in capsys.readouterr().out


def test_ensure_bounds_raw_failure_code_when_recreating(firestore):
    confirmed = ledger.ensure_dead_letter_confirmed(
        'job-10', uid='u1', failure_code='sync_decode_failed', firestore_client=firestore
    )
    assert confirmed['failure_code'] == 'unknown'
    assert firestore.doc('job-10')['failure_code'] == 'unknown'


def test_ensure_keeps_known_failure_code_when_recreating(firestore):
    confirmed = ledger.ensure_dead_letter_confirmed(
        'job-11', uid='u1', failure_code='stt_failed', firestore_client=firestore
    )
    assert confirmed['failure_code'] == 'stt_failed'
    assert firestore.doc('job-11')['failure_code'] == 'stt_failed'


def test_ensure_missing_doc_without_uid_fails_closed(firestore):
    with pytest.raises(RuntimeError):
        ledger.ensure_dead_letter_confirmed('job-x', firestore_client=firestore)

    assert firestore.doc('job-x') is None


def test_ensure_existing_doc_uid_mismatch_fails_closed(firestore, capsys):
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)

    with pytest.raises(RuntimeError):
        ledger.ensure_dead_letter_confirmed('job-1', uid='intruder', firestore_client=firestore)

    assert firestore.doc('job-1')['status'] == 'pending'
    assert capsys.readouterr().out == ''


def test_confirm_transaction_retry_does_not_double_emit(firestore, capsys, monkeypatch):
    """A committed-but-unacknowledged write followed by a retry that observes
    ``dead_letter`` must not emit the confirmed event again."""
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)
    capsys.readouterr()
    calls = {'count': 0}

    def retrying_transactional(fn):
        def run(transaction):
            calls['count'] += 1
            fn(transaction)
            calls['count'] += 1
            return fn(transaction)

        return run

    monkeypatch.setattr(ledger.firestore, 'transactional', retrying_transactional)

    confirmed = ledger.confirm_dead_letter('job-1', firestore_client=firestore)

    assert confirmed['status'] == 'dead_letter'
    assert calls['count'] == 2
    assert capsys.readouterr().out == ''


def test_confirm_emits_once_on_the_winning_attempt(firestore, capsys, monkeypatch):
    """When the retried attempt performs the transition itself the event fires
    exactly once."""
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)
    capsys.readouterr()
    committed = {'done': False}

    def flaky_transactional(fn):
        def run(transaction):
            if not committed['done']:
                committed['done'] = True
                raise ConnectionError('commit response lost')
            return fn(transaction)

        return run

    monkeypatch.setattr(ledger.firestore, 'transactional', flaky_transactional)

    with pytest.raises(ConnectionError):
        ledger.confirm_dead_letter('job-1', firestore_client=firestore)

    monkeypatch.setattr(ledger.firestore, 'transactional', lambda fn: fn)
    confirmed = ledger.confirm_dead_letter('job-1', firestore_client=firestore)

    assert confirmed['status'] == 'dead_letter'
    assert capsys.readouterr().out.count('sync_backfill_dead_letter') == 1


def test_confirmed_doc_never_regresses_to_pending(firestore):
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)
    ledger.confirm_dead_letter('job-1', firestore_client=firestore)

    again = ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)

    assert again['status'] == 'dead_letter'
    assert again['attempt_count'] == 2


def test_get_dead_letter_returns_doc_or_none(firestore):
    assert ledger.get_dead_letter('missing', firestore_client=firestore) is None
    ledger.record_dead_letter_pending(job_id='job-1', uid='u1', firestore_client=firestore)
    assert ledger.get_dead_letter('job-1', firestore_client=firestore)['status'] == 'pending'


class _Recorder:
    """Captures ledger calls in order; ``fail`` simulates Firestore down."""

    def __init__(self, calls):
        self.calls = calls
        self.fail = False
        self.pending_args = []

    def record_dead_letter_pending(self, **kwargs):
        if self.fail:
            raise ConnectionError('firestore down')
        self.calls.append('pending')
        self.pending_args.append(kwargs)

    def confirm_dead_letter(self, job_id, **kwargs):
        self.calls.append('confirm')

    def dead_letter_failure_code(self, reason):
        return ledger.dead_letter_failure_code(reason)


class _JobRedis:
    """Dict-backed job store replaying the raw-CAS scripts as applied."""

    def __init__(self, job, calls):
        self.calls = calls
        self.raw = json.dumps(job, default=str)

    def get(self, _key):
        return self.raw

    def set(self, _key, value, ex=None):
        self.calls.append('set')
        self.raw = value
        return True

    def eval(self, script, numkeys, *args):
        self.calls.append('eval')
        return [b'applied', args[-2]]


def _hook_harness(monkeypatch, job):
    calls: list[str] = []
    fake_redis = _JobRedis(job, calls)
    recorder = _Recorder(calls)
    monkeypatch.setattr(sync_jobs, 'r', fake_redis)
    monkeypatch.setattr(sync_jobs, 'sync_dead_letters', recorder)
    return fake_redis, recorder, calls


def _backfill_job(**overrides):
    return {
        'job_id': 'job-1',
        'uid': 'u1',
        'status': 'processing',
        'lane': 'backfill',
        'conversation_id': 'conv-1',
        'updated_at': time.time(),
        'created_at': time.time(),
        **overrides,
    }


def test_mark_job_failed_writes_pending_then_confirms(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job())

    finalized = sync_jobs.mark_job_failed('job-1', 'boom', reason_code='sync_decode_failed')

    assert finalized['status'] == 'failed'
    assert calls == ['pending', 'eval', 'confirm']
    assert recorder.pending_args[0]['failure_code'] == 'unknown'
    assert recorder.pending_args[0]['uid'] == 'u1'


def test_mark_job_failed_skips_fresh_lane(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job(lane='fresh'))

    sync_jobs.mark_job_failed('job-1', 'boom')

    assert calls == ['eval']


def test_finalize_partial_failure_records_ledger(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job())

    finalized = sync_jobs.finalize_sync_job('job-1', {'failed_segments': 1, 'total_segments': 3})

    assert finalized['status'] == 'partial_failure'
    assert calls == ['pending', 'eval', 'confirm']


def test_finalize_completed_never_touches_ledger(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job())

    finalized = sync_jobs.finalize_sync_job('job-1', {'failed_segments': 0, 'total_segments': 3})

    assert finalized['status'] == 'completed'
    assert calls == ['eval']


def test_pending_write_failure_keeps_redis_non_terminal(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job())
    recorder.fail = True

    with pytest.raises(ConnectionError):
        sync_jobs.mark_job_failed('job-1', 'boom')

    assert calls == []
    assert json.loads(fake_redis.raw)['status'] == 'processing'


def test_fenced_cas_loss_leaves_unconfirmed_pending_orphan(monkeypatch):
    fake_redis, recorder, calls = _hook_harness(monkeypatch, _backfill_job())
    fake_redis.eval = lambda *a, **k: calls.append('eval') or [b'conflict', fake_redis.raw]

    mutation = sync_jobs.fenced_mark_job_failed('job-1', 'token', 'boom')

    assert mutation.applied is False
    assert calls == ['pending', 'eval', 'eval', 'eval']


def test_stale_backfill_self_heal_writes_pending_first(monkeypatch):
    job = _backfill_job(status='processing', updated_at=time.time() - 700, created_at=time.time() - 800)
    fake_redis, recorder, calls = _hook_harness(monkeypatch, job)

    result = sync_jobs.get_sync_job('job-1')

    assert result['status'] == 'failed'
    assert calls == ['pending', 'set']


def _poll(job, dead_letter_doc, monkeypatch):
    monkeypatch.setattr(sync_router, 'get_sync_job', lambda _job_id: deepcopy(job))
    monkeypatch.setattr(sync_router, 'get_sync_ledger_fence_mode', lambda: sync_router.SyncLedgerFenceMode.LEGACY)
    monkeypatch.setattr(sync_router, 'is_sync_job_stale', lambda _job, **kw: False)
    monkeypatch.setattr(
        sync_router.sync_dead_letters,
        'get_dead_letter',
        MagicMock(return_value=dead_letter_doc),
    )
    return sync_router.get_sync_job_status('job-1', uid='u1')


def _client_terminal_policy(status, is_terminal):
    if not is_terminal:
        return 'wait'
    return 'acknowledge' if status == 'completed' else 'retry'


def test_poll_failed_backfill_without_ledger_is_503_not_ack(monkeypatch):
    job = _backfill_job(status='failed', reason_code='sync_decode_failed')

    with pytest.raises(HTTPException) as excinfo:
        _poll(job, None, monkeypatch)

    assert excinfo.value.status_code == 503
    assert excinfo.value.headers['Retry-After'] == '10'


def _ledger_doc(**overrides):
    return {'job_id': 'job-1', 'uid': 'u1', 'status': 'pending', **overrides}


def test_poll_failed_backfill_with_pending_ledger_serves_failed(monkeypatch):
    job = _backfill_job(status='failed', reason_code='stt_failed')
    resp = _poll(job, _ledger_doc(), monkeypatch)

    assert resp['status'] == 'failed'
    assert resp['reason_code'] == 'stt_failed'
    assert resp['status'] != 'dead_letter'
    assert _client_terminal_policy(resp['status'], is_terminal=True) == 'retry'


def test_poll_terminal_backfill_with_confirmed_ledger_serves_status(monkeypatch):
    job = _backfill_job(status='partial_failure', failed_segments=1, total_segments=3)
    resp = _poll(job, _ledger_doc(status='dead_letter'), monkeypatch)

    assert resp['status'] == 'partial_failure'
    assert _client_terminal_policy(resp['status'], is_terminal=True) == 'retry'


def test_poll_stale_self_healed_backfill_releases_inflight_slot(monkeypatch):
    stale_job = _backfill_job(status='processing', updated_at=time.time() - 700, created_at=time.time() - 800)
    fake_redis, _, _ = _hook_harness(monkeypatch, stale_job)
    released = []
    monkeypatch.setattr(sync_router, 'get_sync_job', sync_jobs.get_sync_job)
    monkeypatch.setattr(sync_router, 'get_sync_ledger_fence_mode', lambda: sync_router.SyncLedgerFenceMode.LEGACY)
    monkeypatch.setattr(sync_router.sync_dead_letters, 'get_dead_letter', MagicMock(return_value=_ledger_doc()))
    monkeypatch.setattr(sync_router, 'release_backfill_slot', lambda uid, jid: released.append((uid, jid)))

    resp = sync_router.get_sync_job_status('job-1', uid='u1')

    assert resp['status'] == 'failed'
    assert json.loads(fake_redis.raw)['status'] == 'failed'
    assert released == [('u1', 'job-1')]


def test_poll_failed_backfill_without_ledger_does_not_release_slot(monkeypatch):
    job = _backfill_job(status='failed', reason_code='sync_decode_failed')
    released = []
    monkeypatch.setattr(sync_router, 'release_backfill_slot', lambda uid, jid: released.append((uid, jid)))

    with pytest.raises(HTTPException) as excinfo:
        _poll(job, None, monkeypatch)

    assert excinfo.value.status_code == 503
    assert released == []


@pytest.mark.parametrize(
    'doc',
    [
        _ledger_doc(uid='other-user'),
        _ledger_doc(job_id='other-job'),
        _ledger_doc(status='archived'),
        {'uid': 'u1', 'status': 'pending'},
    ],
    ids=['wrong_uid', 'wrong_job_id', 'wrong_status', 'missing_job_id'],
)
def test_poll_failed_backfill_with_mismatched_ledger_is_503(monkeypatch, doc):
    job = _backfill_job(status='failed')

    with pytest.raises(HTTPException) as excinfo:
        _poll(job, doc, monkeypatch)

    assert excinfo.value.status_code == 503


def test_poll_failed_fresh_lane_needs_no_ledger(monkeypatch):
    job = _backfill_job(status='failed', lane='fresh')
    resp = _poll(job, None, monkeypatch)

    assert resp['status'] == 'failed'


def test_poll_ledger_read_error_fails_closed(monkeypatch):
    job = _backfill_job(status='failed')
    monkeypatch.setattr(sync_router, 'get_sync_job', lambda _job_id: deepcopy(job))
    monkeypatch.setattr(sync_router, 'is_sync_job_stale', lambda _job, **kw: False)
    monkeypatch.setattr(
        sync_router.sync_dead_letters,
        'get_dead_letter',
        MagicMock(side_effect=RuntimeError('firestore down')),
    )

    with pytest.raises(HTTPException) as excinfo:
        sync_router.get_sync_job_status('job-1', uid='u1')

    assert excinfo.value.status_code == 503


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _run_job_harness(monkeypatch, job, *, ensure_error=None):
    calls: list[str] = []
    monkeypatch.setattr(
        sync_router,
        'get_sync_ledger_fence_mode',
        MagicMock(return_value=sync_router.SyncLedgerFenceMode.LEGACY),
    )
    monkeypatch.setattr(sync_router, 'get_sync_job', MagicMock(return_value=deepcopy(job)))
    monkeypatch.setattr(sync_router, 'geolocation_from_private_header', lambda _header: None)

    async def passthrough(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(sync_router, 'run_blocking', passthrough)
    monkeypatch.setattr(sync_router, 'try_acquire_job_run_lock', MagicMock(return_value='tok'))
    monkeypatch.setattr(sync_router, 'release_job_run_lock', MagicMock())

    def record(name):
        def inner(*_a, **_kw):
            calls.append(name)

        return inner

    async def delete_blobs(_paths):
        calls.append('delete_blobs')

    def ensure(*_a, **_kw):
        calls.append('ensure')
        if ensure_error is not None:
            raise ensure_error

    monkeypatch.setattr(sync_router, '_delete_staged_blobs_async', delete_blobs)
    monkeypatch.setattr(sync_router, 'release_backfill_slot', record('release_slot'))
    monkeypatch.setattr(sync_router, 'release_sync_content_claim', record('release_claim'))
    monkeypatch.setattr(sync_router.sync_dead_letters, 'ensure_dead_letter_confirmed', ensure)
    return calls


def _terminal_run_payload():
    return {
        'job_id': 'job-1',
        'uid': 'u1',
        'raw_blob_paths': ['blob-1'],
        'source': 'omi',
        'lane': 'backfill',
        'content_id': 'content-1',
    }


def test_terminal_delivery_confirms_ledger_before_ack(monkeypatch):
    job = _backfill_job(status='failed', ledger_fence_mode='legacy')
    calls = _run_job_harness(monkeypatch, job)

    resp = asyncio.run(sync_router.run_sync_job(_FakeRequest(_terminal_run_payload()), task_retry_count=0))

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    assert calls == ['ensure', 'release_slot', 'release_claim']


def test_failed_backfill_terminal_delivery_never_deletes_staged_audio(monkeypatch):
    job = _backfill_job(status='partial_failure', ledger_fence_mode='legacy')
    calls = _run_job_harness(monkeypatch, job)

    resp = asyncio.run(sync_router.run_sync_job(_FakeRequest(_terminal_run_payload()), task_retry_count=0))

    assert resp.status_code == 200
    assert 'delete_blobs' not in calls
    assert calls == ['ensure', 'release_slot', 'release_claim']


def test_terminal_delivery_uses_persisted_lane_not_payload_lane(monkeypatch):
    job = _backfill_job(status='failed', ledger_fence_mode='legacy')
    calls = _run_job_harness(monkeypatch, job)
    payload = {**_terminal_run_payload(), 'lane': 'fresh'}

    resp = asyncio.run(sync_router.run_sync_job(_FakeRequest(payload), task_retry_count=0))

    assert resp.status_code == 200
    assert calls == ['ensure', 'release_slot', 'release_claim']


def test_terminal_delivery_passes_raw_reason_code_to_ledger(monkeypatch):
    job = _backfill_job(status='failed', ledger_fence_mode='legacy', reason_code='sync_decode_failed')
    _run_job_harness(monkeypatch, job)
    captured: dict = {}

    def ensure(job_id, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(sync_router.sync_dead_letters, 'ensure_dead_letter_confirmed', ensure)

    resp = asyncio.run(sync_router.run_sync_job(_FakeRequest(_terminal_run_payload()), task_retry_count=0))

    assert resp.status_code == 200
    assert captured['failure_code'] == 'sync_decode_failed'


def test_terminal_delivery_skips_ledger_for_completed(monkeypatch):
    job = _backfill_job(status='completed', ledger_fence_mode='legacy')
    calls = _run_job_harness(monkeypatch, job)

    resp = asyncio.run(sync_router.run_sync_job(_FakeRequest(_terminal_run_payload()), task_retry_count=0))

    assert resp.status_code == 200
    assert 'ensure' not in calls
    assert calls == ['delete_blobs', 'release_slot']


def test_terminal_delivery_ensure_failure_blocks_ack(monkeypatch):
    job = _backfill_job(status='failed', ledger_fence_mode='legacy')
    calls = _run_job_harness(monkeypatch, job, ensure_error=RuntimeError('firestore down'))

    with pytest.raises(RuntimeError):
        asyncio.run(sync_router.run_sync_job(_FakeRequest(_terminal_run_payload()), task_retry_count=0))

    assert 'delete_blobs' not in calls
    assert 'release_slot' not in calls
