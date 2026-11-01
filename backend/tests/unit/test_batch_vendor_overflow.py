"""GPU-capacity overflow: fresh units start on a vendor while the GPU ring is past its SLO."""

import copy
import json
from types import SimpleNamespace

import pytest

from config.batch_pipeline import Priority
from config.batch_pipeline_vendor_overflow import thresholds
from config.policy.batch import cohort_bucket
from database import batch_pipeline_store as bps
from tests.unit.test_batch_language_eligibility import admitted, upload
from utils.batch_pipeline import gpu_overflow, intake
from utils.batch_pipeline import route_selection as rs
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline import vendor_route_metrics as m
from utils.observability.reasons import VendorHealthReason, VendorRouteReason as Reason

SUPPORTED = 'en'
UNSUPPORTED = 'ja'
UID = 'synthetic-owner-1'


def _route(price, *, failover_only=False):
    return {
        'price_usd_per_audio_hour': price,
        'daily_audio_hours_cap': None,
        'monthly_budget_usd': None,
        'failover_only': failover_only,
        'speaker_turns': 'discard',
    }


def _option(route):
    return {'route': route, 'quality_tier': 'accepted', 'quality_source': 'legacy_parity'}


# The Monday overflow table shape: GPU first where Parakeet serves, Modulate next, Soniox failover.
TABLE = {
    'schema_version': 1,
    'table_version': 'overflow-t1',
    'selection': 'ordered',
    'gpu_floor_percent': 0.0,
    'routes': {
        'gpu': _route(0.001),
        'modulate': _route(0.0434),
        'soniox': _route(0.1134, failover_only=True),
    },
    'rows': [
        {'language_class': 'gpu_supported', 'options': [_option('gpu'), _option('modulate'), _option('soniox')]},
        {'language_class': '*', 'options': [_option('modulate'), _option('soniox')]},
    ],
}


class Health:
    def __init__(self, down=()):
        self.down = set(down)

    def allows(self, service):
        if service in self.down:
            return False, VendorHealthReason.BREAKER_OPEN
        return True, VendorHealthReason.HEALTHY


class Probe:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def __call__(self):
        self.calls += 1
        return self.answer


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in c.FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rs, '_tables', rs._TableCache())
    monkeypatch.setattr(rs, '_health', c.AlwaysHealthy())
    monkeypatch.setattr(gpu_overflow, '_overflow', None)


def _cohort(monkeypatch, table=TABLE):
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_PERCENT', '100')
    monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', json.dumps(table))


def _select(language, probe, *, uid=UID, eligible=True):
    return rs.select_route(
        language, byok=False, uid=uid, batch_percent=100.0, vendor_eligible=eligible, gpu_saturated=probe
    )


# --- selection -------------------------------------------------------------------------------------


def test_saturated_gpu_overflows_a_supported_unit_to_modulate_with_soniox_failover(monkeypatch):
    _cohort(monkeypatch)
    decision = _select(SUPPORTED, Probe(True))
    assert (decision.selected, decision.reason) == ('modulate', Reason.GPU_OVERFLOW)
    assert decision.route.stt_route == 'provider' and decision.route.provider_service == 'modulate'
    assert decision.route.provider_reason == 'none'  # a vendor chosen over a capable GPU
    assert decision.failover == ('soniox',)


def test_unsaturated_gpu_keeps_the_unit_on_gpu(monkeypatch):
    _cohort(monkeypatch)
    probe = Probe(False)
    decision = _select(SUPPORTED, probe)
    assert (decision.selected, decision.reason) == ('gpu', Reason.ORDERED)
    assert probe.calls == 1


def test_no_probe_means_no_overflow(monkeypatch):
    _cohort(monkeypatch)
    assert _select(SUPPORTED, None).selected == 'gpu'


def test_overflow_never_spends_soniox_as_a_primary(monkeypatch):
    # Modulate down: the only other capable route is failover-only, so the unit waits for GPU.
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, '_health', Health(down={'modulate'}))
    probe = Probe(True)
    decision = _select(SUPPORTED, probe)
    assert decision.selected == 'gpu' and probe.calls == 0


def test_floor_share_never_overflows_and_never_reads_the_backlog(monkeypatch):
    _cohort(monkeypatch, {**copy.deepcopy(TABLE), 'gpu_floor_percent': 100.0})
    probe = Probe(True)
    decision = _select(SUPPORTED, probe)
    assert (decision.selected, decision.reason) == ('gpu', Reason.GPU_FLOOR)
    assert probe.calls == 0


def test_floor_share_splits_owners_under_overflow(monkeypatch):
    _cohort(monkeypatch, {**copy.deepcopy(TABLE), 'gpu_floor_percent': 50.0})
    uids = [f'synthetic-owner-{i}' for i in range(400)]
    on_gpu = {uid for uid in uids if _select(SUPPORTED, Probe(True), uid=uid).selected == 'gpu'}
    assert on_gpu == {uid for uid in uids if cohort_bucket(uid, c.GPU_FLOOR_COHORT_SALT) < 50.0}


