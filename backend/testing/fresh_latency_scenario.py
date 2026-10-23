"""Fresh-upload latency beside a catch-up owner (David's bar: fresh p95 <= 2 min).

Fresh means capture lag <= 10 min at upload. Normal owners upload steadily; one
catch-up owner uploads a contiguous 300-row backlog newest-first (the app's
``nextSyncUploadBatch`` order) while it keeps uploading fresh audio. The backlog
rides the fresh lane, as production's 6 h lane cutoff routes it. A seeded share
of first-attempt completions is lost so the lease leaks until expiry (the #22805
class), and a share of speech returns empty ASR so it quarantines and recovers
through the paid fallback. Projection is owner-serial in result-log order.
Everything is synthetic; no production or network access is needed.

The metric is upload acceptance -> conversation projected, for fresh uploads:
all owners, the catch-up owner's own fresh uploads, and every other owner's.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json

from testing.hermetic_network import block_outbound_network
from testing.merge_head_wait_scenario import _check_owner_chains, _leaky_scheduler
from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.scorer import percentile, score
from testing.pipeline_sim.sim import SimConfig, Simulation
from testing.pipeline_sim.stt import SPEECH, STTProfile
from testing.pipeline_sim.workload import BURST, SegmentSpec, UploadSpec, WorkloadSpec, content_id_for

FRESH_LAG_SECONDS = 600.0
FRESH_TARGET_SECONDS = 120.0
CATCH_UP_ROWS = 300
CATCH_UP_ARRIVAL_SECONDS = 90.0
CATCH_UP_AT = 60.0
OWNER_FRESH_EVERY_SECONDS = 30.0
OWNER_FRESH_UNTIL = 1500.0

# Each lever and its shipped setting; a variant switches levers off from the shipped stack.
LEVERS = {
    'lease_leak_fixed': ('leak', 0.0, 10.0),  # #22805 (merged; rides the next train)
    'head_wait': ('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', '60', 'off'),  # Fix C (#22820)
    'recovery_dispatch_loop': ('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', '5', 'off'),
    'fresh_first': ('BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH', '16', 'off'),
    'fresh_gpu_priority': ('BATCH_PIPELINE_FRESH_GPU_PRIORITY_ENABLED', 'true', 'false'),
}


WALK_ROWS = 64  # projection.py OWNER_CHAIN_LIMIT
WALK_SECONDS = 30.0  # projection.py OWNER_CHAIN_SECONDS


def _walking_projector(simulation: Simulation):
    """MODEL of the owner-chain walk: owner-serial projection in result-log order.

    Like ``Projector._walk_owner``, each step re-reads the owner's next log row,
    so a row committed while the walk runs projects in the same walk. A walk
    stops after 64 rows or 30 s; the next sweep (serving interval) resumes it.
    A record with an uncommitted segment holds the chain. Sweeps start one walk
    per owner. Unlike production, the 30 s budget is per walk, not shared across
    the owners of one sweep, which flatters many-owner sweeps.
    """
    walking: set[str] = set()

    def unprojected(owner: str | None = None):
        for (table, sid), row in simulation.store.rows.items():
            record = simulation.by_segment.get(sid) if table == 'results' else None
            if record is None or record.projected_at is not None or record.excluded is not None:
                continue
            if owner is None or record.spec.owner == owner:
                yield row['log_sequence'], record

    async def walk(owner: str) -> None:
        deadline = simulation.clock.now + WALK_SECONDS
        try:
            for _ in range(WALK_ROWS):
                if simulation.clock.now >= deadline:
                    break
                head = min(unprojected(owner), default=None, key=lambda pair: pair[0])
                if head is None:
                    break
                record = head[1]
                jobs = [simulation.store.rows.get(('jobs', sid), {}) for sid in record.segment_ids]
                if not all(job.get('state') == 'committed' for job in jobs):
                    break
                if simulation._fenced(record):
                    record.excluded = simulation._fenced(record)
                    continue
                record.projecting = True
                await simulation._project(record)
        finally:
            walking.discard(owner)

    def sweep() -> None:
        for owner in sorted({record.spec.owner for _, record in unprojected()} - walking):
            walking.add(owner)
            simulation.revision.spawn('projection', walk(owner))

    return sweep


def _p(values, q):
    value = percentile(values, q)
    return round(value, 1) if value is not None else None


def _owner_fresh_uploads(owner: str, start: int) -> list[UploadSpec]:
    """The catch-up owner keeps syncing fresh audio while its backlog drains."""
    uploads, n, at = [], start, 15.0
    while at < OWNER_FRESH_UNTIL:
        upload_id = f'f{n:06d}'
        uploads.append(
            UploadSpec(
                upload_id,
                owner,
                BURST,
                at,
                recording_age=90.0 + (n % 5) * 30.0,
                content_id=content_id_for(upload_id),
                segments=(SegmentSpec(0, 60.0, SPEECH),),
            )
        )
        n, at = n + 1, at + OWNER_FRESH_EVERY_SECONDS
    return uploads


def replay(
    *,
    catch_up: bool = True,
    levers: tuple[str, ...] = tuple(LEVERS),
    speech_empty_percent: float = 15.0,
    projection_seconds: float = 1.5,
    catch_up_depth: int | None = None,
    seed: int = 1,
) -> dict:
    flags, leak = {}, 0.0
    for name, (key, on, off) in LEVERS.items():
        value = on if name in levers else off
        if key == 'leak':
            leak = value
        else:
            flags[key] = value
    if catch_up_depth is not None and 'fresh_first' in levers:
        flags['BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH'] = str(catch_up_depth)
    config = SimConfig(
        name='fresh_latency' + ('_catch_up' if catch_up else ''),
        seed=seed,
        workload=WorkloadSpec(
            owners=30,
            uploads_per_owner_per_hour=6.0,
            arrival_seconds=1800.0,
            segments_per_upload=(1, 1),
            speech_seconds=(30.0, 120.0),
            burst_owners=1 if catch_up else 0,
            burst_uploads=CATCH_UP_ROWS,
            burst_at=CATCH_UP_AT,
            burst_segment_seconds=(60.0, 60.0),
            # Production routes captures up to 6 h old to the fresh lane (FRESH priority).
            burst_lane='fresh',
            near_silence_fraction=0,
            silence_fraction=0,
        ),
        gpu_pumps=2,
        pump_batch_size=8,
        gpu_seconds_per_item=1.0,
        projection_seconds=projection_seconds,
        summary_dispatch='task',
        summary_pool='isolated',
        stt=STTProfile(
            min_replicas=4,
            max_replicas=4,
            per_pod_concurrency=8,
            base_latency_seconds=2.0,
            seconds_per_audio_second=0.02,
            speech_empty_rate=speech_empty_percent / 100,
        ),
        horizon_seconds=3 * 3600.0,
        backfill_speech_seconds_per_day=10**9,
        flags=flags,
    )
    dropped: set[str] = set()
    original = sim_module.Scheduler
    try:
        sim_module.Scheduler = _leaky_scheduler(leak, dropped)
        simulation = Simulation(config)
        simulation._projector_sweep = _walking_projector(simulation)
        step = CATCH_UP_ARRIVAL_SECONDS / CATCH_UP_ROWS
        uploads, n, owner = [], 0, None
        for upload in simulation.workload.uploads:
            if upload.owner_kind == BURST:
                # One contiguous recording 30 min to 5 h old, uploaded newest-first.
                at = CATCH_UP_AT + n * step
                upload = replace(upload, at=at, recording_age=at - CATCH_UP_AT + 1800.0 + n * 60.0)
                owner, n = upload.owner, n + 1
            else:
                # Steady owners sync promptly: capture lag 1-8 min.
                upload = replace(upload, recording_age=60.0 + (int(upload.upload_id[1:]) * 37) % 420)
            uploads.append(upload)
        if owner is not None:
            extra = _owner_fresh_uploads(owner, len(uploads))
            for upload in extra:  # Simulation seeds segment truth at construction.
                for segment in upload.segments:
                    simulation.truth[simulation._segment_id(upload, segment.index)] = {
                        'kind': segment.kind,
                        'duration': segment.duration,
                        'owner': owner,
                        'upload': upload,
                    }
            uploads += extra
        simulation.workload.uploads = sorted(uploads, key=lambda u: (u.at, u.upload_id))
        with block_outbound_network():
            result = simulation.run()
    finally:
        sim_module.Scheduler = original

    _check_owner_chains(result.store)
    assert max(result.modulate.calls_by_segment.values(), default=0) <= 1, 'vendor paid more than once per segment'
    strata: dict[str, list[float]] = {'fresh_all': [], 'fresh_catch_up_owner': [], 'fresh_other_owners': []}
    quarantined: list[float] = []
    catch_up_latency: list[float] = []
    for record in result.records:
        if record.accepted_at is None or not record.segment_ids or record.projected_at is None:
            continue
        latency = record.projected_at - record.accepted_at
        if record.spec.recording_age > FRESH_LAG_SECONDS:
            catch_up_latency.append(latency)
            continue
        strata['fresh_all'].append(latency)
        strata['fresh_catch_up_owner' if record.spec.owner == owner else 'fresh_other_owners'].append(latency)
        if any(result.store.rows.get(('jobs', sid), {}).get('quarantined_at') for sid in record.segment_ids):
            quarantined.append(latency)
    sample = score(result)
    out = {
        'catch_up': catch_up,
        'levers': sorted(levers),
        'catch_up_depth': flags['BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH'],
        'projection_seconds': projection_seconds,
        'leaked_leases': len(dropped),
        'unprojected': sum(1 for r in result.records if r.accepted_at is not None and r.projected_at is None),
    }
    for name, values in strata.items():
        out[name] = {
            'n': len(values),
            'p50': _p(values, 0.5),
            'p95': _p(values, 0.95),
            'max': round(max(values), 1) if values else None,
            'over_target': sum(1 for v in values if v > FRESH_TARGET_SECONDS),
        }
    out['fresh_quarantined'] = {'n': len(quarantined), 'p50': _p(quarantined, 0.5), 'p95': _p(quarantined, 0.95)}
    out['catch_up_rows'] = {'n': len(catch_up_latency), 'p95': _p(catch_up_latency, 0.95)}
    out['quarantine_projection_p95_seconds'] = sample['quarantine_projection_p95_seconds']
    return out


def ladder(seed: int = 1) -> list[dict]:
    """Production today, then each lever added in ship order, with and without the catch-up owner."""
    steps = [
        (),
        ('lease_leak_fixed',),
        ('lease_leak_fixed', 'head_wait'),
        ('lease_leak_fixed', 'head_wait', 'recovery_dispatch_loop'),
        ('lease_leak_fixed', 'head_wait', 'recovery_dispatch_loop', 'fresh_gpu_priority'),
        ('lease_leak_fixed', 'head_wait', 'recovery_dispatch_loop', 'fresh_first'),
        tuple(LEVERS),
    ]
    return [replay(catch_up=catch_up, levers=step, seed=seed) for step in steps for catch_up in (False, True)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(ladder(args.seed), indent=2))


if __name__ == '__main__':
    main()
