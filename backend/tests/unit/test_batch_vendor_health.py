"""Batch vendor health (slice C): ops 1.4 breaker replayed on real outage signatures, caps, probes, fallback."""

from __future__ import annotations

import itertools
import json
import math

import fakeredis
import pytest

from config import batch_pipeline_vendor_health as config
from utils.batch_pipeline import vendor_health as vh
from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.observability.reasons import VendorAttemptOutcome as O, VendorHealthReason as R
from utils.stt import vendor_guard

START = 1_761_955_200.0  # 2025-11-01T00:00:00Z, a UTC day and month boundary


class Clock:
    def __init__(self, now: float = START + 3600) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _route(price=0.03, cap=None, budget=None, failover_only=False):
    return contracts.RouteConfig(
        price_usd_per_audio_hour=price,
        daily_audio_hours_cap=cap,
        monthly_budget_usd=budget,
        failover_only=failover_only,
    )


def _service(clock, *, shared=None, routes=None, settings=None, enabled=True, rng=None):
    return vh.VendorHealthService(
        shared=shared,
        routes=(lambda: routes) if routes is not None else vh._builtin_routes,
        settings=settings or (lambda: config.DEFAULT_SETTINGS),
        enabled=lambda: enabled,
        clock=clock,
        rng=rng or itertools.cycle([0.25, 0.75]).__next__,
        background=False,
    )


@pytest.fixture
def admit_soniox(monkeypatch):
    # Slice D admits Soniox on the prerecorded surface; until then policy says NOT_ADMITTED.
    monkeypatch.setattr(vh, 'provider_is_enabled', lambda service, surface: service in contracts.VENDOR_SERVICES)


class Pattern:
    """Exact-rate deterministic outcome stream: the k-th call fails iff floor((k+1)p) > floor(kp)."""

    def __init__(self, rate: float, failure: O, success: O = O.OK) -> None:
        self.rate, self.failure, self.success, self.k = rate, failure, success, 0

    def __call__(self) -> O:
        k, self.k = self.k, self.k + 1
        return self.failure if math.floor((k + 1) * self.rate) > math.floor(k * self.rate) else self.success


def replay(svc, clock, phases, *, per_minute=5, service='modulate'):
    """Drive demand through allows/record. ``phases``: (minutes, outcome() -> O or (O, latency))."""
    trace = []
    for minutes, outcome in phases:
        for _ in range(minutes):
            for _ in range(per_minute):
                clock.now += 60 / per_minute
                allowed, reason = svc.allows(service)
                sent = None
                if allowed:
                    sent = outcome()
                    result, latency = sent if isinstance(sent, tuple) else (sent, 5.0)
                    svc.record_attempt(service, result, latency_seconds=latency)
                trace.append((clock.now, allowed, reason, sent))
    return trace


# --- replayed signatures (vendorscope-ops 1.1/1.4) --------------------------------------------------


def test_chronic_baseline_never_trips_or_flaps():
    clock = Clock()
    svc = _service(clock)
    errors, empties = Pattern(0.03, O.ERROR_5XX), Pattern(0.011, O.EMPTY_VALIDATED)

    def chronic():
        result = errors()
        return result if result is not O.OK else empties()

    # 5/min still fills every window's minimum n (5m: 25, 10m: 50, 30m: 150).
    trace = replay(svc, clock, [(2 * 60, chronic)])
    assert {reason for _, _, reason, _ in trace} == {R.HEALTHY}


def test_1022_modulate_credits_cliff_opens_on_funds_bounds_fanout_and_recovers():
    clock = Clock()
    svc = _service(clock)
    trace = replay(
        svc,
        clock,
        [(30, Pattern(0.01, O.ERROR_5XX)), (73, lambda: O.CREDIT_REFUSAL), (30, lambda: O.OK)],
    )
    onset, recovery = START + 3600 + 30 * 60, START + 3600 + 103 * 60
    before = [row for row in trace if row[0] <= onset]
    outage = [row for row in trace if onset < row[0] <= recovery]
    after = [row for row in trace if row[0] > recovery]
    assert all(allowed for _, allowed, _, _ in before)
    first_refusal = next(row for row in outage if not row[1])
    assert first_refusal[2] is R.FUNDS_REFUSAL and first_refusal[0] - onset <= 60
    # The breaker gates retries: 10-22 fanned one failed call out 5x; here the outage spends the
    # 3 trip refusals plus one fleet probe per 30 s, against 365 demanded sends.
    sent = sum(allowed for _, allowed, _, _ in outage)
    assert sent <= 3 + 73 * 2 + 2
    assert {reason for _, allowed, reason, _ in outage if allowed} <= {R.HEALTHY, R.HALF_OPEN_PROBE}
    reopened = next(row for row in after if row[2] is R.HEALTHY)
    assert reopened[0] - recovery <= 10 * 60
    assert all(row[2] is R.HEALTHY for row in after if row[0] >= reopened[0])


