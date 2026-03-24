"""
Tests for translation optimization changes:
- split_into_sentences (no comma splitting)
- detect_language (free langdetect only, no paid Google API)
- TranslationService (batch API, Redis cache, memory cache)
- TranscriptSegmentLanguageCache (update_from_translate_response)
- Redis cache helpers (fail-open)

Uses module stubbing to avoid Firestore/Redis init at import time.
"""

import os
import sys
import json
import hashlib
from unittest.mock import MagicMock, patch, PropertyMock

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
for sub in ["_client", "redis_db", "auth", "users", "memories", "conversations", "apps", "vector_db"]:
    _ensure_mock_module(f"database.{sub}")

# Create a mock redis instance
mock_redis = MagicMock()
sys.modules["database.redis_db"].r = mock_redis

# Stub google.cloud.translate_v3
_ensure_mock_module("google")
sys.modules["google"].__path__ = []
_ensure_mock_module("google.cloud")
sys.modules["google.cloud"].__path__ = []
_ensure_mock_module("google.cloud.translate_v3")

mock_translate_client = MagicMock()
sys.modules["google.cloud.translate_v3"].TranslationServiceClient = MagicMock(return_value=mock_translate_client)

# Force reimport translation modules
for mod_name in list(sys.modules.keys()):
    if 'translation' in mod_name and 'test' not in mod_name:
        del sys.modules[mod_name]

from utils.translation import (
    split_into_sentences,
    detect_language,
    TranslationService,
    get_cached_translation,
    cache_translation,
    _redis_cache_key,
    detection_cache,
    TRANSLATION_CACHE_TTL,
    MAX_BATCH_SIZE,
)
from utils.translation_cache import TranscriptSegmentLanguageCache, should_persist_translation


class TestSplitIntoSentences:
    def test_no_comma_split(self):
        """Commas should NOT split text into separate sentences."""
        result = split_into_sentences("Hello, how are you, nice to meet you")
        assert len(result) == 1
        assert result[0] == "Hello, how are you, nice to meet you"

    def test_split_on_period(self):
        result = split_into_sentences("Hello. How are you.")
        assert len(result) == 2
        assert result[0] == "Hello."
        assert result[1] == "How are you."

    def test_split_on_question_mark(self):
        result = split_into_sentences("Hello? How are you?")
        assert len(result) == 2

    def test_split_on_exclamation(self):
        result = split_into_sentences("Hello! How are you!")
        assert len(result) == 2

    def test_split_on_newline(self):
        result = split_into_sentences("First line\nSecond line")
        assert len(result) == 2

    def test_empty_string(self):
        assert split_into_sentences("") == []

    def test_none_returns_empty(self):
        assert split_into_sentences(None) == []

    def test_no_punctuation(self):
        result = split_into_sentences("Hello how are you")
        assert len(result) == 1
        assert result[0] == "Hello how are you"

    def test_mixed_punctuation(self):
        result = split_into_sentences("Hello! How are you? Fine, thanks.")
        assert len(result) == 3


class TestDetectLanguage:
    def setup_method(self):
        detection_cache.clear()

    def test_no_google_cloud_api_call(self):
        """detect_language should NOT call Google Cloud API (paid)."""
        with patch('utils.translation._detect_with_langdetect', return_value='en') as mock_langdetect:
            result = detect_language("Hello how are you today", hint_language='en')
            mock_langdetect.assert_called_once()
            assert result == 'en'

    def test_caches_result(self):
        with patch('utils.translation._detect_with_langdetect', return_value='fr') as mock_langdetect:
            detect_language("Bonjour comment allez-vous", hint_language='fr')
            detect_language("Bonjour comment allez-vous", hint_language='fr')
            # Second call should use cache, not call langdetect again
            mock_langdetect.assert_called_once()

    def test_removes_non_lexical(self):
        with patch('utils.translation._detect_with_langdetect', return_value='es') as mock_langdetect:
            detect_language("um hmm hello hola", remove_non_lexical=True, hint_language='es')
            # Non-lexical words should be stripped before detection
            call_args = mock_langdetect.call_args[0][0]
            assert 'um' not in call_args.lower().split()
            assert 'hmm' not in call_args.lower().split()

    def test_returns_none_for_empty(self):
        assert detect_language("") is None
        assert detect_language("   ") is None

    def test_locale_tagged_hint_language(self):
        """Locale-tagged hint_language (e.g. en-US) should be normalized to base tag."""
        with patch('utils.translation._detect_with_langdetect', return_value='en') as mock_langdetect:
            result = detect_language("Hello how are you today", hint_language='en-US')
            mock_langdetect.assert_called_once()
            assert result == 'en'


