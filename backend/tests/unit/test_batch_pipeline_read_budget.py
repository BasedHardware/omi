"""Read-budget contracts for the projection discovery hot path.

The 2026-11-05 batch review measured keyset discovery as the largest Firestore read
amplifier: every serving instance re-read the same oldest-first page each tick. These
tests pin the per-tick query count, forbid per-row document reads, and require that
striped instances start on different pages. A regression fails CI here instead of
showing up on the billing dashboard.
"""

from unittest.mock import Mock

import pytest

from utils.batch_pipeline import projection_discovery
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery

PAGE_LIMIT = 100


def _page_store(oldest: float = 1000.0):
    store = Mock(name='store')
    store.projection_page.side_effect = lambda *, limit, after, **kw: (
        ['row'] * limit,
        (oldest, 'row'),
    )
    return store


@pytest.mark.parametrize('ticks', [1, 5])
def test_tick_costs_one_bounded_page_query_plus_one_startup_head_read(monkeypatch, ticks):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', raising=False)
    store = _page_store()
    scan = ProjectionDiscovery(store, states=('pending',))

    for _ in range(ticks):
        assert len(scan.next(limit=PAGE_LIMIT)) == PAGE_LIMIT

    calls = store.projection_page.call_args_list
    # One seed head read on the first tick, then exactly one page query per tick.
    assert len(calls) == ticks + 1
    assert all(call.kwargs['limit'] <= PAGE_LIMIT for call in calls)
    # Discovery carries ids only. Any per-row job or result read is a regression.
    store.ref.assert_not_called()
    store.projection_pending.assert_not_called()


def test_pagination_kill_switch_is_one_legacy_query_per_tick(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'false')
    store = Mock(name='store')
    store.projection_pending.return_value = ['legacy']
    scan = ProjectionDiscovery(store)

    assert scan.next(limit=PAGE_LIMIT) == ['legacy']
    store.projection_pending.assert_called_once_with(limit=PAGE_LIMIT)
    store.projection_page.assert_not_called()
    store.ref.assert_not_called()


def test_striped_instances_start_on_distinct_pages(monkeypatch):
    # Without striping, N instances request the same first page and race for the same
    # owner claims (claim_busy). Forty instances with evenly spaced phases must not collide.
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', raising=False)
    monkeypatch.setattr(projection_discovery.time, 'time', lambda: 1256.0)
    stripes = [i * projection_discovery.PROJECTION_DISCOVERY_STRIPES // 40 for i in range(40)]

    starts = []
    for stripe in stripes:
        monkeypatch.setattr(projection_discovery, 'projection_discovery_stripe', lambda stripe=stripe: stripe)
        store = _page_store()
        ProjectionDiscovery(store, states=('pending',)).next(limit=PAGE_LIMIT)
        # Call 0 is the startup head read; call 1 is the first striped page.
        starts.append(store.projection_page.call_args_list[1].kwargs['after'])

    assert len(set(starts)) == len(stripes) == 40