def test_0928_modulate_5xx_outage_opens_within_minutes_never_on_funds():
    clock = Clock()
    svc = _service(clock)
    trace = replay(svc, clock, [(30, lambda: O.OK), (60, Pattern(0.97, O.ERROR_5XX))])
    onset = START + 3600 + 30 * 60
    refused = [row for row in trace if not row[1]]
    assert refused and refused[0][0] - onset <= 5 * 60
    assert R.BREAKER_OPEN in {reason for _, _, reason, _ in refused}
    assert R.FUNDS_REFUSAL not in {reason for _, _, reason, _ in refused}
    late = [row for row in trace if row[0] > onset + 10 * 60]
    assert sum(allowed for _, allowed, _, _ in late) <= 50 * 2 + 2  # probes only once open


def test_0928_soniox_balance_exhausted_opens_on_funds(admit_soniox):
    clock = Clock()
    svc = _service(clock)
    trace = replay(svc, clock, [(5, lambda: O.OK), (20, lambda: O.CREDIT_REFUSAL)], service='soniox')
    assert any(reason is R.FUNDS_REFUSAL and not allowed for _, allowed, reason, _ in trace)


def test_1021_partial_39pct_degradation_sheds_but_never_opens():
    clock = Clock()
    svc = _service(clock)
    trace = replay(svc, clock, [(15, lambda: O.OK), (60, Pattern(0.39, O.ERROR_5XX))])
    reasons = {reason for _, _, reason, _ in trace}
    assert R.DEGRADED in reasons
    assert not reasons & {R.BREAKER_OPEN, R.FUNDS_REFUSAL, R.HALF_OPEN_PROBE}
    degraded = [allowed for _, allowed, reason, _ in trace if reason is R.DEGRADED]
    assert 0.4 <= sum(degraded) / len(degraded) <= 0.6  # partial shed at degraded_admit_fraction


def test_1016_latency_tail_degrades_and_extreme_tail_opens():
    clock = Clock()
    svc = _service(clock)
    slow = Pattern(0.10, (O.OK, 45.0), (O.OK, 4.0))
    trace = replay(svc, clock, [(20, slow)])
    assert R.DEGRADED in {reason for _, _, reason, _ in trace}
    clock2 = Clock()
    svc2 = _service(clock2)
    stuck = Pattern(0.10, (O.OK, 150.0), (O.OK, 4.0))
    trace2 = replay(svc2, clock2, [(20, stuck)])
    assert R.BREAKER_OPEN in {reason for _, _, reason, _ in trace2}


def test_validated_empty_rate_degrades_above_five_times_baseline():
    clock = Clock()
    svc = _service(clock)
    trace = replay(svc, clock, [(30, Pattern(0.10, O.EMPTY_VALIDATED))])
    assert R.DEGRADED in {reason for _, _, reason, _ in trace}
    clock2 = Clock()
    svc2 = _service(clock2)
    trace2 = replay(svc2, clock2, [(60, Pattern(0.04, O.EMPTY_VALIDATED))])
    assert {reason for _, _, reason, _ in trace2} == {R.HEALTHY}


def test_sustained_rate_limits_degrade_and_majority_rate_limits_open():
    clock = Clock()
    svc = _service(clock)
    trace = replay(svc, clock, [(10, Pattern(0.30, O.RATE_LIMITED))], per_minute=20)
    assert R.RATE_LIMITED in {reason for _, allowed, reason, _ in trace if not allowed}
    clock2 = Clock()
    svc2 = _service(clock2)
    trace2 = replay(svc2, clock2, [(10, Pattern(0.80, O.RATE_LIMITED))], per_minute=20)
    assert any(not allowed and reason is R.RATE_LIMITED for _, allowed, reason, _ in trace2)


