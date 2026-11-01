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
    for name in (*c.FLAGS, 'BATCH_LEGACY_CAPACITY_FALLBACK_ENABLED'):
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
    'enter,expected',
    [
        (None, (1200.0, 600.0)),
        ('900', (900.0, 450.0)),  # exit is half of enter
        ('nan', (1200.0, 600.0)),
        ('5', (1200.0, 600.0)),  # out of range keeps the default
        ('999999', (1200.0, 600.0)),
    ],
)
def test_thresholds(monkeypatch, enter, expected):
    if enter is not None:
        monkeypatch.setenv('BATCH_VENDOR_OVERFLOW_ENTER_SECONDS', enter)
    assert thresholds() == expected


# --- the backlog signal ----------------------------------------------------------------------------

BUSY = 1000  # admissible fresh units waiting: above the default 300 gate


class Clock:
    def __init__(self):
        self.now = 10_000.0

    def __call__(self):
        return self.now


def _overflow(readings, clock):
    """GpuOverflow whose sample returns the next (age, waiting) reading synchronously; age None: empty."""
    samples = []

    def sample(now):
        samples.append(now)
        reading = readings.pop(0)
        if isinstance(reading, Exception):
            raise reading
        age, waiting = reading
        return (None if age is None else now - age), waiting

    return GpuOverflow(sample, clock=clock, monotonic=clock, submit=lambda fn: fn()), samples


def _answers(overflow, clock, n):
    answers = []
    for _ in range(n):
        answers.append(overflow.saturated())
        clock.now += gpu_overflow.REFRESH_SECONDS
    return answers


GpuOverflow = gpu_overflow.GpuOverflow


def test_hysteresis_enters_at_enter_and_leaves_below_exit():
    clock = Clock()
    ages = [1199.0, 1200.0, 700.0, 600.0, 599.0, None]
    overflow, _ = _overflow([(age, BUSY) for age in ages], clock)
    assert _answers(overflow, clock, 6) == [False, True, True, True, False, False]
    assert m.GPU_OVERFLOW_ACTIVE._value.get() == 0


def test_stuck_heads_are_not_a_backlog():
    # 11-01 18:01Z shape: 111 admissible fresh units, the oldest 42 h old, an idle ring.
    clock = Clock()
    overflow, _ = _overflow([(153_175.0, 111)] * 3, clock)
    assert _answers(overflow, clock, 3) == [False, False, False]


def test_saturation_ends_when_the_backlog_drains_below_half_the_gate():
    clock = Clock()
    overflow, _ = _overflow([(1500.0, 300), (1500.0, 150), (1500.0, 149)], clock)
    assert _answers(overflow, clock, 3) == [True, True, False]


def test_min_ready_units_is_tunable(monkeypatch):
    monkeypatch.setenv('BATCH_VENDOR_OVERFLOW_MIN_READY_UNITS', '50')
    clock = Clock()
    overflow, _ = _overflow([(1500.0, 111)], clock)
    assert overflow.saturated() is True


def test_one_read_per_refresh_window():
    clock = Clock()
    overflow, samples = _overflow([(1500.0, BUSY), (0.0, 0)], clock)
    assert [overflow.saturated() for _ in range(50)] == [True] * 50
    assert len(samples) == 1
    assert m.GPU_BACKLOG_AGE._value.get() == 1500.0


def test_a_failed_read_answers_not_saturated():
    clock = Clock()
    overflow, _ = _overflow([(1500.0, BUSY), RuntimeError('firestore unavailable')], clock)
    assert overflow.saturated() is True
    clock.now += gpu_overflow.REFRESH_SECONDS
    assert overflow.saturated() is False


def test_an_unschedulable_read_answers_not_saturated():
    def refuse(fn):
        raise RuntimeError('executor shut down')

    overflow = GpuOverflow(lambda now: (0.0, BUSY), submit=refuse)
    assert overflow.saturated() is False