def test_unsupported_language_is_untouched_by_overflow(monkeypatch):
    _cohort(monkeypatch)
    probe = Probe(True)
    decision = _select(UNSUPPORTED, probe)
    assert (decision.selected, decision.reason) == ('modulate', Reason.SOLE_CAPABLE)
    assert probe.calls == 0


def test_cheapest_vendor_first_is_not_overflow(monkeypatch):
    table = {**copy.deepcopy(TABLE), 'selection': 'cheapest'}
    table['routes']['gpu']['price_usd_per_audio_hour'] = 0.07
    _cohort(monkeypatch, table)
    probe = Probe(True)
    assert (_select(SUPPORTED, probe).reason, probe.calls) == (Reason.CHEAPEST, 0)


def test_overflow_is_dormant_outside_the_cohort_and_while_legacy_is_on(monkeypatch):
    probe = Probe(True)
    monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', json.dumps(TABLE))
    assert _select(SUPPORTED, probe).reason is Reason.NOT_IN_COHORT  # routing percent 0
    _cohort(monkeypatch)
    assert _select(SUPPORTED, probe, eligible=False).reason is Reason.NOT_IN_COHORT
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_ENABLED', 'false')
    assert _select(SUPPORTED, probe).reason is Reason.KILL_SWITCH
    assert probe.calls == 0


def test_a_raising_probe_serves_todays_routing(monkeypatch):
    _cohort(monkeypatch)

    def boom():
        raise RuntimeError('backlog read failed')

    decision = _select(SUPPORTED, boom)
    assert decision.selected == 'gpu' and decision.route.stt_route == 'parakeet'


# --- thresholds ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'enter,exit_,expected',
    [
        (None, None, (1200.0, 600.0)),
        ('900', '300', (900.0, 300.0)),
        ('900', '900', (900.0, 450.0)),  # exit at/above enter would never leave: half of enter
        ('nan', 'x', (1200.0, 600.0)),
        ('5', '999999', (1200.0, 600.0)),  # out of range keeps defaults
    ],
)
def test_thresholds(monkeypatch, enter, exit_, expected):
    for name, value in (('BATCH_VENDOR_OVERFLOW_ENTER_SECONDS', enter), ('BATCH_VENDOR_OVERFLOW_EXIT_SECONDS', exit_)):
        if value is not None:
            monkeypatch.setenv(name, value)
    assert thresholds() == expected


# --- the backlog signal ----------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 10_000.0

    def __call__(self):
        return self.now


def _overflow(ages, clock):
    """GpuOverflow whose sample returns the next backlog age (None: empty ring) synchronously."""
    samples = []

    def sample(now):
        samples.append(now)
        age = ages.pop(0)
        if isinstance(age, Exception):
            raise age
        return None if age is None else now - age

    return GpuOverflow(sample, clock=clock, monotonic=clock, submit=lambda fn: fn()), samples


GpuOverflow = gpu_overflow.GpuOverflow


def test_hysteresis_enters_at_enter_and_leaves_below_exit():
    clock = Clock()
    overflow, _ = _overflow([1199.0, 1200.0, 700.0, 600.0, 599.0, None], clock)
    answers = []
    for _ in range(6):
        answers.append(overflow.saturated())
        clock.now += gpu_overflow.REFRESH_SECONDS
    assert answers == [False, True, True, True, False, False]
    assert m.GPU_OVERFLOW_ACTIVE._value.get() == 0


def test_one_read_per_refresh_window():
    clock = Clock()
    overflow, samples = _overflow([1500.0, 0.0], clock)
    assert [overflow.saturated() for _ in range(50)] == [True] * 50
    assert len(samples) == 1
    assert m.GPU_BACKLOG_AGE._value.get() == 1500.0


def test_a_failed_read_answers_not_saturated():
    clock = Clock()
    overflow, _ = _overflow([1500.0, RuntimeError('firestore unavailable')], clock)
    assert overflow.saturated() is True
    clock.now += gpu_overflow.REFRESH_SECONDS
    assert overflow.saturated() is False


def test_an_unschedulable_read_answers_not_saturated():
    def refuse(fn):
        raise RuntimeError('executor shut down')

    overflow = GpuOverflow(lambda now: 0.0, submit=refuse)
    assert overflow.saturated() is False


def test_cold_process_answers_not_saturated_until_the_read_lands():
    pending = []
    overflow = GpuOverflow(lambda now: now - 5000.0, submit=pending.append)
    assert overflow.saturated() is False
    assert overflow.saturated() is False and len(pending) == 1  # one read in flight, not two
    pending.pop()()
    assert overflow.saturated() is True