def test_non_signal_outcomes_are_ignored():
    clock = Clock()
    svc = _service(clock)
    for outcome in (O.RUNNING, O.SUPERSEDED, O.UNKNOWN):
        for _ in range(50):
            svc.record_attempt('modulate', outcome)
    assert svc.allows('modulate') == (True, R.HEALTHY)
    assert vh.increments(O.SUPERSEDED, 1.0, config.Thresholds()) is None


# --- breaker state machine ---------------------------------------------------------------------------


def test_failed_probe_rearms_full_open_window():
    t = config.Thresholds()
    now = START
    buckets = {int(now // 60): {'n': 3, 'funds': 3}}
    record = vh.advance(vh.BreakerRecord(), buckets, now, t)
    assert record.state == vh.OPEN and record.reason is R.FUNDS_REFUSAL
    later = now + 40
    buckets[int(later // 60)] = {'n': 1, 'funds': 1}
    rearmed = vh.advance(record, buckets, later, t, 'funds')
    assert rearmed.opened_at == later and rearmed.successes == 0


def test_close_needs_consecutive_successes_and_clean_window():
    t = config.Thresholds()
    record = vh.BreakerRecord(vh.OPEN, R.BREAKER_OPEN, START, 4)
    now = START + 3600
    clean = {int(now // 60): {'n': 5, 'ok': 5}}
    assert vh.advance(record, clean, now, t, 'ok') == vh.BreakerRecord()
    dirty = {int(now // 60): {'n': 10, 'ok': 5, 'err': 5}}
    assert vh.advance(record, dirty, now, t, 'ok').state == vh.OPEN


def test_validated_empty_breaks_the_success_streak():
    t = config.Thresholds()
    record = vh.BreakerRecord(vh.OPEN, R.BREAKER_OPEN, START, 4)
    now = START + 3600
    buckets = {int(now // 60): {'n': 5, 'ok': 4, 'empty': 1}}
    reset = vh.advance(record, buckets, now, t, 'empty')
    assert reset.state == vh.OPEN and reset.successes == 0
    assert vh.advance(reset, buckets, now, t, 'ok').state == vh.OPEN


def test_route_provider_failure_is_state_unavailable_not_raised():
    def boom():
        raise RuntimeError('table read failed')

    svc = _service(Clock())
    svc.routes = boom
    assert svc.allows('modulate') == (False, R.STATE_UNAVAILABLE)
    assert svc.reserve('modulate', 10) == (False, R.STATE_UNAVAILABLE)


def test_one_fleet_wide_probe_per_interval_across_pods():
    server = fakeredis.FakeServer()
    clock = Clock()
    pods = [_service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server))) for _ in range(3)]
    for _ in range(3):
        pods[0].record_attempt('modulate', O.CREDIT_REFUSAL)
    clock.now += config.Thresholds().open_seconds + 1
    answers = []
    for step in range(30):  # 30 s of demand on every pod
        clock.now += 1
        for pod in pods:
            pod._refreshed_at = float('-inf')  # every pod refreshes as often as it can
            answers.append(pod.allows('modulate'))
    probes = [answer for answer in answers if answer == (True, R.HALF_OPEN_PROBE)]
    assert len(probes) == 1
    assert {answer for answer in answers if not answer[0]} == {(False, R.FUNDS_REFUSAL)}


def test_unspent_probe_token_lapses_with_its_interval():
    clock = Clock()
    svc = _service(clock, shared=vh.MemoryStore())
    for _ in range(3):
        svc.record_attempt('modulate', O.CREDIT_REFUSAL)
    clock.now += config.Thresholds().open_seconds + 1
    svc.refresh()
    assert 'modulate' in svc._probe_ready
    clock.now += config.Thresholds().probe_interval_s
    assert not svc._take_probe('modulate')


def test_background_refresh_runs_off_the_caller_thread():
    import threading

    server = fakeredis.FakeServer()
    svc = vh.VendorHealthService(
        shared=vh.RedisStore(fakeredis.FakeRedis(server=server)),
        settings=lambda: config.DEFAULT_SETTINGS,
        enabled=lambda: True,
        clock=Clock(),
    )
    assert svc.allows('modulate') == (True, R.HEALTHY)  # answered from local state at once
    for thread in threading.enumerate():
        if thread.name == 'batch-vendor-health':
            thread.join(timeout=5)
    assert 'modulate' in svc._views and not svc._refreshing


def test_cross_pod_trip_reaches_other_pods_on_refresh():
    server = fakeredis.FakeServer()
    clock = Clock()
    a = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)))
    b = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)))
    assert b.allows('modulate') == (True, R.HEALTHY)
    for _ in range(3):
        a.record_attempt('modulate', O.CREDIT_REFUSAL)
    clock.now += config.Thresholds().refresh_seconds
    assert b.allows('modulate') == (False, R.FUNDS_REFUSAL)


# --- caps and budget -----------------------------------------------------------------------------


def test_daily_cap_is_fleet_wide_unhealthy_not_error_and_resets_next_utc_day():
    server = fakeredis.FakeServer()
    clock = Clock()
    routes = {'gpu': _route(price=0.07), 'modulate': _route(cap=1.0)}
    a = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)), routes=routes)
    b = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)), routes=routes)
    assert a.reserve('modulate', 1800) == (True, R.HEALTHY)
    assert b.reserve('modulate', 1800) == (True, R.HEALTHY)
    assert a.reserve('modulate', 1) == (False, R.DAILY_CAP_REACHED)
    clock.now += 10
    assert b.allows('modulate') == (False, R.DAILY_CAP_REACHED)
    assert b.allows('gpu') == (True, R.HEALTHY)
    clock.now = START + 86400 + 60
    assert a.reserve('modulate', 600) == (True, R.HEALTHY)
    assert b.allows('modulate') == (True, R.HEALTHY)


