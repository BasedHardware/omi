"""The trial grant: a Stripe trial's start (David, 2026-11-02; synthetic only).

Newest first up to ``TRIAL_RECOVERY_GRANT_HOURS`` of held audio, once per account. A retry or a
restart starts nothing more. The grant carries across a month; its limits are in
``test_backlog_release_gate``.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.backlog_release import PRIORITY_HOURS
from config.rate_card import recording_units_per_hour
from config.stt_cap_dispatch import TRIAL_RECOVERY_GRANT_HOURS
from database import processing_backlog as store
from models.users import ProcessingBacklog
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from utils import funded_processing as funded, processing_backlog as backlog, processing_backlog_worker as worker

UID = 'synthetic-owner'
SUMMARY = ('users', UID, 'processing_backlog', 'current')
TRIAL_START = datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp()
RATE = float(recording_units_per_hour('batch'))
GRANT = TRIAL_RECOVERY_GRANT_HOURS * RATE


def trialing(**changes):
    return {'id': 'sub_synthetic', 'status': 'trialing', 'trial_start': TRIAL_START, **changes}


@pytest.fixture
def owner(monkeypatch):
    """A paid trial owner with waiting audio, against a strict transaction fake."""
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    month = {'id': '2026-11'}
    monkeypatch.setattr(funded, 'period_id', lambda: month['id'])
    monkeypatch.setattr(funded, 'allowance', lambda uid: SimpleNamespace(managed=True))
    remaining = {'units': None}  # Unlimited: no finite allowance
    monkeypatch.setattr(
        backlog,
        'snapshot',
        lambda *a, **k: ProcessingBacklog(
            state='waiting_choice', remaining_units=remaining['units'], estimated_units=40 * RATE
        ),
    )
    monkeypatch.setattr(store, '_request_memo', lambda: SimpleNamespace(forget_request_reads=lambda uid: None))
    client = StrictFirestore({SUMMARY: {}})
    strict_set = StrictFirestoreTransaction.set

    def set_summary(tx, ref, data, *, merge=False):
        # Shallow merge for the summary's top-level fields only. These tests assert the
        # request receipt and choice fields, never Firestore's nested merge semantics.
        if merge and ref.path == SUMMARY:
            return strict_set(tx, ref, {**client.rows.get(SUMMARY, {}), **data})
        return strict_set(tx, ref, data, merge=merge)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', set_summary)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    return SimpleNamespace(client=client, month=month, remaining=remaining, choice=lambda: client.rows[SUMMARY])


async def test_trial_start_grants_newest_25_hours_once(owner):
    await worker.trial_started_async(UID, trialing())
    first = deepcopy(owner.choice())
    assert first['state'] == 'processing' and first['automatic'] is True
    assert first['remaining'] == GRANT and first['period'] == '2026-11'
    # A redelivery or a restart finds the receipt: same token, same budget.
    await worker.trial_started_async(UID, trialing())
    assert owner.choice()['token'] == first['token'] and owner.choice()['remaining'] == GRANT


async def test_month_rollover_never_starts_a_second_trial_grant(owner):
    await worker.trial_started_async(UID, trialing())
    owner.choice().update(state='waiting_choice')  # the grant finished in November
    owner.month['id'] = '2026-12'
    await worker.trial_started_async(UID, trialing())
    assert owner.choice()['state'] == 'waiting_choice' and owner.choice()['period'] == '2026-11'


async def test_trial_grant_stays_inside_a_smaller_finite_allowance(owner):
    owner.remaining['units'] = 3 * RATE
    await worker.trial_started_async(UID, trialing())
    assert owner.choice()['remaining'] == 3 * RATE


async def test_late_first_delivery_of_a_trial_start_is_stale_and_recorded(owner):
    await worker.trial_started_async(UID, trialing(trial_start=datetime(2026, 10, 31, tzinfo=timezone.utc).timestamp()))
    assert owner.choice() == {}
    receipts = [path for path in owner.client.rows if 'processing_backlog_requests' in path]
    assert len(receipts) == 1 and owner.client.rows[receipts[0]]['accepted'] is False


@pytest.mark.parametrize(
    'subscription',
    [
        trialing(status='active'),  # the first real charge, or a direct purchase with no trial
        trialing(status='past_due'),
        trialing(trial_start=None),
        trialing(id=None),
    ],
)
async def test_purchases_and_charges_start_nothing(monkeypatch, subscription):
    choose = Mock(side_effect=AssertionError('started recovery without a trial start'))
    monkeypatch.setattr(worker, 'choose', choose)
    await worker.trial_started_async(UID, subscription)


def test_payment_hands_every_subscription_event_to_the_release_hook_once():
    source = (Path(__file__).resolve().parents[2] / 'routers' / 'payment.py').read_text(encoding='utf-8')
    assert source.count('await subscription_changed_async(') == 1
    call = source.index('await subscription_changed_async(')
    gate = source.rindex('if ', 0, call)
    assert 'funded_processing_enabled(uid) and not adopted_active_paid' in source[gate:call]


def _subscription_event(kind, previous_status=None):
    previous = {'status': previous_status} if previous_status else {}
    return {'id': 'evt', 'type': kind, 'created': TRIAL_START, 'data': {'previous_attributes': previous}}


@pytest.fixture
def release_hooks(monkeypatch):
    """The real upgrade path down to choose(); Stripe and the trial grant are synthetic."""
    from models.users import PlanType

    calls = []
    increased = {'value': False}
    statuses = {}

    async def trial(uid, stripe_subscription):
        calls.append(('trial', stripe_subscription['id']))

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    monkeypatch.setattr(
        worker, 'choose', lambda uid, *, request_key, automatic, intent_at: calls.append(('conversion', request_key))
    )
    monkeypatch.setattr(worker, 'trial_started_async', trial)
    monkeypatch.setattr(worker, '_stripe_status', lambda subscription_id: statuses.get(subscription_id))
    monkeypatch.setattr(backlog, 'allowance_increased', lambda previous, current: increased['value'])
    paid = SimpleNamespace(plan=PlanType.unlimited_v2, stripe_subscription_id='sub_synthetic', current_period_end=9)
    return SimpleNamespace(
        calls=calls, increased=increased, statuses=statuses, paid=paid, basic=SimpleNamespace(plan=PlanType.basic)
    )


async def test_only_the_subscription_creation_grants_a_trial(release_hooks):
    created = _subscription_event('customer.subscription.created')
    await worker.subscription_changed_async(UID, created, trialing(), None, release_hooks.paid)
    # A plan change while trialing is an update: it never grants, even with no earlier receipt.
    updated = _subscription_event('customer.subscription.updated')
    await worker.subscription_changed_async(UID, updated, trialing(), release_hooks.paid, release_hooks.paid)
    created_free = _subscription_event('customer.subscription.created')
    await worker.subscription_changed_async(UID, created_free, trialing(), None, release_hooks.basic)
    assert release_hooks.calls == [('trial', trialing()['id'])]


async def test_a_trial_start_that_raises_the_allowance_releases_only_the_grant(release_hooks):
    """Basic -> Unlimited trial raises the allowance, but a trialing subscription never converts."""
    release_hooks.increased['value'] = True
    created = _subscription_event('customer.subscription.created')
    await worker.subscription_changed_async(UID, created, trialing(), None, release_hooks.paid)
    assert release_hooks.calls == [('trial', trialing()['id'])]


async def test_a_trial_converting_on_real_payment_releases_as_a_conversion(release_hooks):
    event = _subscription_event('customer.subscription.updated', previous_status='trialing')
    await worker.subscription_changed_async(
        UID, event, trialing(status='active'), release_hooks.paid, release_hooks.paid
    )
    assert release_hooks.calls == [('conversion', 'subscription-upgrade:evt')]
    release_hooks.calls.clear()
    past_due = _subscription_event('customer.subscription.updated', previous_status='trialing')
    await worker.subscription_changed_async(
        UID, past_due, trialing(status='past_due'), release_hooks.paid, release_hooks.paid
    )
    assert release_hooks.calls == []


async def test_a_paid_subscription_created_active_releases_even_after_checkout_stored_it(release_hooks):
    """The retry for a checkout whose Stripe lookup failed: the payload carries the status."""
    created = _subscription_event('customer.subscription.created')
    # The checkout handler already stored the plan, so no allowance increase is visible here.
    await worker.subscription_changed_async(
        UID, created, trialing(status='active'), release_hooks.paid, release_hooks.paid
    )
    # The real trial_started_async declines an active subscription (test_purchases_and_charges_start_nothing).
    assert release_hooks.calls == [('conversion', 'subscription-upgrade:evt'), ('trial', trialing()['id'])]
    release_hooks.calls.clear()
    renewal = _subscription_event('customer.subscription.updated')
    await worker.subscription_changed_async(
        UID, renewal, trialing(status='active'), release_hooks.paid, release_hooks.paid
    )
    assert release_hooks.calls == []


async def test_a_trial_checkout_never_converts_and_a_paid_one_does(release_hooks):
    release_hooks.increased['value'] = True
    event = {'id': 'evt', 'created': TRIAL_START}
    session = {'id': 'cs_synthetic', 'subscription': 'sub_synthetic'}
    for status in ('trialing', None, 'incomplete'):
        release_hooks.statuses['sub_synthetic'] = status
        await worker.checkout_completed_async(UID, event, session, None, release_hooks.paid)
    assert release_hooks.calls == []
    release_hooks.statuses['sub_synthetic'] = 'active'
    await worker.checkout_completed_async(UID, event, session, None, release_hooks.paid)
    assert release_hooks.calls == [('conversion', 'checkout:cs_synthetic')]


def test_a_plan_change_while_trialing_never_converts(release_hooks):
    release_hooks.increased['value'] = True
    release_hooks.statuses['sub_synthetic'] = 'trialing'
    worker.plan_changed(UID, 'price_synthetic', release_hooks.basic, release_hooks.paid, 'trialing')
    assert release_hooks.calls == []
    # The modified subscription's own status decides; no second Stripe lookup can fail.
    release_hooks.statuses['sub_synthetic'] = None
    worker.plan_changed(UID, 'price_synthetic', release_hooks.basic, release_hooks.paid, 'active')
    assert release_hooks.calls == [('conversion', 'plan-change:sub_synthetic:price_synthetic:9')]


def test_a_stripe_outage_is_retried_then_counted_not_silent(monkeypatch):
    import stripe

    attempts, errors = [], []

    def retrieve(subscription_id):
        attempts.append(subscription_id)
        raise RuntimeError('synthetic outage')

    monkeypatch.setattr(stripe.Subscription, 'retrieve', retrieve)
    monkeypatch.setattr(worker.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(worker, 'record_backlog_choice', lambda source, outcome: errors.append((source, outcome)))
    assert worker._stripe_status('sub_synthetic') is None
    assert len(attempts) == 3
    assert errors == [('conversion', worker.BacklogChoiceOutcome.ERROR)]


async def test_a_resumed_release_rereads_the_hold_and_passes_over_legacy_spend(monkeypatch):
    hold = SimpleNamespace(exists=True, to_dict=lambda: {'state': 'held', 'piece_receipts': {'p': {}}})
    holds = SimpleNamespace(document=lambda identity: SimpleNamespace(get=lambda: hold))
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: holds)
    monkeypatch.setattr(worker.cap_hold_recovery, 'recover_selected', AsyncMock(side_effect=AssertionError('legacy')))

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    token = worker.backlog_release.source.set('conversion')
    try:
        assert await worker._process(UID, {'kind': 'audio', 'id': 'hold'}) is worker.AttemptOutcome.DEFERRED
    finally:
        worker.backlog_release.source.reset(token)


def test_trial_grant_is_a_plain_config_value():
    assert TRIAL_RECOVERY_GRANT_HOURS == 25


async def test_a_second_trial_on_the_same_account_grants_nothing(owner):
    await worker.trial_started_async(UID, trialing())
    first = deepcopy(owner.choice())
    assert first['trial_granted_at'] and first['trial_grant'] is True
    assert first['release_priority_units'] == PRIORITY_HOURS * RATE
    owner.client.rows[SUMMARY]['state'] = 'waiting_choice'
    await worker.trial_started_async(UID, trialing(id='sub_second'))
    assert owner.choice()['state'] == 'waiting_choice'


def test_a_trial_grant_rolls_into_the_next_month_keeping_its_hours(monkeypatch):
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-12')
    job = {'state': 'processing', 'period': '2026-11', 'automatic': True, 'trial_grant': True}
    assert backlog.rolls(job, 50.0)
    assert not backlog.rolls({**job, 'trial_grant': False}, None)


async def test_kill_switch_stops_a_release_already_running(monkeypatch):
    monkeypatch.setenv('BACKLOG_RELEASE_ENABLED', 'false')
    monkeypatch.setattr(worker, 'recovery_cohort_admits', lambda uid: True)
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'paid_owner', lambda uid: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(worker, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(
        worker.store, 'read', lambda uid: {'state': 'processing', 'period': '2026-11', 'automatic': True, 'token': 't'}
    )
    claim = Mock(side_effect=AssertionError('claimed past the kill switch'))
    monkeypatch.setattr(worker.store, 'claim', claim)

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)
    assert await worker.run(UID) is None
    claim.assert_not_called()


@pytest.fixture
def grant_run(monkeypatch):
    """Drive one fenced worker visit over synthetic newest-first holds."""
    monkeypatch.setattr(
        worker.backlog_release, 'decide', lambda uid, job, units, **kw: worker.backlog_release.Decision(True, 'granted')
    )
    job = {
        'state': 'processing',
        'period': '2026-11',
        'token': 'grant',
        'cutoff': 1000.0,
        'remaining': GRANT,
        'automatic': True,
        'reserved': {},
    }
    finished = []
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(worker, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: deepcopy(job))
    monkeypatch.setattr(worker.store, 'claim', lambda *a: 'lease')

    def checkpoint(uid, token, lease, updates):
        job.update(deepcopy(updates))
        return True

    monkeypatch.setattr(worker.store, 'checkpoint', checkpoint)
    monkeypatch.setattr(worker.store, 'finish', lambda *a: finished.append(True) or False)
    # Unlimited: the owner's own allowance never limits; only the grant does.
    monkeypatch.setattr(funded, 'allowance', lambda uid: SimpleNamespace(managed=True))
    monkeypatch.setattr(funded, 'capacity', lambda allowance: (None, None))
    monkeypatch.setattr(worker, '_selected', AsyncMock(return_value=True))
    processed, sources = [], []

    async def process(uid, item):
        processed.append(item['id'])
        sources.append(worker.backlog_release.source.get())
        return worker.AttemptOutcome.COMPLETE

    monkeypatch.setattr(worker, '_process', process)

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', immediate)

    def holds(rows):
        monkeypatch.setattr(
            worker,
            '_page',
            lambda uid, kind, cursor: (
                [
                    ('audio', SimpleNamespace(id=name, to_dict=lambda row=row: dict(row)))
                    for name, row in rows
                    if not cursor or row['listed_at'] < cursor['at']
                ]
                if kind == 'audio'
                else []
            ),
        )
        monkeypatch.setattr(worker.cap_hold, 'remaining_seconds', lambda row: row['seconds'])

    return SimpleNamespace(job=job, processed=processed, sources=sources, finished=finished, holds=holds)


async def test_trial_grant_spends_newest_first_and_stops_at_25_hours(grant_run):
    hour = 3600
    grant_run.holds(
        [
            (f'hold-{index}', {'listed_at': 900 - index, 'created_at': 500, 'seconds': 10 * hour, 'state': 'held'})
            for index in range(4)
        ]
    )
    await worker.run(UID)
    # 10 h + 10 h fit; the next 10 h does not fit the 5 h left, nor does the one after it.
    assert grant_run.processed == ['hold-0', 'hold-1']
    assert grant_run.job['remaining'] == pytest.approx(5 * RATE)
    assert grant_run.finished == [True]


async def test_new_recordings_on_a_trial_never_count_against_the_grant(grant_run):
    hour = 3600
    grant_run.holds(
        [
            # Arrived after the grant began (its cutoff): not part of the grant.
            ('new', {'listed_at': 2000, 'created_at': 2000, 'seconds': 20 * hour, 'state': 'held'}),
            ('held', {'listed_at': 900, 'created_at': 500, 'seconds': 1 * hour, 'state': 'held'}),
        ]
    )
    await worker.run(UID)
    assert grant_run.processed == ['held']
    assert grant_run.job['remaining'] == pytest.approx(GRANT - RATE)


async def test_each_released_recording_carries_its_source_to_admission(grant_run):
    hour = 3600
    grant_run.holds([('held', {'listed_at': 900, 'created_at': 500, 'seconds': 1 * hour, 'state': 'held'})])
    grant_run.job['trial_grant'] = True
    await worker.run(UID)
    assert grant_run.sources == ['trial']
    assert worker.backlog_release.source.get() is None


async def test_an_automatic_release_passes_over_a_hold_legacy_already_started(grant_run):
    """Legacy spend pins a hold to the legacy route, outside the idle gate and vendor table."""
    hour = 3600
    grant_run.holds(
        [
            (
                'legacy',
                {'listed_at': 900, 'created_at': 500, 'seconds': hour, 'state': 'held', 'piece_receipts': {'p': {}}},
            ),
            ('batch', {'listed_at': 800, 'created_at': 500, 'seconds': hour, 'state': 'held'}),
        ]
    )
    await worker.run(UID)
    assert grant_run.processed == ['batch']
    assert grant_run.job['remaining'] == pytest.approx(GRANT - RATE)


def test_new_recordings_on_a_trial_transcribe_normally(monkeypatch):
    """A trial is a paid Unlimited plan; its allowance never reads the recovery grant."""
    from models.users import PlanType, Subscription

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setattr(store, 'read', Mock(side_effect=AssertionError('intake read the recovery grant')))
    trial = Subscription(plan=PlanType.unlimited_v2, current_period_end=int(TRIAL_START) + 30 * 86400)
    result = funded.allowance(UID, subscription=trial, usage={'transcription_seconds': 10**7})
    assert result.managed
