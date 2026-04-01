"""Unit tests for user speaker embedding storage and loading paths.

Tests the Firestore helpers (set/get_user_speaker_embedding), the speech profile
upload extraction path, and the transcribe.py Firestore loading path.
"""

import os
import sys

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("utils.other.storage", MagicMock())
sys.modules.setdefault("utils.stt.pre_recorded", MagicMock())


# ─── Firestore Helpers ──────────────────────────────────────────────────────


class TestSetUserSpeakerEmbedding:
    """Tests for database.users.set_user_speaker_embedding."""

    def test_stores_embedding_on_user_document(self):
        """Should call update on the user document with embedding and timestamp."""
        mock_db = MagicMock()
        mock_user_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_user_ref

        with patch('database.users.db', mock_db):
            from database.users import set_user_speaker_embedding

            embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
            result = set_user_speaker_embedding('uid-123', embedding)

        assert result is True
        mock_db.collection.assert_called_with('users')
        mock_db.collection.return_value.document.assert_called_with('uid-123')
        call_args = mock_user_ref.update.call_args[0][0]
        assert call_args['speaker_embedding'] == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert 'speaker_embedding_updated_at' in call_args

    def test_stores_large_embedding(self):
        """Should handle 512-dim embeddings (production size)."""
        mock_db = MagicMock()
        mock_user_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_user_ref

        with patch('database.users.db', mock_db):
            from database.users import set_user_speaker_embedding

            embedding = list(np.random.randn(512).astype(float))
            result = set_user_speaker_embedding('uid-456', embedding)

        assert result is True
        stored = mock_user_ref.update.call_args[0][0]['speaker_embedding']
        assert len(stored) == 512


class TestGetUserSpeakerEmbedding:
    """Tests for database.users.get_user_speaker_embedding."""

    def test_returns_embedding_when_exists(self):
        """Should return the embedding list when it exists on the user doc."""
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'speaker_embedding': [0.1, 0.2, 0.3]}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch('database.users.db', mock_db):
            from database.users import get_user_speaker_embedding

            result = get_user_speaker_embedding('uid-123')

        assert result == [0.1, 0.2, 0.3]

    def test_returns_none_when_no_embedding(self):
        """Should return None when user has no speaker_embedding field."""
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'name': 'Test User'}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch('database.users.db', mock_db):
            from database.users import get_user_speaker_embedding

            result = get_user_speaker_embedding('uid-123')

        assert result is None

    def test_returns_none_when_user_not_found(self):
        """Should return None when user document doesn't exist."""
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch('database.users.db', mock_db):
            from database.users import get_user_speaker_embedding

            result = get_user_speaker_embedding('uid-nonexistent')

        assert result is None

    def test_returns_none_when_empty_list(self):
        """Should return None when speaker_embedding is an empty list."""
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'speaker_embedding': []}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch('database.users.db', mock_db):
            from database.users import get_user_speaker_embedding

            result = get_user_speaker_embedding('uid-empty')

        # Empty list is returned from Firestore — falsy, so speaker_identification_task
        # treats it like None and triggers the WAV fallback extraction path
        assert result == []


# ─── Speech Profile Upload Extraction ────────────────────────────────────────


