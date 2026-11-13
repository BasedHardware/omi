"""Discovery hints advance independently; they never authorize projection."""

from unittest.mock import Mock

import pytest

from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from config import batch_pipeline
from config.policy import kill_switch
from database.batch_pipeline_store import projection_page
from tests.unit.test_batch_pipeline_followup_desync import ResultQuery
from utils.batch_pipeline import projection_discovery


def test_default_on_independent_scans_wrap_and_kill_switch_restores_first_page(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    store = Mock()
    store.projection_page.side_effect = lambda *, limit, after: (
        (['ready'] * 100, (2.0, 'ready-100')) if after is None else (['sibling', 'other-owner'], None)
    )
    assignment, followup = ProjectionDiscovery(store), ProjectionDiscovery(store)
    assert len(assignment.next()) == 100
    assert assignment.next() == ['sibling', 'other-owner']
    assert len(followup.next()) == 100
    assert followup.next() == ['sibling', 'other-owner']
    assert len(assignment.next()) == 100
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'false')
    store.projection_pending.return_value = ['legacy-page']
    assert assignment.next() == followup.next() == ['legacy-page']
    assert assignment.after is followup.after is None


def test_failed_query_retries_cursor_without_losing_page(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    store = Mock()
    store.projection_page.side_effect = [(['head'], (2.0, 'head')), RuntimeError('query unavailable'), (['tail'], None)]
    scan = ProjectionDiscovery(store)
    assert scan.next(1) == ['head']
    try:
        scan.next(1)
    except RuntimeError:
        pass
    else:
        raise AssertionError('query failure must propagate')
    assert scan.next(1) == ['tail']
    assert [call.kwargs['after'] for call in store.projection_page.call_args_list] == [
        None,
        (2.0, 'head'),
        (2.0, 'head'),
    ]


def scanner(monkeypatch, rows, stripe):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.setattr(projection_discovery, 'projection_discovery_stripe', lambda: stripe)
    monkeypatch.setattr(projection_discovery.time, 'time', lambda: 1256.0)
    query = ResultQuery(rows)
    store = Mock()
    store.projection_page.side_effect = lambda **kw: projection_page(query, 'synthetic', **kw)
    return ProjectionDiscovery(store, states=('pending',)), query


@pytest.mark.parametrize('stripe', [0, 1, 1024, 2048, 4095])
@pytest.mark.parametrize('limit', [1, 17, 100])
def test_striped_cycle_visits_every_row_exactly_once_including_timestamp_ties(monkeypatch, stripe, limit):
    rows = {f'r{i:03d}': {'committed_at': 1000.0 + i // 2, 'projection_state': 'pending'} for i in range(512)}
    scan, query = scanner(monkeypatch, rows, stripe)
    seen = []
    while len(seen) < 2 * len(rows):
        seen.extend(scan.next(limit))
    ordered = sorted(rows)
    first = 2 * ((stripe + 15) // 16)
    rotated = ordered[first:] + ordered[:first]
    assert seen[: len(rows)] == seen[len(rows) : 2 * len(rows)] == rotated
    assert query.calls[0] == (None, 1)  # one scoped startup head read
    assert query.calls[1] == ((1000.0 + stripe / 16,), limit)


def test_process_entropy_is_sampled_and_logged_once_per_process(monkeypatch, caplog):
    monkeypatch.setenv('K_REVISION', 'same-revision-across-replicas')
    entropy = Mock(side_effect=[11, 22])
    monkeypatch.setattr(batch_pipeline.secrets, 'randbits', entropy)
    monkeypatch.setattr(batch_pipeline, '_projection_discovery_stripe_value', None)
    try:
        with caplog.at_level('INFO', logger=batch_pipeline.__name__):
            first = ProjectionDiscovery(Mock()).stripe
            assert ProjectionDiscovery(Mock()).stripe == first
            assert entropy.call_count == 1
            # Simulate another process with identical revision/hostname/PID,
            # injecting a fresh seed rather than relying on probabilistic tests.
            monkeypatch.setattr(batch_pipeline, '_projection_discovery_stripe_value', None)
            second = ProjectionDiscovery(Mock()).stripe
            assert ProjectionDiscovery(Mock()).stripe == second
        assert first != second
        assert 0 <= first < 4096 and 0 <= second < 4096
        assert entropy.call_count == 2
        assert caplog.text.count('event=batch_projection_discovery action=start') == 2
        assert caplog.text.count('stripes=4096') == 2
    finally:
        monkeypatch.setattr(batch_pipeline, '_projection_discovery_stripe_value', None)


@pytest.mark.parametrize('raw', ['', 'on', 'false', 'garbage', 'off', ' OFF '])
@pytest.mark.parametrize('mode', ['off', 'serve'])
def test_only_off_disables_striping(monkeypatch, raw, mode):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', raw)
    assert batch_pipeline.projection_striping_enabled() == (raw.strip().lower() != 'off')
    assert kill_switch('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', flags={})


@pytest.mark.parametrize('count', [0, 1, 3])
def test_empty_short_or_stale_collection_returns_head_without_tick_delay(monkeypatch, count):
    rows = {f'r{i}': {'committed_at': 1000.0, 'projection_state': 'pending'} for i in range(count)}
    scan, _ = scanner(monkeypatch, rows, 4095)
    assert scan.next() == sorted(rows)
    assert scan.next() == sorted(rows)


def test_stripe_seed_query_failure_retries_without_advancing(monkeypatch):
    rows = {'r0': {'committed_at': 1000.0, 'projection_state': 'pending'}}
    scan, _ = scanner(monkeypatch, rows, 128)
    page = scan.store.projection_page.side_effect
    scan.store.projection_page.side_effect = RuntimeError('unavailable')
    with pytest.raises(RuntimeError):
        scan.next()
    assert scan.after is None and not scan.seeded
    scan.store.projection_page.side_effect = page
    assert scan.next() == ['r0']


def test_pagination_off_bypasses_startup_seed(monkeypatch):
    scan, query = scanner(monkeypatch, {}, 128)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'false')
    assert scan.next() == []
    assert query.calls == [(None, 100)]


def test_existing_followup_seed_is_preserved(monkeypatch):
    scan, query = scanner(monkeypatch, {}, 128)
    scan.after = (1200.0, '')
    assert scan.next() == []
    assert query.calls == [((1200.0,), 100)]


def test_due_before_mode_resets_the_cursor_and_seeds_on_the_clock(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.setattr(projection_discovery, 'projection_discovery_stripe', lambda: 2048)
    monkeypatch.setattr(projection_discovery.time, 'time', lambda: 1256.0)
    store = Mock()
    store.projection_page.side_effect = [
        (['head'], (1000.0, 'head')),
        (['a', 'b'], (1060.0, 5.0, 'b')),
        (['head'], (1000.0, 'head')),
        (['legacy'], None),
    ]
    scan = ProjectionDiscovery(store, states=('persisted', 'ready'))
    assert scan.next(limit=2, due_before=1060.0) == ['a', 'b']
    assert scan.due_mode is True
    assert scan.after == (1060.0, 5.0, 'b')
    # The due ordering seeds at the stripe offset on the clock, not on wall time.
    assert store.projection_page.call_args_list[0].kwargs == {
        'limit': 1,
        'after': None,
        'states': ('persisted', 'ready'),
        'due_before': 1060.0,
    }
    assert store.projection_page.call_args_list[1].kwargs['after'] == (1030.0,)
    # A cursor from the due ordering is not reused in the legacy ordering.
    assert scan.next(limit=2) == ['legacy']
    assert scan.due_mode is False and scan.after is None


# --- the newest-commits half page (2026-11-13) --------------------------------------------------


def recent_scanner(monkeypatch, rows, *, stripe=0, now=10_000.0, window='900'):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', window)
    monkeypatch.setattr(projection_discovery, 'projection_discovery_stripe', lambda: stripe)
    clock = {'now': now}
    monkeypatch.setattr(projection_discovery.time, 'time', lambda: clock['now'])
    query = ResultQuery(rows)
    store = Mock()
    store.projection_page.side_effect = lambda **kw: projection_page(query, 'synthetic', **kw)
    return ProjectionDiscovery(store, states=('pending',), recent=True), clock


def backlog_and_new(old=400, new=6, now=10_000.0):
    rows = {f'old{i:03d}': {'committed_at': 100.0 + i, 'projection_state': 'pending'} for i in range(old)}
    rows.update({f'new{i}': {'committed_at': now - 60.0 + i, 'projection_state': 'pending'} for i in range(new)})
    return rows


def test_a_new_commit_is_discovered_on_the_first_page_behind_a_long_backlog(monkeypatch):
    """2026-11-13: with 154,000 pending rows a new commit waited about 15 minutes to be paged."""
    scan, _ = recent_scanner(monkeypatch, backlog_and_new())
    page = scan.next(100)
    assert page[:6] == [f'new{i}' for i in range(6)]
    # The page is no larger, and the main cursor still walks the backlog from its head.
    assert len(page) == 100 and page[6] == 'old000'


def test_the_main_cursor_still_visits_every_backlog_row(monkeypatch):
    rows = backlog_and_new()
    scan, _ = recent_scanner(monkeypatch, rows)
    seen = set()
    for _ in range(12):
        seen.update(scan.next(100))
    assert seen == set(rows)


def test_recent_half_is_bounded_and_resumes_where_it_stopped(monkeypatch):
    rows = backlog_and_new(old=10, new=120)
    scan, _ = recent_scanner(monkeypatch, rows)
    first = scan.next(100)
    assert (
        first[:50]
        == [f'new{i}' for i in sorted(range(120), key=lambda i: (rows[f'new{i}']['committed_at'], f'new{i}'))][:50]
    )
    second = scan.next(100)
    assert not set(second[:50]) & set(first[:50]) and all(name.startswith('new') for name in second[:50])


def test_recent_cursor_restarts_at_the_window_floor_once_it_falls_behind(monkeypatch):
    rows = backlog_and_new(old=10, new=120)
    scan, clock = recent_scanner(monkeypatch, rows)
    scan.next(100)
    assert scan.recent_after is not None
    clock['now'] += 5_000.0  # Every row is now older than the window.
    page = scan.next(100)
    assert scan.recent_after is None and not any(page.count(name) > 1 for name in page)


def test_first_recent_pass_starts_at_the_process_stripe(monkeypatch):
    rows = {f'r{i:03d}': {'committed_at': 9_100.0 + i, 'projection_state': 'pending'} for i in range(900)}
    scan, _ = recent_scanner(monkeypatch, rows, stripe=2048)
    page = scan.next(20)
    assert page[0] == 'r450'  # Half way into the 900 s window.
    scan.recent_after = None
    assert scan.next(20)[0] == 'r000'  # Later passes start at the floor.


def test_recent_off_and_default_construction_keep_the_single_cursor(monkeypatch):
    scan, _ = recent_scanner(monkeypatch, backlog_and_new(), window='0')
    assert scan.next(100)[0] == 'old000'
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', '900')
    plain = ProjectionDiscovery(scan.store, states=('pending',))
    assert plain.next(100)[0] == 'old000'


def test_a_failed_recent_query_costs_only_that_half_page(monkeypatch):
    scan, _ = recent_scanner(monkeypatch, backlog_and_new())
    real = scan.store.projection_page.side_effect
    calls = []

    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise RuntimeError('query unavailable')
        return real(**kw)

    scan.store.projection_page.side_effect = flaky
    page = scan.next(100)
    assert page[0] == 'old000' and len(page) == 100


def test_a_failed_main_query_does_not_move_the_recent_cursor(monkeypatch):
    """The newest rows read before a failed main query are offered again on the next tick."""
    scan, _ = recent_scanner(monkeypatch, backlog_and_new(old=400, new=120))
    real = scan.store.projection_page.side_effect
    calls = []

    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 2:
            raise RuntimeError('query unavailable')
        return real(**kw)

    scan.store.projection_page.side_effect = flaky
    with pytest.raises(RuntimeError):
        scan.next(100)
    assert scan.recent_after is None and scan.recent_started is False and scan.after is None
    lost = real(limit=50, after=calls[0]['after'], states=('pending',))[0]
    assert len(lost) == 50 and scan.next(100)[:50] == lost


def test_recent_discovery_setting_bounds(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', raising=False)
    assert batch_pipeline.projection_recent_discovery_seconds() == 900
    for raw, want in (('0', 0), ('120', 120), ('99999', 3600), ('-1', 0), ('junk', 900)):
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', raw)
        assert batch_pipeline.projection_recent_discovery_seconds() == want
