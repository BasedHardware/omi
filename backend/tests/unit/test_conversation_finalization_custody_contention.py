"""Durable listen-finalization custody survives Firestore read-time contention.

Failure-Class: FC-hot-row-read-abort-escapes-reconciliation-custody
(new class declared in this diff; the nearest existing classes cover the
neighbouring shapes — ``FC-sync-assignment-read-abort-escapes-retry`` is scoped
to sync intake's assignment transaction, ``FC-retired-transaction-treated-as-fatal``
covers the expired-id commit rejection via ``run_transactional`` alone, and the
recording-session classes cover the live-session fence — not the durable
finalization custody family, whose twenty-one ``run_transactional`` writers
replayed only the expired-id commit rejection and surfaced a read-time
``Aborted`` to their callers as a real failure).

The observed shape (backend-listen 2026-11-01, ``listen finalization
reconciliation claim failed`` ×11/30m): the reconciler's replay claim ran its
``@firestore.transactional`` callable under ``run_transactional`` alone, which
replays the expired-id commit rejection but not a read-time ``Aborted`` — the
exact shape a contention burst on a hot job row produces (the durable worker,
the reconciler, and ``recover_stranded_byok_jobs`` all re-read the same rows
every tick, and the orphan sweep touches every pod's conversation row). Every
sibling custody writer in ``database/conversation_finalization_jobs.py`` had
the same hole. The fix gives every transactional custody writer the same
composition the file's own ``create_or_get_finalization_intent`` already
carries: the shared bounded fresh-transaction contention budget
(``database/firestore_transaction_retry.run_with_transaction_contention_retry``)
owns read-time aborts; ``run_transactional`` inside it still restarts the
expired-id commit rejection. The reconciler keeps its loud classification for
real failures and counts a drained contention budget as a bounded ``skipped``
(the next tick's sweep is the retry), never a crash-out.

Guards:
- every custody writer replays a read-time ``Aborted`` on a fresh transaction
  and commits exactly once;
- an expired-transaction rejection still restarts inside the outer budget;
- after the bounded budget drains, envelope-raising writers surface
  ``FirestoreContentionExhausted``, boolean writers answer False, and claim
  writers surface the typed exhaustion — with no commit landing in any case;
- the reconciler's replay-claim loop counts a drained budget as ``skipped``
  without an error log, while a real failure keeps the loud exception shape;
- concurrency parity: two racing reconcilers converge on one generation bump;
- the budget's pacing contract (equal-jitter, bounded) keeps its own guard.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument
from google.cloud import firestore as firestore_sdk

from database import conversation_finalization_jobs as jobs
from database.firestore_transaction_retry import FirestoreContentionExhausted

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid.'
ABORTED_MESSAGE = '409 read contention; aborted transaction'
UID = 'uid-1'
CONVERSATION_ID = 'conversation-1'
JOB_ID = 'job-1'
NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
JOB_PATH = ('conversation_finalization_jobs', JOB_ID)
CONVERSATION_PATH = ('users', UID, 'conversations', CONVERSATION_ID)
STALE_CURSOR_PATH = ('conversation_recovery_state', 'stale_processing_sweep')
MEETING_CURSOR_PATH = ('conversation_recovery_state', 'meeting_receipt_backfill_sweep')
BYOK_CURSOR_PATH = ('conversation_recovery_state', 'byok_abandonment_sweep')
INPROGRESS_CURSOR_PATH = ('conversation_recovery_state', 'in_progress_content_sweep')


def aborts(count: int) -> List[BaseException]:
    errors: List[BaseException] = [Aborted(ABORTED_MESSAGE) for _ in range(count)]
    return errors


def _queued_job(**overrides: Any) -> Dict[str, Any]:
    """A platform-key queued job row as the reconciler's replay claim finds it."""
    row: Dict[str, Any] = {
        'uid': UID,
        'conversation_id': CONVERSATION_ID,
        'status': 'queued',
        'dispatch_generation': 1,
        'dispatch_requested_at': NOW - timedelta(minutes=30),
        'created_at': NOW - timedelta(hours=1),
        'reconcile_after_at': NOW - timedelta(minutes=1),
        'finalization_revision': 1,
    }
    row.update(overrides)
    return row


def _leased_job(**overrides: Any) -> Dict[str, Any]:
    """A leased job row as the lease-settling writers find it."""
    return _queued_job(
        status='leased',
        lease_epoch=1,
        lease_expires_at=NOW + timedelta(minutes=10),
        attempt_count=1,
        **overrides,
    )


def _processing_row(admitted_before_seconds: int = 120) -> Dict[str, Any]:
    return {
        'status': 'processing',
        'processing_admitted_at': NOW - timedelta(seconds=admitted_before_seconds),
    }


class _Snapshot:
    def __init__(
        self,
        data: Optional[Dict[str, Any]],
        doc_id: str = 'doc',
        update_time: Optional[datetime] = None,
    ):
        self._data = data
        self.exists = data is not None
        self.id = doc_id
        self.update_time = update_time

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._data) if self._data is not None else None


class _DocumentRef:
    def __init__(self, client: '_CustodyFakeClient', path: Tuple[str, ...]):
        self._client = client
        self.path = path
        self.id = path[-1]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        if self._client.read_errors:
            raise self._client.read_errors.pop(0)
        row = self._client.documents.get(self.path)
        return _Snapshot(row, doc_id=self.id, update_time=self._client.update_times.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self._client, self.path + (name,))


class _CollectionRef:
    def __init__(self, client: '_CustodyFakeClient', path: Tuple[str, ...]):
        self._client = client
        self.path = path

    def document(self, doc_id: str) -> _DocumentRef:
        return _DocumentRef(self._client, self.path + (doc_id,))


