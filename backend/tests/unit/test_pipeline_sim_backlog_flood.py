"""A flood of settled backlog must not consume the capacity fresh projection needs.

All four full-scale arms share one same-seed no-flood baseline: its short chains
produce identical metrics under both scheduler settings. Four flood arms run in
isolated processes because the sim patches process-global runtime seams. The
unmetered/FIFO arm reproduces the 2026-11-13 incident above a 2x p90 regression.
"""

from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from testing.pipeline_sim.backlog_flood import BacklogFloodSimulation, fresh_baseline, run_backlog_flood
from testing.pipeline_sim.scenarios import backlog_flood_fresh_latency


def _config(release: str, first_turn: int, *, flood: bool = True):
    return backlog_flood_fresh_latency(1, release=release, flood=flood, owner_drain_first_turn_seconds=first_turn)


def _run_arm(release: str, first_turn: int, baseline):
    return run_backlog_flood(_config(release, first_turn), baseline_summary=baseline)


@pytest.fixture(scope='module')
def runs():
    arms = [(release, first_turn) for release in ('held', 'unmetered') for first_turn in (0, 15)]
    baseline = fresh_baseline(BacklogFloodSimulation(_config('held', 15, flood=False)).run())
    # Linux defaults to fork, which can inherit the simulator's patched asyncio/env state and
    # libraries with background threads. Spawn matches the tested macOS path on every platform.
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=len(arms), mp_context=context) as pool:
        samples = list(pool.map(_run_arm, *zip(*arms), repeat(baseline)))
    return {f'{release}_{first_turn}': sample for (release, first_turn), sample in zip(arms, samples)}


def _flood(sample):
    return sample['sim']['backlog_flood']


def test_flood_shape_exercises_steady_fresh_load_and_both_stored_routes(runs):
    flood = _flood(runs['held_15'])
    assert runs['held_15']['sim']['path'] == 'batch'
    assert flood['fresh_owners'] >= 60
    assert flood['fresh_flooded_owners'] * 3 == flood['flooded_owners']
    assert flood['flooded_owners'] >= 30
    assert flood['flooded_to_steady_hourly_ratio'] >= 20
    assert flood['backlog_routes'] == {'parakeet': 396, 'provider': 7524}
    assert runs['held_15']['sim']['paid_fallback_calls'] == 360


@pytest.mark.parametrize('first_turn', [0, 15])
def test_held_fresh_latency_is_baseline_plus_noise_and_depth_is_bounded(runs, first_turn):
    sample = runs[f'held_{first_turn}']
    flood = _flood(sample)
    assert sample['verdict_code'] == 0
    assert flood['fresh_pending'] == 0
    assert flood['fresh_p50_ratio'] <= 1.1
    assert flood['fresh_p90_ratio'] <= 1.1
    assert flood['max_own_backlog_rows_ahead_of_fresh'] <= 16
    assert flood['held_result_ready'] == flood['backlog_routes']['provider']
    assert flood['owner_chain_valid'] is True


@pytest.mark.parametrize('first_turn', [0, 15])
def test_unmetered_drains_every_backlog_row(runs, first_turn):
    sample = runs[f'unmetered_{first_turn}']
    flood = _flood(sample)
    assert sample['verdict_code'] == 1
    if first_turn == 0:
        assert 'fresh_latency' in sample['verdict']
    assert flood['fresh_pending'] == 0
    assert flood['backlog_pending'] == 0
    assert flood['held_result_ready'] == 0
    assert flood['owner_chain_valid'] is True


def test_unmetered_fifo_counterfactual_reproduces_the_incident_by_a_wide_margin(runs):
    incident = _flood(runs['unmetered_0'])
    fixed_queue = _flood(runs['unmetered_15'])
    assert incident['fresh_p90_ratio'] > 2
    assert incident['fresh_unprojected_10_to_20_minutes_share'] > 0
    # This pins PR #25213's change rather than pretending both scheduler shapes are the incident.
    assert fixed_queue['fresh_p90_ratio'] < incident['fresh_p90_ratio']


def test_seed_one_metrics_match_the_deterministic_golden(runs):
    golden_path = Path(__file__).parent / 'fixtures' / 'pipeline_sim_goldens' / 'backlog_flood' / 'fresh_latency.json'
    observed = {name: _flood(sample) for name, sample in runs.items()}
    if os.getenv('PIPELINE_GOLDEN_UPDATE') == '1':
        golden_path.write_text(json.dumps(observed, indent=2, sort_keys=True) + '\n')
    golden = json.loads(golden_path.read_text())
    assert observed == golden


def test_gated_is_the_explicit_step_four_seam_without_faking_a_meter():
    with pytest.raises(ValueError, match='reserved for the step-4 commit gate'):
        run_backlog_flood(_config('gated', 15))