def test_soniox_monthly_budget_latch_holds_until_month_rolls(admit_soniox):
    server = fakeredis.FakeServer()
    clock = Clock()
    routes = {'gpu': _route(price=0.07), 'soniox': _route(price=0.10, budget=1.0, failover_only=True)}
    svc = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)), routes=routes)
    assert svc.reserve('soniox', 9 * 3600) == (True, R.HEALTHY)
    assert svc.reserve('soniox', 2 * 3600) == (False, R.MONTHLY_BUDGET_REACHED)
    assert svc.reserve('soniox', 3600) == (True, R.HEALTHY)  # exactly the $1.00 budget
    clock.now += 10
    assert svc.allows('soniox') == (False, R.MONTHLY_BUDGET_REACHED)
    clock.now += 5 * 86400  # still November: latched
    assert svc.allows('soniox') == (False, R.MONTHLY_BUDGET_REACHED)
    clock.now = START + 30 * 86400 + 60  # 2025-12-01
    assert svc.allows('soniox') == (True, R.HEALTHY)


def test_budget_without_price_fails_closed(admit_soniox):
    clock = Clock()
    routes = {'soniox': _route(price=None, budget=50.0, failover_only=True)}
    svc = _service(clock, shared=vh.MemoryStore(), routes=routes)
    assert svc.reserve('soniox', 1) == (False, R.MONTHLY_BUDGET_REACHED)
    assert svc.allows('soniox') == (False, R.MONTHLY_BUDGET_REACHED)


def test_reserve_lua_is_atomic_under_concurrency():
    from concurrent.futures import ThreadPoolExecutor

    server = fakeredis.FakeServer()
    clock = Clock()
    routes = {'modulate': _route(cap=1.0)}
    pods = [_service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)), routes=routes) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda n: pods[n % 4].reserve('modulate', 300), range(40)))
    assert sum(ok for ok, _ in answers) == 12
    assert {reason for ok, reason in answers if not ok} == {R.DAILY_CAP_REACHED}


# --- degradation of the state itself ---------------------------------------------------------------


class Broken:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError('redis down')

        return fail


def test_shared_store_down_falls_back_to_local_and_caps_fail_closed():
    clock = Clock()
    capped = _service(clock, shared=Broken(), routes={'modulate': _route(cap=10.0)})
    assert capped.allows('modulate') == (True, R.HEALTHY)
    assert capped.reserve('modulate', 60) == (False, R.STATE_UNAVAILABLE)
    for _ in range(3):
        capped.record_attempt('modulate', O.CREDIT_REFUSAL)
    assert capped.allows('modulate') == (False, R.FUNDS_REFUSAL)  # local breaker still trips
    uncapped = _service(clock, shared=Broken(), routes={'modulate': _route()})
    assert uncapped.reserve('modulate', 60) == (True, R.HEALTHY)


