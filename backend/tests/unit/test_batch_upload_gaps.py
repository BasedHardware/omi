"""Accepted same-key cadence, without extra storage IO or behavioral changes."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from database import batch_pipeline_coalescing as rows
from database import batch_pipeline_upload_metrics as upload_metrics
from tests.unit.test_batch_upload_coalescing import group, member, store


def fresh_member(*args, **kwargs):
    result = member(*args, **kwargs)
    result['item']['priority'] = 0
    return result


@pytest.mark.parametrize('clock', [None, True, -1, float('inf'), float('nan')])
def test_unknown_clocks_are_not_bridged(clock):
    assert (
        upload_metrics.inter_upload_gap(
            {'upload_arrived_at': 100}, [{'upload_arrived_at': 1}, {'upload_arrived_at': clock}]
        )
        is None
    )
    assert upload_metrics.inter_upload_gap({'upload_arrived_at': clock}, [{'upload_arrived_at': 1}]) is None


def test_no_first_sample_and_no_reordered_or_zero_samples():
    assert upload_metrics.inter_upload_gap({'upload_arrived_at': 10}, []) is None
    for stamp in (9, 10):
        assert upload_metrics.inter_upload_gap({'upload_arrived_at': stamp}, [{'upload_arrived_at': 10}]) is None


def test_measure_after_commit_once_across_transaction_retry_and_upload_replay(monkeypatch):
    metric = Mock()
    monkeypatch.setattr(upload_metrics, 'INTER_UPLOAD_GAP', metric)
    s = store()
    first = fresh_member('first', upload_arrived_at=8, upload_entitlement='paid')
    second = fresh_member('second', start=110, upload_arrived_at=9, upload_entitlement='paid')
    rows.enqueue(s, first, 'key', 10)
    real_run = s.run

    def retry(commit):
        before = deepcopy(s.rows)
        real_run(commit)
        metric.labels.assert_not_called()  # No aborted-attempt observation.
        s.rows = before
        return real_run(commit)

    monkeypatch.setattr(s, 'run', retry)
    assert rows.enqueue(s, second, 'key', 10) == 'bp_second'
    metric.labels.assert_called_once_with('paid', 'fresh', 'within_group')
    metric.labels.return_value.observe.assert_called_once_with(1)
    monkeypatch.setattr(s, 'run', real_run)
    rows.enqueue(s, second, 'key', 10)
    assert metric.labels.return_value.observe.call_count == 1


def test_previous_completed_group_keeps_the_boundary_gap_without_new_rows(monkeypatch):
    metric = Mock()
    monkeypatch.setattr(upload_metrics, 'INTER_UPLOAD_GAP', metric)
    s = store()
    rows.enqueue(s, fresh_member('first', upload_arrived_at=8), 'key', 10)
    group(s)['state'] = 'done'
    rows.enqueue(s, fresh_member('next', start=110, upload_arrived_at=9), 'key', 10)
    metric.labels.assert_called_once_with('unknown', 'fresh', 'between_groups')
    metric.labels.return_value.observe.assert_called_once_with(1)
    assert {table for table, _ in s.rows} == {
        'coalesce_quota',
        'coalesce_groups',
        'coalesce_heads',
        'coalesce_sources',
        'intakes',
        'content',
    }


def test_no_sample_on_capacity_bypass_wait_or_failed_commit(monkeypatch):
    metric = Mock()
    monkeypatch.setattr(upload_metrics, 'INTER_UPLOAD_GAP', metric)
    s = store()
    first = member('first', upload_arrived_at=8)
    rows.enqueue(s, first, 'key', 10)
    group(s)['state'] = 'draining'
    assert rows.enqueue(s, member('wait', upload_arrived_at=9), 'key', 10) == 'wait'
    s.rows['coalesce_quota', 'global']['groups'] = 64
    assert rows.enqueue(s, member('bypass', upload_arrived_at=9), 'another-key', 10) is None
    monkeypatch.setattr(s, 'run', Mock(side_effect=RuntimeError('commit failed')))
    with pytest.raises(RuntimeError, match='commit failed'):
        rows.enqueue(s, member('failed', upload_arrived_at=9), 'key', 10)
    metric.labels.assert_not_called()


@pytest.mark.parametrize('lane,priority', [('backfill', 0), ('fresh', 1)])
def test_nonfresh_cadence_is_separate_from_fresh_paid(monkeypatch, lane, priority):
    metric = Mock()
    monkeypatch.setattr(upload_metrics, 'INTER_UPLOAD_GAP', metric)
    upload_metrics.observe_gap(
        {'lane': lane, 'item': {'priority': priority}, 'upload_entitlement': 'unexpected-id'},
        65,
        'within_group',
    )
    metric.labels.assert_called_once_with('unknown', 'backlog', 'within_group')