class _FakeTransaction:
    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_CustodyFakeClient', index: int):
        self._client = client
        self._id = f'txn-{index}'.encode()
        self.writes: List[Tuple[Tuple[str, ...], Dict[str, Any], bool]] = []
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id: Any = None) -> None:
        pass

    def _rollback(self) -> None:
        self.rolled_back = True

    def set(self, doc_ref: _DocumentRef, payload: Dict[str, Any], merge: bool = False) -> None:
        self.writes.append((tuple(doc_ref.path), dict(payload), merge))

    def update(self, doc_ref: _DocumentRef, payload: Dict[str, Any]) -> None:
        self.writes.append((tuple(doc_ref.path), dict(payload), True))

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        self._client.commits.append(list(self.writes))


class _CustodyFakeClient:
    """One document store plus bounded read/commit fault queues, SDK-shaped.

    ``firestore.transactional`` stays the real SDK wrapper: it reads the
    transaction id, drives the body, and commits through ``_commit``, so the
    fake reproduces both the read-time abort and the retired-id commit
    rejection without faking the retry policy under test. Committed writes are
    applied to the store (update semantics: shallow merge with
    ``firestore.DELETE_FIELD`` removals; ``set(merge=False)`` replaces), so a
    later attempt's reads see exactly what earlier commits landed.
    """

    def __init__(
        self,
        document: Optional[Dict[str, Any]] = None,
        *,
        read_errors: Optional[List[BaseException]] = None,
        commit_errors: Optional[List[BaseException]] = None,
    ):
        self.document = document
        self.documents: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        self.update_times: Dict[Tuple[str, ...], datetime] = {}
        if document is not None:
            self.documents[JOB_PATH] = copy.deepcopy(document)
        self.read_errors = list(read_errors or [])
        self.commit_errors = list(commit_errors or [])
        self.commits: List[List[Tuple[Tuple[str, ...], Dict[str, Any], bool]]] = []
        self.transactions: List[_FakeTransaction] = []

    def collection(self, collection_id: str) -> _CollectionRef:
        return _CollectionRef(self, (collection_id,))

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction

    def apply_committed_writes(self) -> None:
        for commit in self.commits:
            for path, payload, merge in commit:
                self._apply_write(path, payload, merge)

    def _apply_write(self, path: Tuple[str, ...], payload: Dict[str, Any], merge: bool) -> None:
        row = {} if not merge else dict(self.documents.get(path) or {})
        for key, value in payload.items():
            if value is firestore_sdk.DELETE_FIELD:
                row.pop(key, None)
            else:
                row[key] = value
        self.documents[path] = row


def commit_payloads(client: _CustodyFakeClient) -> List[Dict[str, Any]]:
    """Every write payload the client committed, in order, across transactions."""
    return [payload for commit in client.commits for _path, payload, _merge in commit]


def fault(client: _CustodyFakeClient, errors: List[BaseException]) -> _CustodyFakeClient:
    """Queue read faults on the client after construction."""
    client.read_errors = list(errors)
    return client


@pytest.fixture()
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> List[float]:
    """Neutralize budget pacing; capture the requested delays for assertions."""
    delays: List[float] = []
    from database.firestore_transaction_retry import run_with_transaction_contention_retry as real_budget

    def instant_budget(transaction_factory: Any, operation: Any, **kwargs: Any) -> Any:
        kwargs.pop('random_value', None)
        return real_budget(transaction_factory, operation, sleep=delays.append, random_value=lambda: 0.0, **kwargs)

    monkeypatch.setattr(jobs, 'run_with_transaction_contention_retry', instant_budget)
    return delays


# ---------------------------------------------------------------------------
# The reconciler's replay claim — the prod signature boundary.
# ---------------------------------------------------------------------------


def test_replay_claim_replays_read_abort_on_a_fresh_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), read_errors=[Aborted(ABORTED_MESSAGE)])

    intent = jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert intent['created'] is True
    assert intent['dispatch_generation'] == 2
    assert len(client.transactions) == 2, 'the replay must use a fresh transaction, not the aborted id'
    assert client.transactions[0].rolled_back is True
    assert len(client.commits) == 1
    assert any(payload.get('dispatch_generation') == 2 for payload in commit_payloads(client))


def test_replay_claim_restarts_an_expired_transaction_inside_the_budget(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])

    intent = jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert intent['created'] is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    assert any(payload.get('dispatch_generation') == 2 for payload in commit_payloads(client))


def test_replay_claim_surfaces_typed_exhaustion_after_the_budget_drains(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert client.commits == [], 'a drained budget must not have committed anything'


def test_replay_claim_replays_the_sdk_envelope_carrying_an_abort(no_sleep: List[float]):
    """The SDK's exhausted-retry wrapper carries the abort as its cause."""
    envelope = RuntimeError('RetryError: last exception: aborted')
    envelope.__cause__ = Aborted(ABORTED_MESSAGE)

    client = _CustodyFakeClient(_queued_job(), read_errors=[envelope])

    intent = jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert intent['created'] is True
    assert len(client.commits) == 1


def test_replay_claim_byok_revoke_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _queued_job(requires_byok=True, status='leased', lease_expires_at=NOW - timedelta(minutes=10)),
        read_errors=[Aborted(ABORTED_MESSAGE)],
    )

    intent = jobs.claim_finalization_replay(
        JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client, byok_only=True
    )

    assert intent['status'] == 'blocked_byok'
    assert len(client.transactions) == 2
    assert any(payload.get('status') == 'blocked_byok' for payload in commit_payloads(client))


