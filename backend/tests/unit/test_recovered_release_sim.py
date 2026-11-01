"""5% run 18 replay: the recovery wake's release removes the recovered unit's merge wait.

The replay asserts the owner log-chain, watermark and late-marking invariants
and the single paid call itself. Simulations run once in the module fixture.
"""

import pytest

from testing.recovered_release_scenario import replay


@pytest.fixture(scope='module')
def runs():
    return {release: replay(release=release, gpu_ready_at=False, leak_percent=10.0) for release in (False, True)}


def test_every_unit_commits_and_projects(runs):
    for sample in runs.values():
        assert sample['recovered_units'] > 0 and sample['unprojected'] == 0


def test_release_removes_the_recovered_units_head_wait(runs):
    before, after = runs[False], runs[True]
    # Run 18 measured 65-86 s settled -> commit for held recovered units.
    assert before['recovered_settle_to_commit_p95_seconds'] >= 60
    assert after['recovered_settle_to_commit_p95_seconds'] <= 5
    assert after['recovered_release_commits'] > 0 and before['recovered_release_commits'] == 0


def test_release_never_lengthens_the_gate_metric(runs):
    assert runs[True]['quarantine_projection_p95_seconds'] <= runs[False]['quarantine_projection_p95_seconds']