def test_both_stores_down_is_state_unavailable_never_raises():
    clock = Clock()
    svc = vh.VendorHealthService(
        shared=Broken(), local=Broken(), settings=lambda: config.DEFAULT_SETTINGS, clock=clock, background=False
    )
    assert svc.allows('modulate') == (False, R.STATE_UNAVAILABLE)
    assert svc.allows('gpu') == (True, R.HEALTHY)
    svc.record_attempt('modulate', O.ERROR_5XX)
    svc.refresh()


def test_settings_failure_is_state_unavailable():
    def boom():
        raise RuntimeError('bad settings')

    svc = _service(Clock(), settings=boom)
    assert svc.allows('modulate') == (False, R.STATE_UNAVAILABLE)


def test_stale_snapshot_uses_local_state():
    server = fakeredis.FakeServer()
    clock = Clock()
    svc = _service(clock, shared=vh.RedisStore(fakeredis.FakeRedis(server=server)))
    svc.allows('modulate')
    server.connected = False
    clock.now += config.Thresholds().stale_seconds + 10
    assert svc.allows('modulate') == (True, R.HEALTHY)
    assert 'modulate' not in svc._views


# --- admission, kill switch, gpu -----------------------------------------------------------------


def test_gpu_always_healthy_unknown_and_unadmitted_vendors_refused():
    svc = _service(Clock())
    assert svc.allows('gpu') == (True, R.HEALTHY)
    assert svc.allows('deepgram') == (False, R.NOT_ADMITTED)
    # Today's policy keeps Soniox off the prerecorded surface; slice D admits it.
    assert svc.allows('soniox') == (False, R.NOT_ADMITTED)
    assert svc.reserve('soniox', 10) == (False, R.NOT_ADMITTED)


def test_kill_switch_answers_from_process_local_vendor_guard(monkeypatch):
    vendor_guard.reset_vendor_guard_for_tests()
    clock = Clock()
    svc = _service(clock, enabled=False, routes={'modulate': _route(cap=0.0)})
    assert svc.allows('modulate') == (True, R.HEALTHY)
    assert svc.reserve('modulate', 3600) == (True, R.HEALTHY)  # no caps: today's behaviour
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD):
        vendor_guard.record_breaker_quota_error(vendor_guard.ENDPOINT_STT, budget=True)
    assert svc.allows('modulate') == (False, R.FUNDS_REFUSAL)
    svc.record_attempt('modulate', O.ERROR_5XX)
    assert svc.local.buckets('modulate', clock.now, 600) == {}
    vendor_guard.reset_vendor_guard_for_tests()


def test_breaker_refuses_is_a_pure_read(monkeypatch):
    vendor_guard.reset_vendor_guard_for_tests()
    now = [100.0]
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now[0])
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD):
        vendor_guard.record_breaker_quota_error(vendor_guard.ENDPOINT_STT)
    assert vendor_guard.breaker_refuses(vendor_guard.ENDPOINT_STT)
    now[0] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    assert not vendor_guard.breaker_refuses(vendor_guard.ENDPOINT_STT)
    assert not vendor_guard.breaker_refuses(vendor_guard.ENDPOINT_STT)  # did not take the trial
    assert vendor_guard.breaker_allows(vendor_guard.ENDPOINT_STT)  # the trial is still available
    assert vendor_guard.breaker_refuses(vendor_guard.ENDPOINT_STT)  # now it is in flight
    vendor_guard.reset_vendor_guard_for_tests()


# --- runway and gauges ---------------------------------------------------------------------------


def test_modulate_runway_from_our_own_usage():
    clock = Clock()
    settings = config.parse_settings({'runway': {'modulate': {'balance_usd': 100.0, 'as_of': START}}})
    store = vh.MemoryStore()
    svc = _service(clock, shared=store, routes={'modulate': _route(price=0.03)}, settings=lambda: settings)
    svc.refresh()  # first observation anchors the balance at today's total (0)
    for _ in range(24):
        assert svc.reserve('modulate', 100 * 3600) == (True, R.HEALTHY)  # 100 audio-h per hour
        clock.now += 3600
    clock.now -= 1
    svc.refresh()
    rate = vh.SPEND_RATE.labels(provider='modulate')._value.get()
    assert rate == pytest.approx(3.0)  # $3/h
    spent = 24 * 100 * 0.03
    assert vh.RUNWAY_HOURS.labels(provider='modulate')._value.get() == pytest.approx((100.0 - spent) / 3.0)


