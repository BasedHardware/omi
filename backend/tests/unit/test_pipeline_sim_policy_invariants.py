"""Generated batch/listen policy invariants and replay coverage."""

from dataclasses import replace

import pytest

from config.policy.batch import BatchUnitPolicy
from config.policy.covering_array import pairwise_covering_array
from config.policy.generator import FACTOR_DOMAINS, generate_policy_cases, policy_pairwise_array
from config.policy.listen import ListenSessionPolicy
from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.policy_invariants import assert_policy_invariants, simulate_policy_case
from testing.pipeline_sim.sim import SimConfig, simulate
from testing.pipeline_sim.stt import EMPTY, ExhaustionWindow, FakeModulate, ModulateProfile, SPEECH, STTProfile
from testing.pipeline_sim.trace import GOLDEN_CONFIGS, golden_trace, trace
from testing.pipeline_sim.workload import NORMAL, SegmentSpec, UploadSpec, Workload, WorkloadSpec, content_id_for

PR_SEED = 20261020


@pytest.fixture(scope='module')
def generated_runs():
    cases = generate_policy_cases(PR_SEED)
    return tuple((case, simulate_policy_case(case, seed=PR_SEED + case.index)) for case in cases)


@pytest.fixture(scope='module')
def policy_array():
    return policy_pairwise_array(PR_SEED)


def test_policy_pairwise_generator_covers_every_feasible_pair(policy_array):
    array = policy_array
    assert array.factor_count == len(FACTOR_DOMAINS)
    assert array.candidate_count > 0
    assert array.feasible_pair_count == array.covered_pair_count
    assert array.feasible_pair_count == 5_045
    assert len(array.rows) == 33
    assert len(generate_policy_cases(PR_SEED)) == len(array.rows)
    assert (
        pairwise_covering_array(
            {'left': (False, True), 'right': ('a', 'b')},
            valid=lambda _row: True,
            partial_valid=lambda _row: True,
            seed=PR_SEED,
        ).covered_pair_count
        == 4
    )


def test_covering_array_proves_feasibility_for_rare_constrained_pairs():
    factors = {f'factor_{index}': (False, True) for index in range(6)}
    array = pairwise_covering_array(
        factors,
        valid=lambda row: all(row.values()),
        partial_valid=lambda row: all(row.values()),
        seed=PR_SEED,
    )
    assert array.feasible_pair_count == 15
    assert array.covered_pair_count == 15
    assert array.rows == ({name: True for name in factors},)


def test_full_pairwise_generated_policies_preserve_pipeline_and_listen_invariants(generated_runs):
    cases = [case for case, _ in generated_runs]
    results = [result for _, result in generated_runs]
    assert len(cases) == 33
    assert any(case.batch_policy.batch_enabled for case in cases)
    assert any(not case.batch_policy.batch_enabled for case in cases)
    assert any(result.records for result in results)
    assert any(record.excluded == 'deleted_target' for result in results for record in result.records)
    for result in results:
        assert_policy_invariants(result)


def test_seeded_double_vendor_charge_is_detected(monkeypatch):
    spec = WorkloadSpec(
        owners=1,
        uploads_per_owner_per_hour=1.0,
        arrival_seconds=1.0,
        segments_per_upload=(1, 1),
        speech_seconds=(60.0, 60.0),
        near_silence_fraction=0.0,
        silence_fraction=0.0,
    )
    upload = UploadSpec(
        upload_id='seeded-double-charge',
        owner='sim-owner-0000',
        owner_kind=NORMAL,
        at=0.0,
        recording_age=60.0,
        content_id=content_id_for('seeded-double-charge'),
        segments=(SegmentSpec(0, 60.0, SPEECH),),
    )
    workload = Workload(spec=spec, owners={'sim-owner-0000': NORMAL}, uploads=[upload])
    monkeypatch.setattr(sim_module, 'generate', lambda _spec, _rng: workload)
    original = FakeModulate.__call__

    def double_charge(self, item, binding, audio):
        original(self, item, binding, audio)
        return original(self, item, binding, audio)

    monkeypatch.setattr(FakeModulate, '__call__', double_charge)
    result = simulate(
        SimConfig(
            name='seeded-double-vendor-charge',
            seed=PR_SEED,
            workload=spec,
            stt=STTProfile(
                min_replicas=1,
                max_replicas=1,
                exhaustion=(ExhaustionWindow(0.0, 3600.0, EMPTY),),
            ),
            modulate=ModulateProfile(speech_recover_rate=1.0, latency_sigma=0.0),
            horizon_seconds=3600.0,
            policy=BatchUnitPolicy(batch_enabled=True, batch_percent=100.0),
            listen_policy=ListenSessionPolicy(),
        )
    )
    assert result.modulate.calls_by_segment
    assert max(result.modulate.calls_by_segment.values()) == 2
    with pytest.raises(AssertionError, match='vendor paid more than once per segment'):
        assert_policy_invariants(result)


def test_policy_window_recorded_policy_id_replays_the_golden_decision():
    config = GOLDEN_CONFIGS['policy_window']()
    expected = golden_trace('policy_window')
    recorded_run = simulate(config)
    recorded = next(record.first_summary_policy for record in recorded_run.records if record.first_summary_policy)
    assert recorded.policy_id

    replayed = replace(
        config,
        flags={**config.flags, 'FIRST_SUMMARY_DEADLINE_PERCENT': '100'},
        policy_parts={'first_summary': recorded.to_dict()},
    )
    actual = trace(replayed)
    assert actual == expected
    assert actual['first_summary_policy']['recorded_enabled'] == [False]