# ---------------------------------------------------------------------------
# Worker custody writers.
# ---------------------------------------------------------------------------


def test_worker_claim_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), read_errors=[Aborted(ABORTED_MESSAGE)])

    claim = jobs.claim_finalization_job(JOB_ID, 1, count_worker_claim=True, firestore_client=client)

    assert claim['status'] == 'claimed'
    assert len(client.transactions) == 2
    assert any(payload.get('status') == 'leased' for payload in commit_payloads(client))


def test_worker_claim_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.claim_finalization_job(JOB_ID, 1, count_worker_claim=True, firestore_client=client)

    assert client.commits == []


def test_worker_completion_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(fanout_status='completed'), read_errors=[Aborted(ABORTED_MESSAGE)])

    completed = jobs.mark_finalization_completed(JOB_ID, 1, 1, firestore_client=client)

    assert completed is True
    assert any(payload.get('status') == 'completed' for payload in commit_payloads(client))


def test_worker_completion_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(fanout_status='completed'), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.mark_finalization_completed(JOB_ID, 1, 1, firestore_client=client)

    assert client.commits == []


def test_worker_fenced_terminal_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=[Aborted(ABORTED_MESSAGE)])

    fenced = jobs.mark_finalization_fenced(JOB_ID, 1, 1, firestore_client=client)

    assert fenced is True
    assert any(payload.get('finalization_outcome') == 'fenced' for payload in commit_payloads(client))


def test_worker_fenced_terminal_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.mark_finalization_fenced(JOB_ID, 1, 1, firestore_client=client)

    assert client.commits == []


def test_worker_fanout_claim_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=[Aborted(ABORTED_MESSAGE)])
    client.documents[CONVERSATION_PATH] = {
        'status': 'completed',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
    }

    fanout = jobs.claim_finalization_fanout(JOB_ID, 1, 1, firestore_client=client)

    assert fanout['status'] == 'claimed'
    assert len(client.transactions) == 2
    assert any(payload.get('fanout_status') == 'leased' for payload in commit_payloads(client))


def test_worker_fanout_claim_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.claim_finalization_fanout(JOB_ID, 1, 1, firestore_client=client)

    assert client.commits == []


def test_worker_fanout_completion_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _leased_job(fanout_status='leased', fanout_lease_epoch=1),
        read_errors=[Aborted(ABORTED_MESSAGE)],
    )

    completed = jobs.mark_finalization_fanout_completed(JOB_ID, 1, 1, firestore_client=client)

    assert completed is True
    assert any(payload.get('fanout_status') == 'completed' for payload in commit_payloads(client))


def test_worker_fanout_completion_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _leased_job(fanout_status='leased', fanout_lease_epoch=1),
        read_errors=aborts(50),
    )

    with pytest.raises(FirestoreContentionExhausted):
        jobs.mark_finalization_fanout_completed(JOB_ID, 1, 1, firestore_client=client)

    assert client.commits == []


def test_retryable_settlement_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=[Aborted(ABORTED_MESSAGE)])

    marked = jobs.mark_finalization_retryable(JOB_ID, 1, 1, failure_code='processing_failed', firestore_client=client)

    assert marked is True
    assert any(
        payload.get('status') == 'queued' and payload.get('attempt_count') == 2 for payload in commit_payloads(client)
    )


def test_retryable_settlement_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.mark_finalization_retryable(JOB_ID, 1, 1, failure_code='processing_failed', firestore_client=client)

    assert client.commits == []


# ---------------------------------------------------------------------------
# Reconciler-side terminal writers.
# ---------------------------------------------------------------------------


def test_dead_letter_terminal_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=[Aborted(ABORTED_MESSAGE)])
    client.documents[CONVERSATION_PATH] = {
        'status': 'processing',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
        'photos': [{'description': 'a described photo'}],
    }

    marked = jobs.mark_finalization_dead_letter(
        JOB_ID, 1, 1, retry_count=3, failure_code='final_attempt_failed', firestore_client=client
    )

    assert marked is True
    assert any(payload.get('status') == 'dead_letter' for payload in commit_payloads(client))
    assert any(payload.get('finalization_status') == 'dead_letter' for payload in commit_payloads(client))


def test_dead_letter_terminal_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), read_errors=aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.mark_finalization_dead_letter(JOB_ID, 1, 1, retry_count=3, firestore_client=client)

    assert client.commits == []


def test_dead_letter_terminal_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _leased_job(),
        commit_errors=[InvalidArgument(EXPIRED_MESSAGE)],
    )
    client.documents[CONVERSATION_PATH] = {
        'status': 'processing',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
        'photos': [{'description': 'a described photo'}],
    }

    marked = jobs.mark_finalization_dead_letter(JOB_ID, 1, 1, retry_count=3, firestore_client=client)

    assert marked is True
    assert len(client.transactions) == 2


# ---------------------------------------------------------------------------
# Meeting receipts.
# ---------------------------------------------------------------------------


def _completed_conversation_row() -> Dict[str, Any]:
    return {'status': 'completed', 'finalization_job_id': None, 'finalization_revision': 0}


def test_meeting_receipt_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = _completed_conversation_row()
    fault(client, [Aborted(ABORTED_MESSAGE)])

    receipt = jobs.record_meeting_receipt(
        UID,
        CONVERSATION_ID,
        finalization_job_id=None,
        eligible=True,
        reason='meeting',
        duration_s=600.0,
        dedup_speech_s=120.0,
        firestore_client=client,
    )

    assert receipt['status'] == 'recorded'
    assert len(client.transactions) == 2
    assert client.commits[0], 'the receipt transaction writes both the job row and the conversation'


