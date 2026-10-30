"""5% run 18 replay: post-recovery projection wait for multi-unit catch-up contents.

Run 18 (T0 2026-10-20 13:51Z) scored quarantine -> projection p95 322 s over
22 cohort units. The tail units recovered in 11-36 s, then waited:

- 65-86 s settled -> commit: the recovered row sat behind an owner's leased
  head (a leaked-lease attempt-2/3 row) for the 60 s head wait plus a
  maintenance tick. The post-recovery owner wake ran first and committed
  nothing (46 of 54 wakes advanced no row), so projection waited for the
  20 s serving sweep after the bypass commit.
- about 200 s persisted -> content completed: content siblings sat behind the
  same leased head. The GPU worker image predated Fix C, so its rows carried
  no ``ready_at`` and could never start a head-wait bypass themselves.

This replay models catch-up owners whose contents hold several 10-30 s units,
leaked leases (Fix B not live), empty-ASR quarantine with paid recovery, and
the production recovery wake: ``/recover-quarantine`` -> ``reconcile(owner_id,
recovered)`` -> ``drain_owner`` -> owner chain walk. It compares the release
switch off and on, with the GPU worker stamping ``ready_at`` or not (run 18's
worker did not). All data is synthetic; no network access.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import random
from types import SimpleNamespace

from testing.hermetic_network import block_outbound_network
from testing.merge_head_wait_scenario import _check_owner_chains, _chain_projector, _leaky_scheduler, _p95
from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.scorer import score
from testing.pipeline_sim.sim import SimConfig, Simulation
from testing.pipeline_sim.stt import STTProfile
from testing.pipeline_sim.workload import BURST, SPEECH, SegmentSpec, WorkloadSpec

# Run 18's tail contents: 6-9 units of 10-30 s, three heavy catch-up owners.
CONTENTS_PER_OWNER = 14
UNITS_PER_CONTENT = (6, 9)
UNIT_SECONDS = (10.0, 30.0)
CONTENT_SPACING_SECONDS = 40.0


def _run18_scheduler(leak_percent: float, dropped: set[str], gpu_ready_at: bool):
    base = _leaky_scheduler(leak_percent, dropped)

    class Run18Scheduler(base):
        def complete(self, result, token, now):
            accepted = super().complete(result, token, now)
            if accepted and not gpu_ready_at:
                # Run 18's GPU worker image predated Fix C: completed rows had no ready_at.
                row = self.store.rows.get(('jobs', result.segment_id), {})
                row.pop('ready_at', None)
            return accepted

    return Run18Scheduler


def replay(
    *,
    release: bool = True,
    gpu_ready_at: bool = False,
    leak_percent: float = 10.0,
    speech_empty_percent: float = 15.0,
    projection_seconds: float = 1.5,
    seed: int = 1,
) -> dict:
    config = SimConfig(
        name='recovered_release_run18',
        seed=seed,
        workload=WorkloadSpec(
            owners=12,
            uploads_per_owner_per_hour=6.0,
            arrival_seconds=1800.0,
            speech_seconds=(30.0, 120.0),
            burst_owners=3,
            burst_uploads=CONTENTS_PER_OWNER,
            burst_at=60.0,
            burst_segment_seconds=UNIT_SECONDS,
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
            base_latency_seconds=4.0,
            seconds_per_audio_second=0.02,
            speech_empty_rate=speech_empty_percent / 100,
        ),
        horizon_seconds=3 * 3600.0,
        backfill_speech_seconds_per_day=10**9,
        flags={
            'BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS': '60',
            # Run 18's image (44430ae8) predates the catch-up depth hold; the sim's
            # whole-content projector would also deadlock against it.
            'BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH': 'off',
            'BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED': 'true' if release else 'false',
        },
    )
    dropped: set[str] = set()
    original = sim_module.Scheduler
    try:
        sim_module.Scheduler = _run18_scheduler(leak_percent, dropped, gpu_ready_at)
        simulation = Simulation(config)
        sweep = _chain_projector(simulation)
        simulation._projector_sweep = sweep
        rng = random.Random(seed)
        uploads, per_owner = [], {}
        for upload in simulation.workload.uploads:
            if upload.owner_kind == BURST:
                # Newest-first catch-up: each content is one recording of several units.
                n = per_owner.get(upload.owner, 0)
                per_owner[upload.owner] = n + 1
                count = rng.randint(*UNITS_PER_CONTENT)
                segments = tuple(
                    SegmentSpec(index, round(rng.uniform(*UNIT_SECONDS), 2), SPEECH) for index in range(count)
                )
                at = config.workload.burst_at + n * CONTENT_SPACING_SECONDS
                upload = replace(
                    upload, at=at, recording_age=at + 3600.0 - (CONTENTS_PER_OWNER - n) * 240.0, segments=segments
                )
            uploads.append(upload)
        simulation.workload.uploads = sorted(uploads, key=lambda u: (u.at, u.upload_id))
        # Seed ground truth for the reshaped contents' new units (idempotent setdefault).
        simulation.truth.clear()
        simulation._seed_customers()

        def project_owner(owner_id, recovered=None):
            sweep()
            return []

        start = simulation._start_supervisor

        def start_supervisor():
            serving, recovery = simulation.serving, simulation.recovery
            serving.projector = SimpleNamespace(sweep=sweep, project_owner=project_owner)
            # Production's /recover-quarantine makes ONE reconcile call carrying
            # the owner wake. The sim handler calls reconcile() with no
            # arguments right after recover() returns (no await between them),
            # so that call becomes the single owner wake; the supervisor's
            # periodic calls pass keywords and are unchanged.
            last: dict = {}
            recover, reconcile = recovery.recover, serving.reconcile

            def recover_and_note(segment_id, owner_id):
                outcome = recover(segment_id, owner_id)
                last.update(segment=segment_id, owner=owner_id)
                return outcome

            def reconcile_as_wake(**kwargs):
                if not kwargs and last:
                    wake = dict(last)
                    last.clear()
                    return reconcile(owner_id=wake['owner'], recovered=wake['segment'])
                return reconcile(**kwargs)

            recovery.recover = recover_and_note
            serving.reconcile = reconcile_as_wake
            start()

        simulation._start_supervisor = start_supervisor
        with block_outbound_network():
            result = simulation.run()
    finally:
        sim_module.Scheduler = original

    _check_owner_chains(result.store)
    assert max(result.modulate.calls_by_segment.values(), default=0) <= 1, 'vendor paid more than once per segment'
    settle_to_commit, released = [], 0
    for (table, sid), job in result.store.rows.items():
        if table != 'jobs' or job.get('recovery_state') != 'recovered':
            continue
        entry = result.store.rows.get(('results', sid))
        settled = (job.get('recovery') or {}).get('settled_at')
        if entry and settled:
            settle_to_commit.append(entry['committed_at'] - settled)
            released += bool(entry.get('recovered_release'))
    sample = score(result)
    return {
        'release': release,
        'gpu_ready_at': gpu_ready_at,
        'leak_percent': leak_percent,
        'leaked_leases': len(dropped),
        'recovered_units': len(settle_to_commit),
        'recovered_release_commits': released,
        'recovered_settle_to_commit_p95_seconds': _p95(settle_to_commit),
        'quarantine_cohort': sample['quarantine_projection_cohort_count'],
        'quarantine_projection_p95_seconds': sample['quarantine_projection_p95_seconds'],
        'quarantine_projection_max_seconds': sample['quarantine_projection_max_seconds'],
        'unprojected': sum(1 for r in result.records if r.accepted_at is not None and r.projected_at is None),
    }


def matrix(seed: int = 1) -> list[dict]:
    return [
        replay(release=release, gpu_ready_at=gpu_ready_at, leak_percent=leak, seed=seed)
        for leak in (10.0, 0.0)
        for gpu_ready_at in (False, True)
        for release in (False, True)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(matrix(args.seed), indent=2))


if __name__ == '__main__':
    main()
