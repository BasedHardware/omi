"""Each named scenario reproduces its production phenomenon on the simulated pipeline (seeded).

Every variant runs once in the module fixture (setup phase); tests only assert on the samples, so the
fast-unit CPU guard measures assertions, not simulations.
"""

import pytest

from testing.pipeline_sim.scenarios import run
from testing.pipeline_sim.workload import NORMAL, PRIVACY_AT_ADMISSION

# Recovery dispatched only from the serving pass: the cadence #22321 was measured on.
PASS_DISPATCH = {'BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS': 'off'}

VARIANTS = {
    'serial': ('burst_owner_serial_sequencer', {}),
    'widened': ('burst_owner_serial_sequencer', {'per_owner_concurrency': 32}),
    'steady': ('mixed_fleet_steady', {}),
    'exhaustion': ('provider_exhaustion_window', {'overrides': {'flags': PASS_DISPATCH}}),
    'exhaustion_dispatch_loop': ('provider_exhaustion_window', {}),
    # Diagnostic counterfactual only; the exhaustion baseline uses shipping defaults.
    'exhaustion_former_rate': (
        'provider_exhaustion_window',
        {'overrides': {'flags': {**PASS_DISPATCH, 'BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE': '1'}}},
    ),
    'stale': ('stale_finalize_targets', {}),
    # Strict merge order (head wait off) isolates what the purge alone prevents.
    'stale_no_purge': (
        'stale_finalize_targets',
        {'overrides': {'purge_on_fence': False, 'flags': {'BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS': 'off'}}},
    ),
    'stale_no_purge_head_wait': ('stale_finalize_targets', {'overrides': {'purge_on_fence': False}}),
    'privacy': ('privacy_blocked_users', {}),
    'summary_shared': ('summary_behind_transcription', {}),
    'summary_isolated': ('summary_behind_transcription', {'summary_pool': 'isolated'}),
}


@pytest.fixture(scope='module')
def samples() -> dict[str, dict]:
    return {key: run(name, 1, **kwargs) for key, (name, kwargs) in VARIANTS.items()}


def test_burst_owner_drains_serially_and_breaches_the_15_minute_obligation(samples):
    serial = samples['serial']
    assert serial['verdict'] == 'GATE_FAIL obligation_over_15m'
    assert serial['sim']['sequencer']['max_active_per_owner'] == 1
    assert serial['sim']['sequencer']['max_pending_per_owner'] >= 360
    # ~365 sequential jobs: the last capture waits hours, not minutes.
    assert serial['sim']['accept_to_projection_max_seconds'] > 2 * 3600

    widened = samples['widened']
    assert widened['verdict'] == 'GATE_PASS'
    assert widened['sim']['accept_to_projection_max_seconds'] < 15 * 60


def test_mixed_fleet_steady_passes_every_gate(samples):
    sample = samples['steady']
    assert sample['verdict'] == 'GATE_PASS'
    assert sample['sim']['completion_rate'] == 1.0
    assert sample['sim']['job_states'] == {'committed': sample['admissions']}
    assert sample['sim']['accept_to_projection_p95_seconds'] < 120
    assert sample['sim']['max_paid_calls_per_segment'] <= 1


def test_bounded_recovery_clears_exhaustion_tail_without_hiding_unrecovered_audio(samples):
    sample = samples['exhaustion']
    sim = sample['sim']
    assert sample['quarantine_projection_cohort_count'] >= 20  # above the gate's low-sample floor
    assert 0 < sample['quarantine_projection_p95_seconds'] < 300
    # Main #22321 removes the dispatch bottleneck. A real modeled failed-held
    # piece still fails the gate; faster scheduling must not imply full recovery.
    assert sample['verdict'] == 'GATE_FAIL unrecovered_quarantine'
    assert sim['recovery_states']['failed_held'] > 0
    assert sample['unrecovered_quarantines'] == sim['recovery_states']['failed_held']
    former = samples['exhaustion_former_rate']
    assert former['quarantine_projection_p95_seconds'] > 300
    assert former['verdict'] == 'GATE_FAIL quarantine_projection_p95_over_5m'
    assert former['sim']['paid_fallback_calls'] == sim['paid_fallback_calls']
    assert former['sim']['recovery_states'] == sim['recovery_states']
    assert former['sim']['max_paid_calls_per_segment'] == 1
    # Every quarantine spent exactly one paid call (the durable intent is never reissued).
    assert sim['paid_fallback_calls'] == sample['quarantine_projection_cohort_count']
    assert sim['max_paid_calls_per_segment'] == 1
    assert set(sim['recovery_states']) <= {'recovered', 'failed_held'}
    assert sum(sim['recovery_states'].values()) == sim['paid_fallback_calls']
    assert sim['recovery_states']['recovered'] >= 0.95 * sim['paid_fallback_calls']


