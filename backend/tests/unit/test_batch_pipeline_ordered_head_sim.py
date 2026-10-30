"""Optional stacked qualification; automatically runs once PR #22201 lands."""

import pytest


@pytest.fixture(scope='module')
def reverse_upload():
    pytest.importorskip('testing.pipeline_sim.sim', reason='virtual-clock harness is in PR #22201')
    scenario = pytest.importorskip('testing.ordered_head_scenario')
    return scenario.qualify()


def test_reverse_upload_160_selects_capture_head_without_waiting_for_fifo(reverse_upload):
    assert reverse_upload['jobs'] == reverse_upload['committed'] == 160
    assert reverse_upload['first_lease_capture_rank'] == 0
    assert reverse_upload['predecessor_wait_p95_seconds'] < 30
    assert reverse_upload['peak_result_ready'] <= 32
