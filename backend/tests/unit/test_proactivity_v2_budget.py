from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from config.proactivity_v2 import AttemptEnvelope, ProactivityDenied, daily_cap
from database import proactivity as ledger
from database import proactivity_budget as money
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


class Redis:
    def __init__(self):
        self.values = {}
        self.down = False

    def set(self, key, value, **kwargs):
        if self.down:
            raise ConnectionError('offline')
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script, count, key, value):
        if self.values.get(key) == value:
            del self.values[key]


@pytest.fixture
def store(monkeypatch):
    db = StrictFirestore()
    db.rows[('users', 'u')] = {
        'subscription': {'plan': 'plus', 'current_period_end': (NOW + timedelta(days=2)).timestamp()},
        'mentor_notification_frequency': 3,
    }
    for name in ['conversation_mentor_v2', 'commitment_followup']:
        db.rows[(ledger.CONTROLS, name)] = dict(version=1, state='enabled', checked_at=NOW)
    db.rows[('users', 'u', 'action_items', 'a')] = {'description': 'synthetic'}
    monkeypatch.setattr(money, 'record_llm_gateway_attempt', lambda *args, **kwargs: True)
    return db


def claim(store, event='due', producer='commitment_followup'):
    return ledger.claim_item(
        uid='u',
        producer=producer,
        source_kind='action_item',
        source_id='a',
        source_revision='1',
        source_event_id=event,
        firestore_client=store,
        now=NOW,
    )


def reserve(authority, item, amount=2000, call=None):
    return authority.reserve(
        uid='u',
        item_id=item['item_id'],
        producer=item['producer'],
        call_id=call or str(uuid4()),
        envelope=AttemptEnvelope('openai', 'gpt-6-luna', 'card', amount, 'hash', 'phrase'),
    )


def test_mentor_six_steps_share_budget_seventh_is_denied(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    item = claim(store, producer='conversation_mentor_v2')
    for _ in range(6):
        reservation = reserve(authority, item)
        assert authority.settle(reservation=reservation, event=event(reservation))
    with pytest.raises(ProactivityDenied, match='call_limit'):
        reserve(authority, item)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert len(row['attempts']) == 6 and row['charged_micro_usd'] == 6000


def event(reservation, cost=1000):
    return SimpleNamespace(
        as_dict=lambda: dict(
            user_uid='u',
            request_id=reservation.call_id,
            feature=f'proactivity_v2_{reservation.producer}',
            payer='omi',
            estimated_cost_micro_usd=cost,
            cost_status='estimated' if cost is not None else 'indeterminate',
            attempt_id='attempt-' + reservation.call_id,
            provider='openai',
            configured_model='gpt-6-luna',
        )
    )


@pytest.mark.parametrize(
    'plan,cap',
    [
        ('basic', 0),
        ('free', 0),
        ('operator', 163333),
        ('architect', 663333),
        ('unlimited_v2', 99966),
        ('unlimited', 66666),
        ('plus', 66666),
    ],
)
def test_cap_arithmetic(plan, cap):
    assert daily_cap(plan) == (cap, False)


def test_exact_cap_shared_across_producers_and_redis_loss(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    first = reserve(authority, claim(store), 66666)
    authority.redis.values.clear()
    with pytest.raises(ProactivityDenied, match='budget_exhausted'):
        reserve(authority, claim(store, 'mentor', 'conversation_mentor_v2'), 1)
    assert authority.settle(reservation=first, event=event(first, 66665))
    assert reserve(authority, claim(store, 'mentor2', 'conversation_mentor_v2'), 1).reserved_micro_usd == 1


def test_duplicate_reservation_and_settlement(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    item = claim(store)
    first = reserve(authority, item, call='same')
    with pytest.raises(ProactivityDenied, match='duplicate'):
        reserve(authority, item, call='same')
    assert authority.settle(reservation=first, event=event(first))
    assert authority.settle(reservation=first, event=event(first))
    with pytest.raises(ProactivityDenied, match='settlement_conflict'):
        authority.settle(reservation=first, event=event(first, 999))
    assert store.rows[('users', 'u', ledger.DAYS, '2026-10-03')]['charged_micro_usd'] == 1000


def test_unknown_retains_hold_and_stops_item(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    item = claim(store, producer='conversation_mentor_v2')
    first = reserve(authority, item)
    assert not authority.settle(reservation=first, event=event(first, None))
    with pytest.raises(ProactivityDenied, match='cost_unsettled'):
        reserve(authority, item)
    assert store.rows[('users', 'u', ledger.DAYS, '2026-10-03')]['charged_micro_usd'] == 2000


def test_overrun_kills_producer_and_blocks_day(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    first = reserve(authority, claim(store), 2000)
    assert not authority.settle(reservation=first, event=event(first, 2001))
    assert store.rows[(ledger.CONTROLS, 'commitment_followup')]['state'] == 'killed'
    assert store.rows[('users', 'u', ledger.DAYS, '2026-10-03')]['blocked']


def test_store_unavailable_never_reserves(store):
    redis = Redis()
    redis.down = True
    authority = money.BudgetAuthority(firestore_client=store, redis_client=redis, clock=lambda: NOW)
    item = claim(store)
    with pytest.raises(ProactivityDenied, match='unavailable'):
        reserve(authority, item)
    assert store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['attempts'] == {}


def test_settlement_crosses_midnight_without_changing_original_day(store):
    clock = [NOW]
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: clock[0])
    first = reserve(authority, claim(store))
    clock[0] += timedelta(days=1)
    authority.settle(reservation=first, event=event(first))
    assert store.rows[('users', 'u', ledger.DAYS, '2026-10-03')]['charged_micro_usd'] == 1000
    assert ('users', 'u', ledger.DAYS, '2026-10-04') not in store.rows


def test_deleted_owner_cannot_be_resurrected_by_settlement(store):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    first = reserve(authority, claim(store))
    store.rows[('account_deletions', 'u')] = {'wipe_status': 'completed'}
    with pytest.raises(ProactivityDenied, match='not_found'):
        authority.settle(reservation=first, event=event(first))


def test_future_unpriced_paid_plan_uses_lowest_known_cap(monkeypatch):
    from config import proactivity_v2 as config

    policy = dict(config.PROACTIVITY_V2_BUDGET)
    policy['monthly_reference_cents'] = {k: v for k, v in policy['monthly_reference_cents'].items() if k != 'plus'}
    monkeypatch.setattr(config, 'PROACTIVITY_V2_BUDGET', policy)
    assert daily_cap('plus') == (66666, True)
    with pytest.raises(ProactivityDenied, match='unknown_plan'):
        daily_cap('unrecognized')