def test_kill_switch_answers_not_saturated_without_reading(monkeypatch):
    monkeypatch.setenv('BATCH_VENDOR_OVERFLOW_ENABLED', 'false')
    samples = []
    overflow = GpuOverflow(lambda now: samples.append(now) or 0.0, submit=lambda fn: fn())
    assert overflow.saturated() is False and samples == []


def test_store_binding_reads_the_fresh_priority_once_per_process(monkeypatch):
    asked = []

    class Store:
        def oldest_admissible_ready(self, priority, now):
            asked.append(priority)
            return now - 5000.0

    monkeypatch.setattr(gpu_overflow, '_submit', lambda fn: fn())
    assert gpu_overflow.saturated(Store()) is True
    bound = gpu_overflow._overflow
    assert gpu_overflow.saturated(Store()) is True and gpu_overflow._overflow is bound
    assert asked == [int(Priority.FRESH)]


def test_store_without_the_read_never_overflows():
    assert gpu_overflow.saturated(SimpleNamespace()) is False
    assert gpu_overflow._overflow is None


# --- the store read --------------------------------------------------------------------------------

NOW = 50_000.0


def _job(enqueued_at, **overrides):
    job = {
        'state': 'ready',
        'merge_pending': True,
        'compute_decision': {'outcome': 'allowed'},
        'available_at': NOW - 1,
        'enqueued_at': enqueued_at,
    }
    job.update(overrides)
    return job


@pytest.mark.parametrize(
    'overrides,expected',
    [
        ({}, True),
        ({'compute_decision': {'outcome': 'unattempted'}}, True),
        ({'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'}}, False),
        ({'compute_decision': None, 'last_policy_hold': {'reason': 'allowance_exhausted'}}, False),
        ({'available_at': NOW + 60}, False),  # a deferred retry is not backlog yet
        ({'merge_pending': False}, False),
        ({'available_at': None}, False),
    ],
)
def test_admissible_ready_predicate(overrides, expected):
    assert bps.is_admissible_ready(_job(1.0, **overrides), NOW) is expected


class FakeQuery:
    def __init__(self, docs, log):
        self.docs, self.log = docs, log

    def where(self, field, op, value):
        self.log.append(('where', field, op, value))
        return self

    def order_by(self, field):
        self.log.append(('order_by', field))
        return self

    def limit(self, n):
        self.log.append(('limit', n))
        self.docs = self.docs[:n]
        return self

    def stream(self):
        return iter(SimpleNamespace(to_dict=lambda job=job: dict(job)) for job in self.docs)


class FakeClient:
    def __init__(self, docs):
        self.docs, self.log = docs, []

    def collection(self, name):
        self.log.append(('collection', name))
        return FakeQuery(self.docs, self.log)


def test_oldest_admissible_ready_skips_holds_and_deferred_rows():
    client = FakeClient(
        [
            _job(10.0, compute_decision={'outcome': 'held', 'reason': 'allowance_exhausted'}),
            _job(20.0, available_at=NOW + 300),
            _job(30.0),
            _job(40.0),
        ]
    )
    assert bps.oldest_admissible_ready(client, 'batch_pipeline_prod', 0, NOW) == 30.0
    assert client.log[:5] == [
        ('collection', 'batch_pipeline_prod_jobs'),
        ('where', 'priority', '==', 0),
        ('where', 'state', '==', 'ready'),
        ('order_by', 'enqueued_at'),
        ('limit', bps.ADMISSIBLE_READY_SCAN_LIMIT),
    ]


def test_a_prefix_of_holds_reads_as_no_backlog():
    held = {'compute_decision': {'outcome': 'held', 'reason': 'allowance_exhausted'}}
    client = FakeClient([_job(float(i), **held) for i in range(bps.ADMISSIBLE_READY_SCAN_LIMIT)] + [_job(999.0)])
    assert bps.oldest_admissible_ready(client, 'batch_pipeline_prod', 0, NOW) is None


# --- intake ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('priority,offered', [(Priority.FRESH, True), (Priority.RECENT, False), (Priority.DEEP, False)])
async def test_intake_offers_overflow_to_fresh_units_only(monkeypatch, priority, offered):
    seen = {}
    real = intake.select_route

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    reads = []
    monkeypatch.setattr(intake, 'select_route', spy)
    monkeypatch.setattr(intake, 'priority_for', lambda lane, age: priority)
    monkeypatch.setattr(intake.gpu_overflow, 'saturated', lambda store: reads.append(store) or False)
    response, staged, _ = await upload(monkeypatch, user_language='en', single=True, mode='draining')
    assert admitted(response, staged)
    if offered:
        assert seen['gpu_saturated']() is False and len(reads) == 1
    else:
        assert seen['gpu_saturated'] is None
