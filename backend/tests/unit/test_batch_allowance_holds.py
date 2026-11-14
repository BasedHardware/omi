"""The generation changes only with plan authority or the usage period."""

from datetime import datetime, timezone
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.allowance_hold import generation
from database.batch_pipeline_allowance_hold import enabled
from utils.batch_pipeline import allowance_hold
from utils import backfill_hours_cap, stt_cap_dispatch

# entitlement() imports utils.subscription lazily. Load it at collection so the
# first test that reaches entitlement() is not charged the one-time import.
from utils import subscription as _subscription  # noqa: F401
from utils.batch_pipeline.scheduler import Scheduler
from utils.referral_campaign import CAMPAIGN_ID, GRANT_FIELD, effective_subscription_payload
from utils.transcription_allowance import TranscriptionAllowance
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def test_usage_counter_changes_do_not_reoffer_a_generation_but_plan_and_month_do():
    start = stamp('2026-11-14')
    user = {'subscription': {'plan': 'basic', 'status': 'active'}}
    first = generation(user, start)
    assert generation({**user, 'usage': 0, 'display_name': 'unrelated'}, start + 3600) == first
    assert generation({'subscription': {'plan': 'unlimited', 'status': 'active'}}, start) != first
    assert generation(user, stamp('2026-12-01')) != first


def test_subscription_expiry_changes_generation_without_a_writer():
    now = stamp('2026-11-14')
    user = {'subscription': {'plan': 'plus', 'current_period_end': now + 60}}
    assert generation(user, now) != generation(user, now + 61)


def test_enabled_backfill_daily_cap_has_a_daily_generation(monkeypatch):
    monkeypatch.setattr(backfill_hours_cap, 'cap_enabled', lambda: True)
    user = {'subscription': {'plan': 'unlimited_v2', 'status': 'active'}}
    start = stamp('2026-11-14')
    assert generation(user, start) == generation(user, start + 86399)
    assert generation(user, start) != generation(user, start + 86400)


@pytest.fixture
def discovery(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    now = stamp('2026-11-14')
    user = {'subscription': {'plan': 'basic', 'status': 'active'}}
    clock = [now]
    document = Mock()

    def projected_read(*, field_paths):
        projected = {key: deepcopy(user[key]) for key in field_paths if key in user}
        return SimpleNamespace(exists=True, to_dict=lambda: projected)

    document.get.side_effect = projected_read
    client = Mock()
    client.collection.return_value.document.return_value = document
    monkeypatch.setattr(allowance_hold, 'get_data_plane_firestore_client', lambda: client)

    def funding(uid, *, lane):
        assert lane == 'batch'
        effective = effective_subscription_payload(
            user['subscription'], user.get(GRANT_FIELD), now=datetime.fromtimestamp(clock[0], timezone.utc)
        )
        managed = effective['plan'] == 'unlimited_v2'
        return TranscriptionAllowance('managed' if managed else 'on_device', None if managed else 0, 'resolved')

    funded = Mock(side_effect=funding)
    monkeypatch.setattr(stt_cap_dispatch, 'funded_allowance', funded)
    return SimpleNamespace(user=user, now=now, clock=clock, document=document, funded=funded)


def discover(fixture, at, previous=None):
    fixture.clock[0] = at
    return allowance_hold.entitlement('synthetic-owner', at, previous)


@pytest.mark.parametrize('reason', ['usage_invalid', 'allowance_unavailable'])
def test_untrusted_usage_does_not_acknowledge_generation(discovery, reason):
    discovery.funded.side_effect = [
        TranscriptionAllowance('on_device', 0, reason),
        TranscriptionAllowance('managed', None, 'resolved'),
    ]
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held', owner='synthetic-owner'), 0)
    lease = queue.pull(1)[0]
    assert queue.defer('held', lease.token, 2, held_reason='allowance_exhausted')
    controller = allowance_hold.AllowanceHolds(store, allowance_hold.entitlement)
    assert controller.tick(discovery.now) == 0
    mark = store.rows['allowance_holds', store.rows['jobs', 'held']['owner_key']]
    assert 'generation' not in mark
    assert controller.tick(discovery.now + 121) == 1
    assert store.rows['jobs', 'held']['state'] == 'ready'


def test_reparked_daily_cap_refusal_releases_after_utc_reset(discovery, monkeypatch):
    monkeypatch.setattr(backfill_hours_cap, 'cap_enabled', lambda: True)
    discovery.funded.side_effect = lambda *args, **kwargs: TranscriptionAllowance('managed', None, 'resolved')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held', owner='synthetic-owner'), 0)
    lease = queue.pull(1)[0]
    assert queue.defer('held', lease.token, 2, held_reason='allowance_exhausted')
    controller = allowance_hold.AllowanceHolds(store, allowance_hold.entitlement)
    assert controller.tick(discovery.now) == 1
    # Ordinary backfill admission can still reject the same day's reoffer.
    lease = queue.pull(discovery.now + 1)[0]
    assert queue.defer('held', lease.token, discovery.now + 2, held_reason='allowance_exhausted')
    assert controller.tick(discovery.now + 301) == 0
    assert store.rows['jobs', 'held']['state'] == 'allowance_held'
    assert controller.tick(discovery.now + 86400) == 1
    assert store.rows['jobs', 'held']['state'] == 'ready'


def grant(start, end, **fields):
    return {'campaign_id': CAMPAIGN_ID, 'status': 'active', 'starts_at': int(start), 'ends_at': int(end), **fields}


def test_actual_discovery_resolver_releases_acknowledged_owner_after_referral_claim(discovery):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('held', owner='synthetic-owner'), 0)
    lease = queue.pull(1)[0]
    assert queue.defer('held', lease.token, 2, held_reason='allowance_exhausted')
    controller = allowance_hold.AllowanceHolds(store, allowance_hold.entitlement)
    assert controller.tick(discovery.now) == 0
    discovery.user[GRANT_FIELD] = grant(discovery.now, discovery.now + 86400)
    discovery.clock[0] = discovery.now + 301
    assert controller.tick(discovery.clock[0]) == 1
    assert store.rows['jobs', 'held']['state'] == 'ready'
    assert discovery.funded.call_count == 2
    assert discovery.document.get.call_args.kwargs['field_paths'] == ['subscription', GRANT_FIELD]