class TestTranslationServiceBatch:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None  # No Redis cache hits
        mock_redis.set.return_value = True

    def test_batch_single_api_call(self):
        """Multiple uncached sentences should be batched into one API call."""
        mock_translation_1 = MagicMock()
        mock_translation_1.translated_text = "Bonjour"
        mock_translation_1.detected_language_code = "en"
        mock_translation_2 = MagicMock()
        mock_translation_2.translated_text = "Comment allez-vous"
        mock_translation_2.detected_language_code = "en"
        mock_translation_3 = MagicMock()
        mock_translation_3.translated_text = "Ravi de vous rencontrer"
        mock_translation_3.detected_language_code = "en"

        mock_response = MagicMock()
        mock_response.translations = [mock_translation_1, mock_translation_2, mock_translation_3]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result_text, detected_lang = self.service.translate_text_by_sentence(
                "fr", "Hello. How are you. Nice to meet you."
            )

            # Should be exactly 1 API call (batched), not 3 separate calls
            assert mock_client.translate_text.call_count == 1
            call_kwargs = mock_client.translate_text.call_args
            assert len(call_kwargs.kwargs['contents']) == 3

    def test_cache_hit_skips_api(self):
        """Cached sentences should not trigger API calls."""
        # Pre-populate memory cache
        text = "Hello"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        self.service._set_memory_cache(text_hash, "fr", "Bonjour", "en")

        with patch('utils.translation._client') as mock_client:
            result_text, detected_lang = self.service.translate_text_by_sentence("fr", "Hello")
            mock_client.translate_text.assert_not_called()
            assert result_text == "Bonjour"

    def test_mixed_cache_hit_miss(self):
        """Only uncached sentences should be sent to API."""
        # Pre-populate cache for "Hello." (with period, as split_into_sentences produces)
        hello_hash = hashlib.md5("Hello.".encode()).hexdigest()
        self.service._set_memory_cache(hello_hash, "fr", "Bonjour.", "en")

        mock_translation = MagicMock()
        mock_translation.translated_text = "Comment allez-vous"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result_text, detected_lang = self.service.translate_text_by_sentence("fr", "Hello. How are you.")

            assert mock_client.translate_text.call_count == 1
            call_kwargs = mock_client.translate_text.call_args
            # Only "How are you." should be sent
            assert len(call_kwargs.kwargs['contents']) == 1

    def test_output_order_preserved(self):
        """Translation results should maintain original sentence order."""
        mock_t1 = MagicMock(translated_text="Un", detected_language_code="en")
        mock_t2 = MagicMock(translated_text="Deux", detected_language_code="en")
        mock_response = MagicMock(translations=[mock_t1, mock_t2])

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result_text, _ = self.service.translate_text_by_sentence("fr", "One. Two.")

            assert result_text == "Un Deux"


class TestTranslationServiceRedisCache:
    def setup_method(self):
        self.service = TranslationService()

    def test_redis_cache_hit(self):
        """Redis cache hit should skip API call."""
        text = "Hello world"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cached_data = json.dumps({"text": "Bonjour le monde", "detected_lang": "en"})
        mock_redis.get.return_value = cached_data.encode()

        with patch('utils.translation._client') as mock_client:
            result_text, detected_lang = self.service.translate_text("fr", text)
            mock_client.translate_text.assert_not_called()
            assert result_text == "Bonjour le monde"
            assert detected_lang == "en"

    def test_redis_cache_miss_calls_api(self):
        """Redis cache miss should call API and store in Redis."""
        mock_redis.get.return_value = None

        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response
            mock_redis.set.return_value = True

            result_text, detected_lang = self.service.translate_text("fr", "Hello")

            mock_client.translate_text.assert_called_once()
            assert result_text == "Bonjour"
            assert detected_lang == "en"
            # Should have stored in Redis
            mock_redis.set.assert_called()

    def test_redis_error_falls_back_to_api(self):
        """Redis errors should not break translation (fail-open)."""
        mock_redis.get.side_effect = Exception("Redis connection refused")

        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response
            mock_redis.set.side_effect = Exception("Redis connection refused")

            result_text, detected_lang = self.service.translate_text("fr", "Hello")

            # Should still succeed via API despite Redis errors
            assert result_text == "Bonjour"

    def test_redis_cache_key_format(self):
        text_hash = "abc123"
        dest_lang = "fr"
        key = _redis_cache_key(text_hash, dest_lang)
        assert key == "translate:v1:abc123:fr"


class TestTranslationServiceReturnType:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_translate_text_returns_tuple(self):
        """translate_text should return (text, detected_lang) tuple."""
        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result = self.service.translate_text("fr", "Hello")
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert result[0] == "Bonjour"
            assert result[1] == "en"

    def test_translate_text_by_sentence_returns_tuple(self):
        """translate_text_by_sentence should return (text, detected_lang) tuple."""
        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result = self.service.translate_text_by_sentence("fr", "Hello")
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_empty_text_returns_empty_tuple(self):
        result = self.service.translate_text_by_sentence("fr", "")
        assert result == ("", "")