def test_meeting_receipt_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = _completed_conversation_row()
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.record_meeting_receipt(
            UID,
            CONVERSATION_ID,
            finalization_job_id=None,
            eligible=True,
            reason='meeting',
            duration_s=600.0,
            dedup_speech_s=120.0,
            firestore_client=client,
        )

    assert client.commits == []


# ---------------------------------------------------------------------------
# Sweep cursor writers (three sweeps share the CAS cursor transaction).
# ---------------------------------------------------------------------------


def test_stale_processing_cursor_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    fault(client, [Aborted(ABORTED_MESSAGE)])

    advanced = jobs.advance_stale_processing_sweep_cursor(
        0, 'conversation_finalization_jobs/job-2', firestore_client=client
    )

    assert advanced is True
    assert len(client.transactions) == 2
    assert any(
        payload.get('resume_after_path') == 'conversation_finalization_jobs/job-2'
        for payload in commit_payloads(client)
    )


def test_stale_processing_cursor_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.advance_stale_processing_sweep_cursor(0, 'conversation_finalization_jobs/job-2', firestore_client=client)

    assert client.commits == []


def test_meeting_receipt_cursor_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    fault(client, [Aborted(ABORTED_MESSAGE)])

    advanced = jobs.advance_meeting_receipt_backfill_cursor(
        0, 'conversation_finalization_jobs/job-3', firestore_client=client
    )

    assert advanced is True
    assert len(client.transactions) == 2


def test_byok_abandonment_cursor_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    fault(client, [Aborted(ABORTED_MESSAGE)])

    advanced = jobs.advance_byok_abandonment_sweep_cursor(
        0, 'conversation_finalization_jobs/job-4', firestore_client=client
    )

    assert advanced is True
    assert len(client.transactions) == 2


def test_in_progress_content_cursor_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    fault(client, [Aborted(ABORTED_MESSAGE)])

    advanced = jobs.advance_in_progress_content_sweep_cursor(
        0, 'users/uid-1/conversations/conversation-1', firestore_client=client
    )

    assert advanced is True
    assert len(client.transactions) == 2


def test_cursor_cas_loss_stays_false_and_writes_nothing(no_sleep: List[float]):
    """A contention replay must re-read the generation, not replay the decision."""
    client = _CustodyFakeClient()
    client.documents[STALE_CURSOR_PATH] = {'generation': 1, 'resume_after_path': 'conversation_finalization_jobs/job-0'}

    advanced = jobs.advance_stale_processing_sweep_cursor(
        0, 'conversation_finalization_jobs/job-2', firestore_client=client
    )

    assert advanced is False
    assert commit_payloads(client) == [], 'a CAS loss writes nothing, only an empty transaction commits'


def test_stale_processing_cursor_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])

    advanced = jobs.advance_stale_processing_sweep_cursor(
        0, 'conversation_finalization_jobs/job-2', firestore_client=client
    )

    assert advanced is True
    assert len(client.transactions) == 2


# ---------------------------------------------------------------------------
# Orphan terminal and admission-stamp writers.
# ---------------------------------------------------------------------------


def test_orphan_terminal_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    row = _processing_row()
    client.documents[CONVERSATION_PATH] = row
    fault(client, [Aborted(ABORTED_MESSAGE)])

    completed = jobs.complete_orphan_conversation(
        UID,
        CONVERSATION_ID,
        expected_admitted_at=row['processing_admitted_at'],
        firestore_client=client,
    )

    assert completed is True
    assert len(client.transactions) == 2
    assert any(payload.get('status') == 'completed' for payload in commit_payloads(client))


def test_orphan_terminal_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = _processing_row()
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.complete_orphan_conversation(
            UID,
            CONVERSATION_ID,
            expected_admitted_at=NOW - timedelta(seconds=120),
            firestore_client=client,
        )

    assert client.commits == []


def test_orphan_terminal_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    row = _processing_row()
    client.documents[CONVERSATION_PATH] = row

    completed = jobs.complete_orphan_conversation(
        UID,
        CONVERSATION_ID,
        expected_admitted_at=row['processing_admitted_at'],
        firestore_client=client,
    )

    assert completed is True
    assert len(client.transactions) == 2


def test_unstampable_orphan_terminal_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    row = {'status': 'processing'}  # a legacy row that can never carry the fence
    client.documents[CONVERSATION_PATH] = row
    client.update_times[CONVERSATION_PATH] = datetime.now(timezone.utc) - timedelta(hours=3)
    fault(client, [Aborted(ABORTED_MESSAGE)])

    completed = jobs.complete_unstampable_orphan_conversation(
        UID, CONVERSATION_ID, stale_after=timedelta(hours=2), firestore_client=client
    )

    assert completed is True
    assert any(payload.get('status') == 'completed' for payload in commit_payloads(client))


def test_unstampable_orphan_terminal_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing'}
    client.update_times[CONVERSATION_PATH] = datetime.now(timezone.utc) - timedelta(hours=3)
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.complete_unstampable_orphan_conversation(
            UID, CONVERSATION_ID, stale_after=timedelta(hours=2), firestore_client=client
        )

    assert client.commits == []


def test_stamp_admission_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing'}
    fault(client, [Aborted(ABORTED_MESSAGE)])

    stamped = jobs.stamp_processing_admission_if_absent(UID, CONVERSATION_ID, firestore_client=client)

    assert stamped is True
    assert any('processing_admitted_at' in payload for payload in commit_payloads(client))