def test_recovery_dispatch_loop_shortens_the_quarantine_tail_without_extra_paid_calls(samples):
    pass_only, loop = samples['exhaustion'], samples['exhaustion_dispatch_loop']
    assert loop['quarantine_projection_cohort_count'] == pass_only['quarantine_projection_cohort_count']
    assert loop['quarantine_projection_p95_seconds'] < pass_only['quarantine_projection_p95_seconds']
    assert loop['sim']['paid_fallback_calls'] == pass_only['sim']['paid_fallback_calls']
    assert loop['sim']['max_paid_calls_per_segment'] <= 1
    # Unrecovered audio is still scored, whichever units the model leaves held.
    assert loop['unrecovered_quarantines'] == loop['sim']['recovery_states'].get('failed_held', 0)


def test_stale_finalize_targets_are_neither_failures_nor_paid(samples):
    sample = samples['stale']
    sim = sample['sim']
    assert sample['verdict'] == 'GATE_PASS'
    assert sim['excluded_uploads'].get('deleted_target', 0) > 0
    assert sim['paid_fallback_calls_on_excluded_segments'] == 0
    assert sim['paid_fallback_calls_after_privacy_fence'] == 0
    # Duplicate uploads and duplicate worker/recovery deliveries never double-spend or double-commit.
    assert sim['counters']['duplicate_uploads_deduplicated'] > 0
    assert sim['max_paid_calls_per_segment'] <= 1
    assert sample['errors'] == 0 and sim['completion_rate'] == 1.0


def test_without_the_purge_a_fenced_head_blocks_the_owners_ordered_merge(samples):
    sample = samples['stale_no_purge']
    states = sample['sim']['job_states']
    assert states.get('privacy_blocked', 0) > 0 and states.get('result_ready', 0) > 0
    assert sample['projection_obligations_over_15m'] > 0


def test_bounded_head_wait_commits_past_a_fenced_head_without_the_purge(samples):
    # Each released row still passes its own privacy fence; only the fenced head stays behind.
    states = samples['stale_no_purge_head_wait']['sim']['job_states']
    assert states.get('privacy_blocked', 0) > 0 and states.get('result_ready', 0) == 0


def test_privacy_blocked_users_get_no_paid_calls_or_projection_and_are_reported_distinctly(samples):
    sample = samples['privacy']
    sim = sample['sim']
    assert sim['upload_status']['rejected_privacy'] > 0
    assert sim['paid_fallback_calls_by_owner_kind'].get(PRIVACY_AT_ADMISSION, 0) == 0
    assert sim['paid_fallback_calls_after_privacy_fence'] == 0
    assert sim['counters']['purged_jobs'] > 0
    assert sim['paid_fallback_calls_by_owner_kind'][NORMAL] > 0
    assert sim['excluded_uploads'].get('privacy_blocked', 0) > 0
    assert sample['verdict'] == 'GATE_PASS'


def test_first_summaries_queue_behind_transcription_on_the_shared_executor(samples):
    shared = samples['summary_shared']
    isolated = samples['summary_isolated']
    assert shared['verdict'] == 'GATE_FAIL first_summary_deadline'
    assert shared['first_summary_breach_rate'] > 0.05
    assert isolated['verdict'] == 'GATE_PASS'
    assert isolated['first_summary_deadline_breaches'] == 0
    shared_wait = shared['sim']['executors']['sync_executor']['p95_wait_seconds']['summary']
    isolated_wait = isolated['sim']['executors']['summary']['p95_wait_seconds']['summary']
    assert shared_wait > 60 > isolated_wait
