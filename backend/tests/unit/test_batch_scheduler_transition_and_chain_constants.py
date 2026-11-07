"""Scheduler transition surfaces and chain constants adjacent to the wave bridge.

The scheduler's re-queue helpers own the custody fences the recover sweep and
the recovery lane rely on; the GPU-acknowledgement release is its own lease
contract. Each helper here is exercised directly against its documented
accept/refuse matrix, and the chain's named constants are pinned one last
time beside the rung table they generate.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import pytest

import database.firestore_transaction_retry as retry_module
from database.firestore_transaction_retry import (
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    equal_jitter_delay,
)
from utils.batch_pipeline.scheduler import Scheduler, owner_key


class TxStub:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        import copy

        return copy.deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        import copy

        self.rows[(table, key)] = copy.deepcopy(value)

    def patch(self, table, key, fields):
        import copy

        self.rows.setdefault((table, key), {}).update(copy.deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


def dead_job(segment='seg-d', owner='owner-a'):
    return {
        'segment_id': segment,
        'owner_id': owner,
        'owner_key': owner_key(owner),
        'state': 'dead',
        'merge_pending': True,
        'priority': 1,
        'available_at': 0.0,
        'duration_seconds': 3.0,
        'capture_at': 0.0,
        'failure': 'earlier failure',
        'token': 'old-token',
        'lease_until': 12.0,
    }


def test_redrive_requeues_a_dead_unit():
    rows = {}
    job = dead_job()
    assert Scheduler.redrive_in_transaction(TxStub(rows), job, 100.0, frontier=0.0) is True
    assert rows[('jobs', 'seg-d')]['state'] == 'ready'


def test_redrive_clears_the_failure_and_custody():
    rows = {}
    Scheduler.redrive_in_transaction(TxStub(rows), dead_job(), 100.0, frontier=0.0)
    job = rows[('jobs', 'seg-d')]
    assert job['failure'] == ''
    assert job['token'] == ''
    assert job['lease_until'] == 0.0


def test_redrive_refuses_a_non_dead_unit():
    job = dead_job()
    job['state'] = 'quarantined'
    assert Scheduler.redrive_in_transaction(TxStub({}), job, 100.0, frontier=0.0) is False


def test_redrive_refuses_a_dead_unit_outside_the_merge():
    job = dead_job()
    job['merge_pending'] = False
    assert Scheduler.redrive_in_transaction(TxStub({}), job, 100.0, frontier=0.0) is False


def test_restore_refuses_a_non_quarantined_row():
    from utils.batch_pipeline.scheduler import Scheduler as S

    job = dead_job()
    job.update(state='retry', recovery_state=None, artifact_disposition=None)
    with pytest.raises(ValueError, match='verified missing-input repair'):
        S.restore_audio_in_transaction(TxStub({}), job, 100.0, frontier=0.0)


def test_restore_refuses_an_unrestored_marker():
    job = dead_job()
    job.update(state='quarantined', recovery_state='failed_held', artifact_disposition={'state': 'pending'})
    with pytest.raises(ValueError, match='verified missing-input repair'):
        Scheduler.restore_audio_in_transaction(TxStub({}), job, 100.0, frontier=0.0)


def test_restore_refuses_a_row_with_a_result():
    from utils.batch_pipeline.scheduler import Scheduler as S

    job = dead_job()
    job.update(
        state='quarantined',
        recovery_state='failed_held',
        artifact_disposition={'state': 'restored'},
        result={'words': []},
    )
    with pytest.raises(ValueError, match='verified missing-input repair'):
        S.restore_audio_in_transaction(TxStub({}), job, 100.0, frontier=0.0)


def test_restore_refuses_a_held_lease():
    from utils.batch_pipeline.scheduler import Scheduler as S

    job = dead_job()
    job.update(
        state='quarantined',
        recovery_state='failed_held',
        artifact_disposition={'state': 'restored'},
        merge_pending=False,
        token='',
        lease_until=999.0,
    )
    with pytest.raises(ValueError, match='verified missing-input repair'):
        S.restore_audio_in_transaction(TxStub({}), job, 100.0, frontier=0.0)


def test_restore_requeues_the_quarantined_row():
    from utils.batch_pipeline.scheduler import Scheduler as S

    rows = {}
    job = dead_job()
    job.update(
        state='quarantined',
        recovery_state='failed_held',
        artifact_disposition={'state': 'restored'},
        merge_pending=False,
        token='',
        lease_until=0.0,
    )
    S.restore_audio_in_transaction(TxStub(rows), job, 100.0, frontier=0.0)
    assert rows[('jobs', 'seg-d')]['state'] == 'ready'


def test_gpu_idle_acknowledge_refuses_unbounded_identities():
    scheduler = Scheduler.__new__(Scheduler)
    with pytest.raises(ValueError):
        scheduler.acknowledge_gpu_idle('', 'token')
    with pytest.raises(ValueError):
        scheduler.acknowledge_gpu_idle('g' * 129, 'token')
    with pytest.raises(ValueError):
        scheduler.acknowledge_gpu_idle('gpu', '')


def test_the_cap_comment_and_the_rungs_agree_on_the_default_chain_window():
    gaps = [equal_jitter_delay(k, random_value=lambda: 1.0) for k in range(1, 5)]
    assert sum(gaps) == 3.0  # 'sum to 1.5-3.0 s' high edge
    assert retry_module._MAX_DELAY_SECONDS == 4.0


def test_the_low_edge_of_the_default_chain_window():
    gaps = [equal_jitter_delay(k, random_value=lambda: 0.0) for k in range(1, 5)]
    assert sum(gaps) == 1.5  # 'sum to 1.5-3.0 s' low edge


def test_the_initial_rung_never_changes_under_the_wave_bridge():
    assert _INITIAL_MAX_DELAY_SECONDS == 0.2
    assert equal_jitter_delay(1, random_value=lambda: 1.0) == 0.2


def test_the_ladder_is_non_decreasing_across_the_documented_rungs():
    highs = [equal_jitter_delay(k, random_value=lambda: 1.0) for k in range(1, 7)]
    assert highs == sorted(highs)