def test_cold_process_answers_not_saturated_until_the_read_lands():
    pending = []
    overflow = GpuOverflow(lambda now: (now - 5000.0, BUSY), submit=pending.append)
    assert overflow.saturated() is False
    assert overflow.saturated() is False and len(pending) == 1  # one read in flight, not two
    pending.pop()()
    assert overflow.saturated() is True


def test_store_binding_reads_the_fresh_priority_once_per_process(monkeypatch):
    asked = []

    class Store:
        def oldest_admissible_ready(self, priority, now):
            asked.append(('oldest', priority))
            return now - 5000.0

        def ready_for_capacity(self, priority, now):
            asked.append(('count', priority))
            return BUSY

    monkeypatch.setattr(gpu_overflow, '_submit', lambda fn: fn())
    assert gpu_overflow.saturated(Store()) is True
    bound = gpu_overflow._overflow
    assert gpu_overflow.saturated(Store()) is True and gpu_overflow._overflow is bound
    fresh = int(Priority.FRESH)
    assert asked == [('oldest', fresh), ('count', fresh)]


def test_store_without_the_reads_never_saturates():
    assert gpu_overflow.saturated(SimpleNamespace(ready_for_capacity=lambda p, n: BUSY)) is False
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
    monkeypatch.setattr(intake.gpu_overflow, 'saturated', lambda store: reads.append(store) or True)
    response, staged, _ = await upload(monkeypatch, user_language='en', single=True, mode='draining')
    assert admitted(response, staged)  # draining: no legacy to fall back to
    if offered:
        assert seen['gpu_saturated']() is True and len(reads) == 1
        monkeypatch.setenv('BATCH_VENDOR_OVERFLOW_ENABLED', 'false')
        assert seen['gpu_saturated']() is False and len(reads) == 1  # the switch is checked first
    else:
        assert seen['gpu_saturated'] is None


def _fallbacks(monkeypatch):
    recorded = []
    monkeypatch.setattr(intake, 'record_fallback', lambda **labels: recorded.append(labels))
    return recorded


@pytest.mark.asyncio
async def test_saturated_ring_keeps_a_fresh_legacy_on_upload_on_legacy(monkeypatch):
    recorded = _fallbacks(monkeypatch)
    monkeypatch.setattr(intake.gpu_overflow, 'saturated', lambda store: True)
    response, staged, probe = await upload(monkeypatch, user_language='en', single=True, mode='on')
    assert response is None and staged == [] and not probe.called  # legacy dispatch, no custody
    assert recorded == [
        {
            'component': 'sync_dispatch',
            'from_mode': 'batch',
            'to_mode': 'legacy',
            'reason': 'capacity_full',
            'outcome': 'recovered',
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    ['not_saturated', 'backfill', 'draining', 'dark', 'kill_switch', 'batch_owned_conversation'],
)
async def test_capacity_fallback_never_applies_outside_its_case(monkeypatch, case):
    recorded = _fallbacks(monkeypatch)
    asked = []
    saturated = case != 'not_saturated'
    monkeypatch.setattr(intake.gpu_overflow, 'saturated', lambda store: asked.append(store) or saturated)
    if case == 'backfill':
        monkeypatch.setattr(intake, 'priority_for', lambda lane, age: Priority.DEEP)
    if case == 'kill_switch':
        monkeypatch.setenv('BATCH_LEGACY_CAPACITY_FALLBACK_ENABLED', 'false')
    response, staged, _ = await upload(
        monkeypatch,
        user_language='en',
        single=True,
        mode=case if case in ('draining', 'dark') else 'on',
        conversation_language='en' if case == 'batch_owned_conversation' else None,
        owner='batch_sync_v1' if case == 'batch_owned_conversation' else None,
    )
    assert admitted(response, staged)
    assert all(labels['reason'] != 'capacity_full' for labels in recorded)
    if case in ('backfill', 'kill_switch', 'batch_owned_conversation'):
        assert asked == []  # the backlog is never read when the fallback cannot apply