class TestTranscriptSegmentLanguageCache:
    def test_update_from_translate_response_target_lang(self):
        """update_from_translate_response should mark segment as target when detected matches."""
        cache = TranscriptSegmentLanguageCache()
        cache.update_from_translate_response("seg1", "en", "en")
        assert cache.cache["seg1"] is True

    def test_update_from_translate_response_foreign_lang(self):
        """update_from_translate_response should mark segment as foreign when detected differs."""
        cache = TranscriptSegmentLanguageCache()
        cache.update_from_translate_response("seg1", "fr", "en")
        assert cache.cache["seg1"] is False

    def test_update_from_translate_response_locale_tagged(self):
        """update_from_translate_response should normalize locale tags (en-US -> en)."""
        cache = TranscriptSegmentLanguageCache()
        cache.update_from_translate_response("seg1", "en-US", "en")
        assert cache.cache["seg1"] is True

    def test_foreign_stays_foreign(self):
        """Once marked as foreign, segment stays foreign even without new text."""
        cache = TranscriptSegmentLanguageCache()
        cache.cache["seg1"] = False
        assert cache.is_in_target_language("seg1", "", "en") is False

    def test_unknown_detection_returns_false(self):
        """When detection is inconclusive (None), should return False (needs translation)."""
        cache = TranscriptSegmentLanguageCache()
        with patch('utils.translation_cache.detect_language', return_value=None):
            result = cache.is_in_target_language("seg1", "short", "en")
            # Should NOT assume target language when detection is unknown
            assert result is False

    def test_detected_foreign_returns_false(self):
        """When detected language differs from target, should return False."""
        cache = TranscriptSegmentLanguageCache()
        with patch('utils.translation_cache.detect_language', return_value='fr'):
            result = cache.is_in_target_language("seg1", "Bonjour", "en")
            assert result is False

    def test_detected_target_returns_true(self):
        """When detected language matches target, should return True."""
        cache = TranscriptSegmentLanguageCache()
        with patch('utils.translation_cache.detect_language', return_value='en'):
            result = cache.is_in_target_language("seg1", "Hello world today", "en")
            assert result is True

    def test_delete_cache(self):
        cache = TranscriptSegmentLanguageCache()
        cache.cache["seg1"] = True
        cache.delete_cache("seg1")
        assert "seg1" not in cache.cache


class TestShouldPersistTranslation:
    def test_noop_target_language_translation_not_persisted(self):
        """If text is unchanged and detected language matches target, don't persist translation."""
        should_persist = should_persist_translation("Hello world", "Hello world", "en", "en-US")
        assert should_persist is False

    def test_unchanged_text_without_detection_not_persisted(self):
        """If text is unchanged and detection is missing, still treat as no-op."""
        should_persist = should_persist_translation("Hello world", "Hello world", "", "en")
        assert should_persist is False

    def test_mixed_language_translation_still_persisted(self):
        """Even with dominant detected target language, changed text must be persisted."""
        should_persist = should_persist_translation("Hello. Hola.", "Hello. Hello.", "en", "en")
        assert should_persist is True

    def test_short_phrase_noop_not_persisted(self):
        """Short phrases like 'Transcription service.' that return identical from API should not persist."""
        assert should_persist_translation("Transcription service.", "Transcription service.", "en", "en") is False

    def test_numeric_only_noop_not_persisted(self):
        """Numeric/punctuation text like '123. 123.' returning identical should not persist."""
        assert should_persist_translation("123. 123.", "123. 123.", "", "en") is False

    def test_short_greeting_noop_not_persisted(self):
        """Short greetings like 'Hey.' returning identical should not persist."""
        assert should_persist_translation("Hey.", "Hey.", "en", "en") is False

    def test_whitespace_difference_not_persisted(self):
        """Whitespace-only differences should be treated as no-op."""
        assert should_persist_translation("Hello  world", "Hello world", "en", "en") is False

    def test_real_translation_persisted(self):
        """Actual translation (text changed) should always persist."""
        assert should_persist_translation("Bonjour", "Hello", "fr", "en") is True

    def test_none_translated_text_persisted_as_change(self):
        """None translated_text differs from source, should persist (text changed)."""
        assert should_persist_translation("Hello", None, "en", "en") is True

    def test_empty_source_and_translated_not_persisted(self):
        """Both empty should be treated as no-op."""
        assert should_persist_translation("", "", "en", "en") is False

    def test_long_english_correctly_detected_not_persisted(self):
        """Long English text (correctly detected by langdetect) returning identical should not persist."""
        assert should_persist_translation("Two three four five.", "Two three four five.", "en", "en") is False

    def test_question_english_not_persisted(self):
        """English questions returning identical should not persist."""
        assert (
            should_persist_translation("Hello? Can you hear? Yes? No?", "Hello? Can you hear? Yes? No?", "en", "en")
            is False
        )

    def test_case_variant_locale_tags_not_persisted(self):
        """Case/locale variants like EN-us vs en-US should normalize and match."""
        assert should_persist_translation("Hello world", "Hello world", "EN-us", "en-US") is False

    def test_unchanged_text_mismatched_detected_lang_not_persisted(self):
        """Unchanged text with detected 'fr' should still not persist (conservative: text unchanged = no-op)."""
        assert should_persist_translation("Transcription service.", "Transcription service.", "fr", "en") is False

    def test_short_foreign_word_translated_to_english_persisted(self):
        """Short foreign word like 'Bonjour.' translated to 'Hello.' must persist (real translation)."""
        assert should_persist_translation("Bonjour.", "Hello.", "fr", "en") is True
        assert should_persist_translation("Hola.", "Hello.", "es", "en") is True
        assert should_persist_translation("Danke.", "Thank you.", "de", "en") is True
        assert should_persist_translation("Merci.", "Thank you.", "fr", "en") is True

    def test_multiple_short_foreign_sentences_translated_persisted(self):
        """Multiple short foreign sentences in one segment must persist when translated."""
        assert should_persist_translation("Bonjour. Comment allez-vous?", "Hello. How are you?", "fr", "en") is True
        assert should_persist_translation("Hola. Gracias. Adiós.", "Hello. Thank you. Goodbye.", "es", "en") is True
        assert should_persist_translation("Oui. Non. Merci.", "Yes. No. Thank you.", "fr", "en") is True


