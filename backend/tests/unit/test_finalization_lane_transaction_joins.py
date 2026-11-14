"""Every conversation-finalization transactional entry rides the bounded lane runner.

Before this change the twenty-seven transactional entries in
``conversation_finalization_jobs`` handed the bounded engine the SDK's default
transaction factory: every outer attempt minted a transaction whose own commit
loop replays the SAME transaction id up to five times inside the collision
that aborted it. Each test here drives the real site function against a client
whose transactional reads all raise ``Aborted`` and asserts the typed, labeled
bounded outcome — five fresh transactions, one SDK commit attempt each, and an
exhaustion marker that names the flow on the lane channel. On a tree without
the join the mints carry ``None`` (the SDK default) and the lane marker is
absent, so these tests fail there.

Failure-Class: FC-finalization-transaction-attempts-replay-one-retired-id-five-times
"""

from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import Aborted

from database import conversation_finalization_jobs as finalization_db
from database import firestore_transaction_retry as engine
from database.firestore_transaction_retry import FirestoreContentionExhausted

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
CONTENTION_MESSAGE = '409 transaction contention on every transactional read'

DEFAULT_ROW = {
    'status': 'processing',
    'dispatch_generation': 1,
    'lease_epoch': 1,
    'generation': 0,
    'uid': 'u',
    'conversation_id': 'c',
    'job_id': 'job',
    'intent_id': 'intent',
    'requires_byok': False,
    'created_at': NOW,
    'updated_at': NOW,
    'admitted_at': NOW,
    'reconcile_after_at': NOW,
    'resume_after_path': None,
    'revision': 1,
    'finalization_revision': 1,
    'retry_count': 0,
    'failure_code': 'processing_failed',
}


