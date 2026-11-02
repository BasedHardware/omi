"""Sync-origin cap holds recover under the offline boundary that created them (synthetic only).

Offline enforcement holds sync audio regardless of ``STT_CAP_DISPATCH_LANES``. Recovery
scope used to require ``sync`` in that list, so with prod's live-only list no sync hold
could ever recover. Only recovery widens here; intake and consent gating are unchanged.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import stt_cap_dispatch as policy
from utils import funded_processing, processing_backlog_worker as worker
from utils import stt_cap_dispatch as dispatch
from utils.batch_pipeline import cap_hold_admission as adapter
from utils.sync import cap_hold, cap_hold_recovery
from utils.subscription import TranscriptionAllowance
from tests.unit.test_sync_cap_hold_recovery import state  # noqa: F401 (legacy recovery harness)

UID = 'owner'


@pytest.fixture
def prod_scope(monkeypatch):
    """Prod's shape: legacy enforcement on, live-only lanes, runtime cohort, offline on."""
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.delenv('STT_CAP_RECOVERY_COHORT', raising=False)
    monkeypatch.setattr(policy, '_cohort_resolver', lambda: f'uid:{UID}')
    # A paid owner: Free owners never recover (test_held_recovery_paid_only.py).
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda uid: True)


def test_sync_holds_enter_recovery_scope_with_live_only_lanes(prod_scope):
    assert policy.recovery_admission_enabled(UID, 'sync')
    assert policy.recovery_admission_enabled(UID, 'live')
    assert policy.any_recovery_admission_enabled(UID)
    # Batch stays behind its own code-owned fence; nothing else widens.
    assert not policy.recovery_admission_enabled(UID, 'batch')
    assert not policy.recovery_admission_enabled('outside', 'sync')


@pytest.mark.parametrize(
    'env,expected',
    [
        ({'STT_CAP_OFFLINE_ENFORCEMENT': 'false'}, False),  # kill switch is the rollback
        ({'STT_CAP_DISPATCH_ENFORCEMENT': 'false'}, False),  # no execution admission configured
        ({'STT_CAP_DISPATCH_ENFORCEMENT': 'false', 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED': 'true'}, True),
        ({'STT_CAP_RECOVERY_COHORT': 'uid:someone-else'}, False),
        ({'STT_CAP_RECOVERY_COHORT': 'uid:owner,typo'}, False),  # malformed denies all recovery
        ({'STT_CAP_DISPATCH_LANES': 'live,sync'}, True),  # explicit selection still works
        ({'STT_CAP_DISPATCH_LANES': 'live,typo'}, False),  # malformed list denies, as selected() does
        ({'STT_CAP_DISPATCH_LANES': 'live,'}, False),  # empty token is malformed too
        ({'STT_CAP_DISPATCH_LANES': ' '}, True),  # blank list is the live default, sync not required
    ],
)
def test_sync_recovery_scope_follows_offline_switch_and_cohorts(prod_scope, monkeypatch, env, expected):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert policy.recovery_admission_enabled(UID, 'sync') is expected


def test_malformed_lane_list_denies_every_recovery_surface(prod_scope, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,syncc')
    assert not policy.selected(UID, 'live')
    assert not policy.recovery_admission_enabled(UID, 'sync')
    assert not policy.any_recovery_admission_enabled(UID)


def test_empty_cap_cohort_admits_no_sync_recovery(prod_scope, monkeypatch):
    monkeypatch.setattr(policy, '_cohort_resolver', lambda: '')
    assert not policy.recovery_admission_enabled(UID, 'sync')
    assert not policy.any_recovery_admission_enabled(UID)


def _intake_surface(uid):
    """Every intake/consent predicate a new sync upload or owner surface reads."""
    with funded_processing.backlog_consent(uid, 'other-month'):
        foreign_grant = funded_processing.consent_allows(uid)
    return (
        policy.offline_admission_enabled(uid, 'sync'),
        policy.execution_admission_enabled(uid, 'sync'),
        policy.any_execution_admission_enabled(uid),
        funded_processing.enabled(uid),
        funded_processing.enabled(uid, 'sync'),
        funded_processing.consent_allows(uid),
        foreign_grant,
    )


@pytest.mark.parametrize('uid', [UID, 'outside'])
@pytest.mark.parametrize('lanes', ['live', 'live,sync', ''])
@pytest.mark.parametrize('offline', ['true', 'false'])
@pytest.mark.parametrize('legacy,ladder', [('true', 'false'), ('false', 'true'), ('false', 'false')])
def test_new_sync_intake_and_consent_gating_are_unchanged(prod_scope, monkeypatch, uid, lanes, offline, legacy, ladder):
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', offline)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', legacy)
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', ladder)
    monkeypatch.setattr(funded_processing, 'period_id', lambda: 'this-month')
    widened = _intake_surface(uid)
    monkeypatch.setattr(policy, '_offline_hold_recovery_selected', lambda uid, lane: False)
    assert _intake_surface(uid) == widened


@pytest.mark.parametrize('managed', [True, False])
def test_sync_intake_admission_decision_is_unchanged(prod_scope, monkeypatch, managed):
    allowance = TranscriptionAllowance(
        'managed' if managed else 'on_device',
        None if managed else 0,
        'plan_allowance_available' if managed else 'plan_allowance_exhausted',
        limit_seconds=None if managed else 0,
    )
    monkeypatch.setattr(dispatch, 'funded_allowance', lambda uid, lane=None, **kwargs: allowance)
    monkeypatch.setattr(dispatch, 'record_decision', lambda *args: None)
    monkeypatch.setattr(dispatch, 'record_audio', lambda *args: None)
    widened = dispatch.sync_admission(UID, 30, 'parakeet')
    monkeypatch.setattr(policy, '_offline_hold_recovery_selected', lambda uid, lane: False)
    assert dispatch.sync_admission(UID, 30, 'parakeet') == widened
    assert widened[0] is managed


def _hold_ref(monkeypatch, origin):
    ref = Mock()
    ref.document.return_value.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'metadata': 'cipher'})
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: ref)
    meta = {} if origin is None else {'origin': origin}
    monkeypatch.setattr(worker.cap_hold, 'metadata', lambda uid, row: meta)
    monkeypatch.setattr(cap_hold, 'metadata', lambda uid, row: meta)


