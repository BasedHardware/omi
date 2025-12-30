import pytest
from unittest.mock import MagicMock

from database import users as users_db


def test_add_and_remove_shared_person(monkeypatch):
    # Mock Firestore collection/document behaviour via monkeypatching db.collection
    fake_collection = {}

    class FakeDoc:
        def __init__(self, path):
            self.path = path
            self._data = {}

        def set(self, data, merge=False):
            fake_collection[self.path] = data

        def get(self):
            class Doc:
                def __init__(self, exists, data):
                    self._exists = exists
                    self._data = data

                @property
                def exists(self):
                    return self._exists

                def to_dict(self):
                    return self._data

            d = fake_collection.get(self.path)
            return Doc(d is not None, d)

        def delete(self):
            if self.path in fake_collection:
                del fake_collection[self.path]

    # Monkeypatch collection/document creation
    monkeypatch.setattr(users_db, 'db', MagicMock())
    def collection(doc):
        class C:
            def document(self, doc_id):
                return FakeDoc(f"users/{doc}/{doc_id}")
        return C()

    users_db.db.collection = lambda name: collection(name)

    # Add shared person
    users_db.add_shared_person_to_user('target', 'source', 'Alice', [0.1, 0.2, 0.3], 'url')
    shared = users_db.get_shared_people('target')
    assert isinstance(shared, list)

    # Remove shared person
    removed = users_db.remove_shared_person_from_user('target', 'source')
    assert removed is True


def test_get_shared_people_empty(monkeypatch):
    monkeypatch.setattr(users_db, 'db', MagicMock())
    users_db.db.collection = lambda name: MagicMock(stream=lambda: [])
    res = users_db.get_shared_people('target')
    assert res == []
