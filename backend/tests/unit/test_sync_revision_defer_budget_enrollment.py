"""Enrollment tests: the sync-revision fence yield rides the shared contention budget.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

``defer_sync_revision_fence`` is the losing processor's yield on the
conversation-finalization persistence fence: it returns a still-owned job to
the durable sync-revision replay queue. Every other custody writer in
``conversation_finalization_jobs`` rides the bounded contention budget; this
yield ran the decorated transaction bare on one ``client.transaction()``, so
one read-time ``Aborted`` on the hot job document escaped as a raw SDK error
and the redispatch a fresh transaction would have landed was lost with the
attempt. These tests pin the enrolled behavior: replayable contention
(including expired-chain retirements) replays on a fresh transaction, the
attempt cap surfaces as the typed ``FirestoreContentionExhausted``, an
ambient deadline scope bounds the chain, and a non-contention failure still
propagates unwrapped. The contention, expiry and deadline tests fail against
the bare-transactional parent; the remaining tests guard semantics that must
not move with the enrollment.
"""

from __future__ import annotations

from typing import Any

from database import conversation_finalization_jobs as jobs
from database.firestore_transaction_retry import FirestoreContentionExhausted, transaction_retry_deadline_scope

from tests.unit.sync_revision_defer_budget_grid_harness import (
    ADVANCED_REVISION,
    CALL_EPOCH,
    CALL_GENERATION,
    EXPECTED_REVISION,
    JOB_PATH,
    PROGRAMS,
    PROJ_SHARD,
    SYNC_DEFER_QUIET_DEFAULT,
    _CellPatch,
    build_store,
    decode_job,
    run_defer_cell,
)

OWNER_JOB = 'mp01n'
OWNER_CONV = 'pucjm'


def _owner_store(**kwargs: Any) -> Any:
    return build_store(OWNER_JOB, OWNER_CONV, **kwargs)


def _yield_under(
    store: Any,
    *,
    max_attempts: int = 5,
    deadline: float | None = None,
    clock: bool = False,
    per_attempt: float = 1.0,
    ambient: Any = None,
) -> tuple[Any, BaseException | None, _CellPatch]:
    """Run one yield call through the patched boundary; return (result, raised, patch)."""
    patch = _CellPatch(store)
    patch.max_attempts = max_attempts
    if deadline is not None:
        patch.deadline = deadline
        patch.clock = {'now': 0.0}
        patch.per_attempt = per_attempt
    elif clock:
        patch.clock = {'now': 0.0}
        patch.per_attempt = per_attempt

    def call():
        return jobs.defer_sync_revision_fence(
            'grid-sync-job', CALL_GENERATION, CALL_EPOCH, EXPECTED_REVISION, firestore_client=store
        )

    raised = None
    result = None
    if ambient is not None:
        with ambient:
            with patch:
                try:
                    result = call()
                except Exception as error:
                    raised = error
    else:
        with patch:
            try:
                result = call()
            except Exception as error:
                raised = error
    return result, raised, patch


def test_single_abort_replays_on_a_fresh_transaction_and_lands_the_redispatch():
    store = _owner_store()
    store.faults = list(PROGRAMS['ab1'])
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is True
    assert len(store.transactions) == 2
    assert patch.sleeps == [0.15]
    job = store.documents[JOB_PATH]
    assert job['status'] == 'queued'
    assert job['sync_revision_redispatch_count'] == 1
    assert job['worker_claim_count'] == 0


def test_abort_chain_recovers_within_the_default_cap():
    store = _owner_store()
    store.faults = list(PROGRAMS['ab4'])
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is True
    assert patch.sleeps == [0.15, 0.3, 0.6, 1.2]
    assert len(store.transactions) == 5
    assert store.documents[JOB_PATH]['status'] == 'queued'


def test_attempt_cap_exhausts_as_the_typed_error_and_preserves_the_lease():
    store = _owner_store()
    store.faults = list(PROGRAMS['ex5'])
    before = dict(store.documents[JOB_PATH])
    result, raised, patch = _yield_under(store)
    assert result is None
    assert isinstance(raised, FirestoreContentionExhausted)
    assert raised.reason == 'attempts_exhausted'
    assert patch.sleeps == [0.15, 0.3, 0.6, 1.2]
    assert len(store.transactions) == 5
    assert store.writes == 0
    assert store.documents[JOB_PATH] == before


def test_non_contention_failure_is_never_retried():
    store = _owner_store()
    store.faults = list(PROGRAMS['rte1'])
    result, raised, patch = _yield_under(store)
    assert result is None
    assert type(raised).__name__ == 'RuntimeError'
    assert not isinstance(raised, FirestoreContentionExhausted)
    assert patch.sleeps == []
    assert len(store.transactions) == 1
    assert store.writes == 0


def test_plain_invalid_argument_is_not_contention():
    store = _owner_store()
    store.faults = list(PROGRAMS['inv1'])
    result, raised, patch = _yield_under(store)
    assert result is None
    assert type(raised).__name__ == 'InvalidArgument'
    assert patch.sleeps == []
    assert len(store.transactions) == 1


def test_expired_chain_replays_on_a_fresh_transaction():
    store = _owner_store()
    store.faults = list(PROGRAMS['exp1'])
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is True
    assert patch.sleeps == [0.15]
    assert len(store.transactions) == 2
    assert store.documents[JOB_PATH]['status'] == 'queued'


