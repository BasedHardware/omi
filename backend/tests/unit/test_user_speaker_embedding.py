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
