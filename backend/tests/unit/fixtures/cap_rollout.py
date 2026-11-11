"""Explicit future-ready all-owner/all-lane policy for enforcement regression tests."""

import pytest

from config import stt_cap_dispatch as policy
from utils import funded_processing


@pytest.fixture(autouse=True)
def full_cap_dispatch_rollout(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync,batch')
    # Exercise existing enforcement paths; production readiness is tested without
    # this fixture in test_stt_cap_cohort_lanes.py.
    monkeypatch.setattr(policy, '_BATCH_LANE_READY', True)
    # Recovery spends only for paid owners; these regression owners are paid.
    # The Free gate itself is tested by overriding this in test_held_recovery_paid_only.py.
    monkeypatch.setattr(funded_processing, 'paid_owner', lambda _uid: True)
