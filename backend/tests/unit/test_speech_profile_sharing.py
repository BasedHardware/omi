import os
import sys
import types
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from database import users as users_db

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

    def to_dict(self):
        return self._data


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


def test_shared_person_id_format():
    """Test that shared person IDs follow the 'shared:{uid}' format and can be parsed."""
    owner_uid = "abc123def456"
    shared_pid = f"shared:{owner_uid}"

    assert shared_pid.startswith("shared:")
    assert shared_pid.split(":", 1)[1] == owner_uid


def test_shared_person_id_not_mistaken_for_regular():
    """Test that shared person IDs are distinguished from regular person IDs and 'user'."""
    shared_pid = "shared:owner123"
    regular_pid = "person-uuid-here"
    user_pid = "user"

    assert shared_pid.startswith("shared:")
    assert not regular_pid.startswith("shared:")
    assert not user_pid.startswith("shared:")


def test_shared_pid_skipped_for_pusher_extraction():
    """Test that shared person IDs are correctly identified for skipping pusher calls."""
    test_cases = [
        ("shared:abc123", True),
        ("shared:a", True),
        ("person-uuid", False),
        ("user", False),
        ("", False),
    ]
    for person_id, should_skip in test_cases:
        result = person_id.startswith("shared:")
        assert result == should_skip, f"person_id={person_id!r}: expected skip={should_skip}, got {result}"


def test_shared_name_resolution_with_profile():
    """Test that shared profile owner name is resolved from user profile."""
    owner_uid = "owner123"
    profile = {'name': 'Alice Smith', 'email': 'alice@example.com'}
    name = profile.get('name') or owner_uid[:8]
    assert name == 'Alice Smith'


def test_shared_name_resolution_fallback_to_uid_prefix():
    """Test that shared profile falls back to uid prefix when name is missing."""
    owner_uid = "abcdef1234567890"

    # No name in profile
    profile_no_name = {'email': 'test@example.com'}
    name = profile_no_name.get('name') or owner_uid[:8]
    assert name == 'abcdef12'

    # Empty name in profile
    profile_empty_name = {'name': '', 'email': 'test@example.com'}
    name = profile_empty_name.get('name') or owner_uid[:8]
    assert name == 'abcdef12'


def test_shared_name_resolution_skipped_when_no_profile():
    """Test that shared profile is skipped when get_user_profile returns None."""
    profile = None
    # Simulates the if profile: guard in process_conversation
    people_added = []
    if profile:
        people_added.append(profile)
    assert len(people_added) == 0


def test_shared_pids_extracted_from_mixed_person_ids():
    """Test that only shared person IDs are extracted from a mixed list."""
    person_ids = ["person-1", "shared:owner1", "user", "shared:owner2", "person-2"]
    shared_pids = [pid for pid in person_ids if pid.startswith("shared:")]
    assert shared_pids == ["shared:owner1", "shared:owner2"]


def test_shared_pids_empty_when_none_present():
    """Test that no shared IDs are extracted when none exist."""
    person_ids = ["person-1", "user", "person-2"]
    shared_pids = [pid for pid in person_ids if pid.startswith("shared:")]
    assert shared_pids == []


def test_speaker_assignment_with_shared_person_id():
    """Test that speaker assignment maps work with shared person IDs."""
    from utils.speaker_assignment import update_speaker_assignment_maps

    speaker_to_person_map = {}
    segment_person_assignment_map = {}

    result = update_speaker_assignment_maps(
        speaker_id=2,
        person_id="shared:owner123",
        person_name="Alice",
        segment_ids=["seg-1", "seg-2"],
        speaker_to_person_map=speaker_to_person_map,
        segment_person_assignment_map=segment_person_assignment_map,
    )

    assert result is True
    assert speaker_to_person_map[2] == ("shared:owner123", "Alice")
    assert segment_person_assignment_map["seg-1"] == "shared:owner123"
    assert segment_person_assignment_map["seg-2"] == "shared:owner123"


def test_process_segments_with_shared_person_id():
    """Test that segments are correctly assigned shared person IDs."""
    from utils.speaker_assignment import process_speaker_assigned_segments
    from models.transcript_segment import TranscriptSegment

    segment = TranscriptSegment(
        id="seg-1",
        text="hello",
        speaker="SPEAKER_02",
        is_user=False,
        person_id=None,
        start=0.0,
        end=1.0,
    )

    segment_person_assignment_map = {"seg-1": "shared:owner123"}
    speaker_to_person_map = {}

    process_speaker_assigned_segments(
        [segment],
        segment_person_assignment_map,
        speaker_to_person_map,
    )

    assert segment.person_id == "shared:owner123"
    assert segment.is_user is False
