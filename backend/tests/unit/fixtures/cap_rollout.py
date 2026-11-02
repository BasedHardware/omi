"""Explicit future-ready all-owner/all-lane policy for enforcement regression tests."""

import pytest

from config import stt_cap_dispatch as policy


@pytest.fixture(autouse=True)
def full_cap_dispatch_rollout(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync,batch')
    # Exercise existing enforcement paths; production readiness is tested without
    # this fixture in test_stt_cap_cohort_lanes.py.
    monkeypatch.setattr(policy, '_BATCH_LANE_READY', True)
