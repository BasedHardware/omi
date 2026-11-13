"""Generated grid: budget fault programs x attempt caps. Cross-verified cell by cell at emit time.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

Each test re-drives its cell through the real boundary
(``run_defer_cell``) and compares the full observable freeze against the
literal the emit-time cross-verify produced; the independent model walk and
the emitter live outside the tree. Do not edit frozen literals by hand.
"""

from tests.unit.sync_revision_defer_budget_grid_harness import run_defer_cell


def test_c_mp0nn_clean_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'clean', max_attempts=2) == {
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


def test_c_mp01n_clean_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'clean', max_attempts=2) == {
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


def test_c_mp03n_clean_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'clean', max_attempts=2) == {
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


def test_c_mp0fn_clean_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'clean', max_attempts=2) == {
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


def test_c_mp0zn_clean_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'clean', max_attempts=2) == {
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


def test_c_mp0nn_clean_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'clean', max_attempts=3) == {
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


def test_c_mp01n_clean_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'clean', max_attempts=3) == {
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


def test_c_mp03n_clean_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'clean', max_attempts=3) == {
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


def test_c_mp0fn_clean_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'clean', max_attempts=3) == {
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


def test_c_mp0zn_clean_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'clean', max_attempts=3) == {
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


def test_c_mp0nn_clean_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'clean', max_attempts=5) == {
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


def test_c_mp01n_clean_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'clean', max_attempts=5) == {
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


def test_c_mp03n_clean_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'clean', max_attempts=5) == {
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


def test_c_mp0fn_clean_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'clean', max_attempts=5) == {
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


def test_c_mp0zn_clean_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'clean', max_attempts=5) == {
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


def test_c_mp0nn_clean_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'clean', max_attempts=6) == {
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


def test_c_mp01n_clean_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'clean', max_attempts=6) == {
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


def test_c_mp03n_clean_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'clean', max_attempts=6) == {
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


def test_c_mp0fn_clean_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'clean', max_attempts=6) == {
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


def test_c_mp0zn_clean_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'clean', max_attempts=6) == {
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


def test_c_mp0nn_ab1_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab1', max_attempts=2) == {
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


def test_c_mp01n_ab1_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=2) == {
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


def test_c_mp03n_ab1_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab1', max_attempts=2) == {
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


def test_c_mp0fn_ab1_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab1', max_attempts=2) == {
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


def test_c_mp0zn_ab1_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab1', max_attempts=2) == {
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


def test_c_mp0nn_ab1_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab1', max_attempts=3) == {
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


def test_c_mp01n_ab1_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=3) == {
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


def test_c_mp03n_ab1_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab1', max_attempts=3) == {
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


def test_c_mp0fn_ab1_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab1', max_attempts=3) == {
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


def test_c_mp0zn_ab1_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab1', max_attempts=3) == {
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


def test_c_mp0nn_ab1_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab1', max_attempts=5) == {
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


def test_c_mp01n_ab1_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=5) == {
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


def test_c_mp03n_ab1_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab1', max_attempts=5) == {
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


def test_c_mp0fn_ab1_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab1', max_attempts=5) == {
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


def test_c_mp0zn_ab1_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab1', max_attempts=5) == {
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


def test_c_mp0nn_ab1_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab1', max_attempts=6) == {
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


def test_c_mp01n_ab1_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab1', max_attempts=6) == {
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


def test_c_mp03n_ab1_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab1', max_attempts=6) == {
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


def test_c_mp0fn_ab1_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab1', max_attempts=6) == {
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


def test_c_mp0zn_ab1_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab1', max_attempts=6) == {
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


def test_c_mp0nn_ab2_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_ab2_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_ab2_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_ab2_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_ab2_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_ab2_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab2', max_attempts=3) == {
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


def test_c_mp01n_ab2_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=3) == {
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


def test_c_mp03n_ab2_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab2', max_attempts=3) == {
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


def test_c_mp0fn_ab2_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab2', max_attempts=3) == {
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


def test_c_mp0zn_ab2_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab2', max_attempts=3) == {
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


def test_c_mp0nn_ab2_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab2', max_attempts=5) == {
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


def test_c_mp01n_ab2_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=5) == {
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


def test_c_mp03n_ab2_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab2', max_attempts=5) == {
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


def test_c_mp0fn_ab2_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab2', max_attempts=5) == {
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


def test_c_mp0zn_ab2_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab2', max_attempts=5) == {
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


def test_c_mp0nn_ab2_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab2', max_attempts=6) == {
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


def test_c_mp01n_ab2_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab2', max_attempts=6) == {
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


def test_c_mp03n_ab2_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab2', max_attempts=6) == {
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


def test_c_mp0fn_ab2_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab2', max_attempts=6) == {
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


def test_c_mp0zn_ab2_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab2', max_attempts=6) == {
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


def test_c_mp0nn_ab3_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_ab3_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_ab3_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_ab3_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_ab3_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_ab3_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab3', max_attempts=3) == {
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


def test_c_mp01n_ab3_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=3) == {
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


def test_c_mp03n_ab3_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab3', max_attempts=3) == {
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


def test_c_mp0fn_ab3_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab3', max_attempts=3) == {
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


def test_c_mp0zn_ab3_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab3', max_attempts=3) == {
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


def test_c_mp0nn_ab3_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab3', max_attempts=5) == {
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


def test_c_mp01n_ab3_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=5) == {
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


def test_c_mp03n_ab3_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab3', max_attempts=5) == {
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


def test_c_mp0fn_ab3_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab3', max_attempts=5) == {
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


def test_c_mp0zn_ab3_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab3', max_attempts=5) == {
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


def test_c_mp0nn_ab3_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab3', max_attempts=6) == {
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


def test_c_mp01n_ab3_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab3', max_attempts=6) == {
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


def test_c_mp03n_ab3_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab3', max_attempts=6) == {
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


def test_c_mp0fn_ab3_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab3', max_attempts=6) == {
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


def test_c_mp0zn_ab3_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab3', max_attempts=6) == {
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


def test_c_mp0nn_ab4_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab4', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_ab4_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_ab4_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab4', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_ab4_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab4', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_ab4_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab4', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_ab4_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab4', max_attempts=3) == {
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


def test_c_mp01n_ab4_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=3) == {
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


def test_c_mp03n_ab4_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab4', max_attempts=3) == {
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


def test_c_mp0fn_ab4_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab4', max_attempts=3) == {
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


def test_c_mp0zn_ab4_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab4', max_attempts=3) == {
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


def test_c_mp0nn_ab4_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab4', max_attempts=5) == {
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


def test_c_mp01n_ab4_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=5) == {
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


def test_c_mp03n_ab4_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab4', max_attempts=5) == {
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


def test_c_mp0fn_ab4_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab4', max_attempts=5) == {
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


def test_c_mp0zn_ab4_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab4', max_attempts=5) == {
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


def test_c_mp0nn_ab4_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ab4', max_attempts=6) == {
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


def test_c_mp01n_ab4_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ab4', max_attempts=6) == {
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


def test_c_mp03n_ab4_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ab4', max_attempts=6) == {
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


def test_c_mp0fn_ab4_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ab4', max_attempts=6) == {
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


def test_c_mp0zn_ab4_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ab4', max_attempts=6) == {
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


def test_c_mp0nn_ex5_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ex5', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_ex5_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ex5', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_ex5_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ex5', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_ex5_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ex5', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_ex5_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ex5', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_ex5_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ex5', max_attempts=3) == {
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


def test_c_mp01n_ex5_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ex5', max_attempts=3) == {
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


def test_c_mp03n_ex5_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ex5', max_attempts=3) == {
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


def test_c_mp0fn_ex5_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ex5', max_attempts=3) == {
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


def test_c_mp0zn_ex5_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ex5', max_attempts=3) == {
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


def test_c_mp0nn_ex5_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ex5', max_attempts=5) == {
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


def test_c_mp01n_ex5_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ex5', max_attempts=5) == {
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


def test_c_mp03n_ex5_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ex5', max_attempts=5) == {
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


def test_c_mp0fn_ex5_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ex5', max_attempts=5) == {
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


def test_c_mp0zn_ex5_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ex5', max_attempts=5) == {
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


def test_c_mp0nn_ex5_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'ex5', max_attempts=6) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 6,
        'sleeps': [0.15, 0.3, 0.6, 1.2, 2.4],
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


