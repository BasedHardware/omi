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

        deepgram_prerecorded_from_bytes(b'\x00' * 100, model='nova-2-general', language='zh')

        call_args = mock_client.listen.rest.v.return_value.transcribe_file.call_args
        options = call_args[0][1]

        assert options['model'] == 'nova-2-general'
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
    def test_nova2_language_uses_correct_model(self, mock_get_model, mock_dg, mock_postprocess):
        """Chinese should use nova-2-general model."""
        from utils.chat import transcribe_pcm_bytes

        mock_get_model.return_value = ('zh', 'nova-2-general')
        mock_dg.return_value = [{'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': '你好'}]
        mock_seg = MagicMock()
        mock_seg.text = '你好'
        mock_postprocess.return_value = [mock_seg]

        text, lang = transcribe_pcm_bytes(b'\x00' * 100, 'test-uid', language='zh')

        call_kwargs = mock_dg.call_args[1]
        assert call_kwargs['model'] == 'nova-2-general'
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
                '/v2/voice-message/transcribe',
                content=b'\x00' * 3200,
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data['transcript'] == 'Hello world'
            assert data['language'] == 'en'
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

    def test_octet_stream_oversize_413(self):
        """Oversized octet-stream body should return 413."""
        client, module, saved = _make_chat_client()
        try:
            resp = client.post(
                '/v2/voice-message/transcribe',
                content=b'\x00' * (6 * 1024 * 1024),
                headers={'Content-Type': 'application/octet-stream'},
            )
            assert resp.status_code == 413
            assert 'too large' in resp.json()['detail']
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