def test_stamp_admission_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing'}
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.stamp_processing_admission_if_absent(UID, CONVERSATION_ID, firestore_client=client)

    assert client.commits == []


# ---------------------------------------------------------------------------
# Deferred-ownership writers.
# ---------------------------------------------------------------------------


def test_reacquire_deferred_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': True}
    fault(client, [Aborted(ABORTED_MESSAGE)])

    claimed = jobs.reacquire_deferred_processing(UID, CONVERSATION_ID, firestore_client=client)

    assert claimed is True
    assert any(payload.get('deferred') is False for payload in commit_payloads(client))


def test_reacquire_deferred_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': True}
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.reacquire_deferred_processing(UID, CONVERSATION_ID, firestore_client=client)

    assert client.commits == []


def test_recover_deferred_failure_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': False}
    fault(client, [Aborted(ABORTED_MESSAGE)])

    recovered = jobs.recover_deferred_processing_failure(UID, CONVERSATION_ID, firestore_client=client)

    assert recovered is True
    assert any(payload.get('deferred') is True for payload in commit_payloads(client))


def test_recover_deferred_failure_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': False}
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.recover_deferred_processing_failure(UID, CONVERSATION_ID, firestore_client=client)

    assert client.commits == []


# ---------------------------------------------------------------------------
# BYOK abandonment terminal.
# ---------------------------------------------------------------------------


def test_byok_abandonment_replays_read_abort(no_sleep: List[float]):
    real_now = datetime.now(timezone.utc)
    client = _CustodyFakeClient(
        _queued_job(
            requires_byok=True,
            status='leased',
            lease_epoch=1,
            lease_expires_at=real_now - timedelta(minutes=10),
            created_at=real_now - timedelta(hours=2),
        ),
        read_errors=[Aborted(ABORTED_MESSAGE)],
    )
    client.documents[CONVERSATION_PATH] = {
        'status': 'processing',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
    }

    result = jobs.abandon_byok_finalization_job(
        JOB_ID,
        expected_status='leased',
        expected_dispatch_generation=1,
        expected_lease_epoch=1,
        abandoned_after=timedelta(minutes=5),
        firestore_client=client,
    )

    assert result['status'] == 'abandoned'
    assert result['conversation_outcome'] == 'closed'
    assert len(client.transactions) == 2


def test_byok_abandonment_surfaces_typed_exhaustion(no_sleep: List[float]):
    real_now = datetime.now(timezone.utc)
    client = _CustodyFakeClient(
        _queued_job(
            requires_byok=True,
            status='leased',
            lease_epoch=1,
            lease_expires_at=real_now - timedelta(minutes=10),
        ),
        read_errors=aborts(50),
    )

    with pytest.raises(FirestoreContentionExhausted):
        jobs.abandon_byok_finalization_job(
            JOB_ID,
            expected_status='leased',
            expected_dispatch_generation=1,
            expected_lease_epoch=1,
            abandoned_after=timedelta(minutes=5),
            firestore_client=client,
        )

    assert client.commits == []


# ---------------------------------------------------------------------------
# The reconciler's claim loop: bounded exhaustion is a skip, not a crash-out.
# ---------------------------------------------------------------------------


def _summary_stub() -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        name: 0
        for name in (
            'accepted',
            'success',
            'failure',
            'stale',
            'nonterminal',
            'blocked_byok',
            'terminal_unknown',
            'queued',
            'leased',
            'dead_letter',
        )
    }
    summary['oldest_nonterminal_age_seconds'] = 0.0
    summary['oldest_blocked_byok_age_seconds'] = 0.0
    return summary


