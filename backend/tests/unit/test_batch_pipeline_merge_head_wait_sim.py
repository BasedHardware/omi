"""Reverse catch-up replay of the run 14 shape: strict order against W=60, with and without leaked leases.

Simulations run once in the module fixture; the replay itself asserts the owner
log-chain, watermark and late-marking invariants and the single paid call.
"""

import pytest

from testing.merge_head_wait_scenario import replay


@pytest.fixture(scope='module')
def runs():
    return {
        (head_wait, leak): replay('run14', head_wait=head_wait, leak_percent=leak)
        for head_wait in ('off', '60')
        for leak in (10.0, 0.0)
    }


def test_every_row_commits_and_projects(runs):
    for sample in runs.values():
        assert sample['committed'] > 0 and sample['unprojected'] == 0


def test_head_wait_bounds_the_catch_up_merge_wait(runs):
    for leak in (10.0, 0.0):
        strict, bounded = runs['off', leak], runs['60', leak]
        assert strict['catch_up_merge_wait_p95_seconds'] > 200
        # W plus at most one maintenance or serving tick.
        assert bounded['catch_up_merge_wait_p95_seconds'] <= 60 + 20
        assert (
            bounded['catch_up_accept_to_projection_p95_seconds']
            < 0.6 * strict['catch_up_accept_to_projection_p95_seconds']
        )
        assert bounded['catch_up_head_wait_bypass'] > 0 and strict['catch_up_head_wait_bypass'] == 0


def test_bypass_reaches_normal_owners_only_through_leaked_leases(runs):
    assert runs['60', 0.0]['normal_head_wait_bypass'] == 0
    assert runs['60', 0.0]['normal_merge_wait_p95_seconds'] == runs['off', 0.0]['normal_merge_wait_p95_seconds']
    assert runs['60', 10.0]['normal_merge_wait_p95_seconds'] <= 60 + 20
