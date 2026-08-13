"""Historical staged-task score metadata ignores stale or promoted IDs."""

from unittest.mock import MagicMock

from database import staged_tasks as staged_tasks_db


def _snapshot(doc_id: str):
    snapshot = MagicMock()
    snapshot.id = doc_id
    return snapshot


def _score_store(monkeypatch, active_ids: list[str]):
    query = MagicMock()
    query.select.return_value = query
    query.stream.return_value = [_snapshot(doc_id) for doc_id in active_ids]
    collection = MagicMock()
    collection.where.return_value = query
    batch = MagicMock()
    database = MagicMock()
    database.batch.return_value = batch
    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)
    monkeypatch.setattr(staged_tasks_db, 'db', database)
    return collection, batch, database


def test_batch_scores_updates_only_live_historical_ids(monkeypatch):
    collection, batch, _database = _score_store(monkeypatch, ['task-1', 'task-3'])

    staged_tasks_db.batch_update_staged_scores(
        'user-1',
        [
            {'id': 'task-1', 'relevance_score': 900},
            {'id': 'task-2', 'relevance_score': 500},
            {'id': 'task-3', 'relevance_score': 100},
        ],
    )

    assert batch.update.call_count == 2
    collection.document.assert_any_call('task-1')
    collection.document.assert_any_call('task-3')
    assert 'task-2' not in [call.args[0] for call in collection.document.call_args_list]
    batch.commit.assert_called_once()


def test_batch_scores_empty_input_performs_no_io(monkeypatch):
    collection, batch, database = _score_store(monkeypatch, [])

    staged_tasks_db.batch_update_staged_scores('user-1', [])

    collection.where.assert_not_called()
    database.batch.assert_not_called()
    batch.commit.assert_not_called()


def test_batch_scores_all_stale_ids_do_not_create_batch(monkeypatch):
    _collection, batch, database = _score_store(monkeypatch, [])

    staged_tasks_db.batch_update_staged_scores(
        'user-1',
        [{'id': 'gone-1', 'relevance_score': 500}],
    )

    database.batch.assert_not_called()
    batch.commit.assert_not_called()
