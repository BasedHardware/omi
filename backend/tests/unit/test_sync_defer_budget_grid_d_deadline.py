"""Generated grid: deadline walks: reserve gate, sleep refusal. Cross-verified cell by cell at emit time.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

Each test re-drives its cell through the real boundary
(``run_defer_cell``) and compares the full observable freeze against the
literal the emit-time cross-verify produced; the independent model walk and
the emitter live outside the tree. Do not edit frozen literals by hand.
"""

from tests.unit.sync_revision_defer_budget_grid_harness import run_defer_cell


def test_d_pucjm_ab1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab3_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab3_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab3_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab3', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_ab4_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_ab4_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_ab4_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab4', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp1_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp1', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 0,
            'reconcile_after': 'now+30s',
            'not_before': 'now+30s',
            'dispatch_requested': 'now-300s',
            'wait_started': 'now',
            'waiting': True,
            'failure_code': 'sync_revision_advanced',
            'observed': 19,
        },
        'proj': {'generation': 'terminal-outcomes-v1', 'shard': 3, 'leased': -1, 'queued': 1},
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_exp2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_exp2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_exp2_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'exp2', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_3_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=3, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_05_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_05_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_05_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.05, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_3_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_3_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_0_3_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=0.3, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_1_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_1_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_1_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=1.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_2_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_2_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_2_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=2.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_5_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_5_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_5_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=5.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_60_0_0_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=0.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_60_0_1_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=1.0) == {
        'result': None,
        'raised': 'RuntimeError',
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pucjm_aaf_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_qucjm_aaf_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'qucjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'queued',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_d_pecjm_aaf_5_60_0_45_0() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'aaf', max_attempts=5, deadline=60.0, per_attempt=45.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }
