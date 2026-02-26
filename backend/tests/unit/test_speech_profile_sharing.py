import os
import sys
import types
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import numpy as np

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


def _build_embedding_cache(people, shared_owners, get_user_profile_fn):
    """
    Replicates the embedding cache building logic from transcribe.py
    speaker_identification_task (lines 1301-1337).
    """
    person_embeddings_cache = {}

    # Load regular people embeddings
    for person in people:
        emb = person.get('speaker_embedding')
        if emb:
            person_embeddings_cache[person['id']] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': person['name'],
            }

    # Load shared profile embeddings
    uid = 'current_user'
    for owner_uid in shared_owners:
        if owner_uid == uid:
            continue
        profile = get_user_profile_fn(owner_uid)
        if not profile:
            continue
        emb = profile.get('speaker_embedding')
        if emb:
            name = profile.get('display_name') or owner_uid[:8]
            person_embeddings_cache[f"shared:{owner_uid}"] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': name,
            }

    return person_embeddings_cache


def test_cache_loads_shared_profiles():
    """Test that shared profile embeddings are loaded into the speaker ID cache."""
    alice_embedding = [0.1, 0.2, 0.3, 0.4]

    def mock_get_profile(uid):
        if uid == 'alice_uid':
            return {'display_name': 'Alice', 'speaker_embedding': alice_embedding}
        return {}

    cache = _build_embedding_cache(
        people=[],
        shared_owners=['alice_uid'],
        get_user_profile_fn=mock_get_profile,
    )

    assert 'shared:alice_uid' in cache
    assert cache['shared:alice_uid']['name'] == 'Alice'
    np.testing.assert_array_almost_equal(cache['shared:alice_uid']['embedding'].flatten(), alice_embedding)


def test_cache_loads_both_people_and_shared():
    """Test that both regular people and shared profiles coexist in the cache."""
    cache = _build_embedding_cache(
        people=[
            {'id': 'person-bob', 'name': 'Bob', 'speaker_embedding': [0.5, 0.6, 0.7, 0.8]},
        ],
        shared_owners=['alice_uid'],
        get_user_profile_fn=lambda uid: {
            'display_name': 'Alice',
            'speaker_embedding': [0.1, 0.2, 0.3, 0.4],
        },
    )

    assert 'person-bob' in cache
    assert 'shared:alice_uid' in cache
    assert cache['person-bob']['name'] == 'Bob'
    assert cache['shared:alice_uid']['name'] == 'Alice'


def test_cache_skips_shared_without_embedding():
    """Test that shared profiles without embeddings are not added to cache."""
    cache = _build_embedding_cache(
        people=[],
        shared_owners=['no_embed_uid'],
        get_user_profile_fn=lambda uid: {'display_name': 'No Embed User'},
    )

    assert len(cache) == 0


def test_cache_skips_shared_with_no_profile():
    """Test that shared profiles where get_user_profile returns empty are skipped."""
    cache = _build_embedding_cache(
        people=[],
        shared_owners=['ghost_uid'],
        get_user_profile_fn=lambda uid: {},
    )

    assert len(cache) == 0


def test_cache_name_fallback_to_uid_prefix():
    """Test that cache uses uid[:8] when display_name is missing."""
    cache = _build_embedding_cache(
        people=[],
        shared_owners=['abcdef1234567890'],
        get_user_profile_fn=lambda uid: {'speaker_embedding': [0.1, 0.2, 0.3]},
    )

    assert cache['shared:abcdef1234567890']['name'] == 'abcdef12'


def test_cache_skips_self_sharing():
    """Test that if current user's own UID appears in shared_owners, it's skipped."""
    cache = _build_embedding_cache(
        people=[],
        shared_owners=['current_user'],  # same as uid in _build_embedding_cache
        get_user_profile_fn=lambda uid: {'display_name': 'Me', 'speaker_embedding': [0.1]},
    )

    assert len(cache) == 0


def _find_best_match(query_embedding, person_embeddings_cache, threshold=0.45):
    """
    Replicates the matching logic from transcribe.py _match_speaker_embedding
    (lines 1453-1492).
    """
    from scipy.spatial.distance import cdist

    best_match = None
    best_distance = float('inf')

    for person_id, data in person_embeddings_cache.items():
        distance = float(cdist(query_embedding, data['embedding'], metric='cosine')[0, 0])
        if distance < best_distance:
            best_distance = distance
            best_match = (person_id, data['name'])

    if best_match and best_distance < threshold:
        return best_match[0], best_match[1], best_distance
    return None, None, best_distance


