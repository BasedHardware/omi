"""Building blocks of testing/pipeline_sim: virtual clock, store, capacity models, scorer, CLI."""

import asyncio
import json
import random
import time

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.pipeline_sim import cli
from testing.pipeline_sim.clock import SimulationStalled, VirtualClock, run_virtual
from testing.pipeline_sim.models import (
    COMPLETED,
    FIRE_AND_FORGET,
    KILLED,
    REQUEST_SCOPED,
    ExecutorModel,
    RevisionModel,
    SequencerModel,
)
from testing.pipeline_sim.scorer import TERMINAL_UNRECOVERED_SPEECH_LIMIT, percentile, verdict
from testing.pipeline_sim.sim import SimConfig, simulate
from testing.pipeline_sim.store import CustomerData, SimStore
from testing.pipeline_sim.stt import EMPTY, TIMEOUT, WORDS, ExhaustionWindow, FakeSTT, STTProfile
from testing.pipeline_sim.workload import WorkloadSpec, generate
from testing.pipeline_sim.scorer import score
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.scheduler import Scheduler


def test_virtual_clock_runs_hours_without_wall_time_and_fires_epoch_sized_timers():
    clock = VirtualClock()
    fired = []

    async def main():
        loop = asyncio.get_running_loop()
        # A timer due exactly "now + tiny" at epoch magnitude must still fire (float ulp ~2e-7).
        loop.call_at(clock.now + 1e-7, fired.append, 'tiny')
        await asyncio.sleep(6 * 3600)
        await asyncio.wait_for(asyncio.sleep(10), timeout=20)
        return clock.elapsed()

    started = time.monotonic()
    assert run_virtual(clock, main) == pytest.approx(6 * 3600 + 10)
    assert fired == ['tiny']
    assert time.monotonic() - started < 2


def test_virtual_loop_reports_a_modelling_deadlock():
    async def main():
        await asyncio.get_running_loop().create_future()

    with pytest.raises(SimulationStalled):
        run_virtual(VirtualClock(), main)


def _item(segment, owner='sim-owner-a', capture=1.0, conversation=None):
    return WorkItem(
        segment,
        owner,
        capture,
        f'sim://audio/{segment}',
        30.0,
        Priority.FRESH,
        conversation_id=conversation,
        privacy_generation=0,
    )


def test_store_buffers_writes_and_repeats_the_production_privacy_flush_guard():
    customer = CustomerData()
    customer.add_user('sim-owner-a')
    store = SimStore(customer)
    queue = Scheduler(store)
    assert queue.enqueue(_item('s1'), 10.0)
    leased = queue.pull(11.0)
    assert [lease.item.segment_id for lease in leased] == ['s1']

    def failing(tx):
        tx.put('jobs', 's1', {**tx.get('jobs', 's1'), 'state': 'mutated'})
        raise RuntimeError('abort')

    with pytest.raises(RuntimeError):
        store.run(failing)
    assert store.rows[('jobs', 's1')]['state'] == 'leased'  # aborted body applies nothing

    customer.block_privacy('sim-owner-a')
    with pytest.raises(BatchPrivacyBlocked):
        queue.heartbeat('s1', leased[0].token, 12.0)  # every jobs write re-runs the real fence
    with pytest.raises(BatchPrivacyBlocked):
        queue.enqueue(_item('s2', capture=2.0), 13.0)


def test_store_purge_unlinks_queue_so_the_owner_keeps_draining():
    customer = CustomerData()
    customer.add_user('sim-owner-a')
    store = SimStore(customer)
    queue = Scheduler(store)
    for n in range(3):
        queue.enqueue(_item(f's{n}', capture=float(n), conversation=f'sim-conv-{n}'), 1.0)
    customer.delete_conversation('sim-owner-a', 'sim-conv-0')
    assert store.purge('sim-owner-a', 'sim-conv-0') == 1
    assert [lease.item.segment_id for lease in queue.pull(2.0, 2)] == ['s1', 's2']


def test_fake_stt_queues_times_out_and_honours_an_exhaustion_window():
    clock = VirtualClock()
    profile = STTProfile(
        min_replicas=1,
        max_replicas=1,
        per_pod_concurrency=1,
        base_latency_seconds=10.0,
        seconds_per_audio_second=0.0,
        latency_sigma=0.0,
        queue_timeout_seconds=15.0,
        near_silence_empty_rate=0.0,
        exhaustion=(ExhaustionWindow(100.0, 200.0, EMPTY),),
    )
    stt = FakeSTT(clock, profile, random.Random(1))

    async def main():
        burst = await asyncio.gather(*(stt.request('speech', 60.0) for _ in range(3)))
        await asyncio.sleep(150.0 - clock.elapsed())
        during = await stt.request('speech', 60.0)
        return burst, during

    burst, during = run_virtual(clock, main)
    assert burst == [WORDS, WORDS, TIMEOUT]  # one slot, 10 s service, 15 s queue timeout
    assert during == EMPTY
    assert stt.stats.timeouts == 1 and stt.stats.empty == 1


def test_sequencer_model_is_serial_per_owner_unless_k_is_raised():
    def drain(k):
        clock = VirtualClock()
        finished = []

        async def job(name):
            await asyncio.sleep(10.0)
            finished.append(clock.elapsed())

        async def main():
            sequencer = SequencerModel(clock, job, per_owner_concurrency=k, dispatch_seconds=0.0)
            for n in range(6):
                sequencer.register('sim-owner-a', n, float(n))
            await asyncio.sleep(100.0)
            return sequencer.stats.max_active_per_owner

        return run_virtual(clock, main), max(finished)

    assert drain(1) == (1, pytest.approx(60.0))
    assert drain(3) == (3, pytest.approx(20.0))


def test_revision_model_kills_only_unawaited_work_after_drain_and_grace():
    clock = VirtualClock()
    revision = RevisionModel(clock, grace_seconds=5.0)
    executor = ExecutorModel('sync_executor', 1, clock)

    async def main():
        request = asyncio.ensure_future(revision.request('sync-job', executor.run('transcription', 30.0)))
        revision.spawn('summary', asyncio.sleep(60.0))
        revision.spawn('quick', asyncio.sleep(1.0))
        await asyncio.sleep(2.0)
        await revision.replace()
        await request

    run_virtual(clock, main)
    outcomes = {(unit.label, unit.scope, unit.outcome) for unit in revision.report.units}
    assert outcomes == {
        ('sync-job', REQUEST_SCOPED, COMPLETED),
        ('summary', FIRE_AND_FORGET, KILLED),
        ('quick', FIRE_AND_FORGET, COMPLETED),
    }
    assert [unit.label for unit in revision.report.lost] == ['summary']


def test_workload_is_seeded_and_synthetic():
    spec = WorkloadSpec(owners=5, burst_owners=1, burst_uploads=10, duplicate_upload_fraction=0.5)
    first, second = generate(spec, random.Random('7')), generate(spec, random.Random('7'))
    assert first.uploads == second.uploads
    assert all(owner.startswith('sim-owner-') for owner in first.owners)
    assert sum(upload.owner_kind == 'burst' for upload in first.uploads) == 10


def _sample(**changes):
    sample = {
        'errors': 0,
        'unrecovered_quarantines_over_sla': 0,
        'admissions': 10,
        'completed': 10,
        'terminal_unrecovered_speech_status': 'MEASURED',
        'projected_success_units': 10,
        'hold_elapsed_seconds': 3600,
        'oldest_unprojected_seconds': 0,
        'recovery_obligations_over_15m': 0,
        'projection_obligations_over_15m': 0,
        'quarantine_projection_over_900_count': 0,
        'terminal_unrecovered_speech_fraction': 0.0,
        'quarantine_projection_cohort_count': 0,
        'quarantine_projection_p95_seconds': None,
        'quarantine_projection_over_600_count': 0,
        'first_summary_checked_conversations': 30,
        'first_summary_deadline_breaches': 0,
        'first_summary_overdue_over_60_seconds': False,
    }
    sample.update(changes)
    return sample


@pytest.mark.parametrize(
    'changes,expected',
    [
        ({}, 'GATE_PASS'),
        ({'projection_obligations_over_15m': 1}, 'GATE_FAIL obligation_over_15m'),
        (
            {'terminal_unrecovered_speech_fraction': TERMINAL_UNRECOVERED_SPEECH_LIMIT * 1.01},
            'GATE_FAIL terminal_unrecovered_speech_over_0_2pct',
        ),
        (
            {'quarantine_projection_cohort_count': 20, 'quarantine_projection_p95_seconds': 301},
            'GATE_FAIL quarantine_projection_p95_over_5m',
        ),
        # Low-sample caveat: under 20 quarantines p95 is not judged, two >10 min outliers are.
        ({'quarantine_projection_cohort_count': 5, 'quarantine_projection_p95_seconds': 500}, 'GATE_PASS'),
        (
            {
                'quarantine_projection_cohort_count': 5,
                'quarantine_projection_p95_seconds': 700,
                'quarantine_projection_over_600_count': 2,
            },
            'GATE_FAIL quarantine_projection_p95_over_5m',
        ),
        ({'first_summary_deadline_breaches': 2}, 'GATE_FAIL first_summary_deadline'),
        ({'first_summary_deadline_breaches': 1}, 'GATE_PASS'),
        ({'completed': 9}, 'GATE_FAIL timeout_incomplete'),
    ],
)
def test_verdict_mirrors_fleet_gate_thresholds(changes, expected):
    assert verdict(_sample(**changes))[0] == expected


def test_intermediate_poll_keeps_incomplete_work_pending_like_the_gate():
    assert verdict(_sample(completed=9), final=False) is None
    assert percentile([5, 1, 3, 2, 4], 0.95) == 5


def test_small_batch_run_is_deterministic_and_drives_the_real_state_machine():
    config = SimConfig(seed=3, workload=WorkloadSpec(owners=6, arrival_seconds=900.0), horizon_seconds=3600.0)
    first, second = score(simulate(config)), score(simulate(config))
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(second, sort_keys=True, default=str)
    assert first['admissions'] > 0 and first['sim']['job_states'] == {'committed': first['admissions']}
    assert first['verdict'] == 'GATE_PASS'


def test_cli_prints_a_json_gate_sample(capsys):
    code = cli.main(['run', 'burst_owner_serial_sequencer', '--seed', '2', '--json', '--param', 'burst_uploads=40'])
    sample = json.loads(capsys.readouterr().out)
    assert code == sample['verdict_code']
    assert sample['sim']['scenario'] == 'burst_owner_serial_sequencer' and sample['sim']['seed'] == 2
    assert {'verdict', 'admissions', 'quarantine_projection_p95_seconds', 'first_summary_breach_rate'} <= set(sample)