def test_c_mp01n_ex5_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'ex5', max_attempts=6) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 6,
        'sleeps': [0.15, 0.3, 0.6, 1.2, 2.4],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_ex5_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'ex5', max_attempts=6) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 6,
        'sleeps': [0.15, 0.3, 0.6, 1.2, 2.4],
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


def test_c_mp0fn_ex5_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'ex5', max_attempts=6) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 6,
        'sleeps': [0.15, 0.3, 0.6, 1.2, 2.4],
        'writes': 0,
        'job': {
            'status': 'leased',
            'redispatches': 0,
            'claim': 1,
            'reconcile_after': 'absent',
            'not_before': 'absent',
            'dispatch_requested': 'absent',
            'wait_started': 'absent',
            'waiting': 'absent',
            'failure_code': 'absent',
            'observed': 'absent',
        },
        'proj': None,
        'conv': {
            'status': 'processing',
            'sync_content_revision': 19,
            'deleted': None,
            'discarded': None,
            'sync_merged_into': None,
            'finalization_job_id': 'grid-sync-job',
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_ex5_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'ex5', max_attempts=6) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
        'transactions': 6,
        'sleeps': [0.15, 0.3, 0.6, 1.2, 2.4],
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


def test_c_mp0nn_exp1_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=2) == {
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


def test_c_mp01n_exp1_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=2) == {
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


def test_c_mp03n_exp1_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=2) == {
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


def test_c_mp0fn_exp1_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=2) == {
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


def test_c_mp0zn_exp1_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=2) == {
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


def test_c_mp0nn_exp1_3() -> None:
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


def test_c_mp01n_exp1_3() -> None:
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


def test_c_mp03n_exp1_3() -> None:
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


def test_c_mp0fn_exp1_3() -> None:
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


def test_c_mp0zn_exp1_3() -> None:
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


def test_c_mp0nn_exp1_5() -> None:
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


def test_c_mp01n_exp1_5() -> None:
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


def test_c_mp03n_exp1_5() -> None:
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


def test_c_mp0fn_exp1_5() -> None:
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


def test_c_mp0zn_exp1_5() -> None:
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


def test_c_mp0nn_exp1_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp1', max_attempts=6) == {
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


def test_c_mp01n_exp1_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp1', max_attempts=6) == {
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


def test_c_mp03n_exp1_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp1', max_attempts=6) == {
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


def test_c_mp0fn_exp1_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp1', max_attempts=6) == {
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


def test_c_mp0zn_exp1_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp1', max_attempts=6) == {
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


def test_c_mp0nn_exp2_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_exp2_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_exp2_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_exp2_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_exp2_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_exp2_3() -> None:
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


def test_c_mp01n_exp2_3() -> None:
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


def test_c_mp03n_exp2_3() -> None:
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


def test_c_mp0fn_exp2_3() -> None:
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


def test_c_mp0zn_exp2_3() -> None:
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


def test_c_mp0nn_exp2_5() -> None:
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


def test_c_mp01n_exp2_5() -> None:
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


def test_c_mp03n_exp2_5() -> None:
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


def test_c_mp0fn_exp2_5() -> None:
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


def test_c_mp0zn_exp2_5() -> None:
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


def test_c_mp0nn_exp2_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp2', max_attempts=6) == {
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


def test_c_mp01n_exp2_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp2', max_attempts=6) == {
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


def test_c_mp03n_exp2_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp2', max_attempts=6) == {
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


def test_c_mp0fn_exp2_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp2', max_attempts=6) == {
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


def test_c_mp0zn_exp2_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp2', max_attempts=6) == {
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


def test_c_mp0nn_exp3_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_exp3_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_exp3_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_exp3_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_exp3_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_exp3_3() -> None:
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


def test_c_mp01n_exp3_3() -> None:
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


def test_c_mp03n_exp3_3() -> None:
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


def test_c_mp0fn_exp3_3() -> None:
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


def test_c_mp0zn_exp3_3() -> None:
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


def test_c_mp0nn_exp3_5() -> None:
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


def test_c_mp01n_exp3_5() -> None:
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


def test_c_mp03n_exp3_5() -> None:
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


def test_c_mp0fn_exp3_5() -> None:
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


def test_c_mp0zn_exp3_5() -> None:
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


def test_c_mp0nn_exp3_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'exp3', max_attempts=6) == {
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


def test_c_mp01n_exp3_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'exp3', max_attempts=6) == {
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


def test_c_mp03n_exp3_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'exp3', max_attempts=6) == {
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


def test_c_mp0fn_exp3_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'exp3', max_attempts=6) == {
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


def test_c_mp0zn_exp3_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'exp3', max_attempts=6) == {
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


def test_c_mp0nn_inv1_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'inv1', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_inv1_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'inv1', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_inv1_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'inv1', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_inv1_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'inv1', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_inv1_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'inv1', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_inv1_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'inv1', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_inv1_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'inv1', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_inv1_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'inv1', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_inv1_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'inv1', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_inv1_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'inv1', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_inv1_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'inv1', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_inv1_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'inv1', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_inv1_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'inv1', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_inv1_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'inv1', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_inv1_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'inv1', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_inv1_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'inv1', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_inv1_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'inv1', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_inv1_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'inv1', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_inv1_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'inv1', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_inv1_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'inv1', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_rte1_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'rte1', max_attempts=2) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_rte1_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'rte1', max_attempts=2) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_rte1_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'rte1', max_attempts=2) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_rte1_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'rte1', max_attempts=2) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_rte1_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'rte1', max_attempts=2) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_rte1_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'rte1', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_rte1_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'rte1', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_rte1_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'rte1', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_rte1_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'rte1', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_rte1_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'rte1', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_rte1_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'rte1', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_rte1_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'rte1', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_rte1_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'rte1', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_rte1_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'rte1', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_rte1_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'rte1', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_rte1_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'rte1', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_rte1_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'rte1', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_rte1_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'rte1', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_rte1_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'rte1', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_rte1_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'rte1', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aaf_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aaf', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aaf_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aaf_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aaf', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aaf_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aaf', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aaf_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aaf', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aaf_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aaf', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aaf_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=3) == {
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


