"""Discovery hints advance independently; they never authorize projection."""

from unittest.mock import Mock

from utils.batch_pipeline.projection_discovery import ProjectionDiscovery


def test_default_on_independent_scans_wrap_and_kill_switch_restores_first_page(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
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


def test_failed_query_retries_cursor_without_losing_page():
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