def test_expired_chain_ceiling_without_a_deadline():
    store = _owner_store()
    store.faults = list(PROGRAMS['exp3'])
    before = dict(store.documents[JOB_PATH])
    result, raised, patch = _yield_under(store)
    assert result is None
    assert isinstance(raised, FirestoreContentionExhausted)
    assert raised.reason == 'attempts_exhausted'
    assert patch.sleeps == [0.15, 0.3]
    assert len(store.transactions) == 3
    assert store.writes == 0
    assert store.documents[JOB_PATH] == before


def test_expired_then_aborted_chain_recovers():
    store = _owner_store()
    store.faults = list(PROGRAMS['eab'])
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is True
    assert len(store.transactions) == 3
    assert store.documents[JOB_PATH]['status'] == 'queued'


def test_ambient_deadline_scope_bounds_the_yield():
    store = _owner_store()
    store.faults = list(PROGRAMS['ab8'])
    result, raised, patch = _yield_under(
        store, clock=True, per_attempt=2.0, ambient=transaction_retry_deadline_scope(1.0)
    )
    assert result is None
    assert isinstance(raised, FirestoreContentionExhausted)
    assert raised.reason == 'deadline_exhausted'
    assert patch.sleeps == []
    assert len(store.transactions) == 1
    assert store.writes == 0


def test_non_owner_yield_stays_a_noop_under_contention():
    store = build_store('gp01n', OWNER_CONV)
    store.faults = list(PROGRAMS['ab1'])
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is False
    assert len(store.transactions) == 2
    assert store.writes == 0
    assert store.documents[JOB_PATH]['status'] == 'leased'


def test_cap_blocked_row_terminates_without_a_write():
    store = build_store('mp33n', OWNER_CONV)
    result, raised, patch = _yield_under(store)
    assert raised is None
    assert result is False
    assert patch.sleeps == []
    assert store.writes == 0
    assert store.documents[JOB_PATH]['sync_revision_redispatch_count'] == 3


def test_recovered_write_matches_the_documented_shape():
    cell = run_defer_cell(OWNER_JOB, OWNER_CONV, 'clean', exact=True)
    assert cell['result'] is True
    assert cell['writes'] == 2
    assert cell['job_after']['status'] == 'queued'
    assert cell['job_after']['sync_revision_redispatch_count'] == 1
    assert cell['job_after']['sync_revision_observed'] == ADVANCED_REVISION
    assert cell['job_after']['reconcile_after_at'] == f'now+{SYNC_DEFER_QUIET_DEFAULT}s'
    assert cell['job_after']['sync_revision_not_before'] == f'now+{SYNC_DEFER_QUIET_DEFAULT}s'
    assert cell['job_after']['dispatch_requested_at'] == 'now-300s'
    assert cell['job_after']['sync_revision_wait_started_at'] == 'now'
    assert cell['job_after']['last_failure_code'] == 'sync_revision_advanced'
    assert cell['job_after']['sync_revision_waiting'] is True
    assert cell['job_after']['worker_claim_count'] == 0
    assert cell['proj'] == {'generation': 'terminal-outcomes-v1', 'shard': PROJ_SHARD, 'leased': -1, 'queued': 1}
    assert cell['conv']['sync_content_revision'] == ADVANCED_REVISION


def test_claim_decrement_is_conditional_on_the_counts_attempt_flag():
    flagged = run_defer_cell('mp011p', OWNER_CONV, 'clean')
    assert flagged['result'] is True
    assert flagged['job']['claim'] == 0
    unflagged = run_defer_cell('mp0f1p', OWNER_CONV, 'clean')
    assert unflagged['result'] is True
    assert unflagged['job']['claim'] == 1
    assert 'lease_counts_worker_attempt' not in decode_job('mp0f1p')
    zero = run_defer_cell('mp0z1p', OWNER_CONV, 'clean')
    assert zero['result'] is True
    assert zero['job']['claim'] == 0


def test_prior_wait_start_is_preserved_by_the_redispatch():
    kept = run_defer_cell('mp01p', OWNER_CONV, 'clean')
    assert kept['result'] is True
    assert kept['job']['wait_started'] == 'now-7200s'
    fresh = run_defer_cell('mp01n', OWNER_CONV, 'clean')
    assert fresh['result'] is True
    assert fresh['job']['wait_started'] == 'now'


def test_projection_tuple_gates_the_shard_write():
    absent = run_defer_cell(OWNER_JOB, OWNER_CONV, 'clean', projection='none')
    assert absent['result'] is True
    assert absent['writes'] == 1
    assert absent['proj'] is None
    stale_generation = run_defer_cell(OWNER_JOB, OWNER_CONV, 'clean', projection='badgen')
    assert stale_generation['writes'] == 1
    out_of_range = run_defer_cell(OWNER_JOB, OWNER_CONV, 'clean', projection='badshard')
    assert out_of_range['writes'] == 1
    incremented = run_defer_cell(OWNER_JOB, OWNER_CONV, 'clean', projection_seed='leased5')
    assert incremented['result'] is True
    assert incremented['proj']['leased'] == 4
    assert incremented['proj']['queued'] == 1