def test_referral_extension_is_acknowledged_once_without_commercial_or_usage_changes(discovery):
    discovery.user[GRANT_FIELD] = grant(discovery.now - 1, discovery.now + 86400)
    first, allowed = discover(discovery, discovery.now)
    assert allowed
    assert discover(discovery, discovery.now + 1, first) == (first, False)
    discovery.user['usage'] = 0  # Usage counter changes must not cause another funded evaluation.
    assert discover(discovery, discovery.now + 2, first) == (first, False)
    discovery.user[GRANT_FIELD]['ends_at'] += 86400
    extended, allowed = discover(discovery, discovery.now + 3, first)
    assert extended != first and allowed
    assert discover(discovery, discovery.now + 4, extended) == (extended, False)
    assert discovery.funded.call_count == 2


def test_scheduled_referral_activation_and_expiry_change_discovery_without_writes(discovery):
    discovery.user[GRANT_FIELD] = grant(discovery.now + 100, discovery.now + 200)
    pending, allowed = discover(discovery, discovery.now)
    assert not allowed
    active, allowed = discover(discovery, discovery.now + 100, pending)
    assert active != pending and allowed
    expired, allowed = discover(discovery, discovery.now + 200, active)
    assert expired != active and not allowed
    assert discover(discovery, discovery.now + 201, expired) == (expired, False)
    assert discovery.funded.call_count == 3


def test_paid_coverage_boundaries_recheck_effective_grant_without_writes(discovery):
    discovery.user[GRANT_FIELD] = grant(
        discovery.now - 1,
        discovery.now + 86400,
        paid_coverage=[{'start': int(discovery.now + 100), 'end': int(discovery.now + 200)}],
    )
    active, allowed = discover(discovery, discovery.now)
    assert allowed
    covered, allowed = discover(discovery, discovery.now + 100, active)
    assert covered != active and not allowed
    resumed, allowed = discover(discovery, discovery.now + 200, covered)
    assert resumed != covered and allowed
    assert discovery.funded.call_count == 3


@pytest.mark.parametrize(
    'value,expected', [(None, True), ('on', True), ('OFF', False), (' off ', False), ('false', True)]
)
def test_switch_is_on_unless_explicitly_off(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('BATCH_ALLOWANCE_PARK_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_ALLOWANCE_PARK_ENABLED', value)
    assert enabled() is expected
