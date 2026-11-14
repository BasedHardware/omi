"""Keep historical retune witnesses separate from the approved live 4/8 bounds."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'batch_pipeline_hpa_frontier.py'
SPEC = importlib.util.spec_from_file_location('hpa_frontier', SCRIPT)
FRONTIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FRONTIER)
HISTORICAL_CFG = dict(FRONTIER.cfg, min_replicas=4, max_replicas=16)


def test_historical_volume_capacity_retains_the_retune_witness():
    result = FRONTIER.stats(FRONTIER.series, HISTORICAL_CFG)
    assert result['mean'] == pytest.approx(4.34, abs=0.01)
    assert result['max'] == 5
    assert result['hot'] == 0
    assert result['floor']


def test_current_volume_capacity_stays_cool_and_at_the_audited_floor():
    result = FRONTIER.stats(FRONTIER.series, FRONTIER.cfg)
    assert FRONTIER.cfg['min_replicas'] == 4
    assert FRONTIER.cfg['max_replicas'] == 8
    assert result['mean'] == pytest.approx(4.34, abs=0.01)
    assert result['max'] == 5
    assert result['hot'] == 0
    assert result['floor']


def test_historical_full_volume_sensitivity_retains_the_leads_hot_minute_budget():
    # A synthetic 3.7x fleet-total model, not full-volume qualification. At cap16
    # even the prior 32/0.5 shape has hot minutes; never call this zero-hot safe.
    # This remains the 4/16 retune witness, not qualification of today's 4/8
    # bounds at full volume. Live bounds need a separate capacity assessment.
    result = FRONTIER.stats(FRONTIER.full, HISTORICAL_CFG)
    assert result['mean'] == pytest.approx(11.46, abs=0.01)
    assert result['max'] == 16
    assert result['hot'] <= 7
    assert result['floor']


def test_historical_full_volume_step_has_bounded_wait_and_catch_up():
    worst, caught = FRONTIER.r._step_load(HISTORICAL_CFG['ready_target'], 10, HISTORICAL_CFG, base=4.05, high=12)
    assert worst <= 10
    assert caught is not None and caught <= 25
