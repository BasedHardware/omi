"""Durable listen finalization must survive a retired Firestore transaction id.

Firestore retires transaction ids under load. A finalization boundary running a
bare ``@firestore.transactional`` callable then dies on its first attempt with
``InvalidArgument: 400 The referenced transaction has expired or is no longer
valid`` — the same id-replay the SDK cannot recover — even though nothing was
written and a fresh transaction would succeed. Every previously committed
effect the retry layer owns (lease renewal, deferred re-arm, orphan terminal,
sweep cursor) goes to its caller's failure arm instead, and the worker's
claim/complete/retry transactions surface the retirement as a Cloud Tasks
500. ``run_transactional`` restarts exactly that rejection on a fresh
transaction; the shared contention budget replays read-time aborts. These
tests pin both layers on the job/lease writers through their public wrappers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversation_finalization_jobs as jobs

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid.'


class _FakeSnapshot:
    def __init__(self, data: Dict[str, Any] | None, doc_id: str = 'job-1', update_time: datetime | None = None):
        self._data = data
        self.exists = data is not None
        self.id = doc_id
        self.update_time = update_time

    def to_dict(self) -> Dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, client: '_FinalizationFakeClient', doc_id: str):
        self._client = client
        self.id = doc_id

    def get(self, transaction=None) -> _FakeSnapshot:
        if self.id == self._client.conversation_id and self._client.conversation_document is not None:
            return _FakeSnapshot(self._client.conversation_document, doc_id=self.id)
        return _FakeSnapshot(
            self._client.document,
            doc_id=self.id,
            update_time=getattr(self._client, 'update_time', None),
        )

    def collection(self, _collection_id: str):
        return self._client.photos_collection


class _FakePhotosCollection:
    def limit(self, _count: int):
        return self

    def stream(self, transaction=None):
        return iter(())


class _FakeUserDocument:
    """``users/{uid}`` — every subcollection resolves to the one conversation ref."""

    def __init__(self, client: '_FinalizationFakeClient'):
        self._client = client

    def collection(self, _collection_id: str) -> '_FakeUserSubcollection':
        return _FakeUserSubcollection(self._client)


class _FakeUserSubcollection:
    def __init__(self, client: '_FinalizationFakeClient'):
        self._client = client

    def document(self, doc_id: str) -> _FakeDocumentReference:
        return _FakeDocumentReference(self._client, doc_id)


class _FakeUsersRoot:
    def __init__(self, client: '_FinalizationFakeClient'):
        self._client = client

    def document(self, _uid: str) -> _FakeUserDocument:
        return _FakeUserDocument(self._client)


class _FakeCollectionReference:
    def __init__(self, client: '_FinalizationFakeClient'):
        self._client = client

    def document(self, doc_id: str) -> _FakeDocumentReference:
        return _FakeDocumentReference(self._client, doc_id)


class _FakeTransaction:
    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_FinalizationFakeClient', index: int):
        self._client = client
        self._id = f'txn-{index}'.encode()
        self.payload: Dict[str, Any] | None = None
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id=None) -> None:
        pass

    def _rollback(self) -> None:
        self.rolled_back = True

    def set(self, _doc_ref: Any, payload: Dict[str, Any], merge: bool = False) -> None:
        self.payload = payload

    def update(self, _doc_ref: Any, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        self._client.commits.append(self.payload)


class _FinalizationFakeClient:
    """One document body plus a bounded queue of commit faults, SDK-shaped.

    ``firestore.transactional`` is the real SDK wrapper: it reads the
    transaction id, drives the body, and commits through ``_commit``, so the
    fake reproduces the retired-id commit rejection without faking the retry
    policy under test.
    """

    def __init__(self, document: Dict[str, Any] | None, commit_errors: List[BaseException] | None = None):
        self.document = document
        self.commit_errors = list(commit_errors or [])
        self.commits: List[Dict[str, Any] | None] = []
        self.transactions: List[_FakeTransaction] = []
        self.photos_collection = _FakePhotosCollection()
        self.conversation_id = 'conversation-1'
        self.conversation_document: Dict[str, Any] | None = None

    def collection(self, _collection_id: str) -> Any:
        if _collection_id == 'users':
            return _FakeUsersRoot(self)
        return _FakeCollectionReference(self)

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def _processing_row(admitted_before_seconds: int = 120) -> Dict[str, Any]:
    return {
        'status': 'processing',
        'processing_admitted_at': datetime.now(timezone.utc) - timedelta(seconds=admitted_before_seconds),
    }


def test_renew_processing_lease_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient(_processing_row(), [InvalidArgument(EXPIRED_MESSAGE)])

    renewed = jobs.renew_processing_lease('uid-1', 'conversation-1', firestore_client=client)

    assert renewed is True
    assert len(client.transactions) == 2, 'the restart must use a fresh transaction, not the retired id'
    assert client.transactions[0].rolled_back is True
    assert len(client.commits) == 1
    assert client.commits[0] is not None
    assert 'processing_admitted_at' in client.commits[0]


def test_reacquire_deferred_processing_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient({'status': 'processing', 'deferred': True}, [InvalidArgument(EXPIRED_MESSAGE)])

    claimed = jobs.reacquire_deferred_processing('uid-1', 'conversation-1', firestore_client=client)

    assert claimed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'processing'
    assert written['deferred'] is False


def test_recover_deferred_processing_failure_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient({'status': 'processing', 'deferred': False}, [InvalidArgument(EXPIRED_MESSAGE)])

    recovered = jobs.recover_deferred_processing_failure('uid-1', 'conversation-1', firestore_client=client)

    assert recovered is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['deferred'] is True


def test_stamp_processing_admission_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient({'status': 'processing'}, [InvalidArgument(EXPIRED_MESSAGE)])

    stamped = jobs.stamp_processing_admission_if_absent('uid-1', 'conversation-1', firestore_client=client)

    assert stamped is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert 'processing_admitted_at' in written


def test_complete_orphan_conversation_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient(_processing_row(), [InvalidArgument(EXPIRED_MESSAGE)])

    completed = jobs.complete_orphan_conversation(
        'uid-1',
        'conversation-1',
        expected_admitted_at=client.document['processing_admitted_at'],
        firestore_client=client,
    )

    assert completed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'completed'


def test_worker_claim_transaction_survives_a_retired_transaction_id():
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'queued',
        'dispatch_generation': 1,
        'created_at': datetime.now(timezone.utc),
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    claim = jobs.claim_finalization_job('job-1', 1, count_worker_claim=True, firestore_client=client)

    assert claim['status'] == 'claimed'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'leased'


def test_worker_completion_transaction_survives_a_retired_transaction_id():
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'fanout_status': 'completed',
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    completed = jobs.mark_finalization_completed('job-1', 1, 1, firestore_client=client)

    assert completed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'completed'


def test_retryable_transition_survives_a_retired_transaction_id():
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    requeued = jobs.mark_finalization_retryable('job-1', 1, 1, firestore_client=client)

    assert requeued is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'queued'


def test_stale_processing_sweep_cursor_survives_a_retired_transaction_id():
    client = _FinalizationFakeClient(
        {'resume_after_path': 'users/u/c/a', 'generation': 3}, [InvalidArgument(EXPIRED_MESSAGE)]
    )

    advanced = jobs.advance_stale_processing_sweep_cursor(3, 'users/u/c/b', firestore_client=client)

    assert advanced is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['resume_after_path'] == 'users/u/c/b'


def test_non_retryable_retirement_still_fails_the_caller():
    """An unrelated 400 keeps its raise: only retirement is a restart."""
    client = _FinalizationFakeClient(_processing_row(), [InvalidArgument('9 Failed precondition quota exceeded.')])

    with pytest.raises(InvalidArgument):
        jobs.renew_processing_lease('uid-1', 'conversation-1', firestore_client=client)

    assert len(client.transactions) == 1, 'no retry may burn a second transaction on a real failure'


def test_permanent_rejection_is_not_restarted_into_a_completed_job():
    """A 1 MiB ceiling 400 must surface, not be absorbed as success."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument('400 The request is larger than the maximum size 1048576.')])

    with pytest.raises(InvalidArgument):
        jobs.mark_finalization_retryable('job-1', 1, 1, firestore_client=client)

    assert client.commits == []


