"""Owner-chain projection throughput (``testing.pipeline_sim.projection_drain``).

Virtual time with modelled run-14 latencies; the walk, sweep and drain are real.
Rates are model outputs to compare between modes, not production numbers. The
1.2k-row and many-owner runs are ``slow``; run them with
``BACKEND_PYTEST_MARK_EXPR= BACKEND_UNIT_TEST_FILE_LIST=<this file> bash test.sh``.
"""

import pytest

from testing.pipeline_sim import projection_drain as sim


def report(result):
    print(
        f"{result['mode']}: owners={result['owners']} rows/owner={result['rows_per_owner']} "
        f"rows/min min={result['rows_per_min_min']} max={result['rows_per_min_max']} "
        f"check_transactions={result['check_transactions']} result_loads={result['result_loads']}"
    )


def per_owner(assignments):
    """Owners are independent; only each owner's own order is a contract."""
    owners: dict[str, list] = {}
    for call in assignments:
        owners.setdefault(call[0].rsplit('-s', 1)[0], []).append(call)
    return owners


def assert_same_projection(baseline, result):
    assert result['all_persisted'] and result['chain_order']
    assert per_owner(result['assignments']) == per_owner(baseline['assignments'])
    assert result['index'] == baseline['index']


def test_drain_beats_the_sweep_walk_on_a_short_backlog():
    today = sim.run('sweep_walk', rows=100)
    phase1 = sim.run('drain', rows=100)
    assert today['all_persisted'] and today['chain_order']
    assert_same_projection(today, phase1)
    assert phase1['rows_per_min_min'] > today['rows_per_min_min']
    assert phase1['check_transactions'] < today['check_transactions'] / 10


@pytest.mark.slow
def test_a_1200_row_owner_drains_in_about_ten_minutes(capsys):
    results = {mode: sim.run(mode, rows=1200) for mode in sim.MODES}
    for result in results.values():
        report(result)
        assert_same_projection(results['sweep_walk'], result)
    # Today: ~35 rows/min (run 14/16 measured 1.7-1.8 s/row), ~35 min for 1.2k.
    assert 30 <= results['sweep_walk']['rows_per_min_min'] <= 45
    # Phase 1 (no Firestore hot-document contention modelled): about 10 min.
    assert results['drain']['rows_per_min_min'] >= 100
    # Read-ahead survives step boundaries: at most one wasted load per turn.
    assert results['drain']['result_loads'] <= 1200 + 1200 // 60


@pytest.mark.slow
def test_heavy_owners_keep_their_rate_under_the_drain(capsys):
    today = sim.run('sweep_walk', rows=300, owners=12)
    phase1 = sim.run('drain', rows=300, owners=12)
    report(today)
    report(phase1)
    assert_same_projection(today, phase1)
    # The sweep-shared 30 s budget collapses each owner's duty cycle (I4).
    assert today['rows_per_min_max'] < 10
    assert phase1['rows_per_min_min'] >= 50
