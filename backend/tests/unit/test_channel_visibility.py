"""Unit tests for database.channel_visibility — uid sanitization,
stream resilience, and payload validation.

Covers the normal flow, cohort gating, whitespace stripping, malformed
payloads, and exception handling per the module's contract.
"""

from unittest.mock import patch

from database import channel_visibility


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class _FakeStreamCollection:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


class _FakeUserDoc:
    def __init__(self, channel_links, chat_sessions):
        self._links = channel_links
        self._sessions = chat_sessions

    def collection(self, name):
        return {
            'channel_links': _FakeStreamCollection(self._links),
            'chat_sessions': _FakeStreamCollection(self._sessions),
        }[name]


class _FakeUsersCollection:
    def __init__(self, user_doc):
        self._user_doc = user_doc
        self.requested_path = None

    def document(self, uid):
        self.requested_path = uid
        return self._user_doc


class _FakeDb:
    def __init__(self, user_doc):
        self.users = _FakeUsersCollection(user_doc)
        self.collection_calls = []

    def collection(self, name):
        self.collection_calls.append(name)
        return {'users': self.users}[name]


def _db_with(link_data, session_data):
    links = [_FakeDoc(i, d) for i, d in enumerate(link_data)]
    sessions = [_FakeDoc(f'session-{i}', d) for i, d in enumerate(session_data)]
    return _FakeDb(_FakeUserDoc(links, sessions))


class TestVisibleSessions:
    def test_returns_sessions_for_visible_channels(self):
        db = _db_with(
            [{'visible_in_app': True}],
            [{'channel_link_id': 0}, {'channel_link_id': 99}],
        )
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            out = channel_visibility.visible_sessions('u1', firestore_client=db)
        assert len(out) == 1
        assert out[0]['id'] == 'session-0'

    def test_cohort_disabled_returns_empty(self):
        db = _db_with([{'visible_in_app': True}], [{'channel_link_id': 0}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=False):
            assert channel_visibility.visible_sessions('u1', firestore_client=db) == []
        assert db.collection_calls == []

    def test_whitespace_uid_stripped_before_lookup(self):
        db = _db_with([{'visible_in_app': True}], [{'channel_link_id': 0}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            channel_visibility.visible_sessions('  u7  ', firestore_client=db)
        assert db.users.requested_path == 'u7'

    def test_blank_uid_returns_empty_without_touching_db(self):
        db = _db_with([], [])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            assert channel_visibility.visible_sessions('   ', firestore_client=db) == []
        assert db.collection_calls == []

    def test_no_visible_links_returns_empty(self):
        db = _db_with([{'visible_in_app': False}], [{'channel_link_id': 0}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            assert channel_visibility.visible_sessions('u1', firestore_client=db) == []

    def test_malformed_link_payload_skipped(self):
        db = _db_with([None, {'visible_in_app': True}], [{'channel_link_id': 1}, {'channel_link_id': 0}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            out = channel_visibility.visible_sessions('u1', firestore_client=db)
        # link 0 is malformed (skipped); link 1 is visible -> the session
        # pointing at link 1 (session-0) is the only match.
        assert [s['id'] for s in out] == ['session-0']

    def test_stream_failure_returns_empty(self):
        class _BoomDb:
            def collection(self, name):
                raise TimeoutError('data plane degraded')

        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            assert channel_visibility.visible_sessions('u1', firestore_client=_BoomDb()) == []

    def test_session_missing_channel_link_id_skipped(self):
        db = _db_with([{'visible_in_app': True}], [{'title': 'no link field'}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            assert channel_visibility.visible_sessions('u1', firestore_client=db) == []

    def test_link_payload_non_dict_truthy_skipped(self):
        db = _db_with(['yes', {'visible_in_app': True}], [{'channel_link_id': 0}, {'channel_link_id': 1}])
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True):
            out = channel_visibility.visible_sessions('u1', firestore_client=db)
        # link 0's truthy non-dict payload is not a dict -> not visible;
        # only the session on link 1 matches.
        assert [s['id'] for s in out] == ['session-1']

    def test_none_client_returns_empty(self):
        with patch.object(channel_visibility, 'cohort_enabled', return_value=True), patch.object(
            channel_visibility, 'get_firestore_client', return_value=None
        ):
            assert channel_visibility.visible_sessions('u1') == []