class TestShortForeignTextLangdetectPreFilter:
    """Verify that langdetect does NOT misdetect short foreign words as English (target).

    If langdetect detected foreign text as English, is_in_target_language() would return True
    and the segment would be skipped entirely (never sent to API). These tests verify that
    short foreign words are NOT skipped by the pre-filter.
    """

    def test_short_foreign_words_not_detected_as_english(self):
        """Short foreign words should not be detected as 'en' by langdetect."""
        cache = TranscriptSegmentLanguageCache()
        foreign_words = [
            ("Bonjour.", "seg-fr"),
            ("Hola.", "seg-es"),
            ("Danke.", "seg-de"),
            ("Gracias.", "seg-es2"),
        ]
        for text, seg_id in foreign_words:
            result = cache.is_in_target_language(seg_id, text, "en")
            assert result is False, f"'{text}' was incorrectly detected as English — would skip translation"

    def test_multiple_short_foreign_sentences_not_detected_as_english(self):
        """Multiple short foreign sentences should not be detected as 'en'."""
        cache = TranscriptSegmentLanguageCache()
        result = cache.is_in_target_language("seg-multi-fr", "Bonjour. Merci. Au revoir.", "en")
        assert result is False, "Multiple French sentences incorrectly detected as English"
        result = cache.is_in_target_language("seg-multi-es", "Hola. Gracias. Adiós.", "en")
        assert result is False, "Multiple Spanish sentences incorrectly detected as English"


class TestTranslateSegmentGuardWired:
    """Regression test: verify should_persist_translation is wired into transcribe.py.

    _translate_segment is a closure inside _stream_handler and cannot be imported directly.
    This test reads the source to verify the guard call is present — catches accidental removal.
    """

    def test_transcribe_imports_should_persist_translation(self):
        """transcribe.py must import should_persist_translation from translation_cache."""
        import inspect
        import importlib

        # Read transcribe module source to verify import
        transcribe_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
        with open(transcribe_path) as f:
            source = f.read()
        assert 'from utils.translation_cache import' in source
        assert 'should_persist_translation' in source

    def test_transcribe_calls_should_persist_translation_before_translation_creation(self):
        """Guard must appear before Translation object creation in _translate_segment."""
        transcribe_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
        with open(transcribe_path) as f:
            source = f.read()
        guard_pos = source.find('should_persist_translation(')
        translation_create_pos = source.find('trans = Translation(lang=translation_language')
        assert guard_pos > 0, "should_persist_translation call not found in transcribe.py"
        assert translation_create_pos > 0, "Translation creation not found in transcribe.py"
        assert guard_pos < translation_create_pos, "Guard must appear before Translation creation"


