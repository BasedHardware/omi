"""Tests for None guards and missing-field robustness in staged_tasks database module."""

from unittest.mock import MagicMock

from database import action_items as action_items_db
from database import staged_tasks as staged_tasks_db


def _make_doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def test_create_staged_task_handles_none_doc_in_stream(monkeypatch):
    """When iterating staged tasks for deduplication, doc.to_dict() may return None.

    create_staged_task must not raise AttributeError.
    """
    doc_none = _make_doc('doc-none', None)
    doc_other = _make_doc('doc-other', {'description': 'Do something else'})

    fake_col = MagicMock()
    fake_col.stream.return_value = iter([doc_none, doc_other])

    created_doc = {}
    fake_doc_ref = MagicMock()
    fake_doc_ref.set.side_effect = lambda d: created_doc.update(d)
    fake_col.document.return_value = fake_doc_ref

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)

    result = staged_tasks_db.create_staged_task('uid123', 'New Task')
    assert result['description'] == 'New Task'
    assert fake_doc_ref.set.called


def test_create_staged_task_dedup_match(monkeypatch):
    """When deduplicating against an existing doc, it should return existing with id set."""
    doc_match = _make_doc('doc-match', {'description': 'Existing Task'})
    fake_col = MagicMock()
    fake_col.stream.return_value = iter([doc_match])

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)

    result = staged_tasks_db.create_staged_task('uid123', 'Existing Task')
    assert result['id'] == 'doc-match'
    assert result['description'] == 'Existing Task'


def test_get_staged_tasks_handles_none_doc_in_stream(monkeypatch):
    """When reading staged tasks, doc.to_dict() returning None must not raise TypeError."""
    doc_none = _make_doc('doc-none', None)
    doc_valid = _make_doc('doc-valid', {'description': 'Valid Task', 'relevance_score': 10})

    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.offset.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter([doc_none, doc_valid])

    fake_col = MagicMock()
    fake_col.where.return_value = fake_query

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)

    results = staged_tasks_db.get_staged_tasks('uid123')
    assert len(results) == 2
    assert results[0] == {'id': 'doc-none'}
    assert results[1] == {'id': 'doc-valid', 'description': 'Valid Task', 'relevance_score': 10}


def test_promote_staged_task_handles_none_doc_in_stream(monkeypatch):
    """When promoting the top staged task, doc.to_dict() returning None must not raise TypeError."""
    doc_none = _make_doc('doc-none', None)

    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter([doc_none])

    fake_doc_ref = MagicMock()
    fake_col = MagicMock()
    fake_col.where.return_value = fake_query
    fake_col.document.return_value = fake_doc_ref

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)
    monkeypatch.setattr(action_items_db, 'get_active_action_item_by_description', lambda uid, desc: None)
    monkeypatch.setattr(action_items_db, 'create_action_item', lambda uid, data: 'action-123')
    monkeypatch.setattr(
        action_items_db, 'get_action_item', lambda uid, aid: {'id': aid, 'description': '', 'completed': False}
    )

    result = staged_tasks_db.promote_staged_task('uid123')
    assert result['id'] == 'action-123'
    assert result['description'] == ''
    assert fake_doc_ref.update.called


def test_promote_staged_task_handles_missing_description(monkeypatch):
    """When promoting a staged task without 'description', it should not raise KeyError."""
    doc_nodesc = _make_doc('doc-nodesc', {'priority': 'high'})

    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter([doc_nodesc])

    fake_doc_ref = MagicMock()
    fake_col = MagicMock()
    fake_col.where.return_value = fake_query
    fake_col.document.return_value = fake_doc_ref

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)
    monkeypatch.setattr(action_items_db, 'get_active_action_item_by_description', lambda uid, desc: None)

    created_data = {}

    def mock_create(uid, data):
        created_data.update(data)
        return 'action-456'

    monkeypatch.setattr(action_items_db, 'create_action_item', mock_create)
    monkeypatch.setattr(action_items_db, 'get_action_item', lambda uid, aid: {'id': aid, **created_data})

    result = staged_tasks_db.promote_staged_task('uid123')
    assert result['id'] == 'action-456'
    assert result['description'] == ''
    assert result['priority'] == 'high'
