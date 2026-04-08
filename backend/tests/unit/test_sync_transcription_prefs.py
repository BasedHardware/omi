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
    def test_chinese_selects_nova3(self, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process):
        """Chinese language should select nova-3 model."""
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
        assert kwargs['model'] == 'nova-3'

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

    def test_chinese_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('zh')
        assert lang == 'zh'
        assert model == 'nova-3'

    def test_english_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('en')
        assert lang == 'en'
        assert model == 'nova-3'

    def test_thai_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('th')
        assert lang == 'th'
        assert model == 'nova-3'

    def test_arabic_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('ar')
        assert lang == 'ar'
        assert model == 'nova-3'

    def test_tamil_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('ta')
        assert lang == 'ta'
        assert model == 'nova-3'

    def test_locale_tagged_zh_tw_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('zh-TW')
        assert lang == 'zh-TW'
        assert model == 'nova-3'

    def test_locale_tagged_th_th_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('th-TH')
        assert lang == 'th-TH'
        assert model == 'nova-3'

    def test_locale_tagged_ar_ae_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('ar-AE')
        assert lang == 'ar-AE'
        assert model == 'nova-3'

    def test_locale_tagged_ko_kr_returns_nova3(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('ko-KR')
        assert lang == 'ko-KR'
        assert model == 'nova-3'

    def test_unsupported_language_falls_back_to_multi(self):
        from utils.stt.pre_recorded import get_deepgram_model_for_language

        lang, model = get_deepgram_model_for_language('xx-INVALID')
        assert lang == 'multi'
        assert model == 'nova-3'


# ---------------------------------------------------------------------------
# Speaker identification for sync path
# ---------------------------------------------------------------------------

import io
import struct
import wave

import numpy as np


def _make_wav_bytes(duration_sec: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate silent WAV bytes of the given duration for testing."""
    n_samples = int(duration_sec * sample_rate)
    samples = b'\x00\x00' * n_samples  # 16-bit silence
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples)
    return buf.getvalue()


def _make_transcript_segment(speaker_id, start, end, text='hello', seg_id=None):
    """Create a TranscriptSegment-like object for testing."""
    from models.transcript_segment import TranscriptSegment

    seg = TranscriptSegment(
        text=text,
        speaker='SPEAKER_{:02d}'.format(speaker_id),
        speaker_id=speaker_id,
        is_user=False,
        start=start,
        end=end,
    )
    if seg_id:
        seg.id = seg_id
    return seg


class TestBuildPersonEmbeddingsCache:
    """Verify build_person_embeddings_cache loads user + people embeddings."""

    @patch('routers.sync.users_db')
    def test_loads_user_embedding(self, mock_users_db):
        from routers.sync import build_person_embeddings_cache

        mock_users_db.get_user_speaker_embedding.return_value = [0.1] * 512
        mock_users_db.get_people.return_value = []

        cache = build_person_embeddings_cache('uid1')

        assert 'user' in cache
        assert cache['user']['name'] == 'User'
        assert cache['user']['embedding'].shape == (1, 512)

    @patch('routers.sync.users_db')
    def test_loads_people_embeddings(self, mock_users_db):
        from routers.sync import build_person_embeddings_cache

        mock_users_db.get_user_speaker_embedding.return_value = None
        mock_users_db.get_people.return_value = [
            {'id': 'p1', 'name': 'Alice', 'speaker_embedding': [0.2] * 512},
            {'id': 'p2', 'name': 'Bob'},  # no embedding
            {'id': 'p3', 'name': 'Carol', 'speaker_embedding': [0.3] * 512},
        ]

        cache = build_person_embeddings_cache('uid1')

        assert 'user' not in cache
        assert 'p1' in cache
        assert 'p2' not in cache
        assert 'p3' in cache
        assert cache['p1']['name'] == 'Alice'

    @patch('routers.sync.users_db')
    def test_empty_when_no_embeddings(self, mock_users_db):
        from routers.sync import build_person_embeddings_cache

        mock_users_db.get_user_speaker_embedding.return_value = None
        mock_users_db.get_people.return_value = []

        cache = build_person_embeddings_cache('uid1')
        assert cache == {}


class TestExtractSpeakerClipWav:
    """Verify _extract_speaker_clip_wav clips audio correctly."""

    def test_extracts_clip(self):
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=5.0)
        clip = _extract_speaker_clip_wav(audio, 1.0, 3.0)
        assert clip is not None
        # Verify it's valid WAV
        with wave.open(io.BytesIO(clip), 'rb') as wf:
            clip_duration = wf.getnframes() / wf.getframerate()
            assert 1.8 < clip_duration < 2.2  # ~2 seconds

    def test_returns_none_for_short_clip(self):
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=5.0)
        clip = _extract_speaker_clip_wav(audio, 1.0, 1.5)  # only 0.5s < 1.0s threshold
        assert clip is None

    def test_caps_at_10_seconds(self):
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=20.0)
        clip = _extract_speaker_clip_wav(audio, 0.0, 15.0)
        assert clip is not None
        with wave.open(io.BytesIO(clip), 'rb') as wf:
            clip_duration = wf.getnframes() / wf.getframerate()
            assert clip_duration <= 10.1  # should be capped at ~10s

    def test_clamps_to_audio_bounds(self):
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=3.0)
        clip = _extract_speaker_clip_wav(audio, -1.0, 5.0)
        assert clip is not None
        with wave.open(io.BytesIO(clip), 'rb') as wf:
            clip_duration = wf.getnframes() / wf.getframerate()
            assert 2.8 < clip_duration < 3.2


class TestIdentifySpeakersForSegments:
    """Verify identify_speakers_for_segments matches speakers and applies assignments."""

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_voice_match_assigns_person(self, mock_extract):
        from routers.sync import identify_speakers_for_segments

        # Create a "matching" embedding — same as Alice's
        alice_emb = np.ones((1, 512), dtype=np.float32)
        mock_extract.return_value = alice_emb

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
        }

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=1, start=3.0, end=4.0, text='world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Both segments should be assigned to Alice (speaker_id 1 -> person p1)
        assert segments[0].person_id == 'p1'
        assert segments[1].person_id == 'p1'
        assert not segments[0].is_user
        assert not segments[1].is_user

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_user_match_sets_is_user(self, mock_extract):
        from routers.sync import identify_speakers_for_segments

        user_emb = np.ones((1, 512), dtype=np.float32)
        mock_extract.return_value = user_emb

        cache = {
            'user': {'embedding': user_emb, 'name': 'User'},
        }

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1'),
        ]

        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        assert segments[0].is_user is True
        assert segments[0].person_id is None

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_no_match_above_threshold(self, mock_extract):
        from routers.sync import identify_speakers_for_segments

        # Return an embedding far from the cached one
        mock_extract.return_value = np.ones((1, 512), dtype=np.float32)
        far_emb = -np.ones((1, 512), dtype=np.float32)

        cache = {
            'p1': {'embedding': far_emb, 'name': 'Alice'},
        }

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1'),
        ]

        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # No match — segments should remain unassigned
        assert segments[0].person_id is None
        assert not segments[0].is_user

    @patch('routers.sync.users_db')
    @patch('routers.sync.extract_embedding_from_bytes')
    def test_text_detection_fallback(self, mock_extract, mock_users_db):
        from routers.sync import identify_speakers_for_segments

        # Embedding extraction fails (too short clip), so voice matching skips
        mock_extract.side_effect = ValueError("Audio too short")
        mock_users_db.get_person_by_name.return_value = {'id': 'p2', 'name': 'Bob'}

        cache = {'p1': {'embedding': np.ones((1, 512), dtype=np.float32), 'name': 'Alice'}}

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='my name is Bob', seg_id='s1'),
        ]

        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Text detection should match "Bob" and assign person_id
        assert segments[0].person_id == 'p2'

    @patch('routers.sync.users_db')
    def test_empty_cache_still_runs_text_detection(self, mock_users_db):
        from routers.sync import identify_speakers_for_segments

        mock_users_db.get_person_by_name.return_value = {'id': 'p1', 'name': 'Alice'}

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='my name is Alice', seg_id='s1'),
        ]

        # Empty cache + no audio — text detection should still run
        identify_speakers_for_segments(segments, None, {}, 'uid1')

        assert segments[0].person_id == 'p1'

    @patch('routers.sync.users_db')
    def test_no_audio_still_runs_text_detection(self, mock_users_db):
        from routers.sync import identify_speakers_for_segments

        mock_users_db.get_person_by_name.return_value = {'id': 'p2', 'name': 'Bob'}

        cache = {'p1': {'embedding': np.ones((1, 512), dtype=np.float32), 'name': 'Alice'}}

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='I am Bob', seg_id='s1'),
        ]

        # Cache exists but audio is None — voice matching skipped, text detection runs
        identify_speakers_for_segments(segments, None, cache, 'uid1')

        assert segments[0].person_id == 'p2'

    @patch('routers.sync.users_db')
    def test_undiarized_text_detection_assigns_per_segment(self, mock_users_db):
        from routers.sync import identify_speakers_for_segments

        mock_users_db.get_person_by_name.return_value = {'id': 'p1', 'name': 'Alice'}

        # speaker_id=0 (undiarized) — should still get per-segment assignment
        segments = [
            _make_transcript_segment(speaker_id=0, start=0.0, end=2.0, text='my name is Alice', seg_id='s1'),
            _make_transcript_segment(speaker_id=0, start=3.0, end=4.0, text='hello there', seg_id='s2'),
        ]

        identify_speakers_for_segments(segments, None, {}, 'uid1')

        # First segment matched via text detection
        assert segments[0].person_id == 'p1'
        # Second segment has no text match — should remain unassigned
        # (speaker_to_person_map not updated for speaker_id=0)
        assert segments[1].person_id is None

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_short_segments_skip_embedding(self, mock_extract):
        from routers.sync import identify_speakers_for_segments

        cache = {'p1': {'embedding': np.ones((1, 512), dtype=np.float32), 'name': 'Alice'}}

        # All segments under 1.0s — too short for embedding extraction
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=0.5, text='hi', seg_id='s1'),
            _make_transcript_segment(speaker_id=1, start=1.0, end=1.3, text='ok', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # extract_embedding_from_bytes should not have been called
        mock_extract.assert_not_called()
        assert segments[0].person_id is None

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_multiple_speakers_matched(self, mock_extract):
        from routers.sync import identify_speakers_for_segments

        alice_emb = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        bob_emb = np.array([[0.0, 1.0] + [0.0] * 510], dtype=np.float32)

        # Return different embeddings based on call order
        mock_extract.side_effect = [alice_emb, bob_emb]

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
            'p2': {'embedding': bob_emb, 'name': 'Bob'},
        }

        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=3.0, end=5.0, text='world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=6.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        assert segments[0].person_id == 'p1'
        assert segments[1].person_id == 'p2'

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_matched_person_not_reused_across_speakers(self, mock_extract):
        """Once a person matches a speaker, they are excluded from candidates for other speakers.
        Leverages diarization speaker count to reduce embedding distance calculations."""
        from routers.sync import identify_speakers_for_segments

        alice_emb = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        # Both speakers return embeddings close to Alice
        mock_extract.side_effect = [alice_emb, alice_emb]

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
        }

        # Speaker 1 has longer total duration, so it gets matched first
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=3.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=4.0, end=6.0, text='world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=7.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Speaker 1 (longer) matches Alice
        assert segments[0].person_id == 'p1'
        # Speaker 2 should NOT match Alice again — person already used
        assert segments[1].person_id is None

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_best_clip_speaker_matched_first(self, mock_extract):
        """Speakers are sorted by best single segment (clip quality) not total duration."""
        from routers.sync import identify_speakers_for_segments

        alice_emb = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        # Both speakers return embeddings close to Alice
        mock_extract.side_effect = [alice_emb, alice_emb]

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
        }

        # Speaker 1 has MORE total duration (3 x 1.2s = 3.6s) but shorter best clip (1.2s)
        # Speaker 2 has LESS total duration (3.0s) but longer best clip (3.0s)
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=1.2, text='hi', seg_id='s1a'),
            _make_transcript_segment(speaker_id=1, start=2.0, end=3.2, text='there', seg_id='s1b'),
            _make_transcript_segment(speaker_id=1, start=4.0, end=5.2, text='friend', seg_id='s1c'),
            _make_transcript_segment(speaker_id=2, start=6.0, end=9.0, text='hello world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=10.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Speaker 2 (best clip 3.0s) matched first despite lower total, gets Alice
        assert segments[3].person_id == 'p1'
        # Speaker 1 (best clip 1.2s) can't match — Alice already taken
        assert segments[0].person_id is None

    @patch('routers.sync.compare_embeddings')
    @patch('routers.sync.extract_embedding_from_bytes')
    def test_dedup_skips_matched_candidates_in_comparison(self, mock_extract, mock_compare):
        """Verify compare_embeddings is NOT called for already-matched person IDs."""
        from routers.sync import identify_speakers_for_segments

        emb_a = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        emb_b = np.array([[0.0, 1.0] + [0.0] * 510], dtype=np.float32)
        mock_extract.side_effect = [emb_a, emb_b]

        cache = {
            'p1': {'embedding': emb_a, 'name': 'Alice'},
            'p2': {'embedding': emb_b, 'name': 'Bob'},
        }

        # Speaker 1 has better clip (3s vs 2s), so matched first
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=3.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=4.0, end=6.0, text='world', seg_id='s2'),
        ]

        # Speaker 1 compares against p1 (0.1) and p2 (0.9) → matches p1
        # Speaker 2 should only compare against p2 (p1 already matched)
        mock_compare.side_effect = [0.1, 0.9, 0.15]

        audio = _make_wav_bytes(duration_sec=7.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # 3 calls total: speaker1 vs p1, speaker1 vs p2, speaker2 vs p2 only
        assert mock_compare.call_count == 3
        assert segments[0].person_id == 'p1'
        assert segments[1].person_id == 'p2'

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_dedup_falls_back_to_next_candidate(self, mock_extract):
        """When best candidate is taken, second speaker falls back to next-best match."""
        from routers.sync import identify_speakers_for_segments

        alice_emb = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        bob_emb = np.array([[0.0, 1.0] + [0.0] * 510], dtype=np.float32)
        # Speaker 1 returns embedding close to Alice; Speaker 2 also close to Alice but falls back to Bob
        mixed_emb = np.array([[0.7, 0.7] + [0.0] * 510], dtype=np.float32)
        mock_extract.side_effect = [alice_emb, mixed_emb]

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
            'p2': {'embedding': bob_emb, 'name': 'Bob'},
        }

        # Speaker 1 (3s clip) gets Alice, Speaker 2 (2s clip) should fall back to Bob
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=3.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=4.0, end=6.0, text='world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=7.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        assert segments[0].person_id == 'p1'
        # Speaker 2's mixed_emb vs bob_emb cosine distance ≈ 0.293, under threshold 0.45.
        # Alice (p1) is taken, so Bob (p2) is the only remaining candidate and matches.
        assert segments[1].person_id == 'p2'

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_equal_best_clip_stable_order(self, mock_extract):
        """When speakers have equal best clip duration, stable input order is preserved."""
        from routers.sync import identify_speakers_for_segments

        alice_emb = np.array([[1.0] + [0.0] * 511], dtype=np.float32)
        bob_emb = np.array([[0.0, 1.0] + [0.0] * 510], dtype=np.float32)
        mock_extract.side_effect = [alice_emb, bob_emb]

        cache = {
            'p1': {'embedding': alice_emb, 'name': 'Alice'},
            'p2': {'embedding': bob_emb, 'name': 'Bob'},
        }

        # Both speakers have identical best clip duration (2.0s)
        segments = [
            _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=3.0, end=5.0, text='world', seg_id='s2'),
        ]

        audio = _make_wav_bytes(duration_sec=6.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Both should still match correctly regardless of tie ordering
        assert segments[0].person_id == 'p1'
        assert segments[1].person_id == 'p2'


class TestProcessSegmentSpeakerIdIntegration:
    """Verify process_segment wires speaker identification correctly."""

    @staticmethod
    def _mock_words():
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
    @patch('routers.sync.identify_speakers_for_segments')
    @patch('routers.sync._download_audio_bytes')
    def test_speaker_id_called_when_cache_provided(
        self, mock_download, mock_identify, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        from routers.sync import process_segment

        mock_dg.return_value = (self._mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')
        mock_download.return_value = b'fake-audio-bytes'

        cache = {'p1': {'embedding': np.ones((1, 512)), 'name': 'Alice'}}

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment(
            'test/path.bin',
            'uid123',
            response,
            lock,
            errors,
            person_embeddings_cache=cache,
        )

        mock_download.assert_called_once()
        mock_identify.assert_called_once()

    @patch('routers.sync.process_conversation')
    @patch('routers.sync.get_closest_conversation_to_timestamps', return_value=None)
    @patch('routers.sync.get_timestamp_from_path', return_value=1700000000)
    @patch('routers.sync.deepgram_prerecorded')
    @patch('routers.sync.delete_syncing_temporal_file')
    @patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='http://example.com/audio.wav')
    @patch('routers.sync.identify_speakers_for_segments')
    @patch('routers.sync._download_audio_bytes')
    def test_no_cache_skips_download_but_runs_identification(
        self, mock_download, mock_identify, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        from routers.sync import process_segment

        mock_dg.return_value = (self._mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        process_segment(
            'test/path.bin',
            'uid123',
            response,
            lock,
            errors,
            person_embeddings_cache=None,
        )

        # Should not attempt to download audio when no cache
        mock_download.assert_not_called()
        # Should still run identification (for text-based detection)
        mock_identify.assert_called_once()


class TestSyncEndpointSpeakerIdWiring:
    """Verify sync_local_files builds speaker embeddings cache."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_endpoint_builds_embeddings_cache(self):
        """sync_local_files must call build_person_embeddings_cache."""
        source = self._read_sync_source()
        fn_start = source.index('async def sync_local_files(')
        fn_body = source[fn_start:]
        assert 'build_person_embeddings_cache' in fn_body

    def test_endpoint_passes_cache_to_thread(self):
        """Each thread must receive person_embeddings_cache as an argument."""
        source = self._read_sync_source()
        fn_start = source.index('async def sync_local_files(')
        fn_body = source[fn_start:]
        assert 'person_embeddings_cache' in fn_body


# ---------------------------------------------------------------------------
# Additional coverage: download, exception handling, boundaries, propagation
# ---------------------------------------------------------------------------


class TestDownloadAudioBytes:
    """Verify _download_audio_bytes handles success and failure."""

    @patch('routers.sync.requests')
    def test_download_success(self, mock_requests):
        from routers.sync import _download_audio_bytes

        mock_resp = MagicMock()
        mock_resp.content = b'wav-bytes'
        mock_resp.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_resp

        result = _download_audio_bytes('http://example.com/audio.wav')
        assert result == b'wav-bytes'
        mock_requests.get.assert_called_once_with('http://example.com/audio.wav', timeout=60)

    @patch('routers.sync.requests')
    def test_download_failure_returns_none(self, mock_requests):
        from routers.sync import _download_audio_bytes

        mock_requests.get.side_effect = Exception("Connection refused")

        result = _download_audio_bytes('http://example.com/audio.wav')
        assert result is None


class TestSpeakerIdExceptionHandling:
    """Verify process_segment swallows speaker ID exceptions gracefully."""

    @staticmethod
    def _mock_words():
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
    @patch('routers.sync.identify_speakers_for_segments', side_effect=RuntimeError("embedding API down"))
    @patch('routers.sync._download_audio_bytes', return_value=b'audio')
    def test_speaker_id_exception_does_not_break_processing(
        self, mock_download, mock_identify, mock_url, mock_delete, mock_dg, mock_ts, mock_closest, mock_process
    ):
        from routers.sync import process_segment

        mock_dg.return_value = (self._mock_words(), 'en')
        mock_process.return_value = MagicMock(id='test-id')

        cache = {'p1': {'embedding': np.ones((1, 512)), 'name': 'Alice'}}
        response = {'new_memories': set(), 'updated_memories': set()}
        lock = threading.Lock()
        errors = []

        # Should not raise — exception is caught and logged
        process_segment(
            'test/path.bin',
            'uid123',
            response,
            lock,
            errors,
            person_embeddings_cache=cache,
        )

        # Conversation should still be created despite speaker ID failure
        mock_process.assert_called_once()
        assert 'test-id' in response['new_memories']


class TestSpeakerIdBoundaries:
    """Verify boundary conditions for speaker identification."""

    def test_exact_threshold_clip_duration(self):
        """Clip exactly at SPEAKER_ID_MIN_AUDIO (1.0s) should be extracted."""
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=5.0)
        clip = _extract_speaker_clip_wav(audio, 1.0, 2.0)  # exactly 1.0s
        assert clip is not None
        with wave.open(io.BytesIO(clip), 'rb') as wf:
            duration = wf.getnframes() / wf.getframerate()
            assert 0.9 < duration < 1.1

    def test_just_below_threshold_clip_duration(self):
        """Clip just below 1.0s threshold should return None."""
        from routers.sync import _extract_speaker_clip_wav

        audio = _make_wav_bytes(duration_sec=5.0)
        clip = _extract_speaker_clip_wav(audio, 1.0, 1.99)  # 0.99s < 1.0s
        assert clip is None

    @patch('routers.sync.extract_embedding_from_bytes')
    def test_speaker_id_none_normalized_to_zero(self, mock_extract):
        """Segments with speaker_id=None should be treated as speaker_id=0."""
        from routers.sync import identify_speakers_for_segments

        mock_extract.return_value = np.ones((1, 512), dtype=np.float32)

        cache = {'p1': {'embedding': np.ones((1, 512), dtype=np.float32), 'name': 'Alice'}}

        seg = _make_transcript_segment(speaker_id=1, start=0.0, end=2.0, text='hello', seg_id='s1')
        seg.speaker_id = None  # Override to None

        segments = [seg]
        audio = _make_wav_bytes(duration_sec=5.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Should be grouped under speaker_id=0, and still get voice matched
        assert segments[0].person_id == 'p1'

    @patch('routers.sync.users_db')
    @patch('routers.sync.extract_embedding_from_bytes')
    def test_diarized_text_match_propagates_to_all_speaker_segments(self, mock_extract, mock_users_db):
        """When text detection matches a diarized speaker, all segments with that speaker_id get assigned."""
        from routers.sync import identify_speakers_for_segments

        # Embedding doesn't match anyone
        mock_extract.return_value = np.zeros((1, 512), dtype=np.float32)
        far_emb = np.ones((1, 512), dtype=np.float32)
        cache = {'p1': {'embedding': far_emb, 'name': 'Alice'}}

        mock_users_db.get_person_by_name.return_value = {'id': 'p2', 'name': 'Bob'}

        segments = [
            _make_transcript_segment(speaker_id=2, start=0.0, end=2.0, text='my name is Bob', seg_id='s1'),
            _make_transcript_segment(speaker_id=2, start=3.0, end=4.0, text='how are you', seg_id='s2'),
            _make_transcript_segment(speaker_id=2, start=5.0, end=6.0, text='goodbye', seg_id='s3'),
        ]

        audio = _make_wav_bytes(duration_sec=7.0)
        identify_speakers_for_segments(segments, audio, cache, 'uid1')

        # Text detection matched "Bob" on s1 → speaker_to_person_map[2] = p2
        # All speaker_id=2 segments should be assigned via speaker_to_person_map
        assert segments[0].person_id == 'p2'
        assert segments[1].person_id == 'p2'
        assert segments[2].person_id == 'p2'