def test_reconciler_counts_a_drained_budget_as_skipped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A drained contention budget is a bounded skip; the next sweep is the retry.

    The loud ``logger.exception('listen finalization reconciliation claim
    failed')`` traceback — the prod signature — stays reserved for real claim
    failures; a contention burst that drained its own bounded budget already
    logged its warnings inside the budget and must not re-crash the sweep.
    """
    import logging

    import services.conversation_finalization as service

    def failing_claim(job_id: str, **_kwargs: Any) -> Any:
        raise FirestoreContentionExhausted(
            f'Firestore transaction contention exhausted for finalization_replay:{job_id}'
        )

    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setattr(
        service.jobs_db, 'recover_stranded_byok_jobs', lambda **_kw: {'scanned': 0, 'blocked': 0, 'errors': 0}
    )
    monkeypatch.setattr(
        service.jobs_db,
        'get_finalization_replay_candidates',
        lambda **_kw: [{'job_id': JOB_ID, 'status': 'queued'}],
    )
    monkeypatch.setattr(service.jobs_db, 'claim_finalization_replay', failing_claim)
    monkeypatch.setattr(service.jobs_db, 'get_finalization_job_summary', lambda **_kw: _summary_stub())

    with caplog.at_level(logging.ERROR):
        result = service.reconcile_listen_finalization_jobs()

    assert result['skipped'] == 1
    assert result.get('error', 0) == 0
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_reconciler_keeps_the_loud_shape_for_a_real_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    import logging

    import services.conversation_finalization as service

    def real_failure(job_id: str, **_kwargs: Any) -> Any:
        raise RuntimeError(f'unrelated datastore failure for {job_id}')

    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setattr(
        service.jobs_db, 'recover_stranded_byok_jobs', lambda **_kw: {'scanned': 0, 'blocked': 0, 'errors': 0}
    )
    monkeypatch.setattr(
        service.jobs_db,
        'get_finalization_replay_candidates',
        lambda **_kw: [{'job_id': JOB_ID, 'status': 'queued'}],
    )
    monkeypatch.setattr(service.jobs_db, 'claim_finalization_replay', real_failure)
    monkeypatch.setattr(service.jobs_db, 'get_finalization_job_summary', lambda **_kw: _summary_stub())

    with caplog.at_level(logging.ERROR):
        result = service.reconcile_listen_finalization_jobs()

    assert result['skipped'] == 1
    assert any('listen finalization reconciliation claim failed' in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# Serialization parity: a replay re-decides on fresh reads.
# ---------------------------------------------------------------------------


class _InterleavedClient(_CustodyFakeClient):
    """After the aborted read, a competing worker's lease lands before the replay."""

    def __init__(self, document: Dict[str, Any]):
        super().__init__(document, read_errors=[Aborted(ABORTED_MESSAGE)])

    def collection(self, collection_id: str) -> _CollectionRef:
        row = self.documents.get(JOB_PATH)
        if not self.read_errors and row and row.get('status') == 'queued':
            # A competing Cloud Tasks worker claimed and leased the job
            # (unexpired lease) between this reconciler's aborted read and its
            # replay. The re-read must see the live lease, not re-bump. The
            # lease rides the real clock: ``_now()`` is the fence authority.
            row['status'] = 'leased'
            row['lease_epoch'] = 1
            row['lease_expires_at'] = datetime.now(timezone.utc) + timedelta(minutes=10)
        return super().collection(collection_id)


def test_replay_claim_redecides_after_contention_and_stays_fenced(no_sleep: List[float]):
    """Contention replays the whole read-decide-write, not a stale decision."""
    client = _InterleavedClient(_queued_job())

    intent = jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert intent['created'] is False
    assert intent['status'] == 'leased'
    assert commit_payloads(client) == [], 'the fenced decision must not write on the replay'


def test_commit_abort_replays_inside_the_sdk_wrapper_on_the_same_id():
    """Commit-time aborts are the SDK's own job; the budget is not involved."""
    from database.firestore_transaction_retry import run_with_transaction_contention_retry as real_budget

    client = _CustodyFakeClient(_queued_job(), commit_errors=[Aborted('409 commit contention; aborted transaction')])

    def budget(transaction_factory: Any, operation: Any, **kwargs: Any) -> Any:
        kwargs.pop('random_value', None)
        return real_budget(transaction_factory, operation, sleep=lambda _d: None, random_value=lambda: 0.0, **kwargs)

    original = jobs.run_with_transaction_contention_retry
    jobs.run_with_transaction_contention_retry = budget
    try:
        claim = jobs.claim_finalization_job(JOB_ID, 1, count_worker_claim=True, firestore_client=client)
    finally:
        jobs.run_with_transaction_contention_retry = original

    assert claim['status'] == 'claimed'
    assert len(client.transactions) == 1, 'the SDK wrapper replayed the commit abort on the same transaction'
    assert len(client.commits) == 1


def test_non_contention_failures_keep_their_loud_path(no_sleep: List[float]):
    """A real failure is never replayed by the budget."""
    client = _CustodyFakeClient(_queued_job(), read_errors=[RuntimeError('unrelated datastore outage')])

    with pytest.raises(RuntimeError, match='unrelated datastore outage'):
        jobs.claim_finalization_replay(JOB_ID, stale_after=timedelta(minutes=5), firestore_client=client)

    assert client.commits == []


# ---------------------------------------------------------------------------
# Per-writer expired-id twins: both retry layers compose.
# ---------------------------------------------------------------------------


def test_worker_claim_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(_queued_job(), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])

    claim = jobs.claim_finalization_job(JOB_ID, 1, count_worker_claim=True, firestore_client=client)

    assert claim['status'] == 'claimed'
    assert len(client.transactions) == 2


def test_worker_completion_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _leased_job(fanout_status='completed'), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)]
    )

    completed = jobs.mark_finalization_completed(JOB_ID, 1, 1, firestore_client=client)

    assert completed is True
    assert len(client.transactions) == 2


def test_worker_fenced_terminal_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])

    fenced = jobs.mark_finalization_fenced(JOB_ID, 1, 1, firestore_client=client)

    assert fenced is True
    assert len(client.transactions) == 2


def test_worker_fanout_claim_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[CONVERSATION_PATH] = {
        'status': 'completed',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
    }

    fanout = jobs.claim_finalization_fanout(JOB_ID, 1, 1, firestore_client=client)

    assert fanout['status'] == 'claimed'
    assert len(client.transactions) == 2


def test_worker_fanout_completion_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(
        _leased_job(fanout_status='leased', fanout_lease_epoch=1),
        commit_errors=[InvalidArgument(EXPIRED_MESSAGE)],
    )

    completed = jobs.mark_finalization_fanout_completed(JOB_ID, 1, 1, firestore_client=client)

    assert completed is True
    assert len(client.transactions) == 2


def test_retryable_settlement_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(_leased_job(), commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])

    marked = jobs.mark_finalization_retryable(JOB_ID, 1, 1, firestore_client=client)

    assert marked is True
    assert len(client.transactions) == 2


