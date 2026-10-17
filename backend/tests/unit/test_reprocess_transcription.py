"""User-initiated transcription reprocess: STT on stored audio, then enrichment.

``POST /v1/conversations/{id}/reprocess`` only regenerates the summary from the
existing transcript. This path must replace segments from stored audio and then
reuse ``process_conversation(..., trigger=ProcessingTrigger.USER_REPROCESS)``.
Soft-deleted tombstones stay rejected; discarded conversations stay revivable.
"""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from models.transcript_segment import TranscriptSegment
from models.transcription_reprocess import TranscriptionReprocessErrorResponse
from utils.conversations.process_conversation import AppUsageAttribution
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.reprocess_transcription import (
    StoredAudioEmptyTranscriptError,
    StoredAudioTranscriptionFailedError,
    StoredAudioUnavailableError,
    collect_conversation_audio_timestamps,
    transcribe_stored_conversation_audio,
)
from utils.other import storage


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
    @pytest.mark.parametrize('batch', [False, True])
    @pytest.mark.parametrize('partial_audio', [False, True])
    def test_real_chunk_merger_outage_preserves_failure(self, monkeypatch, batch, partial_audio):
        def download(path):
            if partial_audio and '/2.000.' in path:
                if path.endswith('.bin'):
                    return b'\x00\x01'
                raise storage.NotFound('format absent')
            raise ConnectionError('storage unavailable')

        bucket = SimpleNamespace(blob=lambda path: SimpleNamespace(download_as_bytes=lambda: download(path)))
        monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
        chunks = [{'timestamp': 1.0}]
        if batch:
            chunks[0].update(is_batch=True, path='chunks/u1/c1/1.000-1.100.batch.enc')
        monkeypatch.setattr(storage, 'list_audio_chunks', lambda *args: chunks)
        timestamps = [1.0, 2.0] if partial_audio else [1.0]
        conversation = SimpleNamespace(id='c1', audio_files=[{'chunk_timestamps': timestamps}], language='en')
        with ThreadPoolExecutor(max_workers=2) as executor:
            monkeypatch.setattr(storage, 'storage_executor', executor)
            # Existing playback callers keep their best-effort contract.
            if partial_audio:
                # One second of existing gap-fill precedes the surviving chunk.
                expected = bytes(16000 * 2) + b'\x00\x01'
                assert storage.download_audio_chunks_and_merge('u1', 'c1', timestamps) == expected
            else:
                with pytest.raises(FileNotFoundError):
                    storage.download_audio_chunks_and_merge('u1', 'c1', timestamps)
            # Exercise the real merger, including its individual/batch futures.
            with patch('utils.conversations.reprocess_transcription.prerecorded_from_bytes') as stt:
                with pytest.raises(StoredAudioTranscriptionFailedError):
                    transcribe_stored_conversation_audio('u1', conversation, 'en')
            stt.assert_not_called()

    @pytest.mark.parametrize('operation', ['list_audio_chunks', 'download_audio_chunks_and_merge'])
    def test_storage_outage_is_not_missing_audio(self, operation):
        conversation = SimpleNamespace(id='c1', audio_files=[], language='en')
        with patch(
            'utils.conversations.reprocess_transcription.list_audio_chunks', return_value=[{'timestamp': 1.0}]
        ), patch(
            f'utils.conversations.reprocess_transcription.{operation}',
            side_effect=ConnectionError('storage unavailable'),
        ), patch(
            'utils.conversations.reprocess_transcription.prerecorded_from_bytes'
        ) as stt:
            with pytest.raises(StoredAudioTranscriptionFailedError):
                transcribe_stored_conversation_audio('u1', conversation, 'en')
        stt.assert_not_called()

    @pytest.mark.parametrize('error', [FileNotFoundError('gone'), None])
    def test_missing_or_empty_stored_audio_remains_no_audio(self, error):
        conversation = SimpleNamespace(id='c1', audio_files=[{'chunk_timestamps': [1.0]}], language='en')
        with patch(
            'utils.conversations.reprocess_transcription.download_audio_chunks_and_merge',
            side_effect=error,
            return_value=b'',
        ):
            with pytest.raises(StoredAudioUnavailableError):
                transcribe_stored_conversation_audio('u1', conversation, 'en')

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
        assert exc.value.detail == {'code': 'no_audio', 'message': 'No stored audio available to retranscribe'}
        assert TranscriptionReprocessErrorResponse(detail=exc.value.detail).detail.code == 'no_audio'
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
        assert exc.value.detail == {'code': 'no_speech', 'message': 'Transcription produced no speech'}
        assert TranscriptionReprocessErrorResponse(detail=exc.value.detail).detail.code == 'no_speech'
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
        assert exc.value.detail['code'] == 'failed'
        assert TranscriptionReprocessErrorResponse(detail=exc.value.detail).detail.code == 'failed'
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
        assert process.call_args.kwargs['trigger'] is ProcessingTrigger.USER_REPROCESS
        assert process.call_args.kwargs['app_usage_attribution'] is AppUsageAttribution.NON_USER_REPROCESS
        assert not {'force_process', 'is_reprocess', 'bypass_jit_first_open'} & set(process.call_args.kwargs)