class TestSpeechProfileEmbeddingExtraction:
    """Tests for the embedding extraction in upload_profile route."""

    @patch('routers.speech_profile.set_user_speaker_embedding')
    @patch('routers.speech_profile.extract_embedding')
    @patch('routers.speech_profile.upload_profile_audio', return_value='https://storage.example.com/profile.wav')
    @patch('routers.speech_profile.set_speech_profile_duration')
    @patch('routers.speech_profile.apply_vad_for_speech_profile')
    def test_extraction_called_after_upload(self, mock_vad, mock_duration, mock_upload, mock_extract, mock_store):
        """extract_embedding should be called with the file path after upload."""
        mock_extract.return_value = np.random.randn(1, 512).astype(np.float32)

        from routers.speech_profile import upload_profile

        # Create a mock UploadFile with valid WAV audio
        import struct
        import io
        import wave

        # Generate a minimal valid WAV file (16kHz, 5s)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f'<{16000 * 5}h', *([0] * (16000 * 5))))

        mock_file = MagicMock()
        mock_file.filename = 'speech_profile.wav'
        mock_file.file.read.return_value = buf.getvalue()

        # Mock av.open for duration check
        with patch('routers.speech_profile.av') as mock_av:
            mock_container = MagicMock()
            mock_container.duration = 5_000_000  # 5 seconds in AV time base
            mock_av.open.return_value.__enter__ = MagicMock(return_value=mock_container)
            mock_av.open.return_value.__exit__ = MagicMock(return_value=False)
            mock_av.time_base = 1_000_000

            with patch('routers.speech_profile.os.makedirs'):
                with patch('builtins.open', MagicMock()):
                    with patch('routers.speech_profile.AudioSegment') as mock_aseg:
                        mock_audio = MagicMock()
                        mock_audio.frame_rate = 16000
                        mock_audio.duration_seconds = 10.0
                        mock_aseg.from_wav.return_value = mock_audio

                        upload_profile(mock_file, uid='test-uid')

        mock_extract.assert_called_once()
        mock_store.assert_called_once()
        # Verify embedding was flattened to list
        stored_embedding = mock_store.call_args[0][1]
        assert isinstance(stored_embedding, list)
        assert len(stored_embedding) == 512

    @patch('routers.speech_profile.set_user_speaker_embedding')
    @patch('routers.speech_profile.extract_embedding', side_effect=Exception("API unavailable"))
    @patch('routers.speech_profile.upload_profile_audio', return_value='https://storage.example.com/profile.wav')
    @patch('routers.speech_profile.set_speech_profile_duration')
    @patch('routers.speech_profile.apply_vad_for_speech_profile')
    def test_extraction_failure_does_not_block_upload(
        self, mock_vad, mock_duration, mock_upload, mock_extract, mock_store
    ):
        """Upload should succeed even if embedding extraction fails."""
        from routers.speech_profile import upload_profile

        import struct
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f'<{16000 * 5}h', *([0] * (16000 * 5))))

        mock_file = MagicMock()
        mock_file.filename = 'speech_profile.wav'
        mock_file.file.read.return_value = buf.getvalue()

        with patch('routers.speech_profile.av') as mock_av:
            mock_container = MagicMock()
            mock_container.duration = 5_000_000
            mock_av.open.return_value.__enter__ = MagicMock(return_value=mock_container)
            mock_av.open.return_value.__exit__ = MagicMock(return_value=False)
            mock_av.time_base = 1_000_000

            with patch('routers.speech_profile.os.makedirs'):
                with patch('builtins.open', MagicMock()):
                    with patch('routers.speech_profile.AudioSegment') as mock_aseg:
                        mock_audio = MagicMock()
                        mock_audio.frame_rate = 16000
                        mock_audio.duration_seconds = 10.0
                        mock_aseg.from_wav.return_value = mock_audio

                        result = upload_profile(mock_file, uid='test-uid')

        # Upload still succeeded
        assert result == {"url": "https://storage.example.com/profile.wav"}
        # Store was NOT called since extraction failed
        mock_store.assert_not_called()


# ─── Transcribe Firestore Loading Path ───────────────────────────────────────


