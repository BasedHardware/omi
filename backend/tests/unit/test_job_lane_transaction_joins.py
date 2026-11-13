"""Every sync-backfill and conversation-job transactional entry rides the bounded engine.

Before this change the twenty-four transactional entries across
``sync_backfill_sequencer``, ``conversation_merge_jobs``,
``conversation_processing_recovery`` and ``oversized_conversation_terminal``
handed their bodies to the Firestore SDK's bare transaction path: one
transaction id replayed by the SDK's same-id commit loop, a read-time
``Aborted`` fault escaping as an unclassified error, and an exhaustion
surfacing anonymously. Each test here drives the real site function against
a client whose transactional operations all raise ``Aborted`` and asserts the
typed, labeled bounded outcome — five fresh transactions, one SDK commit
attempt each, and an exhaustion record that names the flow. On a tree without
the join these tests fail with the raw ``Aborted`` fault instead.

Failure-Class: FC-bare-sync-backfill-and-conversation-job-transactions-fail-on-first-contention
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import Aborted

from database import conversation_merge_jobs as merge_db
from database import conversation_processing_recovery as processing_recovery
from database import oversized_conversation_terminal as oversized_db
from database import firestore_transaction_retry as engine
from database import sync_backfill_sequencer as registry
from database.firestore_transaction_retry import FirestoreContentionExhausted

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
CONTENTION_MESSAGE = '409 transaction contention on every operation'


class _FaultingTransaction:
    def get(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def set(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def update(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def delete(self, *_args, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def stream(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)


class _FaultingDocument:
    def get(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def collection(self, *_args):
        return _FaultingCollection()

    def stream(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)


class _FaultingCollection:
    def document(self, *_args):
        return _FaultingDocument()

    def where(self, *_args, **_kwargs):
        return _FaultingQuery()

    def limit(self, *_args):
        return _FaultingQuery()


class _FaultingQuery:
    def stream(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)

    def limit(self, *_args):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def where(self, *_args, **_kwargs):
        return self

    def count(self):
        return self

    def get(self, **_kwargs):
        raise Aborted(CONTENTION_MESSAGE)


class _FaultingClient:
    """Every mint is fresh and single-commit-attempt; every operation aborts."""

    def __init__(self):
        self.minted = []

    def transaction(self, max_attempts=None):
        self.minted.append(max_attempts)
        return _FaultingTransaction()

    def collection(self, *_args):
        return _FaultingCollection()


@pytest.fixture
def lane_env(monkeypatch):
    """Real transactional bodies on a faulting client; the jitter ladder silenced."""

    def passthrough(function):
        return lambda transaction, *args, **kwargs: function(transaction, *args, **kwargs)

    for module in (registry, merge_db, processing_recovery, oversized_db):
        monkeypatch.setattr(module.firestore, 'transactional', passthrough)
    monkeypatch.setattr(engine, 'equal_jitter_delay', lambda attempt, random_value=None: 0.0)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    monkeypatch.delenv('SYNC_BACKFILL_ORDER', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_PERCENT', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', raising=False)
    return _FaultingClient()


def _assert_bounded_exhaustion(caplog, label, minted):
    assert len(minted) == 5, 'a bounded chain mints five fresh transactions'
    assert set(minted) == {1}, 'every fresh transaction carries a single SDK commit attempt'
    assert any(
        record.levelno == logging.ERROR
        and f'operation={label}' in record.getMessage()
        and 'outcome=exhausted' in record.getMessage()
        for record in caplog.records
    ), 'the exhaustion names the flow on the contention channel'
    assert any(
        f'event={label}_contention_exhausted' in record.getMessage() for record in caplog.records
    ), 'the lane marker names the flow on the driving module logger'


def test_sequencer_repair_owner_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.repair_owner('u', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_OWNER_REPAIR_LABEL, lane_env.minted)


def test_sequencer_register_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.register_job('u', 'job', {'uid': 'u', 'job_id': 'job'}, None, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_REGISTER_LABEL, lane_env.minted)


def test_sequencer_retire_expired_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.retire_expired('u', 'job', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_RETIRE_EXPIRED_LABEL, lane_env.minted)


def test_sequencer_claim_next_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.claim_next('u', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_CLAIM_NEXT_LABEL, lane_env.minted)


def test_sequencer_begin_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.begin_job('u', 'job', 1, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_BEGIN_JOB_LABEL, lane_env.minted)


def test_sequencer_renew_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.renew_job('u', 'job', 1, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_RENEW_JOB_LABEL, lane_env.minted)


def test_sequencer_finish_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.finish_job('u', 'job', 1, 'failed', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_FINISH_JOB_LABEL, lane_env.minted)


def test_sequencer_claim_worker_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.claim_worker('u', 'job', 1, 'token', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_CLAIM_WORKER_LABEL, lane_env.minted)


def test_sequencer_fail_worker_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.fail_worker('u', 'job', 1, 'token', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_FAIL_WORKER_LABEL, lane_env.minted)


def test_sequencer_defer_owner_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.defer_owner('u', 60, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_DEFER_OWNER_LABEL, lane_env.minted)


def test_sequencer_note_budget_deferral_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.note_budget_deferral('u', 'job', 1, 2, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_BUDGET_DEFERRAL_LABEL, lane_env.minted)


def test_sequencer_finish_expired_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.finish_expired_job('u', 'job', 1, 'expired', firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_FINISH_EXPIRED_JOB_LABEL, lane_env.minted)


def test_sequencer_owner_release_due_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.owner_release_due('u', 'job', 1, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_OWNER_RELEASE_DUE_LABEL, lane_env.minted)


def test_sequencer_redrive_job_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        registry.redrive_job('u', 'job', 1, firestore_client=lane_env, now=NOW)
    _assert_bounded_exhaustion(caplog, registry.SYNC_BACKFILL_REDRIVE_JOB_LABEL, lane_env.minted)


def test_merge_job_admit_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.admit('u', ['a', 'b'], False, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_ADMIT_LABEL, lane_env.minted)


def test_merge_job_claim_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.claim('job', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_CLAIM_LABEL, lane_env.minted)


def test_merge_job_renew_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.renew('job', 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_RENEW_LABEL, lane_env.minted)


def test_merge_job_finish_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.finish('job', 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_FINISH_LABEL, lane_env.minted)


def test_merge_job_begin_recovery_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.begin_recovery('job', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_BEGIN_RECOVERY_LABEL, lane_env.minted)


def test_merge_job_finish_recovery_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        merge_db.finish_recovery('job', 1, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, merge_db.MERGE_JOB_FINISH_RECOVERY_LABEL, lane_env.minted)


def test_processing_recovery_stamp_admission_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        processing_recovery.stamp_processing_admission_if_absent('u', 'c', firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, processing_recovery.PROCESSING_RECOVERY_STAMP_ADMISSION_LABEL, lane_env.minted)


def test_processing_recovery_complete_unstampable_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        processing_recovery.complete_unstampable_orphan_conversation(
            'u', 'c', stale_after=timedelta(hours=1), firestore_client=lane_env
        )
    _assert_bounded_exhaustion(
        caplog, processing_recovery.PROCESSING_RECOVERY_COMPLETE_UNSTAMPABLE_LABEL, lane_env.minted
    )


def test_processing_recovery_complete_orphan_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        processing_recovery.complete_orphan_conversation('u', 'c', expected_admitted_at=NOW, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, processing_recovery.PROCESSING_RECOVERY_COMPLETE_ORPHAN_LABEL, lane_env.minted)


def test_oversized_in_progress_terminal_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        oversized_db.complete_oversized_in_progress_conversation(
            'u', 'c', quiet_for=timedelta(hours=1), firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, oversized_db.OVERSIZED_IN_PROGRESS_TERMINAL_LABEL, lane_env.minted)