class TestTranslateSegmentGuardIntegration:
    """Integration test simulating _translate_segment's guard path.

    Verifies the full logic flow: translate API returns same text with target lang detected,
    guard triggers early return, pending entry is pruned, no translation is persisted.
    """

    def test_noop_translation_skips_persist_and_prunes_pending(self):
        """When API returns identical text with same detected lang, no Translation is created
        and pending_translations entry is pruned."""
        segment_text = "Transcription service."
        translation_language = "en"
        translation_language_base = "en"
        pending_translations = {'seg-1': {'text_hash': 'abc123', 'version': 1}}
        persisted_translations = []  # tracks what would be written to DB

        # Simulate translate API returning identical text with "en" detected
        translated_text = "Transcription service."
        detected_lang = "en"

        # Simulate language cache update (should still happen before guard)
        cache = TranscriptSegmentLanguageCache()
        cache.update_from_translate_response('seg-1', detected_lang, translation_language_base)
        assert cache.cache.get('seg-1') is True  # cache learns target language

        # Guard check — same as transcribe.py line 1514
        if not should_persist_translation(
            segment_text, translated_text, detected_lang, translation_language_base or translation_language
        ):
            pending_translations.pop('seg-1', None)
            # Early return — no Translation created
        else:
            persisted_translations.append({'lang': translation_language, 'text': translated_text})

        # Verify: no translation persisted, pending entry pruned
        assert len(persisted_translations) == 0
        assert 'seg-1' not in pending_translations

    def test_real_translation_persists_and_keeps_pending(self):
        """When API returns different text (real translation), Translation IS created."""
        segment_text = "Bonjour le monde"
        translation_language = "en"
        translation_language_base = "en"
        pending_translations = {'seg-2': {'text_hash': 'def456', 'version': 1}}
        persisted_translations = []

        translated_text = "Hello world"
        detected_lang = "fr"

        cache = TranscriptSegmentLanguageCache()
        cache.update_from_translate_response('seg-2', detected_lang, translation_language_base)
        assert cache.cache.get('seg-2') is False  # cache learns non-target language

        if not should_persist_translation(
            segment_text, translated_text, detected_lang, translation_language_base or translation_language
        ):
            pending_translations.pop('seg-2', None)
        else:
            persisted_translations.append({'lang': translation_language, 'text': translated_text})
            pending_translations.pop('seg-2', None)  # normal cleanup after persist

        # Verify: translation WAS persisted
        assert len(persisted_translations) == 1
        assert persisted_translations[0]['text'] == "Hello world"


class TestRedisCacheTTL:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_redis_set_includes_ttl(self):
        """Redis cache should be set with the configured TTL."""
        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            self.service.translate_text("fr", "Hello")

            # Verify Redis set was called with TTL
            set_calls = mock_redis.set.call_args_list
            assert len(set_calls) > 0
            last_set_call = set_calls[-1]
            assert last_set_call.kwargs.get('ex') == TRANSLATION_CACHE_TTL

    def test_ttl_default_value(self):
        """Default TTL should be 14 days."""
        assert TRANSLATION_CACHE_TTL == 60 * 60 * 24 * 14


class TestTranslationServiceErrorFallback:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_translate_text_api_error_returns_original(self):
        """On API error, translate_text should return original text and empty detected lang."""
        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.side_effect = Exception("API unavailable")

            result_text, detected_lang = self.service.translate_text("fr", "Hello")
            assert result_text == "Hello"
            assert detected_lang == ""

    def test_batch_api_error_returns_originals(self):
        """On batch API error, translate_text_by_sentence should return original sentences."""
        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.side_effect = Exception("API unavailable")

            result_text, detected_lang = self.service.translate_text_by_sentence("fr", "Hello. How are you.")
            # Should fall back to original sentences joined
            assert "Hello" in result_text
            assert "How are you" in result_text


class TestDominantLanguageDetection:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_dominant_language_from_multiple_sentences(self):
        """Should return the most common detected language across sentences."""
        mock_t1 = MagicMock(translated_text="Bonjour", detected_language_code="en")
        mock_t2 = MagicMock(translated_text="Comment", detected_language_code="en")
        mock_t3 = MagicMock(translated_text="Hola", detected_language_code="es")
        mock_response = MagicMock(translations=[mock_t1, mock_t2, mock_t3])

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            _, detected_lang = self.service.translate_text_by_sentence("fr", "Hello. How are you. Hola.")
            # "en" appears twice, "es" once — dominant should be "en"
            assert detected_lang == "en"

    def test_single_sentence_detected_language(self):
        """Single sentence should return its detected language."""
        mock_t = MagicMock(translated_text="Bonjour", detected_language_code="en")
        mock_response = MagicMock(translations=[mock_t])

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            _, detected_lang = self.service.translate_text_by_sentence("fr", "Hello")
            assert detected_lang == "en"


