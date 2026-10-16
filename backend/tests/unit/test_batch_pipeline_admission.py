"""Spend authorization is fenced, current, conservative and provider-independent."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_intake import admit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import admission
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.scheduler import Scheduler


def setup(monkeypatch, *, fresh=False):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    store = MemoryStore()
    work = replace(
        item('segment', owner='synthetic-owner', priority=0 if fresh else 2),
        privacy_generation=0,
        requires_compute_admission=True,
    )
    binding = ProjectionBinding(work.owner_id, 'bp_job', 'content', ('segment',))
    admit(
        store,
        [work],
        binding,
        0,
        namespace='batch_pipeline_test_spend',
        intake={
            'owner_id': work.owner_id,
            'total_audio_seconds': 3600,
        },
    )
    queue = Scheduler(store)
    lease = queue.pull(0)[0]
    monkeypatch.setattr(admission, 'get_hard_restriction_status', Mock(return_value=(False, None)))
    monkeypatch.setattr(admission, 'is_daily_audio_ceiling_exceeded', Mock(return_value=False))
    reserve = Mock(return_value=SimpleNamespace(allowed=True))
    monkeypatch.setattr(admission, 'reserve_backfill_speech', reserve)
    return store, queue, lease, reserve


def tokens(lease):
    return [{'segment_id': lease.item.segment_id, 'token': lease.token}]


def test_backfill_reserves_content_upper_bound_and_seals_matching_lease(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch)
    assert not queue.complete(WorkResult('segment', 'gs://synthetic/result'), lease.token, 1)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt['allowed'] == ['segment']
    reserve.assert_called_once_with('synthetic-owner', 'content', 3_600_000)
    assert queue.complete(WorkResult('segment', 'gs://synthetic/result'), lease.token, 2)


def test_refusal_defers_without_spending_provider_failure_budget(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch)
    reserve.return_value = SimpleNamespace(allowed=False, retry_after=600)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt == {'allowed': [], 'retry_after': {'segment': 600}}
    assert queue.defer('segment', lease.token, 1, receipt['retry_after']['segment'])
    assert store.rows['jobs', 'segment']['attempt'] == 0
    assert store.rows['jobs', 'segment']['available_at'] == 601
    assert not queue.complete(WorkResult('segment', 'gs://synthetic/result'), lease.token, 2)


def test_stale_or_replaced_lease_cannot_charge_or_seal(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch)
    admission.authorize(store, [{'segment_id': 'segment', 'token': 'stale'}], now=1)
    reserve.assert_not_called()

    def replace_owner(*args):
        store.rows['jobs', 'segment']['token'] = 'replacement'
        return SimpleNamespace(allowed=True)

    reserve.side_effect = replace_owner
    assert admission.authorize(store, tokens(lease), now=1)['allowed'] == []
    assert 'compute_admission_token' not in store.rows['jobs', 'segment']


def test_fresh_rechecks_restrictions_without_backfill_reservation(monkeypatch):
    store, _, lease, reserve = setup(monkeypatch, fresh=True)
    admission.get_hard_restriction_status.return_value = (True, 120)
    assert admission.authorize(store, tokens(lease), now=1)['retry_after'] == {'segment': 120}
    reserve.assert_not_called()


def test_policy_backend_failure_and_missing_duration_fail_closed(monkeypatch):
    store, _, lease, reserve = setup(monkeypatch)
    reserve.side_effect = TimeoutError('synthetic Redis unavailable')
    assert admission.authorize(store, tokens(lease), now=1)['allowed'] == []
    store.rows['intakes', 'bp_job']['total_audio_seconds'] = float('nan')
    reserve.reset_mock()
    assert admission.authorize(store, tokens(lease), now=1)['allowed'] == []
    reserve.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
def test_cap_rechecked_after_queueing_before_gpu_authorization(monkeypatch, enforce):
    from utils import stt_cap_dispatch as cap

    store, queue, lease, reserve = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(
        cap, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    )
    receipt = admission.authorize(store, tokens(lease), now=1)
    if enforce:
        assert receipt == {'allowed': [], 'retry_after': {'segment': 60}}
        assert queue.defer('segment', lease.token, 1, 60)
        assert store.rows['jobs', 'segment']['attempt'] == 0
        assert 'compute_admission_token' not in store.rows['jobs', 'segment']
        reserve.assert_not_called()
    else:
        assert receipt['allowed'] == ['segment']
        cap.funded_allowance.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('duration', [None, 'invalid'])
def test_flag_off_never_parses_new_dispatch_duration(monkeypatch, enforce, duration):
    store, _, lease, _ = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    store.rows['jobs', 'segment']['duration_seconds'] = duration
    gate = Mock(side_effect=AssertionError('unparseable duration must not reach dispatch policy'))
    monkeypatch.setattr(admission, 'sync_allowed', gate)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt == (
        {'allowed': [], 'retry_after': {'segment': 30}} if enforce else {'allowed': ['segment'], 'retry_after': {}}
    )
    gate.assert_not_called()