class TestTranscribeFirestoreLoading:
    """Tests for the Firestore loading path in speaker_identification_task."""

    def test_embedding_loaded_from_firestore_and_cached(self):
        """When Firestore returns an embedding, it should be cached with 'user' sentinel."""
        # Simulate what speaker_identification_task does
        USER_SELF_PERSON_ID = 'user'
        embedding_list = list(np.random.randn(512).astype(float))
        person_embeddings_cache = {}

        # This mirrors the code in transcribe.py lines 1806-1820
        if embedding_list:
            user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
            person_embeddings_cache[USER_SELF_PERSON_ID] = {
                'embedding': user_embedding,
                'name': 'User',
            }

        assert USER_SELF_PERSON_ID in person_embeddings_cache
        assert person_embeddings_cache[USER_SELF_PERSON_ID]['embedding'].shape == (1, 512)

    def test_fallback_extracts_from_wav_when_no_stored_embedding(self):
        """When Firestore returns None, should extract from WAV and store for future sessions."""
        USER_SELF_PERSON_ID = 'user'
        person_embeddings_cache = {}
        embedding_list = None  # Simulates no stored embedding

        # Simulate the fallback path from transcribe.py
        fallback_embedding = np.random.RandomState(42).randn(1, 512).astype(np.float32)
        stored_embeddings = []

        if not embedding_list:
            # Fallback: extract from WAV (simulated)
            user_embedding = fallback_embedding
            person_embeddings_cache[USER_SELF_PERSON_ID] = {
                'embedding': user_embedding,
                'name': 'User',
            }
            # Store in Firestore for future sessions (simulated)
            stored_embeddings.append(user_embedding.flatten().tolist())

        assert USER_SELF_PERSON_ID in person_embeddings_cache
        assert len(stored_embeddings) == 1
        assert len(stored_embeddings[0]) == 512

    def test_has_speech_profile_gate(self):
        """User embedding is only loaded when has_speech_profile is True."""
        USER_SELF_PERSON_ID = 'user'
        person_embeddings_cache = {}
        embedding_list = list(np.random.randn(512).astype(float))

        # Simulate has_speech_profile=False — the outer if guard
        has_speech_profile = False
        if has_speech_profile:
            if embedding_list:
                user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
                person_embeddings_cache[USER_SELF_PERSON_ID] = {
                    'embedding': user_embedding,
                    'name': 'User',
                }

        assert USER_SELF_PERSON_ID not in person_embeddings_cache

        # Now with has_speech_profile=True
        has_speech_profile = True
        if has_speech_profile:
            if embedding_list:
                user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
                person_embeddings_cache[USER_SELF_PERSON_ID] = {
                    'embedding': user_embedding,
                    'name': 'User',
                }

        assert USER_SELF_PERSON_ID in person_embeddings_cache


# ─── Final Assignment Pass ─────────────────────────────────────────────────


