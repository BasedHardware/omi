"""Unit tests for Modulate (Velma-2) STT provider integration.

Tests cover:
- STTService enum includes modulate
- Language routing via get_stt_service_for_language
- Streaming WebSocket message parsing (process_audio_modulate)
- Batch transcription response parsing (modulate_prerecorded_from_bytes)
- Speaker ID mapping (1-indexed → 0-indexed SPEAKER_XX)
- Timestamp conversion (ms → seconds)
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Mock heavy dependencies at sys.modules level before importing
sys.modules.setdefault("database._client", MagicMock())

_mock_gcs_storage = MagicMock()
_mock_gcs_client_instance = MagicMock()
_mock_gcs_storage.Client.return_value = _mock_gcs_client_instance
sys.modules.setdefault("google.cloud.storage", _mock_gcs_storage)
sys.modules.setdefault("google.cloud.storage.transfer_manager", MagicMock())
sys.modules.setdefault("google.cloud.exceptions", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())
sys.modules.setdefault("firebase_admin", MagicMock())
sys.modules.setdefault("firebase_admin.auth", MagicMock())
sys.modules.setdefault("firebase_admin.firestore", MagicMock())

from utils.stt.streaming import (
    STTService,
    get_stt_service_for_language,
    modulate_languages,
    process_audio_modulate,
)


class TestSTTServiceEnum:
    def test_modulate_enum_exists(self):
        assert STTService.modulate == "modulate"

    def test_get_model_name_modulate(self):
        assert STTService.get_model_name(STTService.modulate) == 'modulate_streaming'


class TestModulateLanguages:
    def test_english_supported(self):
        assert 'en' in modulate_languages

    def test_multi_supported(self):
        assert 'multi' in modulate_languages

    def test_common_languages_supported(self):
        for lang in ['es', 'fr', 'de', 'ja', 'zh', 'ko', 'pt', 'ru', 'ar', 'hi']:
            assert lang in modulate_languages, f"{lang} should be in modulate_languages"


class TestModulateLanguageRouting:
    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_routes_english_to_modulate(self):
        service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.modulate
        assert lang == 'en'
        assert model == 'velma-2'

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_routes_multi_to_modulate(self):
        service, lang, model = get_stt_service_for_language('multi', multi_lang_enabled=True)
        assert service == STTService.modulate
        assert lang == 'multi'
        assert model == 'velma-2'

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2'])
    def test_unsupported_language_falls_back_to_deepgram(self):
        service, lang, model = get_stt_service_for_language('xx-unsupported', multi_lang_enabled=False)
        # Fallback is deepgram nova-3
        assert service == STTService.deepgram
        assert lang == 'en'

    @patch('utils.stt.streaming.stt_service_models', ['dg-nova-3', 'modulate-velma-2'])
    def test_deepgram_takes_priority_when_first(self):
        service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.deepgram

    @patch('utils.stt.streaming.stt_service_models', ['modulate-velma-2', 'dg-nova-3'])
    def test_modulate_takes_priority_when_first(self):
        service, lang, model = get_stt_service_for_language('en', multi_lang_enabled=False)
        assert service == STTService.modulate


class _MockModulateSocket:
    """Mock WebSocket that supports async iteration over messages."""

    def __init__(self, messages):
        self._messages = messages
        self.closed = False
        self.send = AsyncMock()
        self.close = AsyncMock()

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for msg in self._messages:
            yield msg


def _make_mock_modulate_socket(messages=None):
    if messages is None:
        messages = []
    return _MockModulateSocket(messages)


class TestProcessAudioModulateConnection:
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'MODULATE_API_KEY': ''})
    async def test_raises_without_api_key(self):
        with pytest.raises(ValueError, match="Modulate API key is not set"):
            await process_audio_modulate(lambda x: None, 16000, 'en')

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key-123'})
    async def test_connects_with_correct_url(self, mock_connect):
        mock_socket = _make_mock_modulate_socket()
        mock_connect.return_value = mock_socket

        await process_audio_modulate(lambda x: None, 16000, 'en')

        mock_connect.assert_called_once()
        call_uri = mock_connect.call_args[0][0]
        assert 'modulate-developer-apis.com' in call_uri
        assert 'api_key=test-key-123' in call_uri
        assert 'speaker_diarization=true' in call_uri
        assert 'sample_rate=16000' in call_uri


class TestModulateMessageParsing:
    """Test that Modulate WebSocket messages are correctly parsed into segments."""

    def _make_utterance_message(self, text, start_ms, duration_ms, speaker=1, language='en'):
        return json.dumps(
            {
                'type': 'utterance',
                'utterance': {
                    'utterance_uuid': 'test-uuid',
                    'text': text,
                    'start_ms': start_ms,
                    'duration_ms': duration_ms,
                    'speaker': speaker,
                    'language': language,
                    'emotion': None,
                    'accent': None,
                },
            }
        )

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_utterance_parsed_to_segment(self, mock_connect):
        received_segments = []
        messages = [self._make_utterance_message("Hello world", 1000, 2000, speaker=1)]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        await process_audio_modulate(lambda segs: received_segments.extend(segs), 16000, 'en')
        await asyncio.sleep(0.1)

        assert len(received_segments) == 1
        seg = received_segments[0]
        assert seg['text'] == 'Hello world'
        assert seg['start'] == 1.0  # 1000ms -> 1.0s
        assert seg['end'] == 3.0  # 1000 + 2000 = 3000ms -> 3.0s
        assert seg['speaker'] == 'SPEAKER_00'  # speaker 1 -> SPEAKER_00
        assert seg['person_id'] is None

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_speaker_id_mapping(self, mock_connect):
        """Modulate uses 1-indexed speakers; we convert to 0-indexed SPEAKER_XX."""
        received_segments = []
        messages = [
            self._make_utterance_message("Speaker one", 0, 1000, speaker=1),
            self._make_utterance_message("Speaker two", 1000, 1000, speaker=2),
            self._make_utterance_message("Speaker three", 2000, 1000, speaker=3),
        ]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        await process_audio_modulate(lambda segs: received_segments.extend(segs), 16000, 'en')
        await asyncio.sleep(0.1)

        assert received_segments[0]['speaker'] == 'SPEAKER_00'
        assert received_segments[1]['speaker'] == 'SPEAKER_01'
        assert received_segments[2]['speaker'] == 'SPEAKER_02'

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_preseconds_skips_early_utterances(self, mock_connect):
        received_segments = []
        messages = [
            self._make_utterance_message("During profile", 5000, 2000, speaker=1),
            self._make_utterance_message("After profile", 16000, 2000, speaker=1),
        ]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        await process_audio_modulate(lambda segs: received_segments.extend(segs), 16000, 'en', preseconds=15)
        await asyncio.sleep(0.1)

        assert len(received_segments) == 1
        assert received_segments[0]['text'] == 'After profile'

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_empty_text_skipped(self, mock_connect):
        received_segments = []
        messages = [
            self._make_utterance_message("", 0, 1000),
            self._make_utterance_message("   ", 1000, 1000),
            self._make_utterance_message("Real text", 2000, 1000),
        ]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        await process_audio_modulate(lambda segs: received_segments.extend(segs), 16000, 'en')
        await asyncio.sleep(0.1)

        assert len(received_segments) == 1
        assert received_segments[0]['text'] == 'Real text'

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_done_message_handled(self, mock_connect):
        received_segments = []
        messages = [
            self._make_utterance_message("Hello", 0, 1000),
            json.dumps({'type': 'done', 'duration_ms': 5000}),
        ]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        await process_audio_modulate(lambda segs: received_segments.extend(segs), 16000, 'en')
        await asyncio.sleep(0.1)

        assert len(received_segments) == 1

    @pytest.mark.asyncio
    @patch('utils.stt.streaming.websockets.connect', new_callable=AsyncMock)
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    async def test_error_message_raises(self, mock_connect):
        messages = [json.dumps({'type': 'error', 'error': 'Internal server error'})]
        mock_connect.return_value = _make_mock_modulate_socket(messages)

        # The error is handled inside the on_message task, not raised to caller
        await process_audio_modulate(lambda segs: None, 16000, 'en')
        await asyncio.sleep(0.1)
        # No crash — error is logged and connection closes


class TestModulateBatchPrerecorded:
    @patch.dict('os.environ', {'MODULATE_API_KEY': ''})
    def test_raises_without_api_key(self):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        with pytest.raises(ValueError, match="MODULATE_API_KEY"):
            modulate_prerecorded_from_bytes(b'fake-audio')

    @patch('utils.stt.pre_recorded.requests.post')
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    def test_parses_batch_response(self, mock_post):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'text': 'Hello world. How are you?',
            'duration_ms': 5000,
            'utterances': [
                {
                    'utterance_uuid': 'uuid-1',
                    'text': 'Hello world.',
                    'start_ms': 0,
                    'duration_ms': 2000,
                    'speaker': 1,
                    'language': 'en',
                    'emotion': None,
                    'accent': None,
                },
                {
                    'utterance_uuid': 'uuid-2',
                    'text': 'How are you?',
                    'start_ms': 2500,
                    'duration_ms': 2500,
                    'speaker': 2,
                    'language': 'en',
                    'emotion': None,
                    'accent': None,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        words = modulate_prerecorded_from_bytes(b'fake-wav-data')

        assert len(words) == 2
        assert words[0]['text'] == 'Hello world.'
        assert words[0]['timestamp'] == [0.0, 2.0]
        assert words[0]['speaker'] == 'SPEAKER_00'
        assert words[1]['text'] == 'How are you?'
        assert words[1]['timestamp'] == [2.5, 5.0]
        assert words[1]['speaker'] == 'SPEAKER_01'

    @patch('utils.stt.pre_recorded.requests.post')
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    def test_return_language(self, mock_post):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'text': 'Bonjour',
            'duration_ms': 1000,
            'utterances': [
                {
                    'utterance_uuid': 'uuid-1',
                    'text': 'Bonjour',
                    'start_ms': 0,
                    'duration_ms': 1000,
                    'speaker': 1,
                    'language': 'fr',
                    'emotion': None,
                    'accent': None,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        words, lang = modulate_prerecorded_from_bytes(b'fake-audio', return_language=True)

        assert lang == 'fr'
        assert len(words) == 1

    @patch('utils.stt.pre_recorded.requests.post')
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    def test_empty_utterances_returns_empty(self, mock_post):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'text': '',
            'duration_ms': 0,
            'utterances': [],
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        words = modulate_prerecorded_from_bytes(b'silence')
        assert words == []

    @patch('utils.stt.pre_recorded.requests.post')
    @patch.dict('os.environ', {'MODULATE_API_KEY': 'test-key'})
    def test_sends_correct_request(self, mock_post):
        from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

        mock_response = MagicMock()
        mock_response.json.return_value = {'text': '', 'duration_ms': 0, 'utterances': []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        modulate_prerecorded_from_bytes(b'audio-data', diarize=True)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        # URL is first positional arg
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get('url', '')
        assert 'velma-2-stt-batch' in url
        # Headers and data in kwargs
        headers = call_args.kwargs.get('headers', {})
        assert headers == {'X-API-Key': 'test-key'}
        data = call_args.kwargs.get('data', {})
        assert data == {'speaker_diarization': 'true'}
