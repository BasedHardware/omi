"""Fresh uploads reach a conversation within 2 min p95, even beside the owner's 300-row catch-up.

Simulations run once in the module fixture; each replay asserts the owner log
chain, watermark and late-marking invariants and the single paid call.
"""

import pytest

from testing.fresh_latency_scenario import FRESH_TARGET_SECONDS, LEVERS, replay


@pytest.fixture(scope='module')
def runs():
    return {
        'today': replay(catch_up=True, levers=()),
        'shipped': replay(catch_up=True),
        'shipped_no_catch_up': replay(catch_up=False),
        'no_fresh_first': replay(catch_up=True, levers=tuple(k for k in LEVERS if k != 'fresh_first')),
    }


def test_every_row_projects(runs):
    for sample in runs.values():
        assert sample['unprojected'] == 0


def test_shipped_levers_meet_the_fresh_bar_with_and_without_a_catch_up_owner(runs):
    for name in ('shipped', 'shipped_no_catch_up'):
        assert runs[name]['fresh_all']['p95'] <= FRESH_TARGET_SECONDS
    shipped = runs['shipped']
    assert shipped['fresh_catch_up_owner']['n'] >= 40
    assert shipped['fresh_catch_up_owner']['p95'] <= FRESH_TARGET_SECONDS
    assert shipped['fresh_quarantined']['p95'] <= FRESH_TARGET_SECONDS


def test_today_the_catch_up_owner_blocks_its_own_fresh_uploads(runs):
    assert runs['today']['fresh_catch_up_owner']['p95'] > 5 * FRESH_TARGET_SECONDS
    # Without fresh-first, the owner's projection chain still holds them behind its backlog.
    assert runs['no_fresh_first']['fresh_catch_up_owner']['p95'] > FRESH_TARGET_SECONDS


def test_fresh_first_leaves_other_owners_and_the_backlog_draining(runs):
    shipped, today = runs['shipped'], runs['today']
    assert shipped['fresh_other_owners']['p95'] <= today['fresh_other_owners']['p95']
    assert shipped['catch_up_rows']['n'] == today['catch_up_rows']['n']
    assert shipped['catch_up_rows']['p95'] < today['catch_up_rows']['p95']
