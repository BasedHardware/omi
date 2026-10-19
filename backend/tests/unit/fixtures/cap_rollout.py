"""Explicit prior all-owner/all-lane policy for pre-cohort regression tests."""

import pytest


@pytest.fixture(autouse=True)
def full_cap_dispatch_rollout(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.delenv('STT_CAP_DISPATCH_LANES', raising=False)