def test_refresh_exports_breaker_state_and_audio_hours():
    from utils.batch_pipeline import vendor_route_metrics as m

    clock = Clock()
    svc = _service(clock, shared=vh.MemoryStore(), routes={'modulate': _route(cap=100.0)})
    svc.reserve('modulate', 7200)
    for _ in range(3):
        svc.record_attempt('modulate', O.CREDIT_REFUSAL)
    svc.refresh()
    assert m.BREAKER_STATE.labels(provider='modulate', state='open')._value.get() == 1
    assert m.AUDIO_HOURS_USED.labels(provider='modulate')._value.get() == pytest.approx(2.0)
    assert m.AUDIO_HOURS_CAP.labels(provider='modulate')._value.get() == 100.0
    clock.now += config.Thresholds().open_seconds + 1
    svc.refresh()
    assert m.BREAKER_STATE.labels(provider='modulate', state='half_open')._value.get() == 1


# --- config --------------------------------------------------------------------------------------


def test_defaults_are_the_ops_14_table():
    t = config.Thresholds()
    assert (t.error_degraded_rate, t.error_degraded_window_s, t.error_degraded_min_n) == (0.20, 600, 30)
    assert (t.error_open_rate, t.error_open_window_s, t.error_open_min_n) == (0.50, 300, 20)
    assert (t.funds_open_count, t.funds_window_s) == (3, 300)
    assert (t.empty_degraded_rate, t.empty_window_s, t.empty_min_n) == (0.055, 1800, 50)
    assert (t.latency_degraded_s, t.latency_open_s) == (30.0, 120.0)
    assert (t.probe_interval_s, t.close_successes, t.close_error_rate) == (30.0, 5, 0.05)
    assert t.cap_alert_fraction == 0.9


def test_thresholds_override_per_vendor_and_ladder(monkeypatch):
    ladder = config._Ladder()
    good = json.dumps({'funds_open_count': 1, 'vendors': {'soniox': {'error_open_rate': 0.9}}})
    settings = ladder.resolve(good)
    assert settings.default.funds_open_count == 1
    assert settings.for_vendor('soniox').error_open_rate == 0.9
    assert settings.for_vendor('soniox').funds_open_count == 1  # vendor overrides layer on the default
    assert settings.for_vendor('modulate').error_open_rate == 0.50
    assert ladder.resolve('{not json') is settings  # last valid
    assert ladder.resolve(json.dumps({'mystery': 1})) is settings
    assert ladder.resolve(None) is config.DEFAULT_SETTINGS  # unset is a deliberate default
    assert config._Ladder().resolve('{bad') is config.DEFAULT_SETTINGS


@pytest.mark.parametrize(
    'raw',
    [
        {'error_open_rate': 1.5},
        {'error_open_rate': 0.1},  # below the degraded bound
        {'funds_open_count': 0},
        {'funds_open_count': 2.5},
        {'empty_window_s': 7200},
        {'probe_interval_s': -1},
        {'probe_interval_s': True},
        {'stale_seconds': 1},
        {'vendors': {'deepgram': {}}},
        {'runway': {'modulate': {'balance_usd': 10}}},
        {'runway': {'modulate': {'balance_usd': -1, 'as_of': 0}}},
        [],
    ],
)
def test_invalid_thresholds_are_rejected(raw):
    with pytest.raises(config.ThresholdsInvalid):
        config.parse_settings(raw)


def test_kill_switch_env_parsing(monkeypatch):
    monkeypatch.delenv(config.ENABLED_ENV, raising=False)
    assert config.health_enabled()
    monkeypatch.setenv(config.ENABLED_ENV, 'false')
    assert not config.health_enabled()
    monkeypatch.setenv(config.ENABLED_ENV, 'garbage')
    assert config.health_enabled()


def test_get_vendor_health_is_a_process_singleton(monkeypatch):
    monkeypatch.setattr(vh, '_service', None)
    first = vh.get_vendor_health()
    assert vh.get_vendor_health() is first
    routes = {'modulate': _route()}
    assert vh.get_vendor_health(lambda: routes).routes() is routes
    health: contracts.VendorHealth = first  # structural conformance, checked by pyright
    assert callable(health.allows)