def test_read_time_contention_on_the_lease_renewal_stays_bounded_for_its_caller():
    """Read-time aborts replay inside the SDK wrapper on the same id and surface typed.

    The SDK replays a commit ``Aborted`` on the same transaction id; a
    read-time ``Aborted`` rides those same in-wrapper attempts, and when they
    run out the wrapper raises its exhausted-``Aborted`` form — the shape the
    shared contention budget exists to replay on fresh transactions where a
    caller wraps one. The heartbeat caller treats every failure the same (log
    and stop), so the renewal's own contract here is: never silently return
    False, and never mask the abort as success.
    """
    client = _RenewingContentionClient()

    with pytest.raises(Exception) as excinfo:
        jobs.renew_processing_lease('uid-1', 'conversation-1', firestore_client=client)

    assert not isinstance(excinfo.value, AssertionError)
    assert 'aborted' in str(excinfo.value).lower() or isinstance(excinfo.value, ValueError)


class _RenewingContentionClient(_FinalizationFakeClient):
    """Raise a read-time abort from the transaction body's reads, SDK-shaped."""

    def __init__(self):
        super().__init__(_processing_row())

    def collection(self, _collection_id: str) -> Any:
        if _collection_id == 'users':
            return _ContendedUsersRoot(self)
        return super().collection(_collection_id)

    def transaction(self) -> Any:
        return super().transaction()


