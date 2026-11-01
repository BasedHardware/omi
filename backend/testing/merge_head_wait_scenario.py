"""Reverse catch-up replay for the bounded ordered-merge head wait (Fix C).

One catch-up owner uploads a contiguous backlog newest-first, as the app's
``nextSyncUploadBatch`` does, beside steady normal owners. A seeded share of
first-attempt completions is lost so the lease leaks until expiry (the Fix B
class), and a share of speech returns empty ASR so it quarantines and recovers
through the paid fallback. Projection is owner-serial. All provider, GPU and
customer data are synthetic; no production or network access is needed.

Shapes: ``run14`` is the allowlisted catch-up owner (about 108 rows over 4 min);
``run16`` is the design's burst (about 280 rows over 90 s, above the serial
projection drain rate). Each runs with strict order (W off) and W=60, with and
without leaked leases (without = Fix B).
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json

from testing.hermetic_network import block_outbound_network
from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.scorer import percentile, score
from testing.pipeline_sim.sim import SimConfig, Simulation
from testing.pipeline_sim.stt import STTProfile
from testing.pipeline_sim.workload import BURST, WorkloadSpec
from utils.batch_pipeline.scheduler import Scheduler

SHAPES = {
    'run14': {'rows': 108, 'arrival_seconds': 240.0},
    'run16': {'rows': 280, 'arrival_seconds': 90.0},
}


def _selected(segment_id: str, salt: str, percent: float) -> bool:
    digest = hashlib.sha256(f'{salt}:{segment_id}'.encode()).digest()
    return int.from_bytes(digest[:4], 'big') % 10_000 < percent * 100


def _leaky_scheduler(leak_percent: float, dropped: set[str]):
    class LeakyScheduler(Scheduler):
        """A lost first-attempt completion: the lease stays held until it expires."""

        def complete(self, result, token, now):
            segment = result.segment_id
            if segment not in dropped and _selected(segment, 'leak', leak_percent):
                job = self.store.run(lambda tx: tx.get('jobs', segment))
                if job.get('attempt') == 1:
                    dropped.add(segment)
                    return False
            return super().complete(result, token, now)

    return LeakyScheduler


CHAIN_WALK_ROWS = 64


def _chain_projector(simulation: Simulation):
    """MODEL of the owner-chain sweep: owner-serial projection in result-log order.

    The simulator's default projector walks capture order one row per sweep;
    production follows the owner's log chain (R3) and keeps walking up to 64
    rows per wake. A binding with an uncommitted sibling holds the chain here,
    which is conservative: production projects each committed row once its
    log predecessor persisted and holds only sibling completion. Catch-up
    rows are single-unit bindings, so their timings are unaffected.
    """
    walking: set[str] = set()

    async def walk(owner: str, records) -> None:
        try:
            for record in records:
                if simulation._fenced(record):
                    record.excluded = simulation._fenced(record)
                    continue
                record.projecting = True
                await simulation._project(record)
        finally:
            walking.discard(owner)

    def sweep() -> None:
        first_log: dict[str, int] = {}
        for (table, sid), row in simulation.store.rows.items():
            record = simulation.by_segment.get(sid) if table == 'results' else None
            if record is not None:
                first_log[record.job_id] = min(first_log.get(record.job_id, row['log_sequence']), row['log_sequence'])
        by_owner: dict[str, list] = {}
        for record in simulation.by_job.values():
            if record.projected_at is None and record.excluded is None and record.job_id in first_log:
                by_owner.setdefault(record.spec.owner, []).append(record)
        for owner, records in sorted(by_owner.items()):
            if owner in walking or any(record.projecting for record in records):
                continue
            chain = []
            for record in sorted(records, key=lambda r: first_log[r.job_id])[:CHAIN_WALK_ROWS]:
                jobs = [simulation.store.rows.get(('jobs', sid), {}) for sid in record.segment_ids]
                if not all(job.get('state') == 'committed' for job in jobs):
                    break
                chain.append(record)
            if chain:
                walking.add(owner)
                simulation.revision.spawn('projection', walk(owner, chain))

    return sweep


def _p95(values):
    value = percentile(values, 0.95)
    return round(value, 1) if value is not None else None


def _check_owner_chains(store) -> None:
    """Append-only owner chains with exact late marking: the R1/R2 invariants."""
    by_owner: dict[str, list[dict]] = {}
    for (table, _), row in store.rows.items():
        if table == 'results':
            by_owner.setdefault(row['owner_key'], []).append(row)
    for key, rows in by_owner.items():
        rows.sort(key=lambda row: row['log_sequence'])
        assert [row['log_sequence'] for row in rows] == list(range(1, len(rows) + 1)), key
        previous, high = None, None
        for row in rows:
            assert row['previous_segment_id'] == previous, row['segment_id']
            position = (row['capture_at'], row['segment_id'])
            assert bool(row['late_capture']) == (high is not None and position <= high), row['segment_id']
            high = position if high is None or position > high else high
            previous = row['segment_id']
        assert store.rows[('owners', key)]['watermark'] == {'capture_at': high[0], 'segment_id': high[1]}


def replay(
    shape: str = 'run16',
    *,
    head_wait: str = '60',
    leak_percent: float = 10.0,
    speech_empty_percent: float = 15.0,
    projection_seconds: float = 2.0,
    seed: int = 1,
) -> dict:
    spec = SHAPES[shape]
    rows, arrival = spec['rows'], spec['arrival_seconds']
    config = SimConfig(
        name=f'merge_head_wait_{shape}',
        seed=seed,
        workload=WorkloadSpec(
            owners=11,
            uploads_per_owner_per_hour=6.0,
            arrival_seconds=1800.0,
            speech_seconds=(60.0, 300.0),
            burst_owners=1,
            burst_uploads=rows,
            burst_at=60.0,
            burst_segment_seconds=(60.0, 60.0),
            near_silence_fraction=0,
            silence_fraction=0,
        ),
        gpu_pumps=2,
        pump_batch_size=8,
        gpu_seconds_per_item=1.0,
        projection_seconds=projection_seconds,
        # Summaries leave the projection chain through the outbox task lane.
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
        # The replay measures ordering, not the per-UID backfill speech budget.
        backfill_speech_seconds_per_day=10**9,
        # The catch-up depth hold is measured by testing/fresh_latency_scenario.py;
        # off here, the replay isolates the head wait.
        flags={'BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS': head_wait, 'BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH': 'off'},
    )
    dropped: set[str] = set()
    original = sim_module.Scheduler
    try:
        sim_module.Scheduler = _leaky_scheduler(leak_percent, dropped)
        simulation = Simulation(config)
        simulation._projector_sweep = _chain_projector(simulation)
        step = arrival / rows
        # The backlog is one contiguous recording uploaded newest-first: arrival
        # n carries the capture 60 s before arrival n-1.
        uploads, n = [], 0
        for upload in simulation.workload.uploads:
            if upload.owner_kind == BURST:
                at = config.workload.burst_at + n * step
                upload = replace(upload, at=at, recording_age=at + 86400.0 - (rows - n) * 60.0)
                n += 1
            uploads.append(upload)
        simulation.workload.uploads = uploads
        with block_outbound_network():
            result = simulation.run()
    finally:
        sim_module.Scheduler = original

    _check_owner_chains(result.store)
    assert max(result.modulate.calls_by_segment.values(), default=0) <= 1, 'vendor paid more than once per segment'
    burst = {owner for owner, kind in result.workload.owners.items() if kind == BURST}
    strata: dict[str, dict[str, list[float]]] = {'catch_up': {}, 'normal': {}}
    for stratum in strata.values():
        stratum.update(
            accept_to_ready=[],
            merge_wait=[],
            commit_to_projection=[],
            accept_to_projection=[],
            quarantine_to_projection=[],
        )
    late = committed = 0
    bypass = {'catch_up': 0, 'normal': 0}
    for record in result.records:
        if record.accepted_at is None or not record.segment_ids:
            continue
        name = 'catch_up' if record.spec.owner in burst else 'normal'
        stratum = strata[name]
        if record.projected_at is not None:
            stratum['accept_to_projection'].append(record.projected_at - record.accepted_at)
        for sid in record.segment_ids:
            job = result.store.rows.get(('jobs', sid), {})
            entry = result.store.rows.get(('results', sid))
            if entry:
                committed += 1
                late += bool(entry['late_capture'])
                bypass[name] += bool(entry.get('head_wait_bypass'))
                if 'ready_at' in job:
                    stratum['accept_to_ready'].append(job['ready_at'] - record.accepted_at)
                    stratum['merge_wait'].append(entry['committed_at'] - job['ready_at'])
                if record.projected_at is not None:
                    stratum['commit_to_projection'].append(record.projected_at - entry['committed_at'])
            if job.get('quarantined_at') and record.projected_at is not None:
                stratum['quarantine_to_projection'].append(record.projected_at - job['quarantined_at'])
    sample = score(result)
    return {
        'shape': shape,
        'head_wait': head_wait,
        'leak_percent': leak_percent,
        'leaked_leases': len(dropped),
        'committed': committed,
        'late_capture': late,
        'catch_up_head_wait_bypass': bypass['catch_up'],
        'normal_head_wait_bypass': bypass['normal'],
        'unprojected': sum(1 for r in result.records if r.accepted_at is not None and r.projected_at is None),
        **{
            f'{name}_{metric}_p95_seconds': _p95(values)
            for name, stratum in strata.items()
            for metric, values in stratum.items()
        },
        'catch_up_rows': len(strata['catch_up']['accept_to_projection']),
        'quarantine_cohort': sample['quarantine_projection_cohort_count'],
        'quarantine_projection_p95_seconds': sample['quarantine_projection_p95_seconds'],
    }


def matrix(shapes=tuple(SHAPES), seed: int = 1) -> list[dict]:
    return [
        replay(shape, head_wait=head_wait, leak_percent=leak, seed=seed)
        for shape in shapes
        for leak in (10.0, 0.0)
        for head_wait in ('off', '60')
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--shape', choices=sorted(SHAPES), action='append')
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(matrix(tuple(args.shape or SHAPES), args.seed), indent=2))


if __name__ == '__main__':
    main()
