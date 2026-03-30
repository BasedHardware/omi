"""
Tests for batch translation in post-conversation processing.
Covers: resolve_translation_language, _batch_translate_segments, 24h hot window.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from enum import Enum

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")


def _ensure_mock_module(name: str):
    if name not in sys.modules:
        mod = MagicMock()
        mod.__path__ = []
        mod.__name__ = name
        mod.__loader__ = None
        mod.__spec__ = None
        mod.__package__ = name if '.' not in name else name.rsplit('.', 1)[0]
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database module and redis
_ensure_mock_module("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], '__path__', [])
for sub in [
    "_client",
    "redis_db",
    "auth",
    "users",
    "memories",
    "conversations",
    "apps",
    "vector_db",
    "notifications",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
]:
    _ensure_mock_module(f"database.{sub}")

mock_redis = MagicMock()
sys.modules["database.redis_db"].r = mock_redis

# Stub google.cloud.translate_v3
_ensure_mock_module("google")
sys.modules["google"].__path__ = []
_ensure_mock_module("google.cloud")
sys.modules["google.cloud"].__path__ = []
_ensure_mock_module("google.cloud.translate_v3")

mock_translate_v3 = sys.modules["google.cloud.translate_v3"]
mock_translate_v3.TranslationServiceClient = MagicMock

# Stub models.conversation with real-enough types for star import
# Need to provide the actual types that process_conversation.py uses from `from models.conversation import *`
conv_mock = _ensure_mock_module("models.conversation")


class _MockConversationStatus(str, Enum):
    in_progress = 'in_progress'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'


class _MockConversationSource(str, Enum):
    omi = 'omi'
    external = 'external'


conv_mock.ConversationStatus = _MockConversationStatus
conv_mock.ConversationSource = _MockConversationSource
conv_mock.Conversation = MagicMock
conv_mock.CreateConversation = MagicMock
conv_mock.ExternalIntegrationCreateConversation = MagicMock
conv_mock.ConversationPhoto = MagicMock
conv_mock.AudioFile = MagicMock
conv_mock.Structured = MagicMock
conv_mock.Geolocation = MagicMock
conv_mock.ConversationVisibility = MagicMock
conv_mock.AppResult = MagicMock
conv_mock.PluginResult = MagicMock
conv_mock.CalendarMeetingContext = MagicMock
conv_mock.__all__ = [
    'ConversationStatus',
    'ConversationSource',
    'Conversation',
    'CreateConversation',
    'ExternalIntegrationCreateConversation',
    'ConversationPhoto',
    'AudioFile',
    'Structured',
    'Geolocation',
    'ConversationVisibility',
    'AppResult',
    'PluginResult',
    'CalendarMeetingContext',
]

# Stub all other heavy dependencies
for mod in [
    "utils.llm",
    "utils.llm.memories",
    "utils.llm.conversation_processing",
    "utils.llm.external_integrations",
    "utils.llm.trends",
    "utils.llm.goals",
    "utils.llm.chat",
    "utils.llm.clients",
    "utils.llm.usage_tracker",
    "utils.notifications",
    "utils.apps",
    "utils.analytics",
    "utils.other",
    "utils.other.hume",
    "utils.other.storage",
    "utils.retrieval",
    "utils.retrieval.rag",
    "utils.webhooks",
    "utils.app_integrations",
    "utils.task_sync",
    "utils.pusher",
    "utils.speaker_identification",
    "models.app",
    "models.memories",
    "models.other",
    "models.task",
    "models.trend",
    "models.notification_message",
    "models.users",
]:
    _ensure_mock_module(mod)

# Force reimport to pick up mocks
for mod_name in list(sys.modules.keys()):
    if 'process_conversation' in mod_name and 'test' not in mod_name:
        del sys.modules[mod_name]
    if 'translation' in mod_name and 'test' not in mod_name:
        del sys.modules[mod_name]

from utils.translation import detect_language
from utils.translation_cache import should_persist_translation
from utils.conversations.process_conversation import (
    resolve_translation_language,
    _batch_translate_segments,
    TRANSLATION_HOT_WINDOW_HOURS,
)
from models.transcript_segment import TranscriptSegment, Translation


def _make_segment(id: str, text: str, translations=None):
    return TranscriptSegment(
        id=id,
        text=text,
        speaker="SPEAKER_00",
        speaker_id=0,
        is_user=False,
        start=0.0,
        end=1.0,
        translations=translations or [],
    )


def _make_conversation(segments, started_at=None, language="en"):
    """Create a mock Conversation object."""
    conv = MagicMock()
    conv.id = "test-conv-123"
    conv.language = language
    conv.started_at = started_at or datetime.now(timezone.utc)
    conv.transcript_segments = segments
    return conv


class TestResolveTranslationLanguage:
    def test_single_language_mode_returns_none(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': True}
            result = resolve_translation_language("uid-1")
            assert result is None

    def test_multi_language_mode_with_conversation_language(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': False}
            result = resolve_translation_language("uid-1", "fr")
            assert result == "fr"

    def test_multi_language_mode_falls_back_to_user_preference(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': False}
            mock_users.get_user_language_preference.return_value = "ja"
            result = resolve_translation_language("uid-1", None)
            assert result == "ja"

    def test_no_language_available_returns_none(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': False}
            mock_users.get_user_language_preference.return_value = ""
            result = resolve_translation_language("uid-1", None)
            assert result is None

    def test_default_prefs_are_multi_language(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {}
            mock_users.get_user_language_preference.return_value = "en"
            result = resolve_translation_language("uid-1")
            assert result == "en"

    def test_multi_conversation_language_falls_back_to_user_pref(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': False}
            mock_users.get_user_language_preference.return_value = "en"
            result = resolve_translation_language("uid-1", "multi")
            assert result == "en"

    def test_multi_conversation_language_without_user_pref_returns_none(self):
        with patch('utils.conversations.process_conversation.users_db') as mock_users:
            mock_users.get_user_transcription_preferences.return_value = {'single_language_mode': False}
            mock_users.get_user_language_preference.return_value = ""
            result = resolve_translation_language("uid-1", "multi")
            assert result is None


class TestBatchTranslateSegments:
    def test_skips_when_translation_disabled(self):
        segments = [_make_segment("s1", "Bonjour le monde")]
        conv = _make_conversation(segments)
        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value=None):
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_skips_empty_segments(self):
        conv = _make_conversation([])
        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"):
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_skips_old_conversations(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        segments = [_make_segment("s1", "Bonjour le monde")]
        conv = _make_conversation(segments, started_at=old_time)
        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"):
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_translates_recent_conversations(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [_make_segment("s1", "Bonjour le monde")]
        conv = _make_conversation(segments, started_at=recent_time)

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', return_value="fr"
        ), patch('utils.conversations.process_conversation.TranslationService') as mock_ts_cls:
            mock_service = MagicMock()
            mock_service.translate_text_by_sentence.return_value = ("Hello world", "fr")
            mock_ts_cls.return_value = mock_service

            result = _batch_translate_segments("uid-1", conv)
            assert result is True
            assert len(segments[0].translations) == 1
            assert segments[0].translations[0].text == "Hello world"
            assert segments[0].translations[0].lang == "en"

    def test_skips_same_language_segments(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [_make_segment("s1", "Hello world, how are you today?")]
        conv = _make_conversation(segments, started_at=recent_time)

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', return_value="en"
        ):
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_skips_segments_with_existing_translation(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        existing_trans = Translation(lang="en", text="Hello world")
        segments = [_make_segment("s1", "Bonjour le monde", translations=[existing_trans])]
        conv = _make_conversation(segments, started_at=recent_time)

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"):
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_inconclusive_detection_still_translates(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [_make_segment("s1", "short text")]
        conv = _make_conversation(segments, started_at=recent_time)

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', return_value=None
        ), patch('utils.conversations.process_conversation.TranslationService') as mock_ts_cls:
            mock_service = MagicMock()
            mock_service.translate_text_by_sentence.return_value = ("short text", "en")
            mock_ts_cls.return_value = mock_service

            # should_persist_translation returns False because text is unchanged
            result = _batch_translate_segments("uid-1", conv)
            assert result is False

    def test_noop_translation_not_persisted(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [_make_segment("s1", "Hello world")]
        conv = _make_conversation(segments, started_at=recent_time)

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', return_value=None
        ), patch('utils.conversations.process_conversation.TranslationService') as mock_ts_cls:
            mock_service = MagicMock()
            mock_service.translate_text_by_sentence.return_value = ("Hello world", "en")
            mock_ts_cls.return_value = mock_service

            result = _batch_translate_segments("uid-1", conv)
            assert result is False
            assert len(segments[0].translations) == 0

    def test_multiple_foreign_segments_translated(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [
            _make_segment("s1", "Bonjour le monde"),
            _make_segment("s2", "Comment allez-vous"),
            _make_segment("s3", "Hello world"),
        ]
        conv = _make_conversation(segments, started_at=recent_time)

        def mock_detect(text):
            if "Bonjour" in text or "Comment" in text:
                return "fr"
            return "en"

        def mock_translate(lang, text):
            if "Bonjour" in text:
                return ("Hello world", "fr")
            if "Comment" in text:
                return ("How are you", "fr")
            return (text, "en")

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', side_effect=mock_detect
        ), patch('utils.conversations.process_conversation.TranslationService') as mock_ts_cls:
            mock_service = MagicMock()
            mock_service.translate_text_by_sentence.side_effect = mock_translate
            mock_ts_cls.return_value = mock_service

            result = _batch_translate_segments("uid-1", conv)
            assert result is True
            assert len(segments[0].translations) == 1
            assert segments[0].translations[0].text == "Hello world"
            assert len(segments[1].translations) == 1
            assert segments[1].translations[0].text == "How are you"
            assert len(segments[2].translations) == 0

    def test_translation_error_continues(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        segments = [
            _make_segment("s1", "Bonjour le monde"),
            _make_segment("s2", "Hola mundo"),
        ]
        conv = _make_conversation(segments, started_at=recent_time)

        call_count = [0]

        def mock_translate(lang, text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("API error")
            return ("Hello world", "es")

        with patch('utils.conversations.process_conversation.resolve_translation_language', return_value="en"), patch(
            'utils.conversations.process_conversation.detect_language', return_value="fr"
        ), patch('utils.conversations.process_conversation.TranslationService') as mock_ts_cls:
            mock_service = MagicMock()
            mock_service.translate_text_by_sentence.side_effect = mock_translate
            mock_ts_cls.return_value = mock_service

            result = _batch_translate_segments("uid-1", conv)
            assert result is True
            assert len(segments[0].translations) == 0  # failed
            assert len(segments[1].translations) == 1  # succeeded


class TestHotWindowConstant:
    def test_hot_window_is_24_hours(self):
        assert TRANSLATION_HOT_WINDOW_HOURS == 24