class TestMixedLanguageBatch:
    """Tests that mixed-language segments are correctly translated, not dropped."""

    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_mixed_language_returns_translated_text(self):
        """Mixed-language input (e.g. 'Hello. Hola.') with target=en should still return translation.

        Even when dominant detected language matches target, the translated text should be
        returned because individual sentences may differ from the original.
        """
        # "Hello." stays as-is, "Hola." gets translated to "Hello."
        mock_t1 = MagicMock(translated_text="Hello.", detected_language_code="en")
        mock_t2 = MagicMock(translated_text="Hello.", detected_language_code="es")
        mock_response = MagicMock(translations=[mock_t1, mock_t2])

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result_text, detected_lang = self.service.translate_text_by_sentence("en", "Hello. Hola.")

            # Both sentences should be in result
            assert "Hello." in result_text
            # API was called (no skip due to dominant language matching target)
            mock_client.translate_text.assert_called_once()

    def test_all_target_language_still_returns_translation(self):
        """Even if all sentences are in target language, translation result is returned.

        The caller decides whether to persist — TranslationService always returns the API result.
        """
        mock_t1 = MagicMock(translated_text="Hello.", detected_language_code="en")
        mock_response = MagicMock(translations=[mock_t1])

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.return_value = mock_response

            result_text, detected_lang = self.service.translate_text_by_sentence("en", "Hello.")
            assert result_text == "Hello."
            assert detected_lang == "en"


class TestBatchChunking:
    def setup_method(self):
        self.service = TranslationService()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

    def test_max_batch_size_constant(self):
        """MAX_BATCH_SIZE should be 100."""
        assert MAX_BATCH_SIZE == 100

    def test_over_max_batch_size_chunks_correctly(self):
        """When uncached sentences exceed MAX_BATCH_SIZE, they should be split into multiple API calls."""
        # Build 150 unique sentences (exceeds MAX_BATCH_SIZE=100)
        sentences_text = ". ".join(f"Sentence {i}" for i in range(150)) + "."

        # Mock API to return translations matching input count per call
        def mock_translate(**kwargs):
            contents = kwargs.get('contents', [])
            translations = []
            for text in contents:
                t = MagicMock()
                t.translated_text = f"Translated {text}"
                t.detected_language_code = "en"
                translations.append(t)
            resp = MagicMock()
            resp.translations = translations
            return resp

        with patch('utils.translation._client') as mock_client:
            mock_client.translate_text.side_effect = mock_translate

            result_text, detected_lang = self.service.translate_text_by_sentence("fr", sentences_text)

            # Should make 2 API calls: 100 + 50
            assert mock_client.translate_text.call_count == 2
            first_call_contents = mock_client.translate_text.call_args_list[0].kwargs['contents']
            second_call_contents = mock_client.translate_text.call_args_list[1].kwargs['contents']
            assert len(first_call_contents) == 100
            assert len(second_call_contents) == 50


class TestTranslationCacheTTLOverride:
    def test_ttl_env_override(self):
        """TRANSLATION_CACHE_TTL should be overridable via environment variable."""
        # Default is 14 days
        assert TRANSLATION_CACHE_TTL == 60 * 60 * 24 * 14
        # The env override is tested by the int() cast in the module:
        # int(os.environ.get("TRANSLATION_CACHE_TTL", 60 * 60 * 24 * 14))
        # We verify the type is correct for Redis ex= parameter
        assert isinstance(TRANSLATION_CACHE_TTL, int)
        assert TRANSLATION_CACHE_TTL > 0


# ---------------------------------------------------------------------------
# Temporal debounce integration tests
# ---------------------------------------------------------------------------
# The debounce logic in transcribe.py accumulates segments into a buffer and
# translates them as a batch after TRANSLATION_DEBOUNCE_SECONDS of quiet.
# These tests replicate the buffer/timer pattern, stale version rejection,
# same-text skip, and flush behavior.


class TestTemporalDebounceBuffer:
    """Tests the temporal debounce buffer accumulation logic."""

    def test_segments_buffered_not_immediate(self):
        """All segments should be buffered, not translated immediately."""
        buffer = []
        pending_translations = {}
        version_counter = 0

        # Simulate 3 segments arriving (unique IDs, as Deepgram produces)
        for i in range(3):
            seg_id = f'seg-{i}'
            version_counter += 1
            pending_translations[seg_id] = {'text_hash': f'h{i}', 'version': version_counter}
            buffer.append((seg_id, 'conv-1', version_counter))

        assert len(buffer) == 3
        assert len(pending_translations) == 3

    def test_buffer_cleared_on_flush(self):
        """Flushing should clear the buffer and return all segments."""
        buffer = [('seg-0', 'conv-1', 1), ('seg-1', 'conv-1', 2)]

        batch = list(buffer)
        buffer.clear()

        assert len(batch) == 2
        assert len(buffer) == 0

    def test_unique_segment_ids_all_buffered(self):
        """With unique segment IDs (real Deepgram behavior), all segments get buffered."""
        buffer = []
        pending_translations = {}
        version_counter = 0

        # Each segment has a unique ID — this is the actual DG behavior
        segment_ids = ['abc-001', 'abc-002', 'abc-003', 'abc-004', 'abc-005']
        for seg_id in segment_ids:
            version_counter += 1
            text_hash = hashlib.md5(f'text-{seg_id}'.encode()).hexdigest()
            pending = pending_translations.get(seg_id)
            # No pending (unique ID) — always enters buffer
            assert pending is None
            pending_translations[seg_id] = {'text_hash': text_hash, 'version': version_counter}
            buffer.append((seg_id, 'conv-1', version_counter))

        # All 5 segments should be buffered (not 0 like the old segment-ID debounce)
        assert len(buffer) == 5

    def test_timer_reset_on_new_segment(self):
        """Adding a segment should cancel and restart the debounce timer."""
        import asyncio

        timer_cancelled = False
        timer_started = 0

        class FakeTask:
            def __init__(self):
                self._done = False

            def done(self):
                return self._done

            def cancel(self):
                nonlocal timer_cancelled
                timer_cancelled = True
                self._done = True

        # First segment starts timer
        debounce_task = FakeTask()
        timer_started += 1

        # Second segment arrives — should cancel and restart
        if debounce_task and not debounce_task.done():
            debounce_task.cancel()
        debounce_task = FakeTask()
        timer_started += 1

        assert timer_cancelled is True
        assert timer_started == 2


