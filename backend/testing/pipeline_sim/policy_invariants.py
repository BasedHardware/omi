"""Cross-policy invariants exercised by generated pipeline_sim runs."""

from __future__ import annotations

import asyncio

from config.policy.batch import BatchUnitPolicy, batch_generation_violations
from config.policy.listen import ListenSessionPolicy, listen_generation_violations
from routers.listen import policy as listen_policy_store
from testing.pipeline_sim.scorer import score
from testing.pipeline_sim.sim import SimConfig, SimResult, simulate
from testing.pipeline_sim.stt import EMPTY, ExhaustionWindow, ModulateProfile, STTProfile
from testing.pipeline_sim.workload import WorkloadSpec


class _MemoryRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    async def get(self, key):
        return self.data.get(key)

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def set(self, key, payload, *, nx, ex):
        if nx and key in self.data:
            return False
        self.data[key] = payload
        self.ttls[key] = ex
        return True


class _UnavailableRedis:
    async def get(self, _key):
        raise ConnectionError('simulated redis outage')


async def _exercise_listen_policy(policy: ListenSessionPolicy) -> None:
    uid, identity = 'sim-policy-owner', 'sim-policy-conversation'
    redis = _MemoryRedis()
    first, source = await listen_policy_store.load_listen_policy(
        uid, identity, resolver=lambda: policy, redis_client=redis
    )
    assert source == 'resolved', 'healthy first write must be recorded as resolved'
    assert first.policy_id == policy.policy_id

    def unexpected_resolution():
        raise AssertionError('reconnect must load the recorded policy')

    reconnected, source = await listen_policy_store.load_listen_policy(
        uid, identity, resolver=unexpected_resolution, redis_client=redis
    )
    assert source == 'redis'
    assert reconnected.policy_id == first.policy_id
    assert reconnected.routing_arm == first.routing_arm
    assert reconnected.window_allocated == first.window_allocated

    fallback, source = await listen_policy_store.load_listen_policy(
        uid, identity + '-redis-fault', resolver=lambda: policy, redis_client=_UnavailableRedis()
    )
    assert source == 'fallback', 'fallback source is reserved for a Redis failure'
    assert fallback.policy_id == policy.policy_id


def assert_listen_policy_invariants(policy: ListenSessionPolicy) -> None:
    assert listen_generation_violations(policy) == ()
    # The serialization round trip is the recorded-policy replay boundary.
    replayed = ListenSessionPolicy.from_dict(policy.to_dict())
    assert replayed.policy_id == policy.policy_id
    asyncio.run(_exercise_listen_policy(replayed))


def simulate_policy_case(case, *, seed: int) -> SimResult:
    """Run one generated pair through the hermetic simulator with explicit objects."""
    workload = WorkloadSpec(
        owners=6,
        uploads_per_owner_per_hour=180.0,
        arrival_seconds=120.0,
        segments_per_upload=(2, 3),
        near_silence_fraction=0.25,
        silence_fraction=0.1,
        live_target_fraction=0.1,
        merged_target_fraction=0.1,
        deleted_target_fraction=0.1,
        duplicate_upload_fraction=0.1,
        privacy_blocked_owners=1,
        privacy_midflight_owners=1,
        privacy_midflight_at=60.0,
    )
    return simulate(
        SimConfig(
            name='generated-policy-invariants',
            seed=seed,
            workload=workload,
            stt=STTProfile(
                min_replicas=2,
                max_replicas=3,
                near_silence_empty_rate=1.0,
                exhaustion=(ExhaustionWindow(0.0, 7200.0, EMPTY),),
            ),
            modulate=ModulateProfile(
                concurrency=4,
                base_latency_seconds=0.25,
                seconds_per_audio_second=0.005,
                latency_sigma=0.0,
                speech_recover_rate=1.0,
                near_silence_recover_rate=1.0,
            ),
            horizon_seconds=1800.0,
            gpu_pumps=2,
            pump_batch_size=8,
            gpu_seconds_per_item=0.01,
            projection_seconds=0.01,
            policy=case.batch_policy,
            listen_policy=case.listen_policy,
        )
    )


def assert_policy_invariants(result: SimResult) -> None:
    """Check durable batch invariants and the listen reconnect model for one run."""
    policy = result.config.policy
    listen_policy = result.config.listen_policy
    assert isinstance(policy, BatchUnitPolicy), 'generated BatchUnitPolicy must be supplied to the sim'
    assert isinstance(listen_policy, ListenSessionPolicy), 'generated ListenSessionPolicy must be supplied to the sim'
    assert batch_generation_violations(policy) == ()
    assert_listen_policy_invariants(listen_policy)

    # Every simulated admission records and uses exactly the injected policy.
    for record in result.records:
        assert record.policy is not None and record.policy.policy_id == policy.policy_id
        assert record.policy == policy
    if result.store is not None:
        for row in result.store.jobs():
            recorded = BatchUnitPolicy.from_dict(row.get('policy'))
            assert recorded.policy_id == policy.policy_id
            assert recorded == policy

    # The durable merge log is a strictly increasing per-owner predecessor
    # chain. A capture that arrives behind the owner's watermark must be
    # explicitly marked late instead of silently corrupting that chain.
    results_by_owner: dict[str, list[tuple[str, dict]]] = {}
    if result.store is not None:
        for (table, segment_id), row in result.store.rows.items():
            if table == 'results':
                results_by_owner.setdefault(row['owner_id'], []).append((segment_id, row))
        for rows in results_by_owner.values():
            by_id = {segment_id: row for segment_id, row in rows}
            sequences = [row['log_sequence'] for _, row in rows]
            assert len(sequences) == len(set(sequences))
            for segment_id, row in rows:
                predecessor = row.get('previous_segment_id')
                if predecessor in by_id:
                    previous = by_id[predecessor]
                    assert previous['log_sequence'] < row['log_sequence'], segment_id
                    position = (row['capture_at'], row['segment_id'])
                    previous_position = (previous['capture_at'], predecessor)
                    if position <= previous_position:
                        assert row.get('late_capture'), f'{segment_id} moved behind its owner watermark unmarked'

    # Paid recovery cannot duplicate or run at/after an account/deletion fence.
    # A call made before a later deletion is valid, so compare call timestamps
    # to the target fence instead of treating every eventually excluded upload
    # as stale from the start. The simulator's store re-applies privacy guards
    # on every durable job/result write.
    assert max(result.modulate.calls_by_segment.values(), default=0) <= 1, 'vendor paid more than once per segment'
    sample = score(result)
    assert sample['sim']['paid_fallback_calls_after_privacy_fence'] == 0
    for record in result.records:
        if record.fenced_at is None:
            continue
        assert record.projected_at is None or record.projected_at <= record.fenced_at
        for segment_id in record.segment_ids:
            assert not any(at >= record.fenced_at for at in result.modulate.call_times.get(segment_id, ()))
