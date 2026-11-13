"""Generated grid: expired-chain semantics: ceiling, deadline interplay. Cross-verified cell by cell at emit time.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

Each test re-drives its cell through the real boundary
(``run_defer_cell``) and compares the full observable freeze against the
literal the emit-time cross-verify produced; the independent model walk and
the emitter live outside the tree. Do not edit frozen literals by hand.
"""

from tests.unit.sync_revision_defer_budget_grid_harness import run_defer_cell


def test_e_mp0nn_exp1_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp1_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3) == {
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


def test_e_mp03n_exp1_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp1_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp1_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=3) == {
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


def test_e_mp0nn_exp1_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp1_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5) == {
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


def test_e_mp03n_exp1_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp1_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp1_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=5) == {
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


def test_e_mp0nn_exp1_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp1_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_exp1_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp1_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp1_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0nn_exp1_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp1_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_exp1_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp1_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp1_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_exp1_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp1_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp1_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp1_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp1_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp1_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp1_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp1_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp1_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp1_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp2_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp2_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3) == {
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


def test_e_mp03n_exp2_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp2_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp2_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=3) == {
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


def test_e_mp0nn_exp2_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp2_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5) == {
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


def test_e_mp03n_exp2_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp2_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp2_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=5) == {
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


def test_e_mp0nn_exp2_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp2_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_exp2_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp2_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp2_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0nn_exp2_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp2_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_exp2_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp2_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp2_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_exp2_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp2_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp2_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp2_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp2_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp2_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp2_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp2_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp2_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp2_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp3_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp3_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=3) == {
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


def test_e_mp03n_exp3_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp3_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=3) == {
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


def test_e_mp0zn_exp3_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp3_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp3_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=5) == {
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


def test_e_mp03n_exp3_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp3_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=5) == {
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


def test_e_mp0zn_exp3_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp3_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp3_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_exp3_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp3_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0zn_exp3_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp3_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp3_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_exp3_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp3_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 4,
        'sleeps': [0.15, 0.3, 0.6],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp3_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_exp3_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp3_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp3_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp3_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp3_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp3_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp3_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp3_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp3_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp3_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp4_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp4_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=3) == {
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


def test_e_mp03n_exp4_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp4_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=3) == {
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


def test_e_mp0zn_exp4_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp4_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp4_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=5) == {
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


def test_e_mp03n_exp4_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp4_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=5) == {
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


def test_e_mp0zn_exp4_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp4_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp4_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_exp4_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp4_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0zn_exp4_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp4_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_exp4_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_exp4_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_exp4_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_exp4_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_exp4_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp4_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp4_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp4_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp4_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp4_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp4', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp4_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp4', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp4_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp4', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp4_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp4', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp4_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp4', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=3) == {
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


def test_e_mp03n_exp5_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=3) == {
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


def test_e_mp0zn_exp5_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=3) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=5) == {
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


def test_e_mp03n_exp5_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=5) == {
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


def test_e_mp0zn_exp5_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=5) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_exp5_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0zn_exp5_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=3, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=5, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=5, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_e_mp03n_exp5_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=5, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=5, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_e_mp0zn_exp5_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=5, deadline=60.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 5,
        'sleeps': [0.15, 0.3, 0.6, 1.2],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp5_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp5_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_exp5_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp5', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_exp5_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp5', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_exp5_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp5', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_exp5_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp5', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_exp5_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp5', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_aec_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_aec_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=3) == {
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


def test_e_mp03n_aec_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_aec_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_aec_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=3) == {
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


def test_e_mp0nn_aec_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_aec_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=5) == {
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


def test_e_mp03n_aec_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_aec_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_aec_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=5) == {
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


def test_e_mp0nn_aec_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_aec_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_aec_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_aec_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_aec_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0nn_aec_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_aec_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_aec_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_aec_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_aec_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_aec_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_aec_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_aec_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_aec_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_aec_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_aec_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_aec_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_aec_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_aec_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_aec_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_eab_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_eab_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=3) == {
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


def test_e_mp03n_eab_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_eab_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_eab_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=3) == {
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


def test_e_mp0nn_eab_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_eab_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=5) == {
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


def test_e_mp03n_eab_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_eab_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_eab_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=5) == {
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


def test_e_mp0nn_eab_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_eab_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_eab_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_eab_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_eab_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0nn_eab_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_eab_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_eab_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_eab_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 3,
        'sleeps': [0.15, 0.3],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_eab_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_eab_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_eab_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_eab_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_eab_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_eab_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_eab_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_eab_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_eab_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_eab_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_eab_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_expa1_None_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_expa1_None_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=3) == {
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


def test_e_mp03n_expa1_None_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_expa1_None_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=3) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_expa1_None_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=3) == {
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


def test_e_mp0nn_expa1_None_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_expa1_None_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=5) == {
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


def test_e_mp03n_expa1_None_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_expa1_None_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=5) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_expa1_None_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=5) == {
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


def test_e_mp0nn_expa1_60_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_expa1_60_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=3, deadline=60.0) == {
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


def test_e_mp03n_expa1_60_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_expa1_60_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=3, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_expa1_60_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=3, deadline=60.0) == {
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


def test_e_mp0nn_expa1_60_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 'absent',
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


def test_e_mp01n_expa1_60_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=5, deadline=60.0) == {
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


def test_e_mp03n_expa1_60_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 2,
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


def test_e_mp0fn_expa1_60_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=5, deadline=60.0) == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 2,
        'sleeps': [0.15],
        'writes': 2,
        'job': {
            'status': 'queued',
            'redispatches': 1,
            'claim': 1,
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


def test_e_mp0zn_expa1_60_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=5, deadline=60.0) == {
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


def test_e_mp0nn_expa1_5_0_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_expa1_5_0_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_expa1_5_0_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_expa1_5_0_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_expa1_5_0_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=3, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0nn_expa1_5_0_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 'absent',
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp01n_expa1_5_0_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp03n_expa1_5_0_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 3,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0fn_expa1_5_0_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_e_mp0zn_expa1_5_0_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=5, deadline=5.0) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'deadline_exhausted',
        'transactions': 1,
        'sleeps': [0.15],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 0,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