def test_byok_resume_replays_read_abort(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[JOB_PATH] = {
        'uid': UID,
        'conversation_id': CONVERSATION_ID,
        'status': 'blocked_byok',
        'requires_byok': True,
        'dispatch_generation': 1,
    }
    fault(client, [Aborted(ABORTED_MESSAGE)])

    intent = jobs.resume_blocked_byok_job_for_live_session(JOB_ID, firestore_client=client)

    assert intent['status'] == 'queued'
    assert len(client.transactions) == 2
    assert any(payload.get('status') == 'queued' for payload in commit_payloads(client))


def test_byok_resume_surfaces_typed_exhaustion(no_sleep: List[float]):
    client = _CustodyFakeClient()
    client.documents[JOB_PATH] = {
        'uid': UID,
        'conversation_id': CONVERSATION_ID,
        'status': 'blocked_byok',
        'requires_byok': True,
    }
    fault(client, aborts(50))

    with pytest.raises(FirestoreContentionExhausted):
        jobs.resume_blocked_byok_job_for_live_session(JOB_ID, firestore_client=client)

    assert client.commits == []


def test_stamp_admission_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient({'status': 'processing'}, commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[JOB_PATH] = {}
    client.documents[JOB_PATH].pop('uid', None)
    client.documents[CONVERSATION_PATH] = {'status': 'processing'}

    stamped = jobs.stamp_processing_admission_if_absent(UID, CONVERSATION_ID, firestore_client=client)

    assert stamped is True
    assert len(client.transactions) == 2


def test_reacquire_deferred_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[JOB_PATH] = {}
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': True}

    claimed = jobs.reacquire_deferred_processing(UID, CONVERSATION_ID, firestore_client=client)

    assert claimed is True
    assert len(client.transactions) == 2


def test_recover_deferred_failure_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[JOB_PATH] = {}
    client.documents[CONVERSATION_PATH] = {'status': 'processing', 'deferred': False}

    recovered = jobs.recover_deferred_processing_failure(UID, CONVERSATION_ID, firestore_client=client)

    assert recovered is True
    assert len(client.transactions) == 2


def test_unstampable_orphan_terminal_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[JOB_PATH] = {}
    client.documents[CONVERSATION_PATH] = {'status': 'processing'}
    client.update_times[CONVERSATION_PATH] = datetime.now(timezone.utc) - timedelta(hours=3)

    completed = jobs.complete_unstampable_orphan_conversation(
        UID, CONVERSATION_ID, stale_after=timedelta(hours=2), firestore_client=client
    )

    assert completed is True
    assert len(client.transactions) == 2


def test_meeting_receipt_restarts_an_expired_transaction(no_sleep: List[float]):
    client = _CustodyFakeClient(commit_errors=[InvalidArgument(EXPIRED_MESSAGE)])
    client.documents[JOB_PATH] = {}
    client.documents[CONVERSATION_PATH] = _completed_conversation_row()

    receipt = jobs.record_meeting_receipt(
        UID,
        CONVERSATION_ID,
        finalization_job_id=None,
        eligible=True,
        reason='meeting',
        duration_s=600.0,
        dedup_speech_s=120.0,
        firestore_client=client,
    )

    assert receipt['status'] == 'recorded'
    assert len(client.transactions) == 2


def test_byok_abandonment_restarts_an_expired_transaction(no_sleep: List[float]):
    real_now = datetime.now(timezone.utc)
    client = _CustodyFakeClient(
        _queued_job(
            requires_byok=True,
            status='leased',
            lease_epoch=1,
            lease_expires_at=real_now - timedelta(minutes=10),
        ),
        commit_errors=[InvalidArgument(EXPIRED_MESSAGE)],
    )
    client.documents[CONVERSATION_PATH] = {
        'status': 'processing',
        'discarded': False,
        'finalization_job_id': JOB_ID,
        'finalization_revision': 1,
    }

    result = jobs.abandon_byok_finalization_job(
        JOB_ID,
        expected_status='leased',
        expected_dispatch_generation=1,
        expected_lease_epoch=1,
        abandoned_after=timedelta(minutes=5),
        firestore_client=client,
    )

    assert result['status'] == 'abandoned'
    assert len(client.transactions) == 2


def test_cursor_cas_loss_after_a_contended_replay_stays_fenced(no_sleep: List[float]):
    """A replay re-reads the generation: a competing advance fences this one."""

    class _RacingCursorClient(_CustodyFakeClient):
        def __init__(self) -> None:
            super().__init__(
                read_errors=[Aborted(ABORTED_MESSAGE)],
            )
            self.documents[STALE_CURSOR_PATH] = {'generation': 0}

        def collection(self, collection_id: str) -> _CollectionRef:
            row = self.documents.get(STALE_CURSOR_PATH)
            if not self.read_errors and row and row.get('generation') == 0:
                row['generation'] = 1  # another pod advanced the cursor mid-retry
            return super().collection(collection_id)

    racing = _RacingCursorClient()

    advanced = jobs.advance_stale_processing_sweep_cursor(
        0, 'conversation_finalization_jobs/job-2', firestore_client=racing
    )

    assert advanced is False
    assert commit_payloads(racing) == []


# ---------------------------------------------------------------------------
# Budget pacing parity (the shared contract this seam now rides).
# ---------------------------------------------------------------------------


def test_budget_pacing_contract_keeps_equal_jitter_and_bounds():
    from database.firestore_transaction_retry import (
        _INITIAL_MAX_DELAY_SECONDS,
        run_with_transaction_contention_retry,
    )

    delays: List[float] = []
    attempts = {'n': 0}

    def contended(_transaction: Any) -> int:
        attempts['n'] += 1
        if attempts['n'] <= 2:
            raise Aborted(ABORTED_MESSAGE)
        return 7

    result = run_with_transaction_contention_retry(
        lambda: object(),
        contended,
        operation_name='custody_pacing',
        sleep=delays.append,
        random_value=lambda: 0.0,
    )

    assert result == 7
    assert delays == [
        _INITIAL_MAX_DELAY_SECONDS * 0.5,
        _INITIAL_MAX_DELAY_SECONDS * 1.0,
    ]


def test_budget_delays_cap_at_the_max_delay():
    from database.firestore_transaction_retry import _MAX_DELAY_SECONDS, run_with_transaction_contention_retry

    delays: List[float] = []
    attempts = {'n': 0}

    def always_abort_twice_then_commit(_transaction: Any) -> int:
        attempts['n'] += 1
        if attempts['n'] <= 3:
            raise Aborted(ABORTED_MESSAGE)
        return 1

    run_with_transaction_contention_retry(
        lambda: object(),
        always_abort_twice_then_commit,
        operation_name='custody_cap',
        sleep=delays.append,
        random_value=lambda: 0.0,
    )

    assert delays == [0.1, 0.2, 0.4], 'equal-jitter low bound doubles per attempt'
    assert _MAX_DELAY_SECONDS == 1.0, 'the schedule stays bounded no matter how long contention lasts'


# ---------------------------------------------------------------------------
# Burst containment: one hot row must not poison its whole candidate page.
# ---------------------------------------------------------------------------


def test_burst_on_one_hot_row_does_not_poison_its_neighbors(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A sustained burst on one job is contained; its page neighbors still enqueue.

    Each candidate owns its own bounded budget: the contended claim drains only
    its own budget and is skipped for this tick, while the next candidate on
    the same sweep claims and enqueues normally.
    """
    import logging

    import services.conversation_finalization as service

    def claim(job_id: str, **_kwargs: Any) -> Any:
        if job_id == 'job-hot':
            raise FirestoreContentionExhausted('Firestore transaction contention exhausted for job-hot')
        return {
            'job_id': job_id,
            'status': 'queued',
            'dispatch_generation': 2,
            'created': True,
            'lease_epoch': None,
            'attempt_count': 0,
            'created_at': None,
        }

    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'cloud_tasks')
    monkeypatch.setattr(
        service.jobs_db, 'recover_stranded_byok_jobs', lambda **_kw: {'scanned': 0, 'blocked': 0, 'errors': 0}
    )
    monkeypatch.setattr(
        service.jobs_db,
        'get_finalization_replay_candidates',
        lambda **_kw: [{'job_id': 'job-hot', 'status': 'queued'}, {'job_id': 'job-cool', 'status': 'queued'}],
    )
    monkeypatch.setattr(service.jobs_db, 'claim_finalization_replay', claim)
    monkeypatch.setattr(service.jobs_db, 'get_finalization_job_summary', lambda **_kw: _summary_stub())
    enqueued: List[str] = []
    monkeypatch.setattr(
        service,
        'enqueue_listen_finalization_job',
        lambda job_id, generation: enqueued.append(job_id),
    )

    with caplog.at_level(logging.ERROR):
        result = service.reconcile_listen_finalization_jobs()

    assert result['requeued'] == 1
    assert result['skipped'] == 1, 'only the contended row is skipped'
    assert enqueued == ['job-cool']
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_byok_reclaim_sweep_cursor_replays_read_abort(monkeypatch: pytest.MonkeyPatch, no_sleep: List[float]):
    """The BYOK reclaim's cursor advance rides the same contention budget.

    ``recover_stranded_byok_jobs`` advances a shared CAS cursor per status;
    pods race on that document every tick, and a read-time abort there used to
    crash the whole startup/periodic sweep.
    """

    class _StubQuerySpec:
        @staticmethod
        def build(_collection: Any, _filters: Any, field_filter_factory: Any = None) -> Any:
            del field_filter_factory

            class _Query:
                def order_by(self, _field: str) -> '_Query':
                    return self

                def start_after(self, _cursor: Any) -> '_Query':
                    return self

                def limit(self, _count: int) -> '_Query':
                    return self

                def stream(self) -> Any:
                    return iter(())

            return _Query()

    monkeypatch.setattr(jobs, 'FINALIZATION_OLDEST_NONTERMINAL_QUERY', _StubQuerySpec)

    class _SweepClient(_CustodyFakeClient):
        """One clean advisory read, then one aborted transactional read per doc."""

        def __init__(self) -> None:
            super().__init__()
            self.documents[('conversation_recovery_state', 'byok_reclaim_queued')] = {
                'resume_after_path': None,
                'generation': 0,
            }
            self.documents[('conversation_recovery_state', 'byok_reclaim_leased')] = {
                'resume_after_path': None,
                'generation': 0,
            }

    class _Doc(_DocumentRef):
        """First get is the sweep's advisory read; the second aborts exactly once."""

        def __init__(self, client: '_CustodyFakeClient', path: Tuple[str, ...]):
            super().__init__(client, path)
            self._gets = 0

        def get(self, transaction: object = None) -> _Snapshot:
            self._gets += 1
            if self._gets == 2:
                raise Aborted(ABORTED_MESSAGE)
            return _Snapshot(self._client.documents.get(self.path), doc_id=self.id)

    class _SweepDocCollection(_CollectionRef):
        def document(self, doc_id: str) -> _DocumentRef:
            if doc_id.startswith('byok_reclaim_'):
                return _Doc(self._client, self.path + (doc_id,))
            return super().document(doc_id)

    class _Client(_SweepClient):
        def collection(self, collection_id: str) -> _CollectionRef:
            return _SweepDocCollection(self, (collection_id,))

    client = _Client()

    result = jobs.recover_stranded_byok_jobs(firestore_client=client)

    assert result == {'scanned': 0, 'blocked': 0, 'errors': 0}
    assert len(client.commits) == 2, 'one cursor advance per status, each after replaying one abort'
    assert len(client.transactions) == 4, 'two attempts per advance: the aborted read and the replay'
