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


def recent_scanner(monkeypatch, rows, *, now=10_000.0, window='900', point=0.0, striping='off', stripe=0):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', striping)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', window)
    monkeypatch.setattr(projection_discovery, 'projection_discovery_stripe', lambda: stripe)
    clock = {'now': now, 'point': point}
    monkeypatch.setattr(projection_discovery.time, 'time', lambda: clock['now'])
    query = ResultQuery(rows)
    store = Mock()
    store.projection_page.side_effect = lambda **kw: projection_page(query, 'synthetic', **kw)
    scan = ProjectionDiscovery(store, states=('pending',), recent=True)
    scan.random = lambda: clock['point']
    return scan, clock


def backlog_and_new(old=400, new=6, now=10_000.0):
    rows = {f'old{i:03d}': {'committed_at': 100.0 + i, 'projection_state': 'pending'} for i in range(old)}
    rows.update(
        {f'new{i:03d}': {'committed_at': now - 60.0 + i / 4, 'projection_state': 'pending'} for i in range(new)}
    )
    return rows


def news(page):
    return [name for name in page if name.startswith('new')]


def test_a_new_commit_is_discovered_on_the_first_page_behind_a_long_backlog(monkeypatch):
    """2026-11-13: with 154,000 pending rows a new commit waited about 15 minutes to be paged."""
    scan, _ = recent_scanner(monkeypatch, backlog_and_new())
    page = scan.next(100)
    assert page[:6] == [f'new{i:03d}' for i in range(6)]
    # The page is no larger, and the main cursor still walks the backlog from its head.
    assert len(page) == 100 and page[6] == 'old000'


def test_the_main_cursor_still_visits_every_backlog_row_while_new_commits_fill_their_half(monkeypatch):
    rows = backlog_and_new(old=400, new=120)
    scan, clock = recent_scanner(monkeypatch, rows)
    seen, sizes = set(), []
    for tick in range(9):
        # A full half page of new commits on every tick, as when commits never stop.
        rows.update(
            {
                f'new{tick}x{i:02d}': {'committed_at': clock['now'] - 1.0 + i / 100, 'projection_state': 'pending'}
                for i in range(50)
            }
        )
        clock['point'] = 1.0 - 2.0 / 900
        page = scan.next(100)
        sizes.append(len(page))
        seen.update(page)
        clock['now'] += 20.0
    assert {name for name in rows if name.startswith('old')} <= seen
    assert max(sizes) <= 100


def test_a_row_is_offered_by_the_recent_read_once_per_process_and_a_restart_adds_one(monkeypatch):
    """Review round 2: a still-pending recent row was re-offered on every tick of the window."""
    # Enough backlog that the main cursor does not reach the new rows inside the test.
    rows = backlog_and_new(old=8000, new=6)
    scan, clock = recent_scanner(monkeypatch, rows)
    offers = 0
    for _ in range(60):  # 20 minutes of ticks; the rows stay pending throughout.
        offers += scan.next(100).count('new000')
        clock['now'] += 20.0
    assert offers == 1
    # A restarted process has an empty memory: one more offer, then none.
    again = ProjectionDiscovery(scan.store, states=('pending',), recent=True)
    again.random = lambda: 0.0
    clock['now'] = 10_000.0
    assert [again.next(100).count('new000') for _ in range(3)] == [1, 0, 0]


def test_rows_already_offered_still_count_against_the_page(monkeypatch):
    scan, _ = recent_scanner(monkeypatch, backlog_and_new(old=4000, new=120))
    first = scan.next(100)
    assert news(first) == first[:50] == [f'new{i:03d}' for i in range(50)]
    second = scan.next(100)
    # The same 50 rows were read again and not offered again; the page read no more rows.
    assert news(second) == [] and len(second) == 50
    assert [call.kwargs['limit'] for call in scan.store.projection_page.call_args_list] == [50, 50, 50, 50]


def test_each_tick_reads_from_a_different_point_of_the_window(monkeypatch):
    scan, clock = recent_scanner(monkeypatch, backlog_and_new(old=4000, new=200))
    first = news(scan.next(100))
    clock['point'] = (900 - 60 + 25) / 900  # 25 s into the minute the new rows span.
    second = news(scan.next(100))
    assert first[0] == 'new000' and second[0] == 'new100' and not set(first) & set(second)


