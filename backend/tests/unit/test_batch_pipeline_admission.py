"""Spend authorization is fenced, current, conservative and provider-independent."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from database.batch_pipeline_intake import admit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import admission
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.scheduler import Scheduler


def setup(monkeypatch, *, fresh=False, priority=None, lane=None):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    store = MemoryStore()
    work = replace(
        item('segment', owner='synthetic-owner', priority=priority if priority is not None else 0 if fresh else 2),
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
            **({'lane': lane} if lane else {}),
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


def test_fresh_lane_catch_up_at_recent_priority_keeps_fresh_fair_use_checks(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch, priority=1, lane='fresh')
    admission.get_hard_restriction_status.return_value = (True, 900)
    assert admission.authorize(store, tokens(lease), now=1) == {
        'allowed': [],
        'retry_after': {'segment': 900},
        'held_reason': {'segment': 'fair_use_restricted'},
    }
    reserve.assert_not_called()
    admission.get_hard_restriction_status.return_value = (False, None)
    admission.is_daily_audio_ceiling_exceeded.return_value = True
    daily = admission.authorize(store, tokens(lease), now=1)
    assert daily['allowed'] == [] and 1 <= daily['retry_after']['segment'] <= 86400
    assert daily['held_reason'] == {'segment': 'daily_audio_ceiling'}
    reserve.assert_not_called()


def test_backfill_lane_reserves_whatever_the_priority(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch, priority=1, lane='backfill')
    assert admission.authorize(store, tokens(lease), now=1)['allowed'] == ['segment']
    reserve.assert_called_once_with('synthetic-owner', 'content', 3_600_000)
    admission.get_hard_restriction_status.assert_not_called()


def test_refusal_defers_without_spending_provider_failure_budget(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch)
    reserve.return_value = SimpleNamespace(allowed=False, retry_after=600)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt == {
        'allowed': [],
        'retry_after': {'segment': 600},
        'held_reason': {'segment': 'backfill_reservation'},
    }
    assert queue.defer('segment', lease.token, 2, receipt['retry_after']['segment'], held_reason='backfill_reservation')
    assert store.rows['jobs', 'segment']['attempt'] == 0
    assert store.rows['jobs', 'segment']['available_at'] == 602
    assert store.rows['jobs', 'segment']['compute_decision'] == {
        'reason': 'backfill_reservation',
        'outcome': 'held',
        'at': 2,
    }
    assert not queue.complete(WorkResult('segment', 'gs://synthetic/result'), lease.token, 3)


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
        assert receipt == {
            'allowed': [],
            'retry_after': {'segment': 60},
            'held_reason': {'segment': 'allowance_exhausted'},
        }
        assert queue.defer('segment', lease.token, 1, 60, held_reason='allowance_exhausted')
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
    monkeypatch.setattr(admission, 'sync_admission', gate)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt == (
        {'allowed': [], 'retry_after': {'segment': 30}, 'held_reason': {}}
        if enforce
        else {'allowed': ['segment'], 'retry_after': {}, 'held_reason': {}}
    )
    gate.assert_not_called()


@pytest.mark.parametrize('dispatch', [False, True])
def test_ladder_rechecked_at_execution_after_queue_admission(monkeypatch, dispatch):
    from utils import ladder_v1

    store, queue, lease, reserve = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    # A valid queued lease is not spend authority after the shared budget moves.
    monkeypatch.setattr(ladder_v1, 'budget_snapshot', lambda *a, **k: {'budget_percent': 100})
    if dispatch:
        from utils import subscription

        monkeypatch.setattr(
            subscription,
            'resolve_transcription_allowance',
            lambda *a, **k: SimpleNamespace(managed=False, reason='usage_budget_exhausted'),
        )
    receipt = admission.authorize(store, tokens(lease), now=1)
    # dispatch=False keeps the ladder-only resolver, whose stub snapshot has no
    # budget_units/used_units keys, so it degrades to allowance_unavailable.
    # Either way the durable reason mirrors the bounded DispatchReason the
    # dispatch counter records for the same decision.
    expected_reason = 'budget_exhausted' if dispatch else 'allowance_unavailable'
    assert receipt == {'allowed': [], 'retry_after': {'segment': 60}, 'held_reason': {'segment': expected_reason}}
    assert 'compute_admission_token' not in store.rows['jobs', 'segment']
    reserve.assert_not_called()


@pytest.mark.parametrize(
    'policy, held',
    [(None, True), ({}, True), ({'provider_reason': 'none'}, True), ({'provider_reason': 'byok'}, False)],
)
def test_byok_admission_is_not_re_held_at_dispatch(monkeypatch, policy, held):
    store, _, lease, _ = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    if policy is not None:
        store.rows['jobs', 'segment']['policy'] = policy
    gate = Mock(return_value=(False, 'allowance_exhausted'))  # no funded consent or allowance for this owner
    monkeypatch.setattr(admission, 'sync_admission', gate)
    receipt = admission.authorize(store, tokens(lease), now=1)
    if held:
        assert receipt == {
            'allowed': [],
            'retry_after': {'segment': 60},
            'held_reason': {'segment': 'allowance_exhausted'},
        }
    else:
        assert receipt['allowed'] == ['segment']
        gate.assert_not_called()


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize(
    'cohort,lanes,held',
    [
        ('uid:synthetic-owner', 'batch', True),
        ('uid:synthetic-owner', 'live', False),
        ('uid:other', 'batch', False),
        ('', 'batch', False),
    ],
)
def test_queued_authorization_uses_owner_and_batch_scope(monkeypatch, ladder, cohort, lanes, held):
    from utils import stt_cap_dispatch as cap

    store, _, lease, _ = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    allowance = Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    monkeypatch.setattr(cap, 'funded_allowance', allowance)
    result = admission.authorize(store, tokens(lease), now=1)
    assert result['allowed'] == ([] if held else ['segment'])
    assert allowance.call_count == int(held)
    if held:
        allowance.assert_called_once_with('synthetic-owner', lane='batch')


@pytest.mark.parametrize('access', ['capped', 'byok', 'reviewer', 'paid', 'kill_off'])
def test_default_on_gpu_allowance_is_independent_of_batch_readiness(monkeypatch, access):
    from config import stt_cap_dispatch as policy
    from utils import stt_cap_dispatch as cap

    store, queue, lease, reserve = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false' if access == 'kill_off' else 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setattr(policy, '_BATCH_LANE_READY', False)
    if access == 'byok':
        store.rows['jobs', 'segment']['policy'] = {'provider_reason': 'byok'}
    resolver = Mock(
        return_value=SimpleNamespace(managed=access in {'reviewer', 'paid'}, reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(cap, 'funded_allowance', resolver)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt['allowed'] == ([] if access == 'capped' else ['segment'])
    if access == 'capped':
        assert 'compute_admission_token' not in store.rows['jobs', 'segment']
        assert queue.defer('segment', lease.token, 1, 60)
        assert store.rows['jobs', 'segment']['attempt'] == 0
    if access in {'byok', 'kill_off'}:
        resolver.assert_not_called()
    reserve.assert_not_called()


def test_allow_seals_latest_decision_with_the_lease_transition(monkeypatch):
    from utils import stt_cap_dispatch as cap

    store, _, lease, _ = setup(monkeypatch, fresh=True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(
        cap, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=True, reason='plan_allowance_available'))
    )
    receipt = admission.authorize(store, tokens(lease), now=5)
    assert receipt == {'allowed': ['segment'], 'retry_after': {}, 'held_reason': {}}
    job = store.rows['jobs', 'segment']
    assert job['compute_admission_token'] == lease.token
    assert job['compute_decision'] == {'reason': 'entitled', 'outcome': 'allowed', 'at': 5}


def test_latest_decision_overwrites_a_prior_hold(monkeypatch):
    """The durable field is the latest decision, never a sticky last denial."""
    from utils import stt_cap_dispatch as cap

    store, queue, lease, _ = setup(monkeypatch)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    allowance = Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    monkeypatch.setattr(cap, 'funded_allowance', allowance)
    held = admission.authorize(store, tokens(lease), now=1)
    assert held['held_reason'] == {'segment': 'allowance_exhausted'}
    assert queue.defer('segment', lease.token, 2, held['retry_after']['segment'], held_reason='allowance_exhausted')
    assert store.rows['jobs', 'segment']['compute_decision'] == {
        'reason': 'allowance_exhausted',
        'outcome': 'held',
        'at': 2,
    }
    # The owner's allowance recovers: the next lease is sealed allowed and the
    # recorded decision follows, so a later reader cannot mistake the unit for
    # a still-held one.
    store.rows['jobs', 'segment']['available_at'] = 0
    queue.recover(3)
    lease = queue.pull(3)[0]
    allowance.return_value = SimpleNamespace(managed=True, reason='plan_allowance_available')
    assert admission.authorize(store, tokens(lease), now=4)['allowed'] == ['segment']
    assert store.rows['jobs', 'segment']['compute_decision'] == {'reason': 'entitled', 'outcome': 'allowed', 'at': 4}


def test_policy_backend_failure_leaves_the_prior_decision_untouched(monkeypatch):
    store, queue, lease, reserve = setup(monkeypatch)
    assert admission.authorize(store, tokens(lease), now=1)['allowed'] == ['segment']
    sealed = dict(store.rows['jobs', 'segment']['compute_decision'])
    # A later lease whose policy backend fails must not invent a decision.
    store.rows['jobs', 'segment'].update(state='retry', token='', available_at=0)
    queue.recover(2)
    lease = queue.pull(2)[0]
    reserve.side_effect = TimeoutError('synthetic Redis unavailable')
    failed = admission.authorize(store, tokens(lease), now=3)
    assert failed['allowed'] == [] and failed['held_reason'] == {}
    assert queue.defer('segment', lease.token, 4, failed['retry_after']['segment'])
    assert store.rows['jobs', 'segment']['compute_decision'] == sealed


def test_privacy_fence_hold_records_its_reason(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from tests.unit.test_batch_pipeline_scheduler import MemoryTransaction

    store, queue, lease, _ = setup(monkeypatch)
    check = MemoryTransaction.check_privacy

    def fenced(tx, uid, conversation_ids=(), expected_generation=None):
        raise BatchPrivacyBlocked('synthetic deletion')

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', fenced)
    receipt = admission.authorize(store, tokens(lease), now=1)
    assert receipt['held_reason'] == {'segment': 'privacy_blocked'}
    assert queue.defer('segment', lease.token, 2, 30, held_reason='privacy_blocked')
    assert store.rows['jobs', 'segment']['compute_decision'] == {
        'reason': 'privacy_blocked',
        'outcome': 'held',
        'at': 2,
    }
    monkeypatch.setattr(MemoryTransaction, 'check_privacy', check)
