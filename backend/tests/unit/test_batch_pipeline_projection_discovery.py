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