def test_c_mp03n_aaf_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aaf', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aaf_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aaf', max_attempts=3) == {
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


def test_c_mp0zn_aaf_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aaf', max_attempts=3) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aaf_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aaf', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aaf_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=5) == {
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


def test_c_mp03n_aaf_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aaf', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aaf_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aaf', max_attempts=5) == {
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


def test_c_mp0zn_aaf_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aaf', max_attempts=5) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aaf_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aaf', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aaf_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aaf', max_attempts=6) == {
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


def test_c_mp03n_aaf_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aaf', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aaf_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aaf', max_attempts=6) == {
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


def test_c_mp0zn_aaf_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aaf', max_attempts=6) == {
        'result': None,
        'raised': 'RuntimeError',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aec_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aec_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aec_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aec_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aec_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aec_3() -> None:
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


def test_c_mp01n_aec_3() -> None:
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


def test_c_mp03n_aec_3() -> None:
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


def test_c_mp0fn_aec_3() -> None:
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


def test_c_mp0zn_aec_3() -> None:
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


def test_c_mp0nn_aec_5() -> None:
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


def test_c_mp01n_aec_5() -> None:
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


def test_c_mp03n_aec_5() -> None:
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


def test_c_mp0fn_aec_5() -> None:
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


def test_c_mp0zn_aec_5() -> None:
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


def test_c_mp0nn_aec_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aec', max_attempts=6) == {
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


def test_c_mp01n_aec_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aec', max_attempts=6) == {
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


def test_c_mp03n_aec_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aec', max_attempts=6) == {
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


def test_c_mp0fn_aec_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aec', max_attempts=6) == {
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


def test_c_mp0zn_aec_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aec', max_attempts=6) == {
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


def test_c_mp0nn_aia_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aia', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aia_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aia', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aia_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aia', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aia_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aia', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aia_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aia', max_attempts=2) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aia_3() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aia', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aia_3() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aia', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aia_3() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aia', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aia_3() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aia', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aia_3() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aia', max_attempts=3) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aia_5() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aia', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aia_5() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aia', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aia_5() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aia', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aia_5() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aia', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aia_5() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aia', max_attempts=5) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_aia_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'aia', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_aia_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'aia', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_aia_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'aia', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_aia_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'aia', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_aia_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'aia', max_attempts=6) == {
        'result': None,
        'raised': 'InvalidArgument',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_eab_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp01n_eab_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp03n_eab_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0fn_eab_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0zn_eab_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=2) == {
        'result': None,
        'raised': 'FirestoreContentionExhausted',
        'reason': 'attempts_exhausted',
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
            'finalization_revision': 5,
        },
    }