class _ContendedDocumentReference(_FakeDocumentReference):
    def get(self, transaction=None) -> _FakeSnapshot:
        raise Aborted('409 read contention; aborted transaction')


class _ContendedUserSubcollection(_FakeUserSubcollection):
    def document(self, doc_id: str) -> _FakeDocumentReference:
        return _ContendedDocumentReference(self._client, doc_id)


class _ContendedUserDocument(_FakeUserDocument):
    def collection(self, _collection_id: str) -> _ContendedUserSubcollection:
        return _ContendedUserSubcollection(self._client)


def test_wedge_first_seen_claim_survives_a_retired_transaction_id():
    """The capture-wedge cohort claim restarts a retired-id commit."""
    from database import capture_wedge_state as wedge

    client = _FinalizationFakeClient({'first_seen_day': '2026-10-25'}, [InvalidArgument(EXPIRED_MESSAGE)])
    monkeypatch_day = '2026-10-26'

    claimed = wedge.claim_wedge_first_seen('uid-1', monkeypatch_day, firestore_client=client)

    assert claimed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['first_seen_day'] == monkeypatch_day


def test_wedge_nudge_cooldown_survives_a_retired_transaction_id():
    """The at-most-once nudge claim restarts a retired-id commit."""
    from database import capture_wedge_state as wedge

    client = _FinalizationFakeClient(None, [InvalidArgument(EXPIRED_MESSAGE)])

    claimed = wedge.claim_wedge_nudge_cooldown('uid-1', firestore_client=client)

    assert claimed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    assert client.commits[0] is not None


def test_sync_dead_letter_pending_survives_a_retired_transaction_id(monkeypatch):
    """The durable diagnosis write restarts a retired-id commit."""
    from database import sync_dead_letters as ledger

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = _FinalizationFakeClient(None, [InvalidArgument(EXPIRED_MESSAGE)])

    record = ledger.record_dead_letter_pending(job_id='job-1', uid='uid-1', firestore_client=client)

    assert record['status'] == 'pending'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    assert client.commits[0] is not None


def test_sync_dead_letter_confirm_survives_a_retired_transaction_id(monkeypatch):
    """The confirmation write restarts a retired-id commit and emits once."""
    from database import sync_dead_letters as ledger

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    existing = {'job_id': 'job-1', 'uid': 'uid-1', 'status': 'pending'}
    client = _FinalizationFakeClient(existing, [InvalidArgument(EXPIRED_MESSAGE)])

    confirmed = ledger.confirm_dead_letter('job-1', firestore_client=client)

    assert confirmed is not None
    assert confirmed['status'] == 'dead_letter'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_byok_resume_survives_a_retired_transaction_id():
    """The live-session BYOK resume restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'blocked_byok',
        'requires_byok': True,
        'dispatch_generation': 1,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    intent = jobs.resume_blocked_byok_job_for_live_session('job-1', firestore_client=client)

    assert intent['status'] == 'queued'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'queued'


def test_fenced_transition_survives_a_retired_transaction_id():
    """The no-fanout fenced terminal restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'fanout_status': 'pending',
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    fenced = jobs.mark_finalization_fenced('job-1', 1, 1, firestore_client=client)

    assert fenced is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'completed'
    assert written['fanout_status'] == 'fenced'