@pytest.mark.parametrize(
    'origin,selected', [('live', True), ('sync', True), (None, True), ('batch', False), ('unknown', False)]
)
async def test_worker_selects_sync_and_pre_origin_holds(prod_scope, monkeypatch, origin, selected):
    _hold_ref(monkeypatch, origin)
    assert await worker._selected(UID, {'kind': 'audio', 'id': 'held'}) is selected


@pytest.mark.parametrize('origin,released', [('sync', False), ('live', False), ('batch', True)])
async def test_worker_does_not_release_sync_reservations_as_excluded(prod_scope, monkeypatch, origin, released):
    _hold_ref(monkeypatch, origin)
    release = Mock(return_value='released')
    monkeypatch.setattr(worker.store, 'release_undispatched_reservation', release)

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    item = {'kind': 'audio', 'id': 'held'}
    result = await worker._release_excluded(UID, 'token', 'lease', 'this-month', item)
    assert (result == 'released') is released
    assert release.called is released


@pytest.fixture
def held_sync(prod_scope, monkeypatch):
    events = []
    row = {'state': 'held', 'lease_token': 'lease'}
    monkeypatch.setattr(cap_hold, 'metadata', lambda uid, current: {'origin': 'sync'})
    monkeypatch.setattr(cap_hold, 'claim', lambda uid, ref, now: dict(row))
    monkeypatch.setattr(cap_hold, 'release', lambda uid, ref, token: events.append(('release', token)))
    monkeypatch.setattr(adapter, 'enabled_for', lambda current, mode=None, uid=None: True)
    monkeypatch.setattr(cap_hold_recovery, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(cap_hold_recovery, 'is_daily_audio_ceiling_exceeded', lambda uid: False)
    monkeypatch.setattr(dispatch, 'record_decision', lambda *args: None)
    monkeypatch.setattr(dispatch, 'record_audio', lambda *args: None)
    lanes = []

    def allowed(uid, lane):
        lanes.append(lane)
        return SimpleNamespace(managed=allowed.managed, reason='plan_allowance_exhausted')

    allowed.managed = True
    monkeypatch.setattr(dispatch, 'funded_allowance', lambda uid, lane=None, **kwargs: allowed(uid, lane))
    monkeypatch.setattr(dispatch, 'allowance_decision_reason', lambda allowance: dispatch.DispatchReason.ENTITLED)
    snapshot = SimpleNamespace(id='hold-1', reference=object(), to_dict=lambda: dict(row))
    return SimpleNamespace(events=events, snapshot=snapshot, allowed=allowed, lanes=lanes)


async def test_exhausted_owner_keeps_sync_hold_without_dispatch(held_sync, monkeypatch):
    held_sync.allowed.managed = False
    monkeypatch.setattr(adapter, 'admit_held', lambda *a: pytest.fail('capped owner admitted'))
    monkeypatch.setattr(cap_hold_recovery, '_recover_row', lambda *a: pytest.fail('capped owner dispatched'))
    assert await cap_hold_recovery.recover_selected(UID, held_sync.snapshot) is False
    assert held_sync.events == [('release', 'lease')]
    assert held_sync.lanes == ['sync']  # allowance is checked on the hold's original lane


async def test_funded_owner_sync_hold_reaches_admission_after_allowance_check(held_sync, monkeypatch):
    admitted = []

    async def admit(uid, snapshot, row):
        admitted.append(uid)
        return adapter.HeldAdmission('retry')

    monkeypatch.setattr(adapter, 'admit_held', admit)
    assert await cap_hold_recovery.recover_selected(UID, held_sync.snapshot) is False
    assert admitted == [UID] and held_sync.lanes == ['sync']


@pytest.fixture
def legacy_sync_hold(prod_scope, state, monkeypatch):  # noqa: F811 (imported pytest fixture)
    """The legacy (non-batch) recovery path for a sync-origin hold under live-only lanes."""
    monkeypatch.setattr(
        cap_hold_recovery.cap_hold,
        'metadata',
        Mock(return_value={'timestamp': 1792152000, 'source': 'omi', 'origin': 'sync'}),
    )
    return state


async def test_legacy_sync_recovery_checks_allowance_on_lane_sync_then_dispatches(legacy_sync_hold):
    assert await cap_hold_recovery._recover_row(UID, legacy_sync_hold.snapshot, legacy_sync_hold.row)
    cap_hold_recovery.sync_allowed.assert_called_with(UID, lane='sync')
    cap_hold_recovery.cap_recovery_pacing.reserve.assert_called_once()
    kwargs = cap_hold_recovery.process_segment.call_args.kwargs
    assert kwargs['cap_recovery'] is True and kwargs['cap_dispatch_lane'] == 'sync'


async def test_legacy_sync_recovery_without_allowance_spends_nothing(legacy_sync_hold):
    cap_hold_recovery.sync_allowed.return_value = False
    assert not await cap_hold_recovery._recover_row(UID, legacy_sync_hold.snapshot, legacy_sync_hold.row)
    cap_hold_recovery.cap_recovery_pacing.reserve.assert_not_called()
    cap_hold_recovery.process_segment.assert_not_called()
    cap_hold_recovery.record_usage.assert_not_called()


@pytest.mark.parametrize('outcome', ['deferred', 'refused'])
async def test_legacy_sync_recovery_stays_inside_shared_pacing(legacy_sync_hold, monkeypatch, outcome):
    decision = cap_hold_recovery.cap_recovery_pacing.Decision(outcome, 30)
    monkeypatch.setattr(cap_hold_recovery.cap_recovery_pacing, 'reserve', Mock(return_value=decision))
    legacy_sync_hold.row['piece_plan'] = {'p.wav': {'seconds': 20}}
    assert not await cap_hold_recovery._recover_row(UID, legacy_sync_hold.snapshot, legacy_sync_hold.row)
    cap_hold_recovery.process_segment.assert_not_called()
    cap_hold_recovery.record_usage.assert_not_called()


async def test_sync_hold_is_out_of_scope_when_offline_switch_is_off(legacy_sync_hold, monkeypatch):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
    assert not await cap_hold_recovery._recover_row(UID, legacy_sync_hold.snapshot, legacy_sync_hold.row)
    cap_hold_recovery.sync_allowed.assert_not_called()
    cap_hold_recovery.process_segment.assert_not_called()


@pytest.mark.parametrize('grant,allowed', [('this-month', True), ('last-month', False)])
def test_recovery_dispatch_requires_the_current_month_backlog_choice(prod_scope, monkeypatch, grant, allowed):
    """Real sync_allowed: a stale consent grant cannot authorize sync-hold recovery."""
    monkeypatch.setattr(funded_processing, 'period_id', lambda: 'this-month')
    managed = TranscriptionAllowance('managed', None, 'plan_allowance_available', limit_seconds=None)
    monkeypatch.setattr(dispatch, 'funded_allowance', lambda uid, lane=None, **kwargs: managed)
    monkeypatch.setattr(dispatch, 'record_decision', lambda *args: None)
    monkeypatch.setattr(cap_hold_recovery, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(cap_hold_recovery, 'is_daily_audio_ceiling_exceeded', lambda uid: False)
    with funded_processing.backlog_consent(UID, grant):
        assert cap_hold_recovery._new_dispatch_allowed(UID, 'sync') is allowed


@pytest.mark.parametrize('lanes', ['live', 'live,sync'])
def test_recovery_cohort_pct_0_stops_all_recovery_and_keeps_the_cap(prod_scope, monkeypatch, lanes):
    """The documented rollback: STT_CAP_RECOVERY_COHORT=pct:0, not the offline kill switch."""
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    monkeypatch.setattr(funded_processing, 'period_id', lambda: 'this-month')
    intake = _intake_surface(UID)
    monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', 'pct:0')
    assert not any(policy.recovery_admission_enabled(UID, lane) for lane in policy.LANES)
    assert not policy.any_recovery_admission_enabled(UID)
    # Intake keeps the offline allowance cap on new sync audio.
    assert _intake_surface(UID) == intake and intake[0] is True
    exhausted = TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted', limit_seconds=0)
    monkeypatch.setattr(dispatch, 'funded_allowance', lambda uid, lane=None, **kwargs: exhausted)
    monkeypatch.setattr(dispatch, 'record_decision', lambda *args: None)
    monkeypatch.setattr(dispatch, 'record_audio', lambda *args: None)
    assert dispatch.sync_admission(UID, 30, 'parakeet')[0] is False


async def test_recovery_cohort_pct_0_parks_worker_and_recovery_before_any_work(held_sync, monkeypatch):
    monkeypatch.setenv('STT_CAP_RECOVERY_COHORT', 'pct:0')
    monkeypatch.setattr(cap_hold, 'claim', lambda *a: pytest.fail('claimed under pct:0'))
    monkeypatch.setattr(adapter, 'admit_held', lambda *a: pytest.fail('admitted under pct:0'))
    monkeypatch.setattr(worker.store, 'read', lambda uid: pytest.fail('worker ran under pct:0'))
    assert await cap_hold_recovery.recover_selected(UID, held_sync.snapshot) is False
    assert await cap_hold_recovery._recover_row(UID, held_sync.snapshot, {'state': 'held'}) is False
    assert await worker.run(UID) is None
    assert held_sync.events == [] and held_sync.lanes == []


def _skipped(outcome):
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value('omi_held_content_recovery_skipped_total', {'outcome': outcome}) or 0.0


@pytest.mark.parametrize(
    'origin,env,skip',
    [
        ('sync', {}, None),
        (None, {}, None),
        ('unknown', {}, 'unknown_origin'),
        ('batch', {}, 'out_of_scope'),
        ('sync', {'STT_CAP_OFFLINE_ENFORCEMENT': 'false'}, 'out_of_scope'),
        ('live', {'STT_CAP_RECOVERY_COHORT': 'pct:0'}, 'out_of_scope'),
    ],
)
async def test_worker_counts_every_scope_skip_by_bounded_outcome(prod_scope, monkeypatch, origin, env, skip):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    _hold_ref(monkeypatch, origin)
    before = {outcome: _skipped(outcome) for outcome in ('out_of_scope', 'unknown_origin', 'unknown')}
    assert await worker._selected(UID, {'kind': 'audio', 'id': 'held'}) is (skip is None)
    after = {outcome: _skipped(outcome) for outcome in before}
    assert {k: after[k] - before[k] for k in before} == {k: float(k == skip) for k in before}


async def test_worker_counts_text_scope_skips_separately(prod_scope, monkeypatch):
    monkeypatch.setattr(funded_processing, 'enabled', lambda uid, lane=None: lane != 'batch')
    before = _skipped('text_out_of_scope')
    assert await worker._selected(UID, {'kind': 'text', 'id': 'conversation'}) is False
    assert _skipped('text_out_of_scope') == before + 1


async def test_selected_and_missing_holds_count_no_skip(prod_scope, monkeypatch):
    ref = Mock()
    ref.document.return_value.get.return_value = SimpleNamespace(exists=False, to_dict=lambda: None)
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: ref)
    before = _skipped('out_of_scope') + _skipped('unknown_origin')
    assert await worker._selected(UID, {'kind': 'audio', 'id': 'gone'}) is True
    assert _skipped('out_of_scope') + _skipped('unknown_origin') == before


def test_skip_counter_is_armed_at_import_with_a_closed_vocabulary():
    from prometheus_client import REGISTRY

    from utils.observability import held_content

    def sample(outcome):
        return REGISTRY.get_sample_value('omi_held_content_recovery_skipped_total', {'outcome': outcome})

    for outcome in ('out_of_scope', 'unknown_origin', 'text_out_of_scope', 'unknown'):
        assert sample(outcome) is not None
    before = sample('unknown')
    held_content.record_recovery_skipped('owner-123')  # free text folds into unknown
    assert sample('owner-123') is None and sample('unknown') == before + 1
