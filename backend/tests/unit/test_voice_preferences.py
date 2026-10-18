"""Unit tests for database.voice_preferences — uid sanitization, read
resilience (data-plane outage falls back to the catalog default), and
guarded writes."""

import pytest

from config.assistant_voices import DEFAULT_ASSISTANT_VOICE
from database import voice_preferences


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocument:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self):
        return _FakeSnapshot(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        if merge:
            self._store.docs.setdefault(self._path, {}).update(data)
        else:
            self._store.docs[self._path] = dict(data)


class _FakeCollection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id):
        return _FakeDocument(self._store, f'{self._name}/{doc_id}')


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def collection(self, name):
        return _FakeCollection(self, name)


@pytest.fixture
def store():
    return _FakeDb()


class TestSanitization:
    def test_set_strips_uid_whitespace(self, store):
        voice_preferences.set_assistant_voice('  u1  ', 'Charon', firestore_client=store)
        assert 'users/u1' in store.docs
        assert 'users/  u1  ' not in store.docs

    def test_set_rejects_blank_uid(self, store):
        with pytest.raises(ValueError, match='invalid_uid'):
            voice_preferences.set_assistant_voice('   ', 'Charon', firestore_client=store)

    def test_get_blank_uid_returns_default(self, store):
        assert voice_preferences.get_assistant_voice('  ', firestore_client=store) == DEFAULT_ASSISTANT_VOICE

    def test_get_strips_uid(self, store):
        store.docs['users/u2'] = {'assistant_voice_id': 'Charon'}
        got = voice_preferences.get_assistant_voice('\tu2 ', firestore_client=store)
        assert got == 'Charon'


class TestReadResilience:
    def test_missing_doc_returns_default(self, store):
        assert voice_preferences.get_assistant_voice('ghost', firestore_client=store) == DEFAULT_ASSISTANT_VOICE

    def test_store_failure_returns_default(self):
        class _Boom:
            def collection(self, name):
                raise TimeoutError('data plane degraded')

        assert voice_preferences.get_assistant_voice('u', firestore_client=_Boom()) == DEFAULT_ASSISTANT_VOICE


class TestWriteGuard:
    def test_write_round_trips(self, store):
        out = voice_preferences.set_assistant_voice('u3', 'Charon', firestore_client=store)
        assert out == 'Charon'
        assert store.docs['users/u3']['assistant_voice_id'] == 'Charon'

    def test_write_normalizes_invalid_voice(self, store):
        out = voice_preferences.set_assistant_voice('u3', 'not-a-voice', firestore_client=store)
        assert out == DEFAULT_ASSISTANT_VOICE

    def test_missing_client_raises_on_write(self, monkeypatch):
        monkeypatch.setattr(voice_preferences, 'get_data_plane_firestore_client', lambda: None)
        with pytest.raises(RuntimeError, match='data plane unavailable'):
            voice_preferences.set_assistant_voice('u3', 'Charon')


def test_programming_error_propagates_not_falls_back():
    """The narrowed except must not swallow bugs — only data-plane faults."""

    class _BoomClient:
        def collection(self, name):
            raise AttributeError('misconfigured client object')

    import pytest

    with pytest.raises(AttributeError):
        voice_preferences.get_assistant_voice('u1', firestore_client=_BoomClient())
