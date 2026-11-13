"""Generated grid: identity gates x fault programs. Cross-verified cell by cell at emit time.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

Each test re-drives its cell through the real boundary
(``run_defer_cell``) and compares the full observable freeze against the
literal the emit-time cross-verify produced; the independent model walk and
the emitter live outside the tree. Do not edit frozen literals by hand.
"""

from tests.unit.sync_revision_defer_budget_grid_harness import run_defer_cell


def test_x_mp0nn_pucjm_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'clean') == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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


def test_x_mp01n_pucjm_clean() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'clean') == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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


def test_x_mp03n_pucjm_clean() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'clean') == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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


def test_x_mp0fn_pucjm_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'clean') == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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


def test_x_mp0zn_pucjm_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'clean') == {
        'result': True,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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


def test_x_mp0nn_pucjm_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab1') == {
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


def test_x_mp01n_pucjm_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1') == {
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


def test_x_mp03n_pucjm_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab1') == {
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


def test_x_mp0fn_pucjm_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab1') == {
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


def test_x_mp0zn_pucjm_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab1') == {
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


def test_x_mp0nn_pucjm_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab2') == {
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


def test_x_mp01n_pucjm_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2') == {
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


def test_x_mp03n_pucjm_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab2') == {
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


def test_x_mp0fn_pucjm_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab2') == {
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


def test_x_mp0zn_pucjm_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab2') == {
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


def test_x_mp0nn_pucjm_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ex5') == {
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


def test_x_mp01n_pucjm_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ex5') == {
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


def test_x_mp03n_pucjm_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ex5') == {
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


def test_x_mp0fn_pucjm_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ex5') == {
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


def test_x_mp0zn_pucjm_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ex5') == {
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


def test_x_mp0nn_pecjm_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecjm_clean() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_x_mp03n_pecjm_clean() -> None:
    assert run_defer_cell('mp03n', 'pecjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecjm_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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


def test_x_mp0zn_pecjm_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecjm_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecjm_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab1') == {
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


def test_x_mp03n_pecjm_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecjm_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecjm', 'ab1') == {
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


def test_x_mp0zn_pecjm_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecjm_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecjm_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ab2') == {
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


def test_x_mp03n_pecjm_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecjm_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecjm', 'ab2') == {
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


def test_x_mp0zn_pecjm_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecjm_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecjm', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecjm_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecjm', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pecjm_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecjm', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecjm_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecjm', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pecjm_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecjm', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcjm_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcjm_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcjm_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcjm_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcjm_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcjm_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcjm_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcjm', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcjm_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcjm_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcjm', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcjm_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcjm_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcjm_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcjm', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcjm_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcjm_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcjm', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcjm_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcjm_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcjm', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcjm_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcjm', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcjm_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcjm', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcjm_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcjm', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcjm_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcjm', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncjm_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncjm_clean() -> None:
    assert run_defer_cell('mp01n', 'pncjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncjm_clean() -> None:
    assert run_defer_cell('mp03n', 'pncjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncjm_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncjm_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncjm', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncjm_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncjm_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncjm', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncjm_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncjm_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncjm', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncjm_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncjm', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncjm_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncjm_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncjm', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncjm_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncjm_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncjm', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncjm_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncjm', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncjm_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncjm', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncjm_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncjm', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncjm_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncjm', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncjm_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncjm', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncjm_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncjm', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pucjx_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucjx_clean() -> None:
    assert run_defer_cell('mp01n', 'pucjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucjx_clean() -> None:
    assert run_defer_cell('mp03n', 'pucjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucjx_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucjx_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucjx_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucjx_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucjx', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucjx_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucjx_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucjx', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucjx_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucjx_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucjx_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucjx', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucjx_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucjx_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucjx', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucjx_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucjx_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucjx', 'ex5') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucjx_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucjx', 'ex5') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucjx_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucjx', 'ex5') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucjx_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucjx', 'ex5') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucjx_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucjx', 'ex5') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecjx_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecjx_clean() -> None:
    assert run_defer_cell('mp01n', 'pecjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecjx_clean() -> None:
    assert run_defer_cell('mp03n', 'pecjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecjx_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecjx_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecjx_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecjx_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecjx', 'ab1') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecjx_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecjx_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecjx', 'ab1') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecjx_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecjx_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecjx_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecjx', 'ab2') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecjx_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecjx_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecjx', 'ab2') == {
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
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecjx_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecjx_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecjx', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecjx_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecjx', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecjx_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecjx', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecjx_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecjx', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecjx_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecjx', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcjx_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcjx_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcjx_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcjx_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcjx_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcjx_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcjx_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcjx', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcjx_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcjx_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcjx', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcjx_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcjx_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcjx_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcjx', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcjx_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcjx_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcjx', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcjx_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcjx_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcjx', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcjx_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcjx', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcjx_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcjx', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcjx_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcjx', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcjx_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcjx', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncjx_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncjx_clean() -> None:
    assert run_defer_cell('mp01n', 'pncjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncjx_clean() -> None:
    assert run_defer_cell('mp03n', 'pncjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncjx_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncjx_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncjx', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncjx_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncjx_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncjx', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncjx_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncjx_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncjx', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncjx_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncjx', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncjx_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncjx_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncjx', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncjx_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncjx_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncjx', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncjx_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncjx', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncjx_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncjx', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncjx_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncjx', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncjx_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncjx', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncjx_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncjx', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncjx_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncjx', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucja_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucja_clean() -> None:
    assert run_defer_cell('mp01n', 'pucja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucja_clean() -> None:
    assert run_defer_cell('mp03n', 'pucja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucja_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucja_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucja_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucja_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucja', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucja_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucja_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucja', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucja_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucja_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucja_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucja', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucja_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucja_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucja', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucja_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucja_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucja', 'ex5') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucja_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucja', 'ex5') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucja_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucja', 'ex5') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucja_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucja', 'ex5') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucja_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucja', 'ex5') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecja_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecja_clean() -> None:
    assert run_defer_cell('mp01n', 'pecja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecja_clean() -> None:
    assert run_defer_cell('mp03n', 'pecja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecja_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecja_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecja_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecja_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecja', 'ab1') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecja_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecja_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecja', 'ab1') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecja_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecja_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecja_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecja', 'ab2') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecja_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecja_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecja', 'ab2') == {
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
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecja_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecja_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecja', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecja_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecja', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecja_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecja', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecja_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecja', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecja_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecja', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcja_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcja_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcja_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcja_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcja_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcja_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcja_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcja', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcja_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcja_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcja', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcja_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcja_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcja_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcja', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcja_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcja_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcja', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcja_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcja_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcja', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcja_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcja', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcja_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcja', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcja_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcja', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcja_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcja', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncja_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncja_clean() -> None:
    assert run_defer_cell('mp01n', 'pncja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncja_clean() -> None:
    assert run_defer_cell('mp03n', 'pncja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncja_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncja_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncja', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncja_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncja_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncja', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncja_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncja_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncja', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncja_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncja', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncja_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncja_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncja', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncja_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncja_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncja', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncja_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncja', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncja_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncja', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncja_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncja', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncja_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncja', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncja_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncja', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncja_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncja', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucom_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pucom_clean() -> None:
    assert run_defer_cell('mp01n', 'pucom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pucom_clean() -> None:
    assert run_defer_cell('mp03n', 'pucom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pucom_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pucom_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pucom_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pucom_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucom', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pucom_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pucom_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucom', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pucom_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pucom_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pucom_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucom', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pucom_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pucom_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucom', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pucom_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pucom_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucom', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pucom_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucom', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pucom_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucom', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pucom_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucom', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pucom_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucom', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecom_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecom_clean() -> None:
    assert run_defer_cell('mp01n', 'pecom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pecom_clean() -> None:
    assert run_defer_cell('mp03n', 'pecom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecom_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pecom_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecom_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecom_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecom', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pecom_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecom_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecom', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pecom_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecom_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecom_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecom', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pecom_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecom_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecom', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pecom_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pecom_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecom', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pecom_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecom', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pecom_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecom', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pecom_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecom', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pecom_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecom', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcom_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcom_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcom_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcom_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcom_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcom_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcom_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcom', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcom_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcom_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcom', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcom_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcom_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcom_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcom', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcom_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcom_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcom', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcom_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pbcom_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcom', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pbcom_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcom', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pbcom_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcom', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pbcom_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcom', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pbcom_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcom', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncom_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncom_clean() -> None:
    assert run_defer_cell('mp01n', 'pncom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncom_clean() -> None:
    assert run_defer_cell('mp03n', 'pncom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncom_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncom_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncom', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncom_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncom_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncom', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncom_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncom_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncom', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncom_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncom', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncom_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncom_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncom', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncom_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncom_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncom', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncom_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncom', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pncom_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncom', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp01n_pncom_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncom', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp03n_pncom_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncom', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0fn_pncom_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncom', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0zn_pncom_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncom', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 5,
        },
    }


def test_x_mp0nn_pucox_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucox_clean() -> None:
    assert run_defer_cell('mp01n', 'pucox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucox_clean() -> None:
    assert run_defer_cell('mp03n', 'pucox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucox_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucox_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucox_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucox_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucox', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucox_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucox_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucox', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucox_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucox_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucox_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucox', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucox_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucox_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucox', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucox_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucox_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucox', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pucox_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucox', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pucox_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucox', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pucox_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucox', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pucox_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucox', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecox_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecox_clean() -> None:
    assert run_defer_cell('mp01n', 'pecox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecox_clean() -> None:
    assert run_defer_cell('mp03n', 'pecox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecox_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecox_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecox_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecox_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecox', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecox_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecox_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecox', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecox_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecox_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecox_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecox', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecox_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecox_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecox', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecox_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pecox_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecox', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pecox_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecox', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pecox_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecox', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pecox_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecox', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pecox_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecox', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcox_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcox_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcox_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcox_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcox_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcox_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcox_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcox', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcox_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcox_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcox', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcox_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcox_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcox_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcox', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcox_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcox_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcox', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcox_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pbcox_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcox', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pbcox_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcox', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pbcox_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcox', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pbcox_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcox', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pbcox_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcox', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncox_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncox_clean() -> None:
    assert run_defer_cell('mp01n', 'pncox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncox_clean() -> None:
    assert run_defer_cell('mp03n', 'pncox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncox_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncox_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncox', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncox_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncox_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncox', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncox_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncox_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncox', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncox_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncox', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncox_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncox_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncox', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncox_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncox_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncox', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncox_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncox', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pncox_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncox', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp01n_pncox_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncox', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp03n_pncox_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncox', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0fn_pncox_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncox', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0zn_pncox_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncox', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': 6,
        },
    }


def test_x_mp0nn_pucoa_clean() -> None:
    assert run_defer_cell('mp0nn', 'pucoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucoa_clean() -> None:
    assert run_defer_cell('mp01n', 'pucoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucoa_clean() -> None:
    assert run_defer_cell('mp03n', 'pucoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucoa_clean() -> None:
    assert run_defer_cell('mp0fn', 'pucoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucoa_clean() -> None:
    assert run_defer_cell('mp0zn', 'pucoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucoa_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pucoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucoa_ab1() -> None:
    assert run_defer_cell('mp01n', 'pucoa', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucoa_ab1() -> None:
    assert run_defer_cell('mp03n', 'pucoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucoa_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pucoa', 'ab1') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucoa_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pucoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucoa_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pucoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucoa_ab2() -> None:
    assert run_defer_cell('mp01n', 'pucoa', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucoa_ab2() -> None:
    assert run_defer_cell('mp03n', 'pucoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucoa_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pucoa', 'ab2') == {
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
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucoa_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pucoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pucoa_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pucoa', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pucoa_ex5() -> None:
    assert run_defer_cell('mp01n', 'pucoa', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pucoa_ex5() -> None:
    assert run_defer_cell('mp03n', 'pucoa', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pucoa_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pucoa', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pucoa_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pucoa', 'ex5') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecoa_clean() -> None:
    assert run_defer_cell('mp0nn', 'pecoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecoa_clean() -> None:
    assert run_defer_cell('mp01n', 'pecoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecoa_clean() -> None:
    assert run_defer_cell('mp03n', 'pecoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecoa_clean() -> None:
    assert run_defer_cell('mp0fn', 'pecoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecoa_clean() -> None:
    assert run_defer_cell('mp0zn', 'pecoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecoa_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pecoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecoa_ab1() -> None:
    assert run_defer_cell('mp01n', 'pecoa', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecoa_ab1() -> None:
    assert run_defer_cell('mp03n', 'pecoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecoa_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pecoa', 'ab1') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecoa_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pecoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecoa_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pecoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecoa_ab2() -> None:
    assert run_defer_cell('mp01n', 'pecoa', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecoa_ab2() -> None:
    assert run_defer_cell('mp03n', 'pecoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecoa_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pecoa', 'ab2') == {
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
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecoa_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pecoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pecoa_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pecoa', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pecoa_ex5() -> None:
    assert run_defer_cell('mp01n', 'pecoa', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pecoa_ex5() -> None:
    assert run_defer_cell('mp03n', 'pecoa', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pecoa_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pecoa', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pecoa_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pecoa', 'ex5') == {
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
            'sync_content_revision': 18,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcoa_clean() -> None:
    assert run_defer_cell('mp0nn', 'pbcoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcoa_clean() -> None:
    assert run_defer_cell('mp01n', 'pbcoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcoa_clean() -> None:
    assert run_defer_cell('mp03n', 'pbcoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcoa_clean() -> None:
    assert run_defer_cell('mp0fn', 'pbcoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcoa_clean() -> None:
    assert run_defer_cell('mp0zn', 'pbcoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcoa_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pbcoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcoa_ab1() -> None:
    assert run_defer_cell('mp01n', 'pbcoa', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcoa_ab1() -> None:
    assert run_defer_cell('mp03n', 'pbcoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcoa_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pbcoa', 'ab1') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcoa_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pbcoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcoa_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pbcoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcoa_ab2() -> None:
    assert run_defer_cell('mp01n', 'pbcoa', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcoa_ab2() -> None:
    assert run_defer_cell('mp03n', 'pbcoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcoa_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pbcoa', 'ab2') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcoa_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pbcoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pbcoa_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pbcoa', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pbcoa_ex5() -> None:
    assert run_defer_cell('mp01n', 'pbcoa', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pbcoa_ex5() -> None:
    assert run_defer_cell('mp03n', 'pbcoa', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pbcoa_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pbcoa', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pbcoa_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pbcoa', 'ex5') == {
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
            'sync_content_revision': 17,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncoa_clean() -> None:
    assert run_defer_cell('mp0nn', 'pncoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncoa_clean() -> None:
    assert run_defer_cell('mp01n', 'pncoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncoa_clean() -> None:
    assert run_defer_cell('mp03n', 'pncoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncoa_clean() -> None:
    assert run_defer_cell('mp0fn', 'pncoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncoa_clean() -> None:
    assert run_defer_cell('mp0zn', 'pncoa', 'clean') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 1,
        'sleeps': [],
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncoa_ab1() -> None:
    assert run_defer_cell('mp0nn', 'pncoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncoa_ab1() -> None:
    assert run_defer_cell('mp01n', 'pncoa', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncoa_ab1() -> None:
    assert run_defer_cell('mp03n', 'pncoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncoa_ab1() -> None:
    assert run_defer_cell('mp0fn', 'pncoa', 'ab1') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncoa_ab1() -> None:
    assert run_defer_cell('mp0zn', 'pncoa', 'ab1') == {
        'result': False,
        'raised': None,
        'reason': None,
        'transactions': 2,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncoa_ab2() -> None:
    assert run_defer_cell('mp0nn', 'pncoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncoa_ab2() -> None:
    assert run_defer_cell('mp01n', 'pncoa', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncoa_ab2() -> None:
    assert run_defer_cell('mp03n', 'pncoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncoa_ab2() -> None:
    assert run_defer_cell('mp0fn', 'pncoa', 'ab2') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncoa_ab2() -> None:
    assert run_defer_cell('mp0zn', 'pncoa', 'ab2') == {
        'result': False,
        'raised': None,
        'reason': None,
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0nn_pncoa_ex5() -> None:
    assert run_defer_cell('mp0nn', 'pncoa', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp01n_pncoa_ex5() -> None:
    assert run_defer_cell('mp01n', 'pncoa', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp03n_pncoa_ex5() -> None:
    assert run_defer_cell('mp03n', 'pncoa', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0fn_pncoa_ex5() -> None:
    assert run_defer_cell('mp0fn', 'pncoa', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }


def test_x_mp0zn_pncoa_ex5() -> None:
    assert run_defer_cell('mp0zn', 'pncoa', 'ex5') == {
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
            'sync_content_revision': None,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'other-job',
            'finalization_revision': None,
        },
    }
