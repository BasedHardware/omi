"""Money review2 reproductions through the canonical commercial writer."""

from datetime import datetime, timedelta, timezone

import pytest

from database import referral_campaign as ledger, users
from tests.unit.fixtures.referral_campaign import NOW, POLICY, prepare, seed_user, settle
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import referral_grant_clock as clock
from utils.referral_campaign import GRANT_FIELD, effective_subscription_payload

DAY = 86400


class DeliveryClock(datetime):
    instant = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.instant


def execute(monkeypatch, order, *, ranges, delivered_days, second_claim=False):
    client = StrictFirestore()
    seed_user(client, 'owner')
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    monkeypatch.setattr(users, 'db', client)
    monkeypatch.setattr(ledger, 'current_policy', lambda: POLICY)
    monkeypatch.setattr(ledger, 'datetime', DeliveryClock)
    for i in range(2):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    granted, _ = ledger.claim_months('owner', client=client, policy=POLICY, now=NOW)
    original = granted['grant'].copy()
    assert original['budget_seconds'] == 61 * DAY
    DeliveryClock.instant = NOW + timedelta(days=delivered_days)
    after_each = []
    for index in order:
        start, end = ranges[index]
        paid = {
            'plan': 'operator',
            'status': 'active',
            'stripe_subscription_id': 'sub_local',
            'current_period_start': int((NOW + timedelta(days=start)).timestamp()),
            'current_period_end': int((NOW + timedelta(days=end)).timestamp()),
        }
        users.update_user_subscription('owner', paid)
        before_replay = client.rows[('users', 'owner')][GRANT_FIELD].copy()
        # Each exact period must remain idempotent even if retried later.
        for _ in range(3):
            users.update_user_subscription('owner', paid)
        assert client.rows[('users', 'owner')][GRANT_FIELD] == before_replay
        assert client.rows[('users', 'owner')]['subscription'] == paid
        after_each.append(before_replay)
    grant = client.rows[('users', 'owner')][GRANT_FIELD]
    account = ledger.read_campaign('owner', client=client, policy=POLICY)
    assert grant == account['grant']
    assert grant['budget_seconds'] == original['budget_seconds']
    # Commercial last-delivery-wins is preserved; access after BOTH paid
    # periods end must still reflect the same promotional obligation.
    paid = client.rows[('users', 'owner')]['subscription']
    probe = max(
        NOW + timedelta(days=delivered_days, seconds=1), NOW + timedelta(days=max(end for _, end in ranges), seconds=1)
    )
    assert effective_subscription_payload(paid, grant, now=probe)['plan'] == 'unlimited_v2'
    assert (
        effective_subscription_payload(paid, grant, now=datetime.fromtimestamp(grant['ends_at'], timezone.utc)) == paid
    )
    return grant, after_each


@pytest.mark.parametrize(
    'ranges,delivered,remaining',
    [
        (((0, 30), (30, 61)), 62, 61),  # exact review2 trace, adjacent and late
        (((0, 30), (20, 61)), 62, 61),  # overlapping coverage cannot double-credit
        (((0, 30), (20, 50)), 62, 50),  # 11 free available days genuinely consumed
        (((0, 20), (30, 61)), 62, 51),  # 10-day paid hole is not presumed covered
        (((0, 30), (30, 61)), 100, 61),  # delivery long after original expiry
        (((-10, 20), (10, 80)), 100, 61),
    ],
)
def test_distinct_paid_period_permutations_restore_equal_duration_end_and_access(
    monkeypatch, ranges, delivered, remaining
):
    ab, _ = execute(monkeypatch, (0, 1), ranges=ranges, delivered_days=delivered)
    ba, _ = execute(monkeypatch, (1, 0), ranges=ranges, delivered_days=delivered)
    assert ab == ba
    assert ab['ends_at'] == int((NOW + timedelta(days=delivered + remaining)).timestamp())
    assert ab['ends_at'] - ab['starts_at'] == remaining * DAY


def test_replayed_covered_period_after_reward_expires_never_restarts_it(monkeypatch):
    grant, _ = execute(monkeypatch, (1, 0), ranges=((0, 30), (30, 61)), delivered_days=62)
    paid = {
        'plan': 'operator',
        'current_period_start': int(NOW.timestamp()),
        'current_period_end': int((NOW + timedelta(days=30)).timestamp()),
    }
    result = clock.requeue_for_paid_period(grant, paid, now=NOW + timedelta(days=400))
    assert result == grant


def test_followup_milestone_extends_budget_only_by_new_calendar_award(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    client = StrictFirestore()
    seed_user(client, 'owner')
    for i in range(5):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
        if i == 1:
            first, _ = ledger.claim_months('owner', client=client, policy=POLICY, now=NOW)
    second, _ = ledger.claim_months('owner', client=client, policy=POLICY, now=NOW)
    assert first['grant']['budget_seconds'] == 61 * DAY
    assert second['grant']['budget_seconds'] == second['grant']['ends_at'] - second['grant']['starts_at']
    assert second['grant']['budget_seconds'] > first['grant']['budget_seconds']
    assert len(second['grant']['availability']) == 1


def test_interval_capacity_fails_without_clamping_or_partial_billing_write(monkeypatch):
    monkeypatch.setattr(clock, 'MAX_CLOCK_INTERVALS', 2)
    with pytest.raises(clock.GrantClockCapacityError):
        clock.merge_intervals([{'start': 0, 'end': 1}, {'start': 2, 'end': 3}, {'start': 4, 'end': 5}])
    assert clock.merge_intervals([{'start': 0, 'end': 2}, {'start': 2, 'end': 4}]) == [{'start': 0, 'end': 4}]


def test_unrecoverable_dormant_scalar_prototype_requires_explicit_reconciliation():
    grant = {'starts_at': 0, 'ends_at': 10, 'paid_coverage_end': 5}
    with pytest.raises(ValueError, match='prototype grant requires billing reconciliation'):
        clock.requeue_for_paid_period(grant, {'current_period_start': 0, 'current_period_end': 7}, now=NOW)


def test_capacity_failure_keeps_canonical_billing_and_obligation_unchanged(monkeypatch):
    from copy import deepcopy

    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    monkeypatch.setattr(clock, 'MAX_CLOCK_INTERVALS', 2)
    anchor = int(NOW.timestamp())
    grant = {
        'campaign_id': POLICY.campaign_id,
        'status': 'active',
        'starts_at': anchor,
        'ends_at': anchor + 1000,
        'budget_seconds': 1000,
        'availability': [{'start': anchor, 'end': anchor + 1000}],
        'paid_coverage': [{'start': anchor + 1, 'end': anchor + 2}, {'start': anchor + 3, 'end': anchor + 4}],
    }
    client = StrictFirestore({('users', 'owner'): {'subscription': {'plan': 'basic'}, GRANT_FIELD: grant}})
    before = deepcopy(client.rows)
    with pytest.raises(clock.GrantClockCapacityError):
        ledger.write_commercial_subscription(
            'owner',
            {'plan': 'operator', 'current_period_start': anchor + 5, 'current_period_end': anchor + 6},
            client=client,
            policy=POLICY,
            now=NOW + timedelta(seconds=7),
        )
    assert client.rows == before
