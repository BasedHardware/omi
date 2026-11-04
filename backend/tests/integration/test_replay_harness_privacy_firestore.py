"""Real privacy writers/readers and Redis Lua, with loopback-only durable authority."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures/privacy-transitions-smoke'


@pytest.fixture(autouse=True)
def require_emulator():
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')


def single_case(kind, fault='drop_invalidation', family='subscription'):
    from testing.replay_harness.manifest import load_case

    return replace(
        load_case(FIXTURE),
        corpus={'privacy_cache': {'transitions': [{'family': family, 'kind': kind, 'fault': fault}]}},
    )


@pytest.mark.parametrize('ttl_override_s', [None, 55])
def test_privacy_smoke_via_registered_runner(tmp_path, ttl_override_s):
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import write_report

    previous = dict(os.environ)
    items = asyncio.run(run_cases([FIXTURE], privacy_ttl_override_s=ttl_override_s))
    write_report(items, tmp_path)
    assert items[0]['expectation_met'] == (ttl_override_s == 55), json.dumps(items)
    details = items[0]['stages'][0]['details']
    assert details['transitions'] == 120 and details['probes'] == 720
    assert details['mismatches'] == 0 if ttl_override_s == 55 else details['mismatches'] > 0
    assert details['completed_transitions'] == details['attempted_transitions'] == 120
    assert not details['errors'], json.dumps(details['errors'])
    assert details['bound_s'] == 60 and details['ttl_override_s'] == ttl_override_s
    assert details['bound_margin_s'] == (5 if ttl_override_s == 55 else 0)
    assert set(details['max_observed_staleness_seconds']) == {
        'deletion_marker',
        'tombstone',
        'legal_hold',
        'batch_privacy',
        'subscription',
        'data_protection',
    }
    assert details['cache_events']['deletion_marker_cache:publish'] > 0
    assert details['cache_events']['tombstone_negative_cache:publish'] > 0
    assert details['cache_events']['legal_hold_fence_cache:publish'] > 0
    assert details['cache_events']['batch:memo_hit'] > 0
    assert details['cache_events']['external:memo_hit'] > 0
    assert details['cache_events']['request_read_dedupe:hit'] > 0
    assert details['overlap_probes'] > 0
    for operation in ('begin_loss:end', 'drop_invalidation:begin', 'drop_invalidation:end', 'redis_down:read'):
        assert details['redis_fault_calls'][operation] > 0
    assert dict(os.environ) == previous


@pytest.mark.parametrize('kind', ['byok_enable', 'byok_disable'])
def test_stage_catches_stale_decisions_in_both_directions(kind):
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    result = asyncio.run(PrivacyCacheDriver(ttl_override_s=120).run(single_case(kind)))
    assert result.status == 'stopped', result
    assert result.reason == 'privacy_cache:staleness_bound_exceeded', result
    cells = result.details['by_family_fault_offset']['subscription']['drop_invalidation']
    assert cells['60.0']['mismatches'] == cells['61.0']['mismatches'] == 1
    assert cells['300.0']['mismatches'] == 0
    assert result.details['mismatches'] == 2 and result.details['bound_margin_s'] == -60
    assert result.details['probes'] == 6
    serialized = json.dumps(result.details)
    assert 'synthetic-privacy' not in serialized and 'synthetic-gate-token' not in serialized


@pytest.mark.parametrize('kind', ['byok_enable', 'byok_disable'])
def test_exact_sixty_second_boundary_without_invalidations(kind):
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    result = asyncio.run(PrivacyCacheDriver().run(single_case(kind)))
    assert result.status == 'stopped', result
    assert result.details['early_mismatches'] == 3
    assert result.details['max_observed_staleness_seconds']['subscription'] == 60
    assert result.details['probes'] == 6 and result.details['mismatches'] == 1
    assert result.details['bound_margin_s'] == 0


def test_stage_catches_stale_deletion_marker(monkeypatch):
    from database import fsr_read_cache as cache
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    original = cache.ttl
    monkeypatch.setattr(
        cache,
        'ttl',
        lambda name, default: 120 if name == 'FSR_DELETION_NEGATIVE_TTL_SECONDS' else original(name, default),
    )
    result = asyncio.run(PrivacyCacheDriver().run(single_case('wipe_intent', family='deletion_marker')))
    assert result.reason == 'privacy_cache:staleness_bound_exceeded', result
    assert result.details['by_family_fault_offset']['deletion_marker']['drop_invalidation']['60.0']['mismatches'] == 1
    assert result.details['mismatches'] == 2 and result.details['probes'] == 6


def test_fake_clock_controls_redis_expiry_and_lua_time():
    from collections import Counter
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.stages.privacy_cache import clock_and_cache
    from database import fsr_read_cache as cache

    with replay_environment() as env:
        patches, redis = clock_and_cache(env, 'none', Counter())
        with patches:
            assert cache._redis() is redis
            env.redis.set('clock-proof', 'present', ex=60)
            assert env.redis.time()[0] == int(env.clock.time())
            env.clock.advance(59)
            assert env.redis.get('clock-proof') == 'present'
            env.clock.advance(1)
            # Redis/fakeredis retain keys in the expiry millisecond. Preserve
            # that boundary here; the strict stage must expose it, not shift its
            # +60s probe to make a 60s cache pass.
            assert env.redis.get('clock-proof') == 'present'
            env.clock.advance(1)
            assert env.redis.get('clock-proof') is None
            assert env.redis.eval("return redis.call('TIME')", 0)[0] == str(int(env.clock.time()))
            assert cache.time.monotonic() == env.clock.time()


def test_manifest_bound_is_independent_from_ttl():
    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    case = single_case('byok_enable')
    case = replace(case, manifest=replace(case.manifest, stages={'privacy_cache': {'expect': 'pass', 'bound_s': 50}}))
    result = asyncio.run(PrivacyCacheDriver(ttl_override_s=55).run(case))
    assert result.reason == 'privacy_cache:staleness_bound_exceeded'
    assert result.details['bound_s'] == 50 and result.details['bound_margin_s'] == -5
    assert result.details['probes'] == 7
    assert result.details['by_family_fault_offset']['subscription']['drop_invalidation']['50.0']['mismatches'] == 1