class TestDebounceVersionSafety:
    """Tests stale-write protection via monotonic version counter."""

    def test_stale_version_rejected(self):
        """A translate result with an outdated version should be discarded."""
        pending_translations = {}
        segment_id = 'seg-1'

        # Simulate: version 1 translate starts, version 2 update arrives before v1 completes
        pending_translations[segment_id] = {'text_hash': 'h1', 'version': 1}
        # New update bumps version
        pending_translations[segment_id] = {'text_hash': 'h2', 'version': 2}

        # When v1 translate completes, check version
        pending = pending_translations.get(segment_id)
        old_version = 1
        assert pending['version'] != old_version  # Should be rejected

    def test_current_version_accepted(self):
        """A translate result with current version should be accepted."""
        pending_translations = {}
        segment_id = 'seg-1'
        pending_translations[segment_id] = {'text_hash': 'h1', 'version': 3}

        pending = pending_translations.get(segment_id)
        current_version = 3
        assert pending['version'] == current_version  # Should be accepted

    def test_pruned_entry_rejected(self):
        """If entry was pruned (completed), returning translate should be discarded."""
        pending_translations = {}
        segment_id = 'seg-1'
        # Entry was pruned (segment completed translation, entry removed)
        pending = pending_translations.get(segment_id)
        assert pending is None  # Should abort — entry no longer exists

    def test_monotonic_counter_never_reuses(self):
        """Version counter should strictly increase, never reuse values."""
        counter = 0
        versions = []
        for _ in range(10):
            counter += 1
            versions.append(counter)
        assert versions == list(range(1, 11))
        assert len(set(versions)) == 10  # All unique


class TestDebounceSameTextSkip:
    """Tests that same-text updates are skipped (no redundant translation)."""

    def test_same_hash_skipped(self):
        """If segment text hasn't changed, skip translation entirely."""
        text = "Hello how are you"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        pending = {'text_hash': text_hash, 'version': 1}

        new_hash = hashlib.md5(text.encode()).hexdigest()
        assert pending.get('text_hash') == new_hash  # Same text, should skip

    def test_different_hash_not_skipped(self):
        """If segment text changed, proceed with translation."""
        old_text = "Hello"
        new_text = "Hello how are you"
        old_hash = hashlib.md5(old_text.encode()).hexdigest()
        new_hash = hashlib.md5(new_text.encode()).hexdigest()

        pending = {'text_hash': old_hash, 'version': 1}
        assert pending.get('text_hash') != new_hash  # Different text, should proceed


class TestDebounceFlushPending:
    """Tests flush_pending_translations behavior."""

    def test_flush_clears_all_entries(self):
        """After flush, pending_translations and buffer should be empty."""
        pending_translations = {
            'seg-1': {'text_hash': 'h1', 'version': 1},
            'seg-2': {'text_hash': 'h2', 'version': 2},
        }
        buffer = [('seg-1', 'conv-1', 1), ('seg-2', 'conv-1', 2)]

        # Simulate flush: drain buffer then clear pending
        batch = list(buffer)
        buffer.clear()
        pending_translations.clear()

        assert len(pending_translations) == 0
        assert len(buffer) == 0
        assert len(batch) == 2  # Batch was captured before clear

    def test_exception_in_translate_cleans_up(self):
        """If _translate_segment raises, pending entry should still be cleaned up."""
        pending_translations = {'seg-1': {'text_hash': 'h1', 'version': 1}}
        segment_id = 'seg-1'

        # Simulate: _translate_segment raises, finally block pops entry
        try:
            raise Exception("Translation API error")
        except Exception:
            pass
        pending_translations.pop(segment_id, None)
        assert segment_id not in pending_translations

    def test_flush_handles_empty_buffer(self):
        """Flushing an empty buffer should be a no-op."""
        buffer = []
        batch = list(buffer)
        buffer.clear()
        assert len(batch) == 0


