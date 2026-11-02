"""Held audio recovers only for an owner on an active paid plan (David, 2026-11-01; synthetic only).

Free owners keep their holds on every lane: no choice, no worker run, no sweep visit and no
dispatch. The entitlement is read on every decision and an unreadable one fails closed.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from config import stt_cap_dispatch as policy
from config.plan_catalog import PAID_PLAN_TYPES
from database import users as users_db
from models.users import PlanType
from routers import users as route
from utils import funded_processing, processing_backlog as backlog, processing_backlog_worker as worker
from utils.sync import cap_hold, cap_hold_recovery

UID = 'synthetic-owner'
_REAL_PAID_OWNER = funded_processing.paid_owner


@pytest.fixture
def prod_scope(monkeypatch):
    """Prod's shape: legacy enforcement on, live-only lanes, runtime cohort, offline on."""
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.delenv('STT_CAP_RECOVERY_COHORT', raising=False)
    monkeypatch.setattr(policy, '_cohort_resolver', lambda: f'uid:{UID}')

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap_hold_recovery, 'run_blocking', immediate)
    monkeypatch.setattr(worker, 'run_blocking', immediate)


@pytest.fixture
def free(prod_scope, monkeypatch):
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda uid: False)


def _counter(name, labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.mark.parametrize(
    'subscription,paid',
    [
        (None, False),  # an inactive Free plan
        (SimpleNamespace(plan=PlanType.basic), False),  # Free, or a lapsed paid period read back as Basic
        *[(SimpleNamespace(plan=plan), True) for plan in sorted(PAID_PLAN_TYPES, key=lambda p: p.value)],
    ],
)
def test_paid_owner_reads_the_entitlement_on_every_call(monkeypatch, subscription, paid):
    reads = []

    def valid(uid, *, provision):
        reads.append((uid, provision))
        return subscription

    monkeypatch.setattr(users_db, 'get_user_valid_subscription', valid)
    assert _REAL_PAID_OWNER(UID) is paid
    assert _REAL_PAID_OWNER(UID) is paid
    # Never provisions a default Free plan onto the owner, and never caches.
    assert reads == [(UID, False), (UID, False)]


def test_unreadable_entitlement_fails_closed(monkeypatch):
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', Mock(side_effect=RuntimeError('synthetic outage')))
    assert _REAL_PAID_OWNER(UID) is False


def test_downgrade_stops_recovery_at_the_next_decision(monkeypatch):
    plans = iter([PlanType.unlimited_v2, PlanType.basic])
    monkeypatch.setattr(
        users_db, 'get_user_valid_subscription', lambda uid, *, provision: SimpleNamespace(plan=next(plans))
    )
    assert _REAL_PAID_OWNER(UID) is True
    assert _REAL_PAID_OWNER(UID) is False


@pytest.mark.parametrize('origin', ['live', 'sync', None])
async def test_free_holds_are_out_of_scope_on_every_lane_before_decrypting(free, monkeypatch, origin):
    monkeypatch.setattr(cap_hold, 'metadata', Mock(side_effect=AssertionError('decrypted a Free hold')))
    lane, skip = await cap_hold_recovery._scope(UID, {'metadata': 'cipher'})
    assert lane is None and skip == 'not_paid'


async def test_paid_holds_stay_in_scope(prod_scope, monkeypatch):
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda uid: True)
    monkeypatch.setattr(cap_hold, 'metadata', lambda uid, row: {'origin': 'sync'})
    assert await cap_hold_recovery._selected_lane(UID, {'metadata': 'cipher'}) == 'sync'


async def test_free_hold_is_never_claimed_or_dispatched(free, monkeypatch):
    monkeypatch.setattr(cap_hold, 'claim', Mock(side_effect=AssertionError('claimed a Free hold')))
    monkeypatch.setattr(cap_hold_recovery, '_recover_row', Mock(side_effect=AssertionError('dispatched')))
    snapshot = SimpleNamespace(id='hold', reference=object(), to_dict=lambda: {'state': 'held'})
    assert await cap_hold_recovery.recover_selected(UID, snapshot) is False


