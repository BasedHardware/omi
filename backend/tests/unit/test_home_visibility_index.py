"""The persisted Home bit follows the two source flags through legacy and partial writes."""

from types import SimpleNamespace

import pytest
from google.cloud.firestore import DELETE_FIELD

from database import home_visibility_index as visibility
from scripts import backfill_home_visibility_index as backfill


@pytest.mark.parametrize(
    'current, patch, expected',
    [
        ({}, {}, True),
        ({}, {'recording': True}, False),
        ({}, {'home_hidden': True}, False),
        ({'home_hidden': True}, {'recording': False}, False),
        ({'recording': True}, {'home_hidden': False}, False),
        ({'recording': True}, {'recording': DELETE_FIELD}, True),
        ({'home_hidden': True, 'recording': None}, {'home_hidden': False}, True),
        ({'home_hidden': 'legacy_truthy_value'}, {}, False),
    ],
)
def test_stamp_uses_post_write_truthiness(current, patch, expected):
    written = visibility.stamp(dict(patch), current)
    assert written == {**patch, visibility.FIELD: expected}


def test_dry_run_reports_both_kinds_of_drift_and_capped_read_cost(monkeypatch):
    rows = [
        {'recording': True, 'home_visible': True},
        {'home_hidden': False},
        {'home_visible': True},
        {'home_visible': 1},
    ]
    snapshots = [
        SimpleNamespace(id=str(i), reference=str(i), to_dict=lambda row=row: row) for i, row in enumerate(rows)
    ]
    monkeypatch.setattr(backfill, '_scan', lambda *_: snapshots)
    result = backfill.plan(None, project='test', uid='owner', after=None, limit=4)
    assert result['rows_scanned'] == result['dry_run_reads'] == 4
    assert result['next_after'] == '3'
    assert (result['missing'], result['mismatched']) == (1, 2)
    assert result['expected_apply_reads'] == 7
    assert result['expected_apply_writes'] == 3
    assert result['max_apply_reads'] == 14


def test_apply_refuses_to_exceed_the_approved_change_count(monkeypatch):
    snapshot = SimpleNamespace(reference='now-missing', to_dict=lambda: {})
    monkeypatch.setattr(backfill, '_scan', lambda *args, **kwargs: [snapshot])
    approved = {
        'project': 'test',
        'uid': 'owner',
        'after': None,
        'through': 'now-missing',
        'rows_scanned': 1,
        'expected_apply_writes': 0,
    }
    with pytest.raises(ValueError, match='candidate count grew'):
        backfill.apply(None, None, approved, project='test', uid='owner')
