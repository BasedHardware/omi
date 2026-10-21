"""Reverse-upload qualification using the virtual-clock harness from PR #22201.

Until that harness lands, put its backend directory on PYTHONPATH. All provider,
GPU and customer data are synthetic. No production or network access is needed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path

from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.scorer import percentile, score
from testing.pipeline_sim.sim import SimConfig, Simulation
from testing.pipeline_sim.store import SimTransaction
from testing.pipeline_sim.stt import STTProfile
from testing.pipeline_sim.workload import WorkloadSpec
from testing.hermetic_network import block_outbound_network


def ready_predecessor(tx, owner_key, priority, segment_id):
    """Model the new indexed query, excluding stale links on non-ready rows."""
    jobs = [
        row
        for (table, _), row in tx.store.rows.items()
        if table == 'jobs'
        and row['owner_key'] == owner_key
        and row['priority'] == priority
        and row['state'] == 'ready'
        and row.get('next') == segment_id
    ]
    return deepcopy(jobs[0]) if len(jobs) == 1 else None


def qualify(*, scheduler_class=None, count=160, batch_size=1, gpu_seconds=10, serving_interval=1):
    config = SimConfig(
        name='reverse_upload_ordered_head',
        seed=1,
        workload=WorkloadSpec(
            owners=1,
            burst_owners=1,
            burst_uploads=count,
            burst_at=1,
            burst_segment_seconds=(30, 30),
            near_silence_fraction=0,
            silence_fraction=0,
        ),
        gpu_pumps=1,
        pump_batch_size=batch_size,
        gpu_seconds_per_item=gpu_seconds,
        serving_interval_seconds=serving_interval,
        stt=STTProfile(
            min_replicas=1,
            max_replicas=1,
            per_pod_concurrency=8,
            base_latency_seconds=1,
            seconds_per_audio_second=0,
            latency_sigma=0,
        ),
        horizon_seconds=3600,
        flags={'BATCH_PIPELINE_HEAD_PRIORITY_ENABLED': 'true'},
    )
    original_scheduler = sim_module.Scheduler
    original_query = getattr(SimTransaction, 'ready_predecessor', None)
    try:
        if scheduler_class is not None:
            sim_module.Scheduler = scheduler_class
        SimTransaction.ready_predecessor = ready_predecessor
        simulation = Simulation(config)
        # One synthetic owner, all 160 admissions before the first GPU poll.
        # Arrival order: newest capture first, oldest (capture head) at FIFO 159.
        simulation.workload.uploads = [
            replace(upload, at=1, recording_age=86400 + n * 60) for n, upload in enumerate(simulation.workload.uploads)
        ]
        ready_at, leased, committed, waits, ready_backlog = {}, [], [], [], []

        def observe(address, previous, row):
            table, sid = address
            if table == 'jobs' and row.get('state') != previous.get('state'):
                if row.get('state') == 'leased':
                    leased.append(sid)
                if row.get('state') == 'result_ready':
                    ready_at[sid] = simulation.clock.now
                    ready_backlog.append(len(simulation.store.jobs_in_state('result_ready')))
            if table == 'results' and not previous:
                committed.append(sid)
                waits.append(row['committed_at'] - ready_at[sid])

        simulation.store.observers.append(observe)
        with block_outbound_network():
            result = simulation.run()
        jobs = sorted(result.store.jobs(), key=lambda row: (row['capture_at'], row['segment_id']))
        ordered = [row['segment_id'] for row in jobs]
        assert committed == ordered, 'capture-order predecessor contract violated'
        assert len(set(leased)) == len(leased) == len(jobs) == count
        sample = score(result)
        return {
            'jobs': len(jobs),
            'committed': len(committed),
            'first_lease_capture_rank': ordered.index(leased[0]),
            'predecessor_wait_p50_seconds': round(percentile(waits, 0.5), 3),
            'predecessor_wait_p95_seconds': round(percentile(waits, 0.95), 3),
            'predecessor_wait_max_seconds': round(max(waits), 3),
            'peak_result_ready': max(ready_backlog),
            'verdict': sample['verdict'],
            'projection_p95_seconds': sample['sim']['accept_to_projection_p95_seconds'],
        }
    finally:
        sim_module.Scheduler = original_scheduler
        if original_query is None:
            del SimTransaction.ready_predecessor
        else:
            SimTransaction.ready_predecessor = original_query


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source', type=Path)
    args = parser.parse_args()
    output = {}
    if args.baseline_source:
        spec = importlib.util.spec_from_file_location('ordered_head_baseline', args.baseline_source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output['before'] = qualify(scheduler_class=module.Scheduler)
    output['after'] = qualify()
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