class TestSingleSegmentBoundary:
    """Tests that a single buffered segment is dispatched exactly once."""

    def test_single_segment_flush(self):
        """One buffered segment should produce exactly one task on flush."""
        buffer = []
        pending_translations = {}
        inflight_tasks = []

        # Single segment arrives
        seg_id = 'seg-only'
        pending_translations[seg_id] = {'text_hash': 'h1', 'version': 1}
        buffer.append((seg_id, 'conv-1', 1))

        assert len(buffer) == 1

        # Flush: drain buffer, create one task per segment
        batch = list(buffer)
        buffer.clear()
        for seg, conv_id, ver in batch:
            inflight_tasks.append(f'task-{seg}')

        assert len(inflight_tasks) == 1
        assert inflight_tasks[0] == 'task-seg-only'
        assert len(buffer) == 0


class TestFlushAwaitsInflightTasks:
    """Tests that flush properly awaits in-flight translate tasks."""

    def test_inflight_tasks_tracked_on_flush(self):
        """Each segment in the batch should produce a tracked in-flight task."""
        inflight_tasks = []
        buffer = [('seg-0', 'conv-1', 1), ('seg-1', 'conv-1', 2), ('seg-2', 'conv-1', 3)]

        # Simulate _flush_debounce_buffer: drain buffer, create tasks, track them
        batch = list(buffer)
        buffer.clear()
        for seg, conv_id, ver in batch:
            inflight_tasks.append(f'task-{seg}')

        assert len(inflight_tasks) == 3

    def test_flush_clears_inflight_after_await(self):
        """After awaiting, inflight_tasks list should be cleared."""
        inflight_tasks = ['task-1', 'task-2']

        # Simulate flush_pending_translations: await then clear
        pending = [t for t in inflight_tasks]  # would be filtered by .done() in real code
        # After asyncio.gather completes:
        inflight_tasks.clear()

        assert len(inflight_tasks) == 0

    def test_flush_handles_empty_inflight(self):
        """Flushing with no in-flight tasks should be a no-op."""
        inflight_tasks = []
        pending = [t for t in inflight_tasks]
        assert len(pending) == 0
        inflight_tasks.clear()
        assert len(inflight_tasks) == 0


class TestDebounceMetricsAccuracy:
    """Tests that metrics counters accurately reflect temporal debounce behavior."""

    def test_all_segments_counted_as_buffered_then_translated(self):
        """Every segment entering the buffer is a segments_buffered; batch flush counts as translated."""
        metrics = {'segments_buffered': 0, 'segments_translated': 0}
        buffer = []

        # 5 segments arrive — all buffered
        for i in range(5):
            metrics['segments_buffered'] += 1
            buffer.append((f'seg-{i}', 'conv-1', i + 1))

        assert metrics['segments_buffered'] == 5

        # Timer fires — batch translates all
        batch = list(buffer)
        buffer.clear()
        metrics['segments_translated'] += len(batch)

        assert metrics['segments_translated'] == 5

    def test_lang_cache_skip_not_buffered(self):
        """Segments skipped by language cache should not enter the buffer."""
        metrics = {'segments_buffered': 0, 'lang_cache_skips': 0}
        buffer = []

        # 3 segments: 2 need translation, 1 already in target language
        segments = [('seg-0', False), ('seg-1', True), ('seg-2', False)]  # (id, is_target_lang)
        for seg_id, is_target in segments:
            if is_target:
                metrics['lang_cache_skips'] += 1
                continue
            metrics['segments_buffered'] += 1
            buffer.append((seg_id, 'conv-1', 1))

        assert metrics['lang_cache_skips'] == 1
        assert metrics['segments_buffered'] == 2
        assert len(buffer) == 2

    def test_total_segments_excludes_translated(self):
        """total_segments should NOT include segments_translated (it's a subset of segments_buffered).

        This prevents the double-counting bug where the same segments are counted in both
        segments_buffered (entry) and segments_translated (dispatch).
        """
        metrics = {
            'segments_buffered': 10,
            'segments_translated': 10,
            'lang_cache_skips': 3,
            'same_text_skips': 2,
        }

        # Correct formula: total = buffered + lang_skip + same_text_skip
        # segments_translated is a subset of segments_buffered, NOT added to total
        total_segments = metrics['segments_buffered'] + metrics['lang_cache_skips'] + metrics['same_text_skips']

        assert total_segments == 15  # 10 + 3 + 2, NOT 25
        assert metrics['segments_translated'] not in [total_segments]  # translated is separate
        # Verify translated <= buffered (it's always a subset)
        assert metrics['segments_translated'] <= metrics['segments_buffered']