class _FaultingTransaction:
    def get(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def set(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def update(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def delete(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def create(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)


class _Snapshot:
    def __init__(self, row, path):
        self._row = dict(row)
        self._path = path
        self.exists = row is not None
        self.id = path.rsplit('/', 1)[-1]

    @property
    def reference(self):
        outer = self

        class _Ref:
            path = outer._path
            id = outer.id

        return _Ref()

    def to_dict(self):
        return dict(self._row)


class _Query:
    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        if name in {'where', 'limit', 'order_by', 'offset', 'select', 'count'}:
            return lambda *_a, **_kw: self
        raise AttributeError(name)

    def stream(self, **_kwargs):
        return list(self._client.page_snapshots)

    def get(self, **_kwargs):
        return list(self._client.page_snapshots)


class _Collection:
    def __init__(self, client, path):
        self._client = client
        self._path = path

    def document(self, *parts):
        path = '/'.join([self._path] + [str(p) for p in parts])
        row = self._client.seeded.get(path, DEFAULT_ROW)
        return _Document(self._client, path, row)

    def where(self, *_args, **_kwargs):
        return _Query(self._client)

    def limit(self, *_args):
        return _Query(self._client)

    def order_by(self, *_args, **_kwargs):
        return _Query(self._client)

    def list_documents(self, **_kwargs):
        return []

    def stream(self, **_kwargs):
        return []


class _Document:
    def __init__(self, client, path, row):
        self._client = client
        self._path = path
        self._row = row

    @property
    def id(self):
        return self._path.rsplit('/', 1)[-1]

    @property
    def path(self):
        return self._path

    def collection(self, *parts):
        return _Collection(self._client, '/'.join([self._path] + [str(p) for p in parts]))

    def get(self, **kwargs):
        if kwargs.get('transaction') is not None:
            raise Aborted(CONTENTION_MESSAGE)
        return _Snapshot(self._row, self._path)

    def stream(self, **kwargs):
        if kwargs.get('transaction') is not None:
            raise Aborted(CONTENTION_MESSAGE)
        return iter([])

    def set(self, *_a, **_kw):
        raise Aborted(CONTENTION_MESSAGE)

    def update(self, *_a, **_kw):
        raise Aborted(CONTENTION_MESSAGE)

    def delete(self, *_a, **_kw):
        raise Aborted(CONTENTION_MESSAGE)


class _FaultingClient:
    """Benign outside transactions; every transactional operation aborts."""

    def __init__(self):
        self.minted = []
        self.seeded = {}
        self.page_snapshots = []

    def transaction(self, max_attempts=None):
        self.minted.append(max_attempts)
        return _FaultingTransaction()

    def collection(self, *parts):
        return _Collection(self, '/'.join(str(p) for p in parts))

    def document(self, *parts):
        path = '/'.join(str(p) for p in parts)
        return _Document(self, path, self.seeded.get(path, DEFAULT_ROW))


@pytest.fixture
def lane_env(monkeypatch):
    """Real transactional bodies on a faulting client; the jitter ladder silenced."""

    def passthrough(function):
        return lambda transaction, *args, **kwargs: function(transaction, *args, **kwargs)

    monkeypatch.setattr(finalization_db.firestore, 'transactional', passthrough)
    monkeypatch.setattr(engine, 'equal_jitter_delay', lambda attempt, random_value=None: 0.0)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    return _FaultingClient()


def _assert_bounded_exhaustion(caplog, label, minted, expected_chains=1):
    assert len(minted) == 5 * expected_chains, 'each bounded chain mints five fresh transactions'
    assert set(minted) == {1}, 'every fresh transaction carries a single SDK commit attempt'
    assert any(
        f'event={label}_contention_exhausted' in record.getMessage() for record in caplog.records
    ), 'the lane marker names the flow on the lane channel'


def test_finalization_intent_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.create_or_get_finalization_intent(
            'u',
            'c',
            requires_byok=False,
            finalization_admission=lambda row: {'created': False},
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'conversation_finalization_intent', lane_env.minted)


def test_byok_resume_for_live_session_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.resume_blocked_byok_job_for_live_session('job', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'byok_resume_for_live_session', lane_env.minted)


def test_worker_claim_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.claim_finalization_job('job', 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_worker_claim', lane_env.minted)


def test_finalization_complete_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_finalization_completed('job', 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_complete', lane_env.minted)


def test_sync_revision_defer_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.defer_sync_revision_fence('job', 1, 1, None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_sync_revision_defer', lane_env.minted)


def test_finalization_fence_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_finalization_fenced('job', 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_fence', lane_env.minted)


def test_fanout_claim_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.claim_finalization_fanout('job', 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_fanout_claim', lane_env.minted)


def test_fanout_complete_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_finalization_fanout_completed('job', 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_fanout_complete', lane_env.minted)


def test_retryable_mark_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_finalization_retryable('job', 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_retryable_mark', lane_env.minted)


def test_dead_letter_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_finalization_dead_letter('job', 1, 1, 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_dead_letter', lane_env.minted)


def test_meeting_receipt_record_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.record_meeting_receipt(
            'u',
            'c',
            finalization_job_id='job',
            eligible=True,
            reason='ok',
            duration_s=1.0,
            dedup_speech_s=0.5,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'meeting_receipt_record', lane_env.minted)


def test_receipt_intent_persisted_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_meeting_receipt_intent_persisted('job', 'intent', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'meeting_receipt_intent_persisted', lane_env.minted)


def test_receipt_materialized_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.mark_meeting_receipt_materialized(
            'u', 'c', 'intent', materialized_at=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'meeting_receipt_materialized', lane_env.minted)


def test_replay_claim_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.claim_finalization_replay('job', stale_after=timedelta(hours=1), firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_replay_claim', lane_env.minted)


def test_byok_reclaim_sweep_cursor_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.recover_stranded_byok_jobs(firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'byok_reclaim_sweep_cursor', lane_env.minted)


def test_finalization_replay_cursor_joins_bounded_lane(lane_env, caplog):
    lane_env.page_snapshots = [
        _Snapshot(
            {'requires_byok': True, 'reconcile_after_at': NOW - timedelta(days=365)},
            'conversation_finalization_jobs/j1',
        ),
        _Snapshot(
            {'requires_byok': True, 'reconcile_after_at': NOW - timedelta(days=365)},
            'conversation_finalization_jobs/j2',
        ),
    ]
    lane_env.seeded['conversation_finalization_jobs/j1'] = DEFAULT_ROW | {'requires_byok': True}
    lane_env.seeded['conversation_finalization_jobs/j2'] = DEFAULT_ROW | {'requires_byok': True}
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.get_finalization_replay_candidates(limit=2, firestore_client=lane_env)
    # The inner replay claims stay blocked on this client (their chain is
    # covered by test_replay_claim_joins_bounded_lane); the entry's own
    # cursor CAS advance is the joined chain under test here.
    _assert_bounded_exhaustion(caplog, 'finalization_replay_cursor', lane_env.minted)


def test_replay_defer_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.defer_finalization_replay({'job_id': 'job'}, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'finalization_replay_defer', lane_env.minted)


def test_in_progress_content_sweep_cursor_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.advance_in_progress_content_sweep_cursor(0, None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'in_progress_content_sweep_cursor', lane_env.minted)


def test_stale_processing_sweep_cursor_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.advance_stale_processing_sweep_cursor(0, None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'stale_processing_sweep_cursor', lane_env.minted)


def test_receipt_backfill_cursor_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.advance_meeting_receipt_backfill_cursor(0, None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'meeting_receipt_backfill_cursor', lane_env.minted)


def test_processing_admission_stamp_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.stamp_processing_admission_if_absent('u', 'c', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'processing_admission_stamp', lane_env.minted)


def test_unstampable_orphan_terminal_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.complete_unstampable_orphan_conversation(
            'u', 'c', stale_after=timedelta(hours=1), firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'unstampable_orphan_terminal', lane_env.minted)


def test_orphan_conversation_terminal_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.complete_orphan_conversation('u', 'c', expected_admitted_at=None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'orphan_conversation_terminal', lane_env.minted)


def test_deferred_processing_reacquire_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.reacquire_deferred_processing('u', 'c', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'deferred_processing_reacquire', lane_env.minted)


def test_recover_deferred_processing_failure_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.recover_deferred_processing_failure('u', 'c', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'recover_deferred_processing_failure', lane_env.minted)


def test_abandon_byok_job_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.abandon_byok_finalization_job(
            'job',
            expected_status='processing',
            expected_dispatch_generation=1,
            expected_lease_epoch=1,
            abandoned_after=timedelta(hours=1),
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'abandon_byok_finalization_job', lane_env.minted)


def test_byok_abandonment_sweep_cursor_joins_bounded_lane(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        finalization_db.advance_byok_abandonment_sweep_cursor(0, None, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'byok_abandonment_sweep_cursor', lane_env.minted)
