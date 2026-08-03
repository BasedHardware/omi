from unittest.mock import Mock

from database import screen_activity


class _Document:
    def __init__(self, doc_id: str, activity=None):
        self.id = doc_id
        self._activity = activity

    def collection(self, _name: str):
        return self._activity


class _Collection:
    def __init__(self, documents, activity=None):
        self.documents = documents
        self._activity = activity

    def select(self, _fields):
        return self

    def stream(self):
        return iter(self.documents)

    def document(self, doc_id: str):
        return _Document(doc_id, self._activity)


class _Batch:
    def __init__(self, events):
        self.deleted = []
        self.commits = 0
        self.events = events

    def delete(self, document):
        self.deleted.append(document.id)

    def commit(self):
        self.commits += 1
        self.events.append('firestore')


class _Database:
    def __init__(self, ids):
        self.batches = []
        self.events = []
        activity_collection = _Collection([_Document(doc_id) for doc_id in ids])
        user = _Document('user-1', activity_collection)
        self.users = _Collection([user], activity=activity_collection)

    def collection(self, _name: str):
        return self.users

    def batch(self):
        batch = _Batch(self.events)
        self.batches.append(batch)
        return batch


def test_purge_all_screen_activity_deletes_firestore_and_bounded_vector_batches(monkeypatch):
    database = _Database([f'screenshot-{i}' for i in range(1001)])
    vector_index = Mock()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(screen_activity, 'db', database)
    monkeypatch.setattr(screen_activity.vector_db, 'index', vector_index)
    vector_index.delete.side_effect = lambda **_kwargs: database.events.append('pinecone')

    assert screen_activity.purge_all_screen_activity() == 1001
    assert [batch.commits for batch in database.batches] == [1, 1, 1]
    assert [len(batch.deleted) for batch in database.batches] == [500, 500, 1]
    assert [len(call.kwargs['ids']) for call in vector_index.delete.call_args_list] == [1000, 1]
    assert database.events == ['pinecone', 'pinecone', 'firestore', 'firestore', 'firestore']


def test_purge_all_screen_activity_skips_shared_firestore_outside_production(monkeypatch):
    database = _Database(['screenshot-1'])
    vector_index = Mock()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(screen_activity, 'db', database)
    monkeypatch.setattr(screen_activity.vector_db, 'index', vector_index)

    assert screen_activity.purge_all_screen_activity() == 0
    assert database.batches == []
    vector_index.delete.assert_not_called()
