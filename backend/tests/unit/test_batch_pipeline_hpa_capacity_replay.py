"""Lock the replacement retune's current/full sensitivity, without editing prior replays."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'batch_pipeline_hpa_frontier.py'
SPEC = importlib.util.spec_from_file_location('hpa_frontier', SCRIPT)
FRONTIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FRONTIER)


def test_current_volume_capacity_stays_cool_and_at_the_floor():
    result = FRONTIER.stats(FRONTIER.series, FRONTIER.cfg)
    assert result['mean'] == pytest.approx(4.34, abs=0.01)
    assert result['max'] == 5
    assert result['hot'] == 0
    assert result['floor']


def test_full_volume_sensitivity_retains_the_leads_hot_minute_budget():
    # A synthetic 3.7x fleet-total model, not full-volume qualification. At cap16
    # even the prior 32/0.5 shape has hot minutes; never call this zero-hot safe.
    result = FRONTIER.stats(FRONTIER.full, FRONTIER.cfg)
    assert result['mean'] == pytest.approx(11.46, abs=0.01)
    assert result['max'] == 16
    assert result['hot'] <= 7
    assert result['floor']


def test_full_volume_step_has_bounded_wait_and_catch_up():
    worst, caught = FRONTIER.r._step_load(FRONTIER.cfg['ready_target'], 10, FRONTIER.cfg, base=4.05, high=12)
    assert worst <= 10
    assert caught is not None and caught <= 25