def test_dead_letter_transition_survives_a_retired_transaction_id():
    """The terminal failure write restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'finalization_revision': 1,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    dead = jobs.mark_finalization_dead_letter('job-1', 1, 1, retry_count=3, firestore_client=client)

    assert dead is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True
    written = client.commits[0]
    assert written is not None
    assert written['status'] == 'dead_letter'


def test_replay_claim_survives_a_retired_transaction_id():
    """The reconciler's replay claim restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'queued',
        'requires_byok': True,
        'dispatch_generation': 1,
        'created_at': datetime.now(timezone.utc) - timedelta(hours=1),
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    intent = jobs.claim_finalization_replay('job-1', stale_after=timedelta(seconds=300), firestore_client=client)

    assert intent['status'] == 'blocked_byok'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_selfheal_content_cursor_survives_a_retired_transaction_id():
    """The self-heal sweep cursor restarts a retired-id commit."""
    client = _FinalizationFakeClient(
        {'resume_after_path': 'users/u/c/a', 'generation': 3}, [InvalidArgument(EXPIRED_MESSAGE)]
    )

    advanced = jobs.advance_in_progress_content_sweep_cursor(3, 'users/u/c/b', firestore_client=client)

    assert advanced is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_meeting_receipt_cursor_survives_a_retired_transaction_id():
    """The meeting-receipt backfill cursor restarts a retired-id commit."""
    client = _FinalizationFakeClient(
        {'resume_after_path': 'users/u/c/a', 'generation': 3}, [InvalidArgument(EXPIRED_MESSAGE)]
    )

    advanced = jobs.advance_meeting_receipt_backfill_cursor(3, 'users/u/c/b', firestore_client=client)

    assert advanced is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_byok_abandonment_cursor_survives_a_retired_transaction_id():
    """The BYOK abandonment sweep cursor restarts a retired-id commit."""
    client = _FinalizationFakeClient(
        {'resume_after_path': 'users/u/c/a', 'generation': 3}, [InvalidArgument(EXPIRED_MESSAGE)]
    )

    advanced = jobs.advance_byok_abandonment_sweep_cursor(3, 'users/u/c/b', firestore_client=client)

    assert advanced is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_unstampable_orphan_terminal_survives_a_retired_transaction_id():
    """The 1 MiB-orphan terminalization restarts a retired-id commit."""
    stale_written = datetime.now(timezone.utc) - timedelta(hours=2)
    row = {'status': 'processing'}
    client = _FinalizationFakeClient(row, [InvalidArgument(EXPIRED_MESSAGE)])
    client.update_time = stale_written

    completed = jobs.complete_unstampable_orphan_conversation(
        'uid-1', 'conversation-1', stale_after=timedelta(seconds=900), firestore_client=client
    )

    assert completed is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_fanout_claim_survives_a_retired_transaction_id():
    """The fanout claim restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'fanout_status': 'pending',
        'fanout_key': 'conversation:conversation-1:finalization:1',
        'finalization_revision': 1,
    }
    conversation_row = {
        'status': 'completed',
        'finalization_job_id': 'job-1',
        'finalization_revision': 1,
        'discarded': False,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])
    client.conversation_document = conversation_row

    claim = jobs.claim_finalization_fanout('job-1', 1, 1, firestore_client=client)

    assert claim['status'] == 'claimed'
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


def test_fanout_completion_survives_a_retired_transaction_id():
    """The committed-fanout completion restarts a retired-id commit."""
    job: Dict[str, Any] = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'fanout_status': 'leased',
        'fanout_lease_epoch': 1,
    }
    client = _FinalizationFakeClient(job, [InvalidArgument(EXPIRED_MESSAGE)])

    done = jobs.mark_finalization_fanout_completed('job-1', 1, 1, firestore_client=client)

    assert done is True
    assert len(client.transactions) == 2
    assert client.transactions[0].rolled_back is True


class _ContendedUsersRoot(_FakeUsersRoot):
    def document(self, _uid: str) -> _ContendedUserDocument:
        return _ContendedUserDocument(self._client)


if __name__ == '__main__':
    import sys

    sys.exit(pytest.main([__file__, '-q']))


# Failure-Class: FC-retired-transaction-treated-as-fatal
# A Firestore commit rejected because its transaction id was retired wrote
# nothing and is recoverable; the storage boundary must restart it on a new
# transaction rather than raise a failure its caller cannot distinguish from a
# real write error. Canonical prevention: run @firestore.transactional
# callables through database._client.run_transactional — applied here to every
# conversation_finalization_jobs boundary (claim, completion, fencing,
# retryable/dead-letter transitions, BYOK resume, replay claim, meeting
# receipt) and the processing-admission state it fences (lease renewal,
# deferred re-arm, orphan terminalization, sweep cursors).