def test_recent_off_and_default_construction_keep_the_single_cursor(monkeypatch):
    scan, clock = recent_scanner(monkeypatch, backlog_and_new(), window='0', striping='on')
    assert scan.next(100)[0] == 'old000'
    clock['now'] += 10_000.0
    scan.next(100)
    assert scan.stripe == 0 and scan.store.projection_page.call_count == 3  # One seed read, no restart.
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', '900')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
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
    fallbacks = []
    monkeypatch.setattr(projection_discovery, 'record_fallback', lambda **labels: fallbacks.append(labels))
    page = scan.next(100)
    assert page[0] == 'old000' and len(page) == 100 and scan.offered == {}
    # The lost half page is recorded, not silent.
    assert [(f['component'], f['from_mode'], f['to_mode'], f['reason']) for f in fallbacks] == [
        ('firestore_read', 'recent_discovery', 'main_cursor', 'unavailable')
    ]


@pytest.mark.parametrize('striping', ['off', 'on'])
def test_rows_read_before_a_failed_main_query_are_offered_on_the_next_tick(monkeypatch, striping):
    scan, _ = recent_scanner(monkeypatch, backlog_and_new(old=400, new=120), striping=striping)
    real = scan.store.projection_page.side_effect
    calls = []

    def flaky(**kw):
        calls.append(kw)
        # The main query is the last one of the first tick (after the seed read when striped).
        if len(calls) == (3 if striping == 'on' else 2):
            raise RuntimeError('query unavailable')
        return real(**kw)

    scan.store.projection_page.side_effect = flaky
    with pytest.raises(RuntimeError):
        scan.next(100)
    assert scan.offered == {} and scan.after is None and scan.seeded is False
    assert news(scan.next(100))[:50] == [f'new{i:03d}' for i in range(50)]


def test_a_main_cursor_that_never_wraps_restarts_at_a_new_random_point(monkeypatch):
    """Review round 2: rows before every process's start point waited for a wrap that never came."""
    rows = {f'old{i:03d}': {'committed_at': 1_000.0 + 10 * i, 'projection_state': 'pending'} for i in range(900)}
    scan, clock = recent_scanner(monkeypatch, rows, striping='on', stripe=2048, window='1')
    assert scan.next(20)[0] == 'old450'  # Seeded half way between the oldest row and now.
    clock['now'] += projection_discovery.MAIN_PASS_SECONDS - 1
    assert scan.next(20)[0] == 'old470'
    clock['now'] += 2  # A whole pass period without reaching the newest row.
    clock['point'] = 0.75
    first = scan.next(20)[0]
    assert scan.stripe == 0.75 * 4096 and first not in ('old000', 'old490')
    # The clock restarts with the pass: no second restart on the next tick.
    assert scan.next(20)[0] != first and scan.stripe == 0.75 * 4096


def test_one_restart_in_eight_begins_at_the_oldest_row(monkeypatch):
    """Review round 3: a random point almost never lands on the head of the log."""
    rows = {f'old{i:03d}': {'committed_at': 1_000.0 + 10 * i, 'projection_state': 'pending'} for i in range(900)}
    scan, clock = recent_scanner(monkeypatch, rows, striping='on', stripe=2048, window='1')
    scan.next(20)
    starts = []
    for draw in (0.124, 0.126, 0.0, 0.5):
        clock['now'] += projection_discovery.MAIN_PASS_SECONDS + 1
        clock['point'] = draw
        starts.append(scan.next(20)[0])
    assert [name == 'old000' for name in starts] == [True, False, True, False]


def test_a_main_cursor_that_wraps_in_time_is_not_restarted(monkeypatch):
    rows = {f'old{i:03d}': {'committed_at': 1_000.0 + 10 * i, 'projection_state': 'pending'} for i in range(30)}
    scan, clock = recent_scanner(monkeypatch, rows, striping='on', stripe=0)
    for _ in range(200):
        scan.next(20)
        clock['now'] += 20.0
    assert scan.stripe == 0


def test_recent_discovery_setting_bounds(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', raising=False)
    assert batch_pipeline.projection_recent_discovery_seconds() == 120
    for raw, want in (('0', 0), ('900', 900), ('99999', 3600), ('-1', 0), ('junk', 120)):
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS', raw)
        assert batch_pipeline.projection_recent_discovery_seconds() == want