async def test_free_skip_has_its_own_outcome_outside_the_recovery_gate(free, monkeypatch):
    ref = Mock()
    ref.document.return_value.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'metadata': 'c'})
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: ref)
    name = 'omi_held_content_recovery_skipped_total'
    gated = ('out_of_scope', 'unknown_origin', 'unknown')
    before = {o: _counter(name, {'outcome': o}) for o in (*gated, 'not_paid')}
    assert await worker._selected(UID, {'kind': 'audio', 'id': 'held'}) is False
    after = {o: _counter(name, {'outcome': o}) for o in before}
    assert {o: after[o] - before[o] for o in before} == {**{o: 0.0 for o in gated}, 'not_paid': 1.0}


async def test_free_owner_worker_parks_before_reading_the_choice(free, monkeypatch):
    monkeypatch.setattr(worker, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(worker.store, 'read', Mock(side_effect=AssertionError('read a Free choice')))
    monkeypatch.setattr(worker.store, 'claim', Mock(side_effect=AssertionError('claimed a Free choice')))
    assert await worker.run(UID) is None


def test_free_tap_starts_nothing_and_counts_not_paid(free, monkeypatch):
    start = Mock(side_effect=AssertionError('started a Free choice'))
    monkeypatch.setattr(worker.store, 'start', start)
    name = 'omi_processing_backlog_choice_total'
    before = _counter(name, {'source': 'manual', 'outcome': 'not_paid'})
    assert backlog.choose(UID, request_key='synthetic-tap') is None
    assert _counter(name, {'source': 'manual', 'outcome': 'not_paid'}) == before + 1


def _allowance(managed=True, reason='plan_allowance_available'):
    return SimpleNamespace(managed=managed, reason=reason, remaining_seconds=3600, limit_seconds=18000)


@pytest.mark.parametrize(
    'paid,managed,count,state,exhausted',
    [
        # Free under its monthly limit with held audio: no process action, and not "limit reached".
        (False, True, 3, 'capped', False),
        (False, True, 0, 'none', False),
        (False, False, 3, 'capped', True),
        (False, False, 0, 'capped', True),
        (True, True, 3, 'waiting_choice', False),
        (True, False, 3, 'capped', True),
    ],
)
def test_snapshot_never_offers_free_owners_the_process_action(
    prod_scope, monkeypatch, paid, managed, count, state, exhausted
):
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda uid: paid)
    allowance = _allowance(managed, 'plan_allowance_available' if managed else 'plan_allowance_exhausted')
    result = backlog.snapshot(UID, allowance=allowance, audio={'count': count, 'seconds': 60 * count}, summary={})
    assert result.state == state and result.budget_exhausted is exhausted
    assert result.held_audio_seconds == 60 * count  # the card still shows the owner's held total


def test_free_process_route_returns_the_existing_402_and_keeps_holds(free, monkeypatch):
    monkeypatch.setattr(funded_processing, 'allowance', lambda uid: _allowance())
    monkeypatch.setattr(worker.store, 'read', lambda uid: {})
    monkeypatch.setattr(worker.store, 'start', Mock(side_effect=AssertionError('started a Free choice')))
    monkeypatch.setattr(cap_hold, 'ensure_summary', lambda uid: {'count': 2, 'seconds': 120})
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        response = client.post('/v1/users/processing-backlog/process', headers={'Idempotency-Key': 'synthetic-tap'})
    assert response.status_code == 402
    assert response.json()['detail'] == {'error': 'usage_budget_exhausted', 'trigger': 'usage_budget'}


def test_a_lapse_between_pieces_stops_the_next_provider_request(prod_scope, monkeypatch):
    """A long hold dispatches several pieces; each new request rereads the entitlement."""
    paid = iter([True, False])
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda uid: next(paid))
    monkeypatch.setattr(cap_hold_recovery, 'sync_allowed', lambda uid, lane: True)
    monkeypatch.setattr(cap_hold_recovery, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(cap_hold_recovery, 'is_daily_audio_ceiling_exceeded', lambda uid: False)
    monkeypatch.setattr(cap_hold_recovery, 'enabled', lambda uid, lane: True)
    assert cap_hold_recovery._new_dispatch_allowed(UID, 'sync') is True
    assert cap_hold_recovery._new_dispatch_allowed(UID, 'sync') is False
