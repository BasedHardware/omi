import os
import sys
import types
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules["database._client"] = MagicMock()
sys.modules["stripe"] = MagicMock()


class NotFound(Exception):
    pass


_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_exceptions_module = types.ModuleType("google.cloud.exceptions")
_google_exceptions_module.NotFound = NotFound
sys.modules.setdefault("google.cloud.exceptions", _google_exceptions_module)
_google_firestore_module = types.ModuleType("google.cloud.firestore")
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
_google_firestore_v1_module = types.ModuleType("google.cloud.firestore_v1")
_google_firestore_v1_module.FieldFilter = MagicMock()
_google_firestore_v1_module.transactional = lambda func: func
sys.modules.setdefault("google.cloud.firestore_v1", _google_firestore_v1_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "exceptions", _google_exceptions_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)

from database import users as users_db


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, doc_id, data=None, exists=True):
        self.id = doc_id
        self._data = data or {}
        self._exists = exists
        self.parent = MagicMock()
        self.parent.parent.id = "owner_uid"

    def get(self):
        return _FakeSnapshot(self._data, exists=self._exists)

    def set(self, data):
        self._data = data

    def update(self, data):
        self._data.update(data)


class _FakeCollectionRef:
    def __init__(self, docs=None):
        self._docs = docs or []

    def document(self, doc_id):
        for doc in self._docs:
            if doc.id == doc_id:
                return doc
        return _FakeDocRef(doc_id, exists=False)

    def stream(self):
        return iter(self._docs)

    def where(self, filter):
        return self


def test_set_user_speaker_embedding():
    """Test storing speaker embedding on user document"""
    mock_db = MagicMock()
    user_ref = MagicMock()
    mock_db.collection.return_value.document.return_value = user_ref

    with patch('database.users.db', mock_db):
        embedding = [0.1, 0.2, 0.3]
        users_db.set_user_speaker_embedding("test_uid", embedding)

        mock_db.collection.assert_called_once_with('users')
        mock_db.collection.return_value.document.assert_called_once_with('test_uid')
        user_ref.update.assert_called_once()
        call_args = user_ref.update.call_args[0][0]
        assert call_args['speaker_embedding'] == embedding
        assert 'speaker_embedding_updated_at' in call_args


def test_share_speech_profile():
    """Test creating a shared speech profile record"""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.share_speech_profile("owner_uid", "target_uid")

        assert result is True
        shared_ref.set.assert_called_once()
        call_args = shared_ref.set.call_args[0][0]
        assert call_args['shared_with_uid'] == 'target_uid'
        assert call_args['revoked_at'] is None
        assert 'created_at' in call_args


def test_revoke_speech_profile_share_exists():
    """Test revoking an existing shared profile"""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    shared_ref.get.return_value.exists = True
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.revoke_speech_profile_share("owner_uid", "target_uid")

        assert result is True
        shared_ref.update.assert_called_once()
        call_args = shared_ref.update.call_args[0][0]
        assert 'revoked_at' in call_args


def test_revoke_speech_profile_share_not_exists():
    """Test revoking a non-existent shared profile"""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    shared_ref.get.return_value.exists = False
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.revoke_speech_profile_share("owner_uid", "target_uid")

        assert result is False
        shared_ref.update.assert_not_called()


def test_get_profiles_shared_with_user():
    """Test retrieving profiles shared with a user"""
    doc1 = _FakeDocRef("owner1", {'shared_with_uid': 'target_uid', 'revoked_at': None})
    doc2 = _FakeDocRef("owner2", {'shared_with_uid': 'target_uid', 'revoked_at': None})
    doc1.reference = MagicMock()
    doc1.reference.parent.parent.id = "owner1"
    doc2.reference = MagicMock()
    doc2.reference.parent.parent.id = "owner2"

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.stream.return_value = [doc1, doc2]
    mock_db.collection_group.return_value.where.return_value.where.return_value = mock_query

    with patch('database.users.db', mock_db):
        result = users_db.get_profiles_shared_with_user("target_uid")

        assert len(result) == 2
        assert "owner1" in result
        assert "owner2" in result


def test_get_users_shared_with():
    """Test retrieving users with whom owner has shared"""
    doc1 = _FakeDocRef("target1", {'shared_with_uid': 'target1', 'revoked_at': None})
    doc2 = _FakeDocRef("target2", {'shared_with_uid': 'target2', 'revoked_at': None})
    doc3 = _FakeDocRef("target3", {'shared_with_uid': 'target3', 'revoked_at': datetime.now(timezone.utc)})

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.stream.return_value = [doc1, doc2]
    mock_collection = MagicMock()
    mock_collection.where.return_value = mock_query
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_collection

    with patch('database.users.db', mock_db):
        result = users_db.get_users_shared_with("owner_uid")

        assert len(result) == 2
        assert "target1" in result
        assert "target2" in result
        assert "target3" not in result


def test_get_users_shared_with_empty():
    """Test retrieving shared users when none exist"""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.stream.return_value = []
    mock_collection = MagicMock()
    mock_collection.where.return_value = mock_query
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_collection

    with patch('database.users.db', mock_db):
        result = users_db.get_users_shared_with("owner_uid")

        assert len(result) == 0


def test_share_profile_idempotent():
    """Test that sharing the same profile twice doesn't cause issues"""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result1 = users_db.share_speech_profile("owner_uid", "target_uid")
        result2 = users_db.share_speech_profile("owner_uid", "target_uid")

        assert result1 is True
        assert result2 is True
        assert shared_ref.set.call_count == 2  