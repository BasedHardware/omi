"""Tests for offline sync transcription preferences parity (#6172).

Verifies that process_segment() applies user vocabulary, language, and model
selection matching the realtime transcription path.
"""

import os
import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level stubs: routers.sync has heavy transitive imports (Firestore,
# GCS, Firebase Admin) that require credentials.  We stub them out so unit
# tests can import process_segment without cloud access.
# ---------------------------------------------------------------------------

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
]:
    _full = f'database.{_sub}'
    if _full not in sys.modules:
        _m = MagicMock()
        sys.modules[_full] = _m
        setattr(_database_pkg, _sub, _m)

# Stub firebase_admin
_fb = MagicMock()
_fb.__path__ = ['firebase_admin']
sys.modules.setdefault('firebase_admin', _fb)
sys.modules.setdefault('firebase_admin.messaging', _fb.messaging)
sys.modules.setdefault('firebase_admin.auth', _fb.auth)

# Stub google.cloud.storage.Client to avoid GCS credentials
import google.cloud.storage as _gcs

_orig_storage_client = _gcs.Client
_gcs.Client = MagicMock

# Ensure env vars for modules that read them at import time
os.environ.setdefault('OPENAI_API_KEY', 'sk-fake-for-test')
os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


# ---------------------------------------------------------------------------
# deepgram_prerecorded: keywords parameter
# ---------------------------------------------------------------------------


class TestDeepgramPrerecordedKeywords:
    """Verify keywords are forwarded correctly to Deepgram options."""

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_keywords_nova3_uses_keyterm(self, mock_client):
        """Nova-3 model should use 'keyterm' option for keywords."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'detected_language': 'en',
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
                        ],
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        deepgram_prerecorded('http://example.com/audio.wav', model='nova-3', keywords=['Omi', 'Kelvin'])

        call_args = mock_client.listen.rest.v.return_value.transcribe_url.call_args
        options = call_args[0][1]
        assert 'keyterm' in options
        assert options['keyterm'] == ['Omi', 'Kelvin']
        assert 'keywords' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_keywords_nova2_uses_keywords(self, mock_client):
        """Nova-2 model should use 'keywords' option."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'detected_language': 'en',
                        'alternatives': [
                            {'words': [{'word': 'hi', 'start': 0, 'end': 0.3, 'speaker': 0, 'punctuated_word': 'Hi'}]}
                        ],
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        deepgram_prerecorded('http://example.com/audio.wav', model='nova-2-general', keywords=['Omi'])

        call_args = mock_client.listen.rest.v.return_value.transcribe_url.call_args
        options = call_args[0][1]
        assert 'keywords' in options
        assert options['keywords'] == ['Omi']
        assert 'keyterm' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_no_keywords_omits_option(self, mock_client):
        """When keywords is None or empty, no keyword option should be set."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'detected_language': 'en',
                        'alternatives': [
                            {'words': [{'word': 'ok', 'start': 0, 'end': 0.2, 'speaker': 0, 'punctuated_word': 'Ok'}]}
                        ],
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        deepgram_prerecorded('http://example.com/audio.wav', keywords=None)

        call_args = mock_client.listen.rest.v.return_value.transcribe_url.call_args
        options = call_args[0][1]
        assert 'keyterm' not in options
        assert 'keywords' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_empty_list_keywords_omits_option(self, mock_client):
        """When keywords is an empty list, no keyword option should be set."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'detected_language': 'en',
                        'alternatives': [
                            {'words': [{'word': 'ok', 'start': 0, 'end': 0.2, 'speaker': 0, 'punctuated_word': 'Ok'}]}
                        ],
                    }
                ]
            }
        }
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        deepgram_prerecorded('http://example.com/audio.wav', keywords=[])

        call_args = mock_client.listen.rest.v.return_value.transcribe_url.call_args
        options = call_args[0][1]
        assert 'keyterm' not in options
        assert 'keywords' not in options

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_keywords_preserved_on_retry(self, mock_client):
        """Keywords should be passed through on retry attempts."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary failure")
            mock_resp = MagicMock()
            mock_resp.to_dict.return_value = {
                'results': {
                    'channels': [
                        {
                            'detected_language': 'en',
                            'alternatives': [
                                {
                                    'words': [
                                        {'word': 'ok', 'start': 0, 'end': 0.2, 'speaker': 0, 'punctuated_word': 'Ok'}
                                    ]
                                }
                            ],
                        }
                    ]
                }
            }
            return mock_resp

        mock_client.listen.rest.v.return_value.transcribe_url.side_effect = side_effect

        deepgram_prerecorded('http://example.com/audio.wav', keywords=['TestWord'])

        # Second call (retry) should also have keywords
        retry_call = mock_client.listen.rest.v.return_value.transcribe_url.call_args_list[1]
        options = retry_call[0][1]
        assert 'keyterm' in options
        assert 'TestWord' in options['keyterm']

    @patch('utils.stt.pre_recorded._deepgram_client')
    def test_empty_transcript_with_keywords_and_return_language(self, mock_client):
        """Silence/noise with keywords and return_language should still return ([], lang)."""
        from utils.stt.pre_recorded import deepgram_prerecorded

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {'channels': [{'detected_language': 'fr', 'alternatives': [{'words': []}]}]}
        }
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        result = deepgram_prerecorded('http://example.com/audio.wav', return_language=True, keywords=['Omi'])
        assert result == ([], 'fr')


# ---------------------------------------------------------------------------
# process_segment: user preferences integration
# ---------------------------------------------------------------------------


class TestProcessSegmentPreferences:
    """Verify process_segment applies user transcription preferences."""

    def _make_mock_words(self):
        return [
            {'timestamp': [0.0, 0.5], 'speaker': 'SPEAKER_00', 'text': 'Hello'},
            {'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00', 'text': 'world'},
        ]

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_vocabulary_passed_to_deepgram(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """User vocabulary should be passed as keywords to deepgram_prerecorded."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': ['Kubernetes', 'FastAPI'], 'language': 'en', 'single_language_mode': False}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        mock_dg.assert_called_once()
        call_kwargs = mock_dg.call_args
        keywords = call_kwargs[1].get('keywords') or call_kwargs[0][8] if len(call_kwargs[0]) > 8 else None
        # Check via keyword arg
        _, kwargs = mock_dg.call_args
        assert 'keywords' in kwargs
        kw_list = kwargs['keywords']
        assert 'Omi' in kw_list
        assert 'Kubernetes' in kw_list
        assert 'FastAPI' in kw_list

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_single_language_mode_selects_model(
        self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        """Single language mode with a language should select the right model."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': [], 'language': 'en', 'single_language_mode': True}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        _, kwargs = mock_dg.call_args
        assert kwargs['language'] == 'en'
        assert kwargs['model'] == 'nova-3'

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_chinese_selects_nova2(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """Chinese language should select nova-2-general model."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'zh')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': [], 'language': 'zh', 'single_language_mode': True}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        _, kwargs = mock_dg.call_args
        assert kwargs['language'] == 'zh'
        assert kwargs['model'] == 'nova-2-general'

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_no_prefs_uses_defaults(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """Without preferences, should use multi/nova-3 defaults."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=None)

        _, kwargs = mock_dg.call_args
        assert kwargs['language'] == 'multi'
        assert kwargs['model'] == 'nova-3'
        # Vocabulary should still include "Omi" even without prefs
        assert 'Omi' in kwargs['keywords']

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_vocabulary_capped_at_100(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """Vocabulary should be capped at 100 items."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        large_vocab = [f'word_{i}' for i in range(150)]
        prefs = {'vocabulary': large_vocab, 'language': '', 'single_language_mode': False}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        _, kwargs = mock_dg.call_args
        assert len(kwargs['keywords']) <= 100
        # "Omi" must be preserved even after truncation
        assert 'Omi' in kwargs['keywords']

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_single_language_empty_language_falls_back(
        self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        """single_language_mode=True with empty language should fall back to multi/nova-3."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': [], 'language': '', 'single_language_mode': True}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        _, kwargs = mock_dg.call_args
        assert kwargs['language'] == 'multi'
        assert kwargs['model'] == 'nova-3'

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_multi_language_mode_default(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """Non-single-language mode should use multi-language detection."""
        from routers.sync import process_segment

        mock_dg.return_value = (self._make_mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': ['Custom'], 'language': 'fr', 'single_language_mode': False}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        _, kwargs = mock_dg.call_args
        assert kwargs['language'] == 'multi'
        assert kwargs['model'] == 'nova-3'

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    def test_single_language_trusts_user_language(
        self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        """Single-language mode should trust user's language, not Deepgram's detection."""
        from routers.sync import process_segment

        # Deepgram detects 'fr' but user chose 'en' in single-language mode
        mock_dg.return_value = (self._make_mock_words(), 'fr')
        mock_process.return_value = MagicMock(id='test-id')

        prefs = {'vocabulary': [], 'language': 'en', 'single_language_mode': True}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment('test/path.bin', 'uid123', response, lock, errors, transcription_prefs=prefs)

        # process_conversation should be called with user's language, not detected
        call_args = mock_process.call_args
        # The language arg is the second positional argument
        assert call_args[0][1] == 'en', "Should use user's language 'en', not Deepgram's detected 'fr'"


# ---------------------------------------------------------------------------
# Structural: endpoint wires transcription_prefs into threads
# ---------------------------------------------------------------------------


class TestSyncEndpointPrefsWiring:
    """Verify sync_local_files fetches prefs and passes to process_segment threads."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_endpoint_fetches_transcription_prefs(self):
        """sync_local_files must call get_user_transcription_preferences before threads."""
        source = self._read_sync_source()
        fn_start = source.index('async def sync_local_files(')
        fn_body = source[fn_start:]
        assert 'get_user_transcription_preferences' in fn_body

    def test_endpoint_passes_prefs_to_thread(self):
        """Each thread must receive transcription_prefs as an argument."""
        source = self._read_sync_source()
        fn_start = source.index('async def sync_local_files(')
        fn_body = source[fn_start:]
        assert 'transcription_prefs' in fn_body


# ---------------------------------------------------------------------------
# get_deepgram_model_for_language edge cases
# ---------------------------------------------------------------------------


class TestGetDeepgramModelForLanguage:
    """Verify model selection for edge-case language values."""

    def test_none_language_falls_back(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language(None)
        assert lang == 'multi'
        assert model == 'nova-3'

    def test_empty_string_falls_back(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('')
        assert lang == 'multi'
        assert model == 'nova-3'

    def test_multi_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('multi')
        assert lang == 'multi'
        assert model == 'nova-3'

    def test_chinese_returns_nova2(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('zh')
        assert lang == 'zh'
        assert model == 'nova-2-general'

    def test_english_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('en')
        assert lang == 'en'
        assert model == 'nova-3'

    def test_thai_returns_nova2(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('th')
        assert lang == 'th'
        assert model == 'nova-2-general'