def test_c_mp0nn_eab_3() -> None:
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


def test_c_mp01n_eab_3() -> None:
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


def test_c_mp03n_eab_3() -> None:
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


def test_c_mp0fn_eab_3() -> None:
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


def test_c_mp0zn_eab_3() -> None:
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


def test_c_mp0nn_eab_5() -> None:
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


def test_c_mp01n_eab_5() -> None:
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


def test_c_mp03n_eab_5() -> None:
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


def test_c_mp0fn_eab_5() -> None:
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


def test_c_mp0zn_eab_5() -> None:
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


def test_c_mp0nn_eab_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'eab', max_attempts=6) == {
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


def test_c_mp01n_eab_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'eab', max_attempts=6) == {
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


def test_c_mp03n_eab_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'eab', max_attempts=6) == {
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


def test_c_mp0fn_eab_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'eab', max_attempts=6) == {
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


def test_c_mp0zn_eab_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'eab', max_attempts=6) == {
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


def test_c_mp0nn_expa1_2() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=2) == {
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


def test_c_mp01n_expa1_2() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=2) == {
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


def test_c_mp03n_expa1_2() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=2) == {
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


def test_c_mp0fn_expa1_2() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=2) == {
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


def test_c_mp0zn_expa1_2() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=2) == {
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


def test_c_mp0nn_expa1_3() -> None:
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


def test_c_mp01n_expa1_3() -> None:
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


def test_c_mp03n_expa1_3() -> None:
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


def test_c_mp0fn_expa1_3() -> None:
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


def test_c_mp0zn_expa1_3() -> None:
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


def test_c_mp0nn_expa1_5() -> None:
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


def test_c_mp01n_expa1_5() -> None:
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


def test_c_mp03n_expa1_5() -> None:
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


def test_c_mp0fn_expa1_5() -> None:
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


def test_c_mp0zn_expa1_5() -> None:
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


def test_c_mp0nn_expa1_6() -> None:
    assert run_defer_cell('mp0nn', 'pucjm', 'expa1', max_attempts=6) == {
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


def test_c_mp01n_expa1_6() -> None:
    assert run_defer_cell('mp01n', 'pucjm', 'expa1', max_attempts=6) == {
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


def test_c_mp03n_expa1_6() -> None:
    assert run_defer_cell('mp03n', 'pucjm', 'expa1', max_attempts=6) == {
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


def test_c_mp0fn_expa1_6() -> None:
    assert run_defer_cell('mp0fn', 'pucjm', 'expa1', max_attempts=6) == {
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


def test_c_mp0zn_expa1_6() -> None:
    assert run_defer_cell('mp0zn', 'pucjm', 'expa1', max_attempts=6) == {
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