def test_match_identifies_shared_profile_by_same_embedding():
    """Test that a query embedding matches the identical shared profile embedding."""
    emb = np.array([[0.3, 0.5, 0.7, 0.9]], dtype=np.float32)
    cache = {
        'shared:alice_uid': {'embedding': emb.copy(), 'name': 'Alice'},
    }

    person_id, name, distance = _find_best_match(emb, cache)
    assert person_id == 'shared:alice_uid'
    assert name == 'Alice'
    assert distance < 0.01  # identical embeddings → ~0 distance


def test_match_picks_closest_among_mixed_people_and_shared():
    """Test that matching picks the closest embedding from both regular and shared profiles."""
    alice_emb = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    bob_emb = np.array([[0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    query = np.array([[0.95, 0.05, 0.0, 0.0]], dtype=np.float32)  # close to Alice

    cache = {
        'shared:alice_uid': {'embedding': alice_emb, 'name': 'Alice'},
        'person-bob': {'embedding': bob_emb, 'name': 'Bob'},
    }

    person_id, name, _ = _find_best_match(query, cache)
    assert person_id == 'shared:alice_uid'
    assert name == 'Alice'


def test_match_returns_none_when_above_threshold():
    """Test that no match is returned when all distances exceed the threshold."""
    alice_emb = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    query = np.array([[0.0, 0.0, 0.0, 1.0]], dtype=np.float32)  # orthogonal → distance ~1.0

    cache = {
        'shared:alice_uid': {'embedding': alice_emb, 'name': 'Alice'},
    }

    person_id, name, distance = _find_best_match(query, cache, threshold=0.45)
    assert person_id is None
    assert name is None
    assert distance > 0.45


def test_match_empty_cache_returns_none():
    """Test that matching with an empty cache returns no match."""
    query = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    person_id, name, _ = _find_best_match(query, {})
    assert person_id is None
    assert name is None


def test_fetch_user_names_returns_display_names():
    """Test that _fetch_user_names fetches names from Firebase Auth via get_user_name."""
    with patch('database.users.get_user_name') as mock_get_name:
        mock_get_name.side_effect = lambda uid, use_default=True: {
            'uid1': 'Alice',
            'uid2': 'Bob',
        }.get(uid, '')

        result = users_db._fetch_user_names(['uid1', 'uid2'])

        assert result == {'uid1': 'Alice', 'uid2': 'Bob'}
        assert mock_get_name.call_count == 2


def test_fetch_user_names_handles_missing_names():
    """Test that _fetch_user_names returns empty string for users without display names."""
    with patch('database.users.get_user_name') as mock_get_name:
        mock_get_name.return_value = None

        result = users_db._fetch_user_names(['uid1'])

        assert result == {'uid1': ''}


def test_fetch_user_names_empty_list():
    """Test that _fetch_user_names handles empty UID list."""
    with patch('database.users.get_user_name') as mock_get_name:
        result = users_db._fetch_user_names([])

        assert result == {}
        mock_get_name.assert_not_called()


def test_get_profiles_shared_with_user_details_returns_uid_and_name():
    """Test that details endpoint returns {uid, name} dicts."""
    with patch('database.users.get_profiles_shared_with_user') as mock_shared, patch(
        'database.users.get_user_name'
    ) as mock_get_name:
        mock_shared.return_value = ['owner1', 'owner2']
        mock_get_name.side_effect = lambda uid, use_default=True: {
            'owner1': 'Alice',
            'owner2': 'Bob',
        }.get(uid, '')

        result = users_db.get_profiles_shared_with_user_details('target_uid')

        assert len(result) == 2
        assert result[0] == {'uid': 'owner1', 'name': 'Alice'}
        assert result[1] == {'uid': 'owner2', 'name': 'Bob'}


def test_get_profiles_shared_with_user_details_empty():
    """Test that details endpoint returns empty list when no profiles shared."""
    with patch('database.users.get_profiles_shared_with_user') as mock_shared:
        mock_shared.return_value = []
        result = users_db.get_profiles_shared_with_user_details('target_uid')
        assert result == []


def test_get_users_shared_with_details_returns_uid_and_name():
    """Test that owner's shared list returns {uid, name} dicts."""
    with patch('database.users.get_users_shared_with') as mock_shared, patch(
        'database.users.get_user_name'
    ) as mock_get_name:
        mock_shared.return_value = ['target1', 'target2']
        mock_get_name.side_effect = lambda uid, use_default=True: {
            'target1': 'Charlie',
            'target2': 'Diana',
        }.get(uid, '')

        result = users_db.get_users_shared_with_details('owner_uid')

        assert len(result) == 2
        assert result[0] == {'uid': 'target1', 'name': 'Charlie'}
        assert result[1] == {'uid': 'target2', 'name': 'Diana'}


def test_remove_shared_profile_from_me():
    """Test that receiver can remove a shared profile."""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    shared_ref.get.return_value = _FakeSnapshot({'shared_with_uid': 'target', 'revoked_at': None}, exists=True)
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.remove_shared_profile_from_me('owner_uid', 'target_uid')

        assert result is True
        shared_ref.update.assert_called_once()
        call_args = shared_ref.update.call_args[0][0]
        assert 'revoked_at' in call_args


def test_remove_shared_profile_from_me_already_revoked():
    """Test that removing an already-revoked profile returns False."""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    shared_ref.get.return_value = _FakeSnapshot(
        {'shared_with_uid': 'target', 'revoked_at': datetime.now(timezone.utc)}, exists=True
    )
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.remove_shared_profile_from_me('owner_uid', 'target_uid')

        assert result is False


def test_remove_shared_profile_from_me_not_exists():
    """Test that removing a non-existent share returns False."""
    mock_db = MagicMock()
    shared_ref = MagicMock()
    shared_ref.get.return_value = _FakeSnapshot({}, exists=False)
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db):
        result = users_db.remove_shared_profile_from_me('owner_uid', 'target_uid')

        assert result is False


def test_full_pipeline_shared_profile_speaker_identification(monkeypatch):
    """
    End-to-end test: User A shares speech profile → User B starts conversation →
    User A speaks → identified by name automatically.

    Covers the full pipeline:
    1. extract_embedding_from_bytes (audio → embedding via mocked API)
    2. set_user_speaker_embedding (store on user doc)
    3. share_speech_profile (create share record in Firestore)
    4. get_profiles_shared_with_user (load shared UIDs)
    5. get_user_profile (load sharer's embedding)
    6. Cache building (shared embedding loaded into person_embeddings_cache)
    7. extract_embedding_from_bytes (live audio from conversation → query embedding)
    8. compare_embeddings (cosine distance between query and cached)
    9. Threshold check (SPEAKER_MATCH_THRESHOLD = 0.45)
    10. update_speaker_assignment_maps (label segment with shared:{uid})
    11. process_speaker_assigned_segments (assign person_id to transcript segment)
    """
    import io
    import wave
    import requests as req_module
    from utils.stt.speaker_embedding import (
        extract_embedding_from_bytes,
        compare_embeddings,
        SPEAKER_MATCH_THRESHOLD,
    )
    from utils.speaker_assignment import update_speaker_assignment_maps, process_speaker_assigned_segments
    from models.transcript_segment import TranscriptSegment

    # --- Simulate User A's voice embedding (512-dim, like real API) ---
    alice_embedding_raw = list(np.random.RandomState(42).randn(512).astype(np.float32))

    # Mock the embedding extraction API to return Alice's embedding
    monkeypatch.setenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "http://fake:1234")
    mock_response = MagicMock()
    mock_response.json.return_value = alice_embedding_raw
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(req_module, "post", MagicMock(return_value=mock_response))

    # Generate a 1-second WAV (passes duration check)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b'\x00\x00' * 16000)
    wav_bytes = buf.getvalue()

    # --- STEP 1: User A records speech profile → embedding extracted ---
    alice_embedding = extract_embedding_from_bytes(wav_bytes, "alice_profile.wav")
    assert alice_embedding.shape == (1, 512)

    # --- STEP 2: Store embedding on User A's document ---
    mock_db = MagicMock()
    user_ref = MagicMock()
    mock_db.collection.return_value.document.return_value = user_ref

    with patch('database.users.db', mock_db):
        users_db.set_user_speaker_embedding("alice_uid", alice_embedding_raw)
        user_ref.update.assert_called_once()
        stored = user_ref.update.call_args[0][0]
        assert stored['speaker_embedding'] == alice_embedding_raw

    # --- STEP 3: User A shares profile with User B ---
    mock_db2 = MagicMock()
    shared_ref = MagicMock()
    mock_db2.collection.return_value.document.return_value.collection.return_value.document.return_value = shared_ref

    with patch('database.users.db', mock_db2):
        result = users_db.share_speech_profile("alice_uid", "bob_uid")
        assert result is True
        call_args = shared_ref.set.call_args[0][0]
        assert call_args['shared_with_uid'] == 'bob_uid'

    # --- STEP 4: User B starts /listen session → backend loads shared profiles ---
    alice_profile = {
        'display_name': 'Alice Smith',
        'speaker_embedding': alice_embedding_raw,
    }

    person_embeddings_cache = _build_embedding_cache(
        people=[],
        shared_owners=['alice_uid'],
        get_user_profile_fn=lambda uid: alice_profile if uid == 'alice_uid' else {},
    )

    assert 'shared:alice_uid' in person_embeddings_cache
    assert person_embeddings_cache['shared:alice_uid']['name'] == 'Alice Smith'
    assert person_embeddings_cache['shared:alice_uid']['embedding'].shape == (1, 512)

    # --- STEP 5: Alice speaks in the conversation → embedding extracted from live audio ---
    query_embedding = alice_embedding.copy()

    # --- STEP 6: Cosine similarity matching ---
    distance = compare_embeddings(query_embedding, person_embeddings_cache['shared:alice_uid']['embedding'])
    assert distance < 0.01  # Same embedding → near-zero distance
    assert distance < SPEAKER_MATCH_THRESHOLD  # Below threshold → match!

    # Find best match (same logic as transcribe.py _match_speaker_embedding)
    person_id, person_name, best_distance = _find_best_match(
        query_embedding, person_embeddings_cache, threshold=SPEAKER_MATCH_THRESHOLD
    )
    assert person_id == 'shared:alice_uid'
    assert person_name == 'Alice Smith'
    assert best_distance < SPEAKER_MATCH_THRESHOLD

    # --- STEP 7: Speaker assignment → segment labeled with Alice's name ---
    speaker_to_person_map = {}
    segment_person_assignment_map = {}

    update_speaker_assignment_maps(
        speaker_id=1,
        person_id=person_id,
        person_name=person_name,
        segment_ids=["seg-001", "seg-002"],
        speaker_to_person_map=speaker_to_person_map,
        segment_person_assignment_map=segment_person_assignment_map,
    )

    assert speaker_to_person_map[1] == ('shared:alice_uid', 'Alice Smith')
    assert segment_person_assignment_map['seg-001'] == 'shared:alice_uid'
    assert segment_person_assignment_map['seg-002'] == 'shared:alice_uid'

    # --- STEP 8: Transcript segments get the person_id ---
    segment = TranscriptSegment(
        id="seg-001",
        text="Hey Bob, how are you?",
        speaker="SPEAKER_01",
        is_user=False,
        person_id=None,
        start=0.0,
        end=2.5,
    )

    process_speaker_assigned_segments(
        [segment],
        segment_person_assignment_map,
        speaker_to_person_map,
    )

    assert segment.person_id == 'shared:alice_uid'
    assert segment.is_user is False  # Shared profile != device owner

    # --- STEP 9: Verify revoke removes from future sessions ---
    mock_db3 = MagicMock()
    revoke_ref = MagicMock()
    revoke_ref.get.return_value.exists = True
    mock_db3.collection.return_value.document.return_value.collection.return_value.document.return_value = revoke_ref

    with patch('database.users.db', mock_db3):
        revoked = users_db.revoke_speech_profile_share("alice_uid", "bob_uid")
        assert revoked is True

    # After revoke, cache would not load Alice's profile
    cache_after_revoke = _build_embedding_cache(
        people=[],
        shared_owners=[],  # revoked → empty list
        get_user_profile_fn=lambda uid: alice_profile,
    )
    assert 'shared:alice_uid' not in cache_after_revoke
    assert len(cache_after_revoke) == 0


def test_full_pipeline_no_match_different_speaker(monkeypatch):
    """
    End-to-end: User A shares profile → User C speaks in User B's conversation →
    User C is NOT identified as Alice (different voice, above threshold).
    """
    from utils.stt.speaker_embedding import compare_embeddings, SPEAKER_MATCH_THRESHOLD

    # Alice's stored embedding
    alice_emb = np.random.RandomState(42).randn(512).astype(np.float32)
    alice_profile = {
        'display_name': 'Alice Smith',
        'speaker_embedding': alice_emb.tolist(),
    }

    # Load Alice into cache
    cache = _build_embedding_cache(
        people=[],
        shared_owners=['alice_uid'],
        get_user_profile_fn=lambda uid: alice_profile,
    )

    # User C speaks → completely different embedding
    charlie_emb = np.random.RandomState(99).randn(512).astype(np.float32)
    query = charlie_emb.reshape(1, -1)

    # Should NOT match Alice
    distance = compare_embeddings(query, cache['shared:alice_uid']['embedding'])
    assert distance > SPEAKER_MATCH_THRESHOLD  # Different person → high distance

    person_id, person_name, _ = _find_best_match(query, cache, threshold=SPEAKER_MATCH_THRESHOLD)
    assert person_id is None
    assert person_name is None


def test_full_pipeline_picks_correct_person_from_multiple(monkeypatch):
    """
    End-to-end: Multiple shared profiles + regular people in cache.
    Query matches the correct person among all candidates.
    """
    from utils.stt.speaker_embedding import SPEAKER_MATCH_THRESHOLD

    # Create 3 distinct embeddings
    rng = np.random.RandomState(123)
    alice_emb = rng.randn(512).astype(np.float32)
    bob_emb = rng.randn(512).astype(np.float32)
    charlie_emb = rng.randn(512).astype(np.float32)

    def mock_profile(uid):
        profiles = {
            'alice_uid': {'display_name': 'Alice', 'speaker_embedding': alice_emb.tolist()},
            'charlie_uid': {'display_name': 'Charlie', 'speaker_embedding': charlie_emb.tolist()},
        }
        return profiles.get(uid, {})

    # Bob is a regular "person" (manually named), Alice & Charlie are shared
    cache = _build_embedding_cache(
        people=[{'id': 'person-bob', 'name': 'Bob', 'speaker_embedding': bob_emb.tolist()}],
        shared_owners=['alice_uid', 'charlie_uid'],
        get_user_profile_fn=mock_profile,
    )

    assert len(cache) == 3  # Bob + Alice + Charlie

    # Query with Bob's exact embedding → should match Bob
    query_bob = bob_emb.reshape(1, -1)
    pid, name, dist = _find_best_match(query_bob, cache, threshold=SPEAKER_MATCH_THRESHOLD)
    assert pid == 'person-bob'
    assert name == 'Bob'

    # Query with Alice's exact embedding → should match Alice (shared)
    query_alice = alice_emb.reshape(1, -1)
    pid, name, dist = _find_best_match(query_alice, cache, threshold=SPEAKER_MATCH_THRESHOLD)
    assert pid == 'shared:alice_uid'
    assert name == 'Alice'

    # Query with Charlie's exact embedding → should match Charlie (shared)
    query_charlie = charlie_emb.reshape(1, -1)
    pid, name, dist = _find_best_match(query_charlie, cache, threshold=SPEAKER_MATCH_THRESHOLD)
    assert pid == 'shared:charlie_uid'
    assert name == 'Charlie'

def test_spoofed_shared_pid_rejected_by_ownership_check():
    """Spoofed shared:{attacker_uid} is rejected because attacker hasn't shared with current user."""
    from utils.shared_profiles import resolve_shared_people

    with patch('utils.shared_profiles.users_db') as mock_users:
        mock_users.get_profiles_shared_with_user.return_value = ['alice_uid']
        mock_users.get_user_profile.return_value = {'display_name': 'Alice'}

        people = resolve_shared_people(['shared:alice_uid', 'shared:attacker_uid'], 'bob_uid')

    resolved_ids = [p.id for p in people]
    assert 'shared:alice_uid' in resolved_ids
    assert 'shared:attacker_uid' not in resolved_ids
    assert len(people) == 1
    assert people[0].name == 'Alice'


def test_all_valid_shared_pids_resolved():
    """All legitimate shared profiles are resolved with correct names."""
    from utils.shared_profiles import resolve_shared_people

    def mock_profile(uid):
        return {
            'alice_uid': {'display_name': 'Alice Smith'},
            'charlie_uid': {'display_name': 'Charlie Brown'},
        }.get(uid, {})

    with patch('utils.shared_profiles.users_db') as mock_users:
        mock_users.get_profiles_shared_with_user.return_value = ['alice_uid', 'charlie_uid']
        mock_users.get_user_profile.side_effect = mock_profile

        people = resolve_shared_people(['shared:alice_uid', 'shared:charlie_uid'], 'bob_uid')

    assert len(people) == 2
    names = {p.name for p in people}
    assert names == {'Alice Smith', 'Charlie Brown'}


def test_shared_pid_with_missing_profile_skipped():
    """Shared ID where get_user_profile returns empty is silently skipped."""
    from utils.shared_profiles import resolve_shared_people

    with patch('utils.shared_profiles.users_db') as mock_users:
        mock_users.get_profiles_shared_with_user.return_value = ['ghost_uid']
        mock_users.get_user_profile.return_value = {}

        people = resolve_shared_people(['shared:ghost_uid'], 'bob_uid')

    assert len(people) == 0


def test_non_shared_person_ids_ignored():
    """Regular person IDs and 'user' are not processed by resolve_shared_people."""
    from utils.shared_profiles import resolve_shared_people

    with patch('utils.shared_profiles.users_db') as mock_users:
        people = resolve_shared_people(['person-bob', 'user', 'regular-id'], 'bob_uid')

    assert len(people) == 0
    mock_users.get_profiles_shared_with_user.assert_not_called()
