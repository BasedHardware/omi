"""Tests for desktop PTT transcription migration (#6286).

Verifies:
- deepgram_prerecorded_from_bytes passes encoding/language/model correctly
- transcribe_pcm_bytes language/model selection and error propagation
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level stubs (same pattern as test_sync_transcription_prefs.py)
# ---------------------------------------------------------------------------

# Stub models package (required before importing utils.stt.pre_recorded)
_models_pkg = ModuleType('models')
_models_pkg.__path__ = ['models']
_models_pkg.__package__ = 'models'
sys.modules.setdefault('models', _models_pkg)

for _msub in [
    'other',
    'transcript_segment',
    'chat',
    'conversation',
    'notification_message',
    'app',
    'memory',
    'action_item',
]:
    _mfull = f'models.{_msub}'
    if _mfull not in sys.modules:
        _mm = MagicMock()
        sys.modules[_mfull] = _mm
        setattr(_models_pkg, _msub, _mm)

# Stub database package
_database_pkg = ModuleType('database')
_database_pkg.__path__ = ['database']
_database_pkg.__package__ = 'database'
sys.modules.setdefault('database', _database_pkg)

for _sub in [
    '_client',
    'action_items',
    'announcements',
    'apps',
    'auth',
    'cache',
    'cache_manager',
    'calendar_meetings',
    'chat',
    'conversations',
    'daily_summaries',
    'dev_api_key',
    'fair_use',
    'folders',
    'goals',
    'helpers',
    'import_jobs',
    'knowledge_graph',
    'llm_usage',
    'mcp_api_key',
    'mem_db',
    'memories',
    'notifications',
    'phone_calls',
    'redis_db',
    'redis_pubsub',
    'screen_activity',
    'tasks',
    'trends',
    'user_usage',
    'users',
    'vector_db',
    'wrapped',
    'people',
    'processing_memories',
    'plugins',
    'sync_jobs',
]:
    _full = f'database.{_sub}'
    if _full not in sys.modules:
        _m = MagicMock()
        sys.modules[_full] = _m
        setattr(_database_pkg, _sub, _m)

_fb = MagicMock()
_fb.__path__ = ['firebase_admin']
sys.modules.setdefault('firebase_admin', _fb)
sys.modules.setdefault('firebase_admin.messaging', _fb.messaging)
sys.modules.setdefault('firebase_admin.auth', _fb.auth)

import google.cloud.storage as _gcs

_gcs.Client = MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-fake-for-test')
os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub transitive imports for utils.chat (avoid pulling in all of utils.llm etc.)
# Do NOT stub utils.other.endpoints — it contains the @timeit decorator that must
# be a real function (not MagicMock) or it corrupts decorated function signatures.
for _ufull in [
    'utils.llm',
    'utils.llm.memories',
    'utils.llm.persona',
    'utils.llm.chat',
    'utils.llm.goals',
    'utils.llm.usage_tracker',
    'utils.conversations',
    'utils.conversations.process_conversation',
    'utils.notifications',
    'utils.other.storage',
    'utils.other.chat_file',
    'utils.apps',
    'utils.retrieval',
    'utils.retrieval.graph',
    'utils.fair_use',
    'utils.log_sanitizer',
    'models.fair_use',
    'models.sync',
    'models.processing_memory',
    'models.integrations',
    'models.goal',
]:
    sys.modules.setdefault(_ufull, MagicMock())

# Force-import real models.chat (has no project deps, needed for FastAPI response_model)
import importlib.util as _ilu

_chat_spec = _ilu.spec_from_file_location(
    'models.chat', os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'chat.py')
)
_real_chat = _ilu.module_from_spec(_chat_spec)
_chat_spec.loader.exec_module(_real_chat)
sys.modules['models.chat'] = _real_chat
setattr(_models_pkg, 'chat', _real_chat)

# Now safe to import the modules under test
from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes

# ---------------------------------------------------------------------------
# deepgram_prerecorded_from_bytes: encoding/language/model options
# ---------------------------------------------------------------------------


class TestDeepgramPrerecordedFromBytesPCM:
    """Verify raw PCM options are forwarded correctly to Deepgram."""

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_pcm_encoding_passed_to_options(self, mock_client):
        """When encoding='linear16', options should include encoding, sample_rate, channels."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'alternatives': [
                            {
                                'words': [
                                    {
                                        'word': 'hello',
                                        'start': 0.0,
                                        'end': 0.5,
                                        'speaker': 0,
                                        'punctuated_word': 'Hello',
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        pcm_bytes = b'\x00' * 3200  # 100ms of 16kHz 16-bit mono
        deepgram_prerecorded_from_bytes(pcm_bytes, encoding='linear16', sample_rate=16000, channels=1)

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        source = call_args[0][0]
        options = call_args[0][1]

        assert source['mimetype'] == 'audio/raw'
        assert options['encoding'] == 'linear16'
        assert options['sample_rate'] == 16000
        assert options['channels'] == 1

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_wav_no_encoding_options(self, mock_client):
        """When encoding=None (WAV mode), encoding/sample_rate/channels should NOT be in options."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {'results': {'channels': [{'alternatives': [{'words': []}]}]}}
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        deepgram_prerecorded_from_bytes(b'\x00' * 1000, encoding=None)

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        source = call_args[0][0]
        options = call_args[0][1]

        assert source['mimetype'] == 'audio/wav'
        assert 'encoding' not in options
        assert 'sample_rate' not in options
        assert 'channels' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_language_passed_to_options(self, mock_client):
        """When language is specified (not multi), it should be in options."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {'results': {'channels': [{'alternatives': [{'words': []}]}]}}
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        deepgram_prerecorded_from_bytes(b'\x00' * 100, language='es', model='nova-3')

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        options = call_args[0][1]

        assert options['language'] == 'es'
        assert options['model'] == 'nova-3'
        assert options['detect_language'] is False

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_multi_language_enables_detection(self, mock_client):
        """When language='multi', detect_language should be True and no language set."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {'results': {'channels': [{'alternatives': [{'words': []}]}]}}
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        deepgram_prerecorded_from_bytes(b'\x00' * 100, language='multi')

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        options = call_args[0][1]

        assert options['detect_language'] is True
        assert 'language' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_model_param_forwarded(self, mock_client):
        """Custom model name should be forwarded to Deepgram options."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {'results': {'channels': [{'alternatives': [{'words': []}]}]}}
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        deepgram_prerecorded_from_bytes(b'\x00' * 100, model='nova-3', language='zh')

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        options = call_args[0][1]

        assert options['model'] == 'nova-3'
        assert options['language'] == 'zh'

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_return_language_extracts_detected_lang(self, mock_client):
        """return_language=True should return (words, detected_language) tuple."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'detected_language': 'es-ES',
                        'alternatives': [
                            {
                                'words': [
                                    {
                                        'word': 'hola',
                                        'start': 0.0,
                                        'end': 0.5,
                                        'speaker': 0,
                                        'punctuated_word': 'Hola',
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        result = deepgram_prerecorded_from_bytes(b'\x00' * 100, language='multi', return_language=True)

        assert isinstance(result, tuple)
        words, detected_lang = result
        assert len(words) == 1
        assert detected_lang == 'es'  # normalized from es-ES


# ---------------------------------------------------------------------------
# transcribe_pcm_bytes: language selection and error propagation
# ---------------------------------------------------------------------------


class TestTranscribePcmBytes:
    """Verify transcribe_pcm_bytes passes language/model and propagates errors."""

    @patch('utils.chat.postprocess_words')
    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_language_model_forwarded(self, mock_get_model, mock_dg, mock_postprocess):
        """stt_language and stt_model should be passed to deepgram_prerecorded_from_bytes."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('es', 'nova-3')
        mock_dg.return_value = [{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': 'Hola'}]
        mock_seg = MagicMock()
        mock_seg.text = 'Hola'
        mock_postprocess.return_value = [mock_seg]

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='es')

        mock_dg.assert_called_once()
        call_kwargs = mock_dg.call_args[1]
        assert call_kwargs['language'] == 'es'
        assert call_kwargs['model'] == 'nova-3'
        assert call_kwargs['encoding'] == 'linear16'
        assert text == 'Hola'

    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_runtime_error_propagates(self, mock_get_model, mock_dg):
        """RuntimeError from Deepgram should propagate (not be caught)."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('en', 'nova-3')
        mock_dg.side_effect = RuntimeError('Deepgram failed')

        with pytest.raises(RuntimeError, match='Deepgram failed'):
            transcribe_pcm_bytes(b'\x00' * 100, 'test-uid')

    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_empty_words_returns_none(self, mock_get_model, mock_dg):
        """Empty word list should return (None, language)."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('en', 'nova-3')
        mock_dg.return_value = []

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='en')
        assert text is None
        assert lang == 'en'

    @patch('utils.chat.postprocess_words')
    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_multi_language_returns_detected_language(self, mock_get_model, mock_dg, mock_postprocess):
        """Multi-language mode should return the Deepgram-detected language, not hardcoded 'en'."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('multi', 'nova-3')
        # return_language=True path returns (words, detected_lang)
        mock_dg.return_value = ([{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': 'Bonjour'}], 'fr')
        mock_seg = MagicMock()
        mock_seg.text = 'Bonjour'
        mock_postprocess.return_value = [mock_seg]

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='multi')

        assert text == 'Bonjour'
        assert lang == 'fr'
        # Verify return_language=True was passed
        call_kwargs = mock_dg.call_args[1]
        assert call_kwargs['return_language'] is True

    @patch('utils.chat.postprocess_words')
    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_chinese_language_uses_nova3(self, mock_get_model, mock_dg, mock_postprocess):
        """Chinese should use nova-3 model."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('zh', 'nova-3')
        mock_dg.return_value = [{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': '你好'}]
        mock_seg = MagicMock()
        mock_seg.text = '你好'
        mock_postprocess.return_value = [mock_seg]

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='zh')

        call_kwargs = mock_dg.call_args[1]
        assert call_kwargs['model'] == 'nova-3'
        assert call_kwargs['language'] == 'zh'

    @patch('utils.chat.postprocess_words')
    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_whitespace_only_transcript_returns_none(self, mock_get_model, mock_dg, mock_postprocess):
        """Whitespace-only transcript after postprocessing should return (None, language)."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('en', 'nova-3')
        mock_dg.return_value = [{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': ' '}]
        mock_seg = MagicMock()
        mock_seg.text = '   '
        mock_postprocess.return_value = [mock_seg]

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='en')
        assert text is None
        assert lang == 'en'

    @patch('utils.chat.deepgram_prerecorded_from_bytes')
    @patch('utils.chat.get_deepgram_model_for_language')
    def test_postprocess_empty_returns_none(self, mock_get_model, mock_dg):
        """postprocess_words returning empty list should return (None, language)."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('en', 'nova-3')
        mock_dg.return_value = [{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': 'hello'}]
        # postprocess_words is imported at module level; mock it
        with patch('utils.chat.postprocess_words', return_value=[]):
            text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='en')
        assert text is None
        assert lang == 'en'


# ---------------------------------------------------------------------------
# deepgram_prerecorded_from_bytes: retry and edge cases
# ---------------------------------------------------------------------------


class TestDeepgramPrerecordedFromBytesEdgeCases:
    """Verify retry logic, return_language with empty words, and error paths."""

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_retry_raises_after_max_attempts(self, mock_client):
        """After 3 failed attempts, should raise RuntimeError."""
        mock_client.listen.rest.v.return_value.transcribe_file.side_effect = Exception('connection timeout')

        with pytest.raises(RuntimeError, match='Deepgram transcription failed after 3 attempts'):
            deepgram_prerecorded_from_bytes(b'\x00' * 100, encoding='linear16')

        # Should have been called 3 times (attempts 0, 1, 2)
        assert mock_client.listen.rest.v.return_value.transcribe_file.call_count == 3

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_return_language_empty_words_returns_detected_lang(self, mock_client):
        """return_language=True with no words should return ([], detected_language)."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {'channels': [{'detected_language': 'ja', 'alternatives': [{'words': []}]}]}
        }
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        result = deepgram_prerecorded_from_bytes(b'\x00' * 100, language='multi', return_language=True)

        assert isinstance(result, tuple)
        words, lang = result
        assert words == []
        assert lang == 'ja'

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_no_channels_raises_and_retries(self, mock_client):
        """Empty channels in response should trigger retry."""
        mock_response = MagicMock()
        mock_response.to_dict.return_value = {'results': {'channels': []}}
        mock_client.listen.rest.v.return_value.transcribe_file.return_value = mock_response

        with pytest.raises(RuntimeError, match='Deepgram transcription failed after 3 attempts'):
            deepgram_prerecorded_from_bytes(b'\x00' * 100)

        assert mock_client.listen.rest.v.return_value.transcribe_file.call_count == 3


# ---------------------------------------------------------------------------
# connect_to_deepgram: start() failure guard (#6302)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Router-level endpoint tests: content-type dispatch and validation
# ---------------------------------------------------------------------------


def _stub_router_deps():
    """Stub all transitive dependencies needed to import routers.chat via importlib."""
    extra_models = [
        'models.fair_use',
        'models.users',
        'models.sync',
        'models.processing_memory',
        'models.integrations',
        'models.goal',
        'models.screen_pipe',
    ]
    extra_database = ['database.sync_jobs', 'database.user_usage']
    extra_utils = [
        'utils.fair_use',
        'utils.log_sanitizer',
        'utils.subscription',
        'utils.social',
        'utils.speaker_assignment',
        'utils.speaker_identification',
        'utils.stt.speaker_embedding',
        'utils.stt.vad',
        'utils.stt.streaming',
        'utils.stt.vad_gate',
        'utils.stt.safe_socket',
    ]
    for mod in extra_models + extra_database + extra_utils:
        sys.modules.setdefault(mod, MagicMock())
    # Ensure redis_db.check_rate_limit returns (True, 99, 0)
    rdb = sys.modules.get('database.redis_db')
    if rdb:
        rdb.check_rate_limit = MagicMock(return_value=(True, 99, 0))


def _make_chat_client():
    """Build a TestClient for the chat router with mocked auth."""
    import importlib.util
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    saved = {k: v for k, v in sys.modules.items()}

    _stub_router_deps()

    sys.modules.pop('routers.chat', None)
    sys.modules.pop('routers.sync', None)
    spec = importlib.util.spec_from_file_location(
        'routers_chat_test',
        os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'chat.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    app = FastAPI()
    app.include_router(module.router)

    # Override the rate-limited auth dependency for all endpoints
    for route in app.routes:
        if hasattr(route, 'dependant'):
            for dep in route.dependant.dependencies:
                if dep.call is not None:
                    app.dependency_overrides[dep.call] = lambda: 'test-uid'

    client = TestClient(app)
    return client, module, saved


def _cleanup_chat_client(saved):
    to_remove = [k for k in sys.modules if k not in saved]
    for k in to_remove:
        del sys.modules[k]


class TestVoiceMessageTranscribeEndpoint:
    """Test /v2/voice-message/transcribe content-type dispatch and validation."""

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_returns_transcript(self, mock_transcribe):
        """application/octet-stream should dispatch to PCM path and return JSON."""
        mock_transcribe.return_value = ('Hello world', 'en')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?keywords=Aarav,Ansh,Aarav',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data['transcript'] == 'Hello world'
            assert data['language'] == 'en'
            assert mock_transcribe.call_args.kwargs['keywords'] == ['Aarav', 'Ansh']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_empty_body_400(self):
        """Empty octet-stream body should return 400."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe',
                content=b'',
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 400
            assert 'No audio data' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_bad_sample_rate_422(self):
        """Non-integer sample_rate should return 422, not 500."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?sample_rate=abc',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'integers' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_bad_channels_422(self):
        """Non-integer channels should return 422, not 500."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?channels=',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'integers' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_sample_rate_zero_422(self):
        """sample_rate=0 should return 422."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?sample_rate=0',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'sample_rate' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_channels_zero_422(self):
        """channels=0 should return 422."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?channels=0',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'channels' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_no_speech_empty_transcript(self, mock_transcribe):
        """No speech detected should return 200 with empty transcript (not 422)."""
        mock_transcribe.return_value = (None, 'en')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
            assert resp.json()['transcript'] == ''
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_runtime_error_returns_500(self, mock_transcribe):
        """RuntimeError from transcribe_pcm_bytes should return 500."""
        mock_transcribe.side_effect = RuntimeError('Deepgram connection failed')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 500
            assert 'Transcription failed' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)


# ---------------------------------------------------------------------------
# WebSocket endpoint tests: /v2/voice-message/transcribe-stream
# ---------------------------------------------------------------------------


class TestTranscribeStreamWebSocket:
    """Test /v2/voice-message/transcribe-stream WebSocket endpoint."""

    def test_ws_connects_and_receives_segments(self):
        """WebSocket should accept connection and forward Deepgram segments."""
        client, module, saved = _make_chat_client()
        try:
            # Mock process_audio_dg to return a fake socket that captures sent audio
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                # Simulate Deepgram returning a segment when audio is received
                def fake_send(data):
                    stream_transcript(
                        [
                            {
                                'speaker': 'SPEAKER_00',
                                'start': 0.0,
                                'end': 1.0,
                                'text': 'Hello',
                                'is_user': False,
                                'person_id': None,
                            }
                        ]
                    )

                mock_dg_socket.send = MagicMock(side_effect=fake_send)
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with client.websocket_connect(
                            '/v2/voice-message/transcribe-stream?language=en&sample_rate=16000'
                        ) as ws:
                            # Send enough audio to trigger a 30ms flush (16000 * 2 * 0.03 = 960 bytes)
                            ws.send_bytes(b'\x00' * 960)
                            # Receive the transcript segment
                            data = ws.receive_json()
                            assert isinstance(data, list)
                            assert len(data) == 1
                            assert data[0]['text'] == 'Hello'
                            assert data[0]['speaker'] == 'SPEAKER_00'
        finally:
            _cleanup_chat_client(saved)

    def test_ws_dg_connection_failure_closes_1011(self):
        """If Deepgram connection fails, WebSocket should close with 1011."""
        client, module, saved = _make_chat_client()
        try:

            async def mock_process_audio_dg_fail(stream_transcript, **kwargs):
                return None

            with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg_fail):
                    with pytest.raises(Exception):
                        with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                            ws.receive_json()  # Should not get here
        finally:
            _cleanup_chat_client(saved)

    def test_ws_rejects_zero_sample_rate(self):
        """sample_rate=0 should be rejected with WS close 1008."""
        client, module, saved = _make_chat_client()
        try:
            with pytest.raises(Exception):
                with client.websocket_connect('/v2/voice-message/transcribe-stream?sample_rate=0') as ws:
                    ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_rejects_invalid_channels(self):
        """channels=0 should be rejected with WS close 1008."""
        client, module, saved = _make_chat_client()
        try:
            with pytest.raises(Exception):
                with client.websocket_connect('/v2/voice-message/transcribe-stream?channels=0') as ws:
                    ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_finalize_flushes_and_finalizes(self):
        """Sending 'finalize' text should flush buffer and call dg_socket.finalize()."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                def fake_send(data):
                    if len(data) > 0:
                        stream_transcript(
                            [
                                {
                                    'speaker': 'SPEAKER_00',
                                    'start': 0.0,
                                    'end': 1.0,
                                    'text': 'Final',
                                    'is_user': False,
                                    'person_id': None,
                                }
                            ]
                        )

                mock_dg_socket.send = MagicMock(side_effect=fake_send)
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with client.websocket_connect(
                            '/v2/voice-message/transcribe-stream?language=en&sample_rate=16000'
                        ) as ws:
                            # Send sub-threshold audio (less than 960 bytes = 30ms at 16kHz)
                            ws.send_bytes(b'\x00' * 500)
                            # Send finalize — should flush the sub-threshold buffer
                            ws.send_text('finalize')
                            # Receive the transcript from flushed audio
                            data = ws.receive_json()
                            assert isinstance(data, list)
                            assert data[0]['text'] == 'Final'

            # Verify finalize was called
            mock_dg_socket.finalize.assert_called()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_stereo_flush_accounts_for_channels(self):
        """Stereo (channels=2) flush threshold should be doubled vs mono."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None
            sent_chunks = []

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                def fake_send(data):
                    sent_chunks.append(data)
                    stream_transcript(
                        [
                            {
                                'speaker': 'SPEAKER_00',
                                'start': 0.0,
                                'end': 1.0,
                                'text': 'Stereo',
                                'is_user': False,
                                'person_id': None,
                            }
                        ]
                    )

                mock_dg_socket.send = MagicMock(side_effect=fake_send)
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with client.websocket_connect(
                            '/v2/voice-message/transcribe-stream?language=en&sample_rate=16000&channels=2'
                        ) as ws:
                            # Stereo 30ms flush = 16000 * 2 * 2 * 0.03 = 1920 bytes
                            # Send 960 bytes — should NOT flush (mono threshold, but stereo needs 1920)
                            ws.send_bytes(b'\x00' * 960)
                            # Send remaining to reach stereo threshold
                            ws.send_bytes(b'\x00' * 960)
                            data = ws.receive_json()
                            assert isinstance(data, list)
                            assert data[0]['text'] == 'Stereo'
        finally:
            _cleanup_chat_client(saved)

    def test_ws_rejects_unsupported_codec(self):
        """codec != linear16 should be rejected with WS close 1008."""
        client, module, saved = _make_chat_client()
        try:
            with pytest.raises(Exception):
                with client.websocket_connect('/v2/voice-message/transcribe-stream?codec=opus') as ws:
                    ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_rejects_sample_rate_above_48000(self):
        """sample_rate above 48000 should be rejected."""
        client, module, saved = _make_chat_client()
        try:
            with pytest.raises(Exception):
                with client.websocket_connect('/v2/voice-message/transcribe-stream?sample_rate=96000') as ws:
                    ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_rejects_channels_above_2(self):
        """channels > 2 should be rejected."""
        client, module, saved = _make_chat_client()
        try:
            with pytest.raises(Exception):
                with client.websocket_connect('/v2/voice-message/transcribe-stream?channels=3') as ws:
                    ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_accepts_boundary_sample_rate_8000(self):
        """sample_rate=8000 (lower bound) should be accepted."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                assert kwargs.get('sample_rate') == 8000
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                    with client.websocket_connect('/v2/voice-message/transcribe-stream?sample_rate=8000') as ws:
                        # Connection accepted — just close gracefully
                        pass
        finally:
            _cleanup_chat_client(saved)

    def test_ws_accepts_boundary_sample_rate_48000(self):
        """sample_rate=48000 (upper bound) should be accepted."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                assert kwargs.get('sample_rate') == 48000
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                    with client.websocket_connect('/v2/voice-message/transcribe-stream?sample_rate=48000') as ws:
                        pass
        finally:
            _cleanup_chat_client(saved)


class TestVoiceMessageTranscribeBoundary:
    """Boundary tests for /v2/voice-message/transcribe REST endpoint."""

    def test_octet_stream_sample_rate_above_48000_rejected(self):
        """sample_rate > 48000 should return 422."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?sample_rate=96000',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'sample_rate' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    def test_octet_stream_channels_above_2_rejected(self):
        """channels > 2 should return 422."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?channels=3',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 422
            assert 'channels' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_accepts_boundary_sample_rate_8000(self, mock_transcribe):
        """sample_rate=8000 (lower bound) should be accepted."""
        mock_transcribe.return_value = ('hello', 'en')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?sample_rate=8000',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_accepts_boundary_sample_rate_48000(self, mock_transcribe):
        """sample_rate=48000 (upper bound) should be accepted."""
        mock_transcribe.return_value = ('hello', 'en')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?sample_rate=48000',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_accepts_channels_2(self, mock_transcribe):
        """channels=2 (upper bound) should be accepted."""
        mock_transcribe.return_value = ('hello', 'en')
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe?channels=2',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
        finally:
            _cleanup_chat_client(saved)


# ---------------------------------------------------------------------------
# Duration budget enforcement: octet-stream, multipart, and WebSocket
# ---------------------------------------------------------------------------


class TestDurationBudgetEnforcement:
    """Test daily budget enforcement across all three endpoints."""

    def test_octet_stream_budget_exhausted_429(self):
        """Octet-stream request with exhausted budget should return 429."""
        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, 'try_consume_budget', return_value=(False, 7200000, 0)):
                resp = client.post(
                    '/v2/voice-message/transcribe',
                    content=b'\x00' * 3200,
                    headers={'Content-Type': 'application/octet-stream'},
                )
                assert resp.status_code == 429
                assert 'budget exhausted' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_budget_consumed_with_correct_duration(self, mock_transcribe):
        """Successful octet-stream request should consume budget with correct duration_ms."""
        mock_transcribe.return_value = ('hello', 'en')
        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, 'try_consume_budget', return_value=(True, 1000, 7199000)) as mock_budget:
                resp = client.post(
                    '/v2/voice-message/transcribe',
                    # 32000 bytes at 16kHz mono = 1 second = 1000ms
                    content=b'\x00' * 32000,
                    headers={'Content-Type': 'application/octet-stream'},
                )
                assert resp.status_code == 200
                mock_budget.assert_called_once()
                call_args = mock_budget.call_args[0]
                assert call_args[0] == 'test-uid'
                assert call_args[1] == 1000  # 32000 / (16000*1*2) * 1000
        finally:
            _cleanup_chat_client(saved)

    def test_multipart_budget_exhausted_429(self):
        """Multipart upload with exhausted budget should return 429."""
        import io

        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, 'read_wav_duration_ms', return_value=60_000):
                with patch.object(module, 'try_consume_budget', return_value=(False, 7200000, 0)):
                    resp = client.post(
                        '/v2/voice-message/transcribe',
                        files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                    )
                    assert resp.status_code == 429
                    assert 'budget exhausted' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)