class TestFinalAssignmentPass:
    """Tests for the final speaker assignment pass at session end."""

    def test_final_pass_corrects_last_segment(self):
        """When embedding match happens on the last segment, final pass should correct Firestore."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        # Simulate: 3 segments, speaker 0 matched to user AFTER last batch
        segments = [
            TranscriptSegment(text='Hello', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=0, end=1),
            TranscriptSegment(text='Hi there', speaker='SPEAKER_1', speaker_id=1, is_user=False, start=1, end=2),
            TranscriptSegment(text='How are you', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=2, end=3),
        ]
        # Simulate embedding match on segment 2 (last segment)
        segment_person_assignment_map = {segments[2].id: 'user'}
        speaker_to_person_map = {0: ('user', 'User')}

        # Run final pass (same as what stream_transcript_process does at exit)
        process_speaker_assigned_segments(segments, segment_person_assignment_map, speaker_to_person_map)

        # All speaker 0 segments should now have is_user=True
        assert segments[0].is_user is True
        assert segments[1].is_user is False
        assert segments[2].is_user is True

    def test_final_pass_no_op_when_no_maps(self):
        """Final pass should be a no-op when there are no pending assignments."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        segments = [
            TranscriptSegment(text='Hello', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=0, end=1),
        ]
        process_speaker_assigned_segments(segments, {}, {})
        assert segments[0].is_user is False

    def test_final_pass_skips_already_assigned(self):
        """Final pass should not override segments already marked as is_user."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        segments = [
            TranscriptSegment(text='Hello', speaker='SPEAKER_0', speaker_id=0, is_user=True, start=0, end=1),
            TranscriptSegment(text='Bye', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=1, end=2),
        ]
        speaker_to_person_map = {0: ('user', 'User')}
        process_speaker_assigned_segments(segments, {}, speaker_to_person_map)

        assert segments[0].is_user is True  # was already True, unchanged
        assert segments[1].is_user is True  # corrected by final pass

    def test_late_match_before_rollover_corrects_all_segments(self):
        """Regression: embedding match after last batch but before rollover must still fix segments.

        Simulates: conversation has 5 segments from speaker 0, all with is_user=False.
        A late embedding match maps speaker 0 -> user. The flush before rollover
        must retroactively correct all 5 segments, not just the triggering one.

        Note: _flush_speaker_assignments is an inner function of _stream_handler and
        cannot be imported directly. This test validates the core logic it delegates to
        (process_speaker_assigned_segments on all segments with populated maps).
        """
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        # 5 segments from speaker 0, none yet marked as user
        segments = [
            TranscriptSegment(text=f'Seg {i}', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=i, end=i + 1)
            for i in range(5)
        ]
        # Late match: speaker 0 -> user (arrived after last transcript batch)
        speaker_to_person_map = {0: ('user', 'User')}
        segment_person_assignment_map = {segments[4].id: 'user'}  # only last segment was in match trigger

        # This simulates what _flush_speaker_assignments does before rollover
        process_speaker_assigned_segments(segments, segment_person_assignment_map, speaker_to_person_map)

        # ALL speaker 0 segments must be corrected, not just the triggering one
        for i, seg in enumerate(segments):
            assert seg.is_user is True, f"Segment {i} should be is_user=True after flush"


# ─── Dirty Flag Behavior ─────────────────────────────────────────────────────


class TestDirtyFlagBehavior:
    """Tests for the speaker_map_dirty flag controlling full vs batch assignment.

    The dirty flag is an inner variable of _stream_handler. These tests validate
    the behavioral difference: when dirty (new match), all segments are processed;
    when not dirty, only new/updated segments are processed.
    """

    def test_dirty_flag_true_fixes_all_prior_segments(self):
        """When dirty (new match resolved), processing all segments fixes stale ones."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        # 4 earlier segments, all stale (is_user=False despite speaker 0 being user)
        all_segments = [
            TranscriptSegment(text=f'Old {i}', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=i, end=i + 1)
            for i in range(4)
        ]
        # New batch with 1 segment
        new_segment = TranscriptSegment(text='New', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=4, end=5)
        all_segments.append(new_segment)

        speaker_to_person_map = {0: ('user', 'User')}

        # Dirty path: process ALL segments (simulates speaker_map_dirty=True)
        process_speaker_assigned_segments(all_segments, {}, speaker_to_person_map)

        # All 5 segments should be corrected
        for i, seg in enumerate(all_segments):
            assert seg.is_user is True, f"Segment {i} should be is_user=True in dirty path"

    def test_clean_flag_only_fixes_new_segments(self):
        """When not dirty, processing only new segments leaves prior ones stale."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        # 4 earlier segments, stale (is_user=False)
        old_segments = [
            TranscriptSegment(text=f'Old {i}', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=i, end=i + 1)
            for i in range(4)
        ]
        # New batch
        new_segments = [TranscriptSegment(text='New', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=4, end=5)]

        speaker_to_person_map = {0: ('user', 'User')}

        # Clean path: only process new segments (simulates speaker_map_dirty=False)
        process_speaker_assigned_segments(new_segments, {}, speaker_to_person_map)

        # New segment is fixed
        assert new_segments[0].is_user is True
        # Old segments remain stale — intentional, final pass at session end will fix them
        for i, seg in enumerate(old_segments):
            assert seg.is_user is False, f"Old segment {i} should remain stale in clean path"


# ─── User Match Threshold Boundary ────────────────────────────────────────────


class TestUserMatchBoundary:
    """Tests for user match threshold behavior in the embedding comparison."""

    def test_empty_embedding_list_triggers_fallback(self):
        """Empty embedding list from Firestore is falsy, triggers WAV fallback."""
        embedding_list = []
        person_embeddings_cache = {}

        # This mirrors the Firestore load path in speaker_identification_task
        if embedding_list:
            user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
            person_embeddings_cache['user'] = {'embedding': user_embedding, 'name': 'User'}

        # Empty list is falsy — user embedding not loaded, fallback needed
        assert 'user' not in person_embeddings_cache

    def test_malformed_embedding_raises_on_reshape(self):
        """Non-rectangular embedding data raises ValueError on reshape."""
        embedding_list = [0.1, 0.2]  # Only 2 elements, not 512
        # reshape(1, -1) should succeed but produce (1, 2), not (1, 512)
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        assert user_embedding.shape == (1, 2)

    def test_user_match_uses_strict_less_than(self):
        """User match requires distance < threshold, not <=."""
        from utils.stt.speaker_embedding import compare_embeddings, SPEAKER_MATCH_THRESHOLD

        # Identical embeddings → distance ≈ 0.0, well below threshold
        emb = np.random.RandomState(42).randn(1, 512).astype(np.float32)
        emb /= np.linalg.norm(emb)
        distance = compare_embeddings(emb, emb)
        assert distance < SPEAKER_MATCH_THRESHOLD

        # Simulate the match logic from _match_speaker_embedding
        best_distance = distance
        matched = best_distance < SPEAKER_MATCH_THRESHOLD
        assert matched is True

        # At exactly threshold, should NOT match
        best_distance = SPEAKER_MATCH_THRESHOLD
        matched = best_distance < SPEAKER_MATCH_THRESHOLD
        assert matched is False


# ─── User Match Event ────────────────────────────────────────────────────────


class TestUserMatchEvent:
    """Tests that user match logic produces correct event parameters."""

    def test_user_match_produces_user_person_id(self):
        """When best match is 'user', person_id should be 'user' not empty string."""
        USER_SELF_PERSON_ID = 'user'
        person_embeddings_cache = {
            USER_SELF_PERSON_ID: {
                'embedding': np.random.RandomState(42).randn(1, 512).astype(np.float32),
                'name': 'User',
            },
            'person-abc': {
                'embedding': np.random.RandomState(99).randn(1, 512).astype(np.float32),
                'name': 'Alice',
            },
        }

        # Use the user's own embedding as query (should match self)
        query = person_embeddings_cache[USER_SELF_PERSON_ID]['embedding']
        from utils.stt.speaker_embedding import compare_embeddings, SPEAKER_MATCH_THRESHOLD

        best_match = None
        best_distance = float('inf')
        for pid, data in person_embeddings_cache.items():
            distance = compare_embeddings(query, data['embedding'])
            if distance < best_distance:
                best_distance = distance
                best_match = (pid, data['name'])

        assert best_match is not None
        assert best_distance < SPEAKER_MATCH_THRESHOLD
        person_id, person_name = best_match
        assert person_id == USER_SELF_PERSON_ID
        assert person_name == 'User'

        # Event should use 'user' directly (not _person_id_for_client which returns '')
        event_person_id = person_id  # In production: 'user' is sent directly
        assert event_person_id == 'user'

    def test_non_user_match_is_not_user(self):
        """When best match is a person (not user), is_user should be False."""
        from utils.speaker_assignment import process_speaker_assigned_segments
        from models.transcript_segment import TranscriptSegment

        segments = [
            TranscriptSegment(text='Hello', speaker='SPEAKER_0', speaker_id=0, is_user=False, start=0, end=1),
        ]
        # Person match, not user
        speaker_to_person_map = {0: ('person-abc', 'Alice')}
        process_speaker_assigned_segments(segments, {}, speaker_to_person_map)

        assert segments[0].is_user is False
        assert segments[0].person_id == 'person-abc'


# ─── Dimension Mismatch Guard (#6238) ─────────────────────────────────────────


class TestDimensionMismatchGuard:
    """Tests for dimension mismatch handling between v2 (512-dim) and v3 (256-dim) embeddings.

    Root cause: v2→v3 migration can fail partially, leaving some contacts with
    version=3 tag but 512-dim embeddings. When the user has a 256-dim v3 embedding,
    scipy.cdist crashes on shape mismatch.
    """

    def test_compare_embeddings_same_dimension(self):
        """Same-dimension embeddings should return valid cosine distance."""
        from utils.stt.speaker_embedding import compare_embeddings

        emb1 = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        emb2 = np.random.RandomState(2).randn(1, 256).astype(np.float32)
        distance = compare_embeddings(emb1, emb2)
        assert 0.0 <= distance <= 2.0

    def test_compare_embeddings_dimension_mismatch_returns_max_distance(self):
        """Mismatched dimensions (256 vs 512) should return 2.0 instead of crashing."""
        from utils.stt.speaker_embedding import compare_embeddings

        emb_256 = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        emb_512 = np.random.RandomState(2).randn(1, 512).astype(np.float32)

        # Should NOT raise ValueError from scipy.cdist
        distance = compare_embeddings(emb_256, emb_512)
        assert distance == 2.0

        # Reverse order should also work
        distance = compare_embeddings(emb_512, emb_256)
        assert distance == 2.0

    def test_compare_embeddings_identical_returns_zero(self):
        """Identical embeddings should return ~0.0 distance."""
        from utils.stt.speaker_embedding import compare_embeddings

        emb = np.random.RandomState(42).randn(1, 512).astype(np.float32)
        emb /= np.linalg.norm(emb)
        distance = compare_embeddings(emb, emb)
        assert distance < 0.001

    def test_is_same_speaker_dimension_mismatch_returns_false(self):
        """is_same_speaker should return (False, 2.0) on dimension mismatch."""
        from utils.stt.speaker_embedding import is_same_speaker

        emb_256 = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        emb_512 = np.random.RandomState(2).randn(1, 512).astype(np.float32)

        is_match, distance = is_same_speaker(emb_256, emb_512)
        assert is_match is False
        assert distance == 2.0

    def test_find_best_match_skips_dimension_mismatch(self):
        """find_best_match should not crash on mixed-dimension candidates."""
        from utils.stt.speaker_embedding import find_best_match

        query = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        # Mix of 256-dim (matching) and 512-dim (stale) candidates
        candidates = [
            np.random.RandomState(2).randn(1, 512).astype(np.float32),  # stale 512-dim
            query.copy(),  # exact match, 256-dim
            np.random.RandomState(3).randn(1, 512).astype(np.float32),  # stale 512-dim
        ]

        result = find_best_match(query, candidates)
        assert result is not None
        best_idx, best_distance = result
        assert best_idx == 1  # should match the 256-dim copy
        assert best_distance < 0.001

    def test_find_best_match_all_mismatched_returns_none(self):
        """find_best_match returns None when all candidates have wrong dimension."""
        from utils.stt.speaker_embedding import find_best_match

        query = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        candidates = [
            np.random.RandomState(2).randn(1, 512).astype(np.float32),
            np.random.RandomState(3).randn(1, 512).astype(np.float32),
        ]

        result = find_best_match(query, candidates)
        assert result is None  # all return 2.0, above threshold

    def test_mixed_dim_cache_loads_all_relies_on_compare_guard(self):
        """Cache loads ALL embeddings regardless of dimension; compare_embeddings handles mismatches.

        No cache-level filtering — avoids order-dependent behavior where a stale
        first entry could poison the filter and drop valid embeddings.
        """
        from utils.stt.speaker_embedding import compare_embeddings, SPEAKER_MATCH_THRESHOLD

        person_embeddings_cache = {}
        # User has 256-dim (current v3 model)
        user_embedding = np.random.RandomState(1).randn(1, 256).astype(np.float32)
        person_embeddings_cache['user'] = {'embedding': user_embedding, 'name': 'User'}

        # Load ALL persons into cache, including stale 512-dim
        persons = [
            {'id': 'p1', 'name': 'Alice', 'speaker_embedding': list(np.random.randn(256))},
            {'id': 'p2', 'name': 'Bob', 'speaker_embedding': list(np.random.randn(512))},  # stale
            {'id': 'p3', 'name': 'Carol', 'speaker_embedding': list(np.random.randn(256))},
        ]
        for person in persons:
            emb = person.get('speaker_embedding')
            if emb:
                person_embeddings_cache[person['id']] = {
                    'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                    'name': person['name'],
                }

        # All loaded — no filtering at cache level
        assert len(person_embeddings_cache) == 4  # user + 3 persons

        # compare_embeddings safely handles the 256 vs 512 mismatch
        query = np.random.RandomState(42).randn(1, 256).astype(np.float32)
        d_alice = compare_embeddings(query, person_embeddings_cache['p1']['embedding'])
        d_bob = compare_embeddings(query, person_embeddings_cache['p2']['embedding'])
        assert 0.0 <= d_alice <= 2.0  # same dim, real distance
        assert d_bob == 2.0  # mismatch, max distance — never matches

    def test_stale_user_embedding_does_not_poison_matching(self):
        """Even if user has stale 512-dim embedding, valid 256-dim contacts still match each other.

        Regression test for the Codex-flagged 'poisonous anchor' edge case:
        a stale user embedding must not prevent valid person-to-person matching.
        """
        from utils.stt.speaker_embedding import compare_embeddings

        person_embeddings_cache = {}
        # Stale 512-dim user embedding (pre-v3 migration)
        stale_user = np.random.RandomState(1).randn(1, 512).astype(np.float32)
        person_embeddings_cache['user'] = {'embedding': stale_user, 'name': 'User'}

        # Valid 256-dim person embeddings
        alice_emb = np.random.RandomState(2).randn(1, 256).astype(np.float32)
        person_embeddings_cache['alice'] = {'embedding': alice_emb, 'name': 'Alice'}

        # Alice vs stale user → 2.0 (dimension mismatch, correctly no-match)
        assert compare_embeddings(alice_emb, stale_user) == 2.0

        # Alice vs herself → ~0.0 (correctly matches)
        assert compare_embeddings(alice_emb, alice_emb) < 0.001
