"""Scan admission survives rollback of unrelated read optimizations."""

import pytest

from tests.unit.test_fsr_s2_singleton_loops import CountingFirestore, fleet  # noqa: F401
from database import durable_queue_age as ages
from utils.other import fsr_leader_lease as leases


def test_real_sampler_wave_reads_with_empty_lever_literal(fleet, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    counts = []
    for override in ('false', 'true'):
        monkeypatch.setenv('FSR_MAINTENANCE_COORDINATION_ENABLED', override)
        fleet.redis.values.clear()
        fleet.redis.expires.clear()
        fleet.redis.now = 0
        replicas = [fleet.replica('queue_age_proof') for _ in range(5)]
        client = CountingFirestore()
        for _ in range(10):
            for replica in replicas:
                replica.run(
                    lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}),
                    300,
                )
            fleet.redis.advance(300)
        counts.append(client.reads)
    assert counts == [1000, 200]


@pytest.mark.parametrize('literal', ['{}', '{"singleton_loops":0}', 'malformed', '{"singleton_loops":5}'])
def test_production_scan_waves_keep_one_admission_per_tick(fleet, monkeypatch, literal):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.delenv('FSR_MAINTENANCE_COORDINATION_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', literal)
    replicas = [fleet.replica('reconcile_stale_in_progress_conversations') for _ in range(20)]
    calls = []
    for _ in range(3):
        for replica in replicas:
            replica.run(lambda: calls.append(fleet.redis.now), 300)
        fleet.redis.advance(300)
    assert calls == [0, 300, 600]
    assert fleet.outcomes.count(('reconcile_stale_in_progress_conversations', 'acquired')) == 3


@pytest.mark.parametrize('override', ['false', '0', 'off', 'no', ' FALSE '])
def test_explicit_kill_switch_restores_per_replica_path_without_redis(fleet, monkeypatch, override):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setenv('FSR_MAINTENANCE_COORDINATION_ENABLED', override)
    calls = []
    for _ in range(5):
        fleet.replica().run(lambda: calls.append('local'), 300)
    assert calls == ['local'] * 5
    assert fleet.redis.calls == 0
    assert leases.queue_age_publisher_eligible()


def test_redis_outage_preserves_local_recovery_during_production_wave(fleet, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.delenv('FSR_MAINTENANCE_COORDINATION_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    fleet.redis.error = True
    assert [fleet.replica().run(lambda: 'recovery', 300) for _ in range(3)] == ['recovery'] * 3
    assert fleet.outcomes.count(('test_loop', 'redis_error')) == 3


def test_queue_sampling_keeps_designated_publisher_and_takeover(fleet, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.delenv('FSR_MAINTENANCE_COORDINATION_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    monkeypatch.setenv('FSR_QUEUE_AGE_PUBLISHER', '0')
    assert not leases.queue_age_publisher_eligible()
    monkeypatch.setenv('FSR_QUEUE_AGE_PUBLISHER', '1')
    assert leases.queue_age_publisher_eligible()
    one, two = fleet.replica(leases.QUEUE_AGE_LOOP), fleet.replica(leases.QUEUE_AGE_LOOP)
    calls = []
    one.run(lambda: calls.append('owner'), 300)
    assert two.run(lambda: pytest.fail('duplicate publisher'), 300) is None
    one.release(clear_tick=True)
    two.run(lambda: calls.append('takeover'), 300)
    assert calls == ['owner', 'takeover']


@pytest.mark.parametrize('stage,deployment', [('dev', ''), ('prod', 'staging'), ('prod', 'preview')])
def test_nonproduction_retains_legacy_qualification_cohort(monkeypatch, stage, deployment):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('OMI_DEPLOYMENT', deployment)
    monkeypatch.delenv('FSR_MAINTENANCE_COORDINATION_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    assert not leases.singleton_loops_enabled()
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"singleton_loops":100}')
    assert leases.singleton_loops_enabled()
    monkeypatch.setenv('FSR_MAINTENANCE_COORDINATION_ENABLED', 'true')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    assert leases.singleton_loops_enabled()
