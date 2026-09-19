"""User-initiated transcription reprocess: STT on stored audio, then enrichment.

``POST /v1/conversations/{id}/reprocess`` only regenerates the summary from the
existing transcript. This path must replace segments from stored audio and then
reuse ``process_conversation(..., is_reprocess=True)``. Soft-deleted tombstones
stay rejected; discarded conversations stay revivable.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import AppUsageAttribution
from utils.conversations.reprocess_transcription import (
    StoredAudioEmptyTranscriptError,
    StoredAudioTranscriptionFailedError,
    StoredAudioUnavailableError,
    collect_conversation_audio_timestamps,
    transcribe_stored_conversation_audio,
)


def _segment(text: str = 'hello from stored audio') -> TranscriptSegment:
    return TranscriptSegment(
        id='seg-new',
        text=text,
        speaker='SPEAKER_00',
        is_user=True,
        start=0.0,
        end=1.5,
    )


class TestCollectConversationAudioTimestamps:
    def test_uses_audio_file_chunk_timestamps(self):
        conversation = SimpleNamespace(
            id='c1',
            audio_files=[SimpleNamespace(chunk_timestamps=[2.0, 1.0, 1.0])],
        )
        assert collect_conversation_audio_timestamps('u1', conversation) == [1.0, 2.0]

    def test_falls_back_to_listed_chunks_when_audio_files_missing(self):
        conversation = SimpleNamespace(id='c1', audio_files=[])
        with patch(
            'utils.conversations.reprocess_transcription.list_audio_chunks',
            return_value=[{'timestamp': 4.0}, {'timestamp': 3.0}],
        ):
            assert collect_conversation_audio_timestamps('u1', conversation) == [3.0, 4.0]


class TestTranscribeStoredConversationAudio:
    def test_raises_when_no_timestamps(self):
        conversation = SimpleNamespace(id='c1', audio_files=[], language='en')
        with patch(
            'utils.conversations.reprocess_transcription.list_audio_chunks',
            return_value=[],
        ):
            with pytest.raises(StoredAudioUnavailableError):
                transcribe_stored_conversation_audio('u1', conversation, 'en')

    def test_raises_when_stt_returns_no_words(self):
        conversation = SimpleNamespace(
            id='c1',
            audio_files=[SimpleNamespace(chunk_timestamps=[1.0])],
            language='en',
        )
        with patch(
            'utils.conversations.reprocess_transcription.download_audio_chunks_and_merge',
            return_value=b'\x00\x01',
        ), patch(
            'utils.conversations.reprocess_transcription.get_user_transcription_preferences',
            return_value={'vocabulary': [], 'language': 'en', 'single_language_mode': True},
        ), patch(
            'utils.conversations.reprocess_transcription.prerecorded_from_bytes',
            return_value=[],
        ):
            with pytest.raises(StoredAudioEmptyTranscriptError):
                transcribe_stored_conversation_audio('u1', conversation, 'en')

    def test_returns_segments_on_success(self):
        conversation = SimpleNamespace(
            id='c1',
            audio_files=[SimpleNamespace(chunk_timestamps=[1.0])],
            language='en',
        )
        words = [{'timestamp': [0.0, 1.0], 'speaker': 'SPEAKER_00', 'text': 'hello'}]
        segments = [_segment()]
        with patch(
            'utils.conversations.reprocess_transcription.download_audio_chunks_and_merge',
            return_value=b'\x00\x01',
        ), patch(
            'utils.conversations.reprocess_transcription.get_user_transcription_preferences',
            return_value={'vocabulary': [], 'language': 'en', 'single_language_mode': True},
        ), patch(
            'utils.conversations.reprocess_transcription.prerecorded_from_bytes',
            return_value=words,
        ) as stt, patch(
            'utils.conversations.reprocess_transcription.postprocess_words',
            return_value=segments,
        ):
            result = transcribe_stored_conversation_audio('u1', conversation, 'en')
        assert result is segments
        assert stt.call_args.kwargs['encoding'] == 'linear16'
        assert stt.call_args.kwargs['language'] == 'en'


class TestReprocessTranscriptionRoute:
    def test_rejects_soft_deleted_conversation(self):
        deleted = {'id': 'c1', 'deleted': True, 'status': 'completed'}
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=deleted), patch.object(
            conv_router, 'transcribe_stored_conversation_audio'
        ) as transcribe, patch.object(conv_router, 'process_conversation') as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation_transcription(conversation_id='c1', uid='u1')
        assert exc.value.status_code == 404
        transcribe.assert_not_called()
        process.assert_not_called()

    def test_returns_400_when_no_stored_audio(self):
        raw = {'id': 'c1', 'status': 'completed'}
        model = SimpleNamespace(id='c1', language='en', transcript_segments=[])
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=raw), patch.object(
            conv_router.conversations_db, 'is_soft_deleted', return_value=False
        ), patch.object(conv_router, 'deserialize_conversation', return_value=model), patch.object(
            conv_router,
            'transcribe_stored_conversation_audio',
            side_effect=StoredAudioUnavailableError('No stored audio available to retranscribe'),
        ), patch.object(
            conv_router, 'process_conversation'
        ) as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation_transcription(conversation_id='c1', uid='u1')
        assert exc.value.status_code == 400
        assert exc.value.detail == 'No stored audio available to retranscribe'
        process.assert_not_called()

    def test_returns_400_when_stt_produces_no_speech(self):
        raw = {'id': 'c1', 'status': 'completed'}
        model = SimpleNamespace(id='c1', language='en', transcript_segments=[])
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=raw), patch.object(
            conv_router.conversations_db, 'is_soft_deleted', return_value=False
        ), patch.object(conv_router, 'deserialize_conversation', return_value=model), patch.object(
            conv_router,
            'transcribe_stored_conversation_audio',
            side_effect=StoredAudioEmptyTranscriptError('Transcription produced no speech'),
        ), patch.object(
            conv_router, 'process_conversation'
        ) as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation_transcription(conversation_id='c1', uid='u1')
        assert exc.value.status_code == 400
        assert exc.value.detail == 'Transcription produced no speech'
        process.assert_not_called()

    def test_returns_502_when_stt_provider_fails(self):
        raw = {'id': 'c1', 'status': 'completed'}
        model = SimpleNamespace(id='c1', language='en', transcript_segments=[])
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=raw), patch.object(
            conv_router.conversations_db, 'is_soft_deleted', return_value=False
        ), patch.object(conv_router, 'deserialize_conversation', return_value=model), patch.object(
            conv_router,
            'transcribe_stored_conversation_audio',
            side_effect=StoredAudioTranscriptionFailedError('Transcription provider failed'),
        ), patch.object(
            conv_router, 'process_conversation'
        ) as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation_transcription(conversation_id='c1', uid='u1')
        assert exc.value.status_code == 502
        process.assert_not_called()

    def test_replaces_segments_and_reuses_enrichment_path(self):
        raw = {'id': 'c1', 'discarded': True, 'status': 'completed'}
        model = SimpleNamespace(id='c1', language='en', transcript_segments=[])
        new_segments = [_segment()]
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=raw), patch.object(
            conv_router.conversations_db, 'is_soft_deleted', return_value=False
        ), patch.object(conv_router, 'deserialize_conversation', return_value=model), patch.object(
            conv_router, 'transcribe_stored_conversation_audio', return_value=new_segments
        ), patch.object(
            conv_router, 'process_conversation', return_value=model
        ) as process:
            result = conv_router.reprocess_conversation_transcription(conversation_id='c1', uid='u1')
        assert result is model
        assert model.transcript_segments is new_segments
        assert process.call_args.kwargs['force_process'] is True
        assert process.call_args.kwargs['is_reprocess'] is True
        assert process.call_args.kwargs['bypass_jit_first_open'] is True
        assert process.call_args.kwargs['app_usage_attribution'] is AppUsageAttribution.NON_USER_REPROCESS
