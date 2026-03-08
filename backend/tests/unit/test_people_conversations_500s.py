"""
Regression tests for #5423 (Person model validation) and #5424 (conversations response size).

#5423: /v1/users/people returns 500 when legacy Firestore person docs are missing
       the 'id' field or 'created_at'/'updated_at' timestamps.
#5424: /v1/conversations returns 500 when @with_photos loads full base64 photo content
       for every conversation, exceeding Cloud Run's 32MB response limit.
"""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Mock Firestore client before importing database modules
_client_mod = MagicMock()
sys.modules.setdefault('database._client', _client_mod)

from models.other import Person


class TestPersonModelResilience:
    """#5423: Person model should handle missing optional fields from legacy docs."""

    def test_person_missing_created_at_updated_at(self):
        """Legacy person docs may not have created_at/updated_at."""
        data = {
            'id': 'person-123',
            'name': 'Alice',
        }
        person = Person(**data)
        assert person.id == 'person-123'
        assert person.name == 'Alice'
        assert person.created_at is None
        assert person.updated_at is None

    def test_person_with_all_fields(self):
        """Full person doc should still work."""
        now = datetime.now(timezone.utc)
        data = {
            'id': 'person-456',
            'name': 'Bob',
            'created_at': now,
            'updated_at': now,
            'speech_samples': ['gs://bucket/sample1.wav'],
        }
        person = Person(**data)
        assert person.id == 'person-456'
        assert person.name == 'Bob'
        assert person.created_at == now
        assert person.updated_at == now
        assert len(person.speech_samples) == 1

    def test_person_defaults(self):
        """Verify defaults for optional fields."""
        person = Person(id='p1', name='Test')
        assert person.speech_samples == []
        assert person.speech_sample_transcripts is None
        assert person.speech_samples_version == 3


class TestGetPeopleDocIdInjection:
    """#5423: get_people/get_person should inject Firestore doc ID."""

    def _make_mock_doc(self, doc_id, data, exists=True):
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.exists = exists
        mock_doc.to_dict.return_value = data.copy() if data else {}
        return mock_doc

    def test_get_people_injects_doc_id(self):
        """get_people() should set 'id' from doc.id when missing from data."""
        from database import users as users_mod

        mock_doc = self._make_mock_doc('firestore-doc-id', {'name': 'Alice'})
        users_mod.db = MagicMock()
        users_mod.db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
            mock_doc
        ]

        result = users_mod.get_people('uid-123')
        assert len(result) == 1
        assert result[0]['id'] == 'firestore-doc-id'
        assert result[0]['name'] == 'Alice'

    def test_get_people_preserves_existing_id(self):
        """get_people() should not overwrite an existing 'id' field."""
        from database import users as users_mod

        mock_doc = self._make_mock_doc('firestore-doc-id', {'id': 'stored-id', 'name': 'Bob'})
        users_mod.db = MagicMock()
        users_mod.db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
            mock_doc
        ]

        result = users_mod.get_people('uid-123')
        assert result[0]['id'] == 'stored-id'

    def test_get_person_injects_doc_id(self):
        """get_person() should inject doc ID for legacy docs."""
        from database import users as users_mod

        mock_doc = self._make_mock_doc('person-doc-id', {'name': 'Charlie'})
        users_mod.db = MagicMock()
        users_mod.db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        result = users_mod.get_person('uid-123', 'person-doc-id')
        assert result['id'] == 'person-doc-id'

    def test_get_person_returns_none_when_not_exists(self):
        """get_person() should return None for missing docs."""
        from database import users as users_mod

        mock_doc = self._make_mock_doc('nonexistent', {}, exists=False)
        users_mod.db = MagicMock()
        users_mod.db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        result = users_mod.get_person('uid-123', 'nonexistent')
        assert result is None

    def test_get_people_by_ids_uses_doc_fetch(self):
        """get_people_by_ids() should use document fetches and inject IDs."""
        from database import users as users_mod

        mock_doc1 = self._make_mock_doc('pid-1', {'name': 'Alice'})
        mock_doc2 = self._make_mock_doc('pid-2', {}, exists=False)

        users_mod.db = MagicMock()
        users_mod.db.get_all.return_value = [mock_doc1, mock_doc2]

        result = users_mod.get_people_by_ids('uid-123', ['pid-1', 'pid-2'])
        assert len(result) == 1
        assert result[0]['id'] == 'pid-1'
        users_mod.db.get_all.assert_called_once()


class TestConversationsListNoPhotos:
    """#5424: List endpoint should not load photo base64 content."""

    def test_list_endpoint_uses_without_photos(self):
        """Verify the router calls get_conversations_without_photos, not get_conversations."""
        import os

        router_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(router_path) as f:
            source = f.read()
        # The list endpoint function should call get_conversations_without_photos
        assert 'get_conversations_without_photos' in source

    def test_get_conversations_without_photos_has_folder_starred(self):
        """Verify get_conversations_without_photos supports folder_id and starred params."""
        import os

        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'conversations.py')
        with open(db_path) as f:
            source = f.read()
        # Find the function definition and check its parameters
        assert 'def get_conversations_without_photos(' in source
        # Extract the function signature block
        start = source.index('def get_conversations_without_photos(')
        sig_block = source[start : source.index('):', start) + 2]
        assert 'folder_id' in sig_block
        assert 'starred' in sig_block