class TestVoiceMessagesEndpointBudget:
    """Test /v2/voice-messages daily budget enforcement."""

    def test_voice_messages_budget_exhausted_429(self):
        """Exhausted budget on /v2/voice-messages should return 429."""
        import io

        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, 'retrieve_file_paths', return_value=['/tmp/test_vm.wav']):
                with patch.object(module, 'decode_files_to_wav', return_value=['/tmp/test_vm_decoded.wav']):
                    with patch.object(module, 'read_wav_duration_ms', return_value=60_000):
                        with patch.object(module, 'try_consume_budget', return_value=(False, 7200000, 0)):
                            resp = client.post(
                                '/v2/voice-messages',
                                files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                            )
                            assert resp.status_code == 429
                            assert 'budget exhausted' in resp.json()['detail']
        finally:
            _cleanup_chat_client(saved)


class TestWsBudgetAndSessionCap:
    """Test WS budget gate and actual duration recording."""

    def test_ws_budget_exhausted_rejects_at_connect(self):
        """WS should close with 1008 if daily budget is exhausted at connect."""
        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, 'check_budget', return_value=(False, 7200000, 0)):
                with pytest.raises(Exception):
                    with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                        ws.receive_json()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_records_actual_duration_on_close(self):
        """WS should call record_actual_duration with correct ms after session ends."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with patch.object(module, 'record_actual_duration') as mock_record:
                            with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                # Send 32000 bytes = 1s at 16kHz mono
                                ws.send_bytes(b'\x00' * 32000)
                            # After WS close, finally block should have called record_actual_duration
                            mock_record.assert_called_once()
                            call_args = mock_record.call_args[0]
                            assert call_args[0] == 'test-uid'
                            assert call_args[1] == 1000  # 32000 / (16000*1*2) * 1000
        finally:
            _cleanup_chat_client(saved)


class TestNoPerSessionCap:
    """Verify that audio >120s is accepted when daily budget remains (no per-session cap)."""

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_octet_stream_over_120s_accepted(self, mock_transcribe):
        """Octet-stream with >120s audio should be accepted if budget allows."""
        mock_transcribe.return_value = ('long message', 'en')
        client, module, saved = _make_chat_client()
        try:
            # 300s at 16kHz mono = 9,600,000 bytes → well over 120s
            audio_300s = b'\x00' * (16000 * 1 * 2 * 300)
            with patch.object(module, 'try_consume_budget', return_value=(True, 300000, 6900000)):
                resp = client.post(
                    '/v2/voice-message/transcribe',
                    content=audio_300s,
                    headers={'Content-Type': 'application/octet-stream'},
                )
                assert resp.status_code == 200
                assert resp.json()['transcript'] == 'long message'
        finally:
            del audio_300s
            _cleanup_chat_client(saved)

    def test_multipart_over_120s_accepted(self):
        """Multipart WAV with >120s duration should be accepted if budget allows."""
        import io

        client, module, saved = _make_chat_client()
        try:
            # WAV reports 300s (5 minutes) — should NOT be rejected
            with patch.object(module, 'read_wav_duration_ms', return_value=300_000):
                with patch.object(module, 'try_consume_budget', return_value=(True, 300000, 6900000)):
                    with patch.object(module, 'transcribe_voice_message_segment', return_value=('long msg', 'en')):
                        resp = client.post(
                            '/v2/voice-message/transcribe',
                            files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                        )
                        assert resp.status_code == 200
        finally:
            _cleanup_chat_client(saved)


class TestWsIdleTimeout:
    """Test that WS idle timeout is based on audio frames, not all messages."""

    def test_ws_idle_timeout_fires(self):
        """WS should close after idle timeout when no audio is sent."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            # Set idle timeout very short for test
            with patch.object(module, '_WS_IDLE_TIMEOUT_S', 0.1):
                with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                    with patch.object(
                        module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')
                    ):
                        with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                            with patch.object(module, 'record_actual_duration'):
                                with pytest.raises(Exception):
                                    with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                        # Don't send any audio — idle timeout should fire
                                        import time

                                        time.sleep(0.3)
                                        ws.receive_json()  # should fail — WS closed
        finally:
            _cleanup_chat_client(saved)

    def test_ws_idle_timeout_fires_despite_text_frames(self):
        """WS should still close for audio-idle even if text frames (finalize) are sent."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            # Set idle timeout very short for test
            with patch.object(module, '_WS_IDLE_TIMEOUT_S', 0.2):
                with patch.object(module, 'check_budget', return_value=(True, 0, 7200000)):
                    with patch.object(
                        module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')
                    ):
                        with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                            with patch.object(module, 'record_actual_duration'):
                                with pytest.raises(Exception):
                                    with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                        import time

                                        # Send finalize text frame — should NOT reset audio-idle timer
                                        time.sleep(0.1)
                                        ws.send_text('finalize')
                                        time.sleep(0.2)
                                        # Audio-idle timeout should have fired despite the text frame
                                        ws.receive_json()
        finally:
            _cleanup_chat_client(saved)


class TestVoiceMessagesBudgetHappyPath:
    """Test /v2/voice-messages budget consumption on the happy path."""

    def test_voice_messages_budget_consumed_on_success(self):
        """Budget should be consumed with first WAV duration on successful stream."""
        import io

        client, module, saved = _make_chat_client()
        try:

            async def mock_stream(*args, **kwargs):
                yield 'data: {"text": "hello"}\n\n'

            with patch.object(module, 'retrieve_file_paths', return_value=['/tmp/test_vm.wav']):
                with patch.object(module, 'decode_files_to_wav', return_value=['/tmp/test_vm_decoded.wav']):
                    with patch.object(module, 'read_wav_duration_ms', return_value=45_000):
                        with patch.object(
                            module, 'try_consume_budget', return_value=(True, 45000, 7155000)
                        ) as mock_budget:
                            with patch.object(module, 'resolve_voice_message_language', return_value='en'):
                                with patch.object(
                                    module, 'process_voice_message_segment_stream', side_effect=mock_stream
                                ):
                                    resp = client.post(
                                        '/v2/voice-messages',
                                        files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                                    )
                                    assert resp.status_code == 200
                                    # Budget consumed with first WAV duration only
                                    mock_budget.assert_called_once()
                                    call_args = mock_budget.call_args[0]
                                    assert call_args[0] == 'test-uid'
                                    assert call_args[1] == 45000
        finally:
            _cleanup_chat_client(saved)


class TestMultipartBudgetAggregation:
    """Test that multipart multi-file uploads sum WAV durations correctly."""

    def test_multipart_multi_file_budget_sums_durations(self):
        """Budget should be consumed with sum of all WAV durations."""
        import io

        client, module, saved = _make_chat_client()
        try:
            # Simulate 3 files: 1000ms, None (unreadable), 2000ms → budget call with 3000
            duration_values = iter([1000, None, 2000])

            with patch.object(module, 'read_wav_duration_ms', side_effect=lambda p: next(duration_values)):
                with patch.object(module, 'try_consume_budget', return_value=(True, 3000, 7197000)) as mock_budget:
                    with patch.object(module, 'transcribe_voice_message_segment', return_value=('hello', 'en')):
                        resp = client.post(
                            '/v2/voice-message/transcribe',
                            files=[
                                ('files', ('a.wav', io.BytesIO(b'\x00' * 100), 'audio/wav')),
                                ('files', ('b.wav', io.BytesIO(b'\x00' * 100), 'audio/wav')),
                                ('files', ('c.wav', io.BytesIO(b'\x00' * 100), 'audio/wav')),
                            ],
                        )
                        assert resp.status_code == 200
                        # Budget consumed with sum: 1000 + 2000 = 3000 (None skipped)
                        mock_budget.assert_called_once()
                        call_args = mock_budget.call_args[0]
                        assert call_args[0] == 'test-uid'
                        assert call_args[1] == 3000
        finally:
            _cleanup_chat_client(saved)


class TestWsMidSessionBudgetEnforcement:
    """Test that WS closes mid-session when cumulative audio exceeds remaining budget."""

    def test_ws_closes_when_budget_exceeded_mid_session(self):
        """WS should close with 1008 when cumulative audio exceeds remaining daily budget.

        The triggering frame should NOT be counted — total_audio_bytes is only
        incremented for frames that pass the budget check and reach Deepgram.
        """
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            # User has only 500ms of budget remaining
            with patch.object(module, 'check_budget', return_value=(True, 7199500, 500)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with patch.object(module, 'record_actual_duration') as mock_record:
                            with pytest.raises(Exception):
                                with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                    # Send 32000 bytes = 1000ms at 16kHz mono — exceeds 500ms remaining
                                    ws.send_bytes(b'\x00' * 32000)
                                    import time

                                    time.sleep(0.1)
                                    ws.receive_json()  # should fail — WS closed due to budget
                            # The triggering frame is NOT counted (check happens before increment),
                            # so record_actual_duration should NOT be called (0 bytes processed)
                            mock_record.assert_not_called()
        finally:
            _cleanup_chat_client(saved)

    def test_ws_allows_audio_within_remaining_budget(self):
        """WS should accept audio that fits within remaining budget."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            # User has 60s of budget remaining
            with patch.object(module, 'check_budget', return_value=(True, 7140000, 60000)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with patch.object(module, 'record_actual_duration'):
                            with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                # Send 32000 bytes = 1000ms at 16kHz mono — well within 60s remaining
                                ws.send_bytes(b'\x00' * 32000)
                                # Connection should stay open — no 1008 close
        finally:
            _cleanup_chat_client(saved)

    def test_ws_mid_session_records_only_processed_audio(self):
        """WS should only record audio that was processed, not the triggering frame."""
        client, module, saved = _make_chat_client()
        try:
            mock_dg_socket = MagicMock()
            mock_dg_socket.is_connection_dead = False
            mock_dg_socket.death_reason = None

            async def mock_process_audio_dg(stream_transcript, **kwargs):
                mock_dg_socket.send = MagicMock()
                mock_dg_socket.finalize = MagicMock()
                mock_dg_socket.finish = MagicMock()
                return mock_dg_socket

            # User has 1500ms of budget remaining
            with patch.object(module, 'check_budget', return_value=(True, 7198500, 1500)):
                with patch.object(module, 'get_stt_service_for_language', return_value=(MagicMock(), 'en', 'nova-3')):
                    with patch.object(module, 'process_audio_dg', side_effect=mock_process_audio_dg):
                        with patch.object(module, 'record_actual_duration') as mock_record:
                            with pytest.raises(Exception):
                                with client.websocket_connect('/v2/voice-message/transcribe-stream') as ws:
                                    # Frame 1: 32000 bytes = 1000ms — within 1500ms budget
                                    ws.send_bytes(b'\x00' * 32000)
                                    # Frame 2: 32000 bytes = would be 2000ms total — exceeds 1500ms
                                    ws.send_bytes(b'\x00' * 32000)
                                    import time

                                    time.sleep(0.1)
                                    ws.receive_json()
                            # Only frame 1 was processed (1000ms), frame 2 was rejected
                            mock_record.assert_called_once()
                            call_args = mock_record.call_args[0]
                            assert call_args[1] == 1000  # 32000 / (16000*1*2) * 1000
        finally:
            _cleanup_chat_client(saved)


class TestOctetStreamBodySizeGuard:
    """Test that octet-stream rejects oversized payloads before buffering."""

    @patch('utils.chat.transcribe_pcm_bytes')
    def test_oversized_body_rejected_413(self, mock_transcribe):
        """Body exceeding _MAX_PCM_BODY_BYTES should be rejected with 413."""
        client, module, saved = _make_chat_client()
        try:
            with patch.object(module, '_MAX_PCM_BODY_BYTES', 1000):
                resp = client.post(
                    '/v2/voice-message/transcribe',
                    content=b'\x00' * 1500,
                    headers={'Content-Type': 'application/octet-stream'},
                )
                assert resp.status_code == 413
                mock_transcribe.assert_not_called()
        finally:
            _cleanup_chat_client(saved)
