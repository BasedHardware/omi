"""Tests for translation.py — elimination of redundant detect_language API calls (issue #4712)."""

from unittest.mock import MagicMock, patch
import pytest

# Mock Google Cloud translate before importing translation module
import sys
mock_translate_v3 = MagicMock()
sys.modules['google.cloud.translate_v3'] = mock_translate_v3
sys.modules['google.cloud'] = MagicMock()

# Now we can safely import
from utils.translation import (
    TranslationResult,
    TranslationService,
    detect_language,
    split_into_sentences,
    detection_cache,
    MAX_DETECTION_CACHE_SIZE,
)
from utils.translation_cache import TranscriptSegmentLanguageCache


class TestTranslationResult:
    def test_namedtuple_fields(self):
        r = TranslationResult(text="hello", detected_language_code="en")
        assert r.text == "hello"
        assert r.detected_language_code == "en"

    def test_default_detected_language_is_none(self):
        r = TranslationResult(text="hello")
        assert r.detected_language_code is None


class TestDetectLanguage:
    """detect_language should only use free langdetect, never Google Cloud API."""

    def test_detects_english(self):
        result = detect_language("This is a test sentence in English", hint_language="en")
        assert result == "en"

    def test_detects_spanish(self):
        result = detect_language("Esta es una prueba en español", hint_language="es")
        assert result == "es"

    def test_returns_none_for_empty(self):
        assert detect_language("") is None
        assert detect_language("   ") is None

    def test_returns_none_for_non_lexical_only(self):
        result = detect_language("hmm uh oh", remove_non_lexical=True, hint_language="en")
        assert result is None

    def test_returns_none_for_unreliable_language(self):
        # hint_language not in LANGDETECT_RELIABLE_LANGUAGES should return None
        result = detect_language("some text", hint_language="xx")
        assert result is None

    def test_caches_results(self):
        detection_cache.clear()
        text = "Ceci est une phrase en français pour le test"
        detect_language(text, hint_language="fr")
        assert text in detection_cache

    def test_no_google_cloud_detect_call(self):
        """Verify _client.detect_language is never called."""
        from utils import translation
        original_client = translation._client
        mock_client = MagicMock()
        translation._client = mock_client
        try:
            detect_language("Hello world test phrase", hint_language="en")
            mock_client.detect_language.assert_not_called()
        finally:
            translation._client = original_client


class TestTranslateText:
    """translate_text should return TranslationResult with detected_language_code from API response."""

    def setup_method(self):
        self.service = TranslationService()

    def test_returns_translation_result(self):
        from utils import translation
        mock_client = MagicMock()
        mock_translation = MagicMock()
        mock_translation.translated_text = "Hola mundo"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]
        mock_client.translate_text.return_value = mock_response

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text("es", "Hello world")
            assert isinstance(result, TranslationResult)
            assert result.text == "Hola mundo"
            assert result.detected_language_code == "en"
        finally:
            translation._client = original_client

    def test_cache_returns_translation_result(self):
        from utils import translation
        mock_client = MagicMock()
        mock_translation = MagicMock()
        mock_translation.translated_text = "Bonjour"
        mock_translation.detected_language_code = "en"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]
        mock_client.translate_text.return_value = mock_response

        original_client = translation._client
        translation._client = mock_client
        try:
            result1 = self.service.translate_text("fr", "Hello")
            result2 = self.service.translate_text("fr", "Hello")
            assert result2.text == "Bonjour"
            assert result2.detected_language_code == "en"
            # API should only be called once (second hit is cached)
            assert mock_client.translate_text.call_count == 1
        finally:
            translation._client = original_client

    def test_error_returns_original_text(self):
        from utils import translation
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = Exception("API error")

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text("es", "Hello")
            assert result.text == "Hello"
            assert result.detected_language_code is None
        finally:
            translation._client = original_client

    def test_empty_detected_language_becomes_none(self):
        from utils import translation
        mock_client = MagicMock()
        mock_translation = MagicMock()
        mock_translation.translated_text = "Hola"
        mock_translation.detected_language_code = ""  # empty string from API
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]
        mock_client.translate_text.return_value = mock_response

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text("es", "Hello")
            assert result.detected_language_code is None
        finally:
            translation._client = original_client


class TestTranslateTextBySentence:
    def setup_method(self):
        self.service = TranslationService()

    def test_empty_text(self):
        result = self.service.translate_text_by_sentence("es", "")
        assert result.text == ""
        assert result.detected_language_code is None

    def test_all_sentences_same_language(self):
        from utils import translation
        mock_client = MagicMock()

        def mock_translate(contents, parent, mime_type, target_language_code):
            mock_t = MagicMock()
            mock_t.translated_text = f"translated_{contents[0]}"
            mock_t.detected_language_code = "en"
            mock_r = MagicMock()
            mock_r.translations = [mock_t]
            return mock_r

        mock_client.translate_text.side_effect = mock_translate

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text_by_sentence("es", "Hello. World.")
            assert result.detected_language_code == "en"
        finally:
            translation._client = original_client

    def test_partial_detection_returns_none(self):
        """If some sentences have None detection, don't treat detected ones as authoritative."""
        from utils import translation
        mock_client = MagicMock()
        call_count = [0]

        def mock_translate(contents, parent, mime_type, target_language_code):
            mock_t = MagicMock()
            mock_t.translated_text = f"translated_{contents[0]}"
            # First sentence detects "en", second returns None (API quirk/error)
            mock_t.detected_language_code = "en" if call_count[0] == 0 else ""
            call_count[0] += 1
            mock_r = MagicMock()
            mock_r.translations = [mock_t]
            return mock_r

        mock_client.translate_text.side_effect = mock_translate

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text_by_sentence("en", "Hello world. Goodbye world.")
            # Should NOT skip translation — one sentence had no detection
            assert result.detected_language_code is None
        finally:
            translation._client = original_client

    def test_mixed_languages_returns_none(self):
        from utils import translation
        mock_client = MagicMock()
        call_count = [0]

        def mock_translate(contents, parent, mime_type, target_language_code):
            mock_t = MagicMock()
            mock_t.translated_text = f"translated_{contents[0]}"
            mock_t.detected_language_code = "en" if call_count[0] == 0 else "fr"
            call_count[0] += 1
            mock_r = MagicMock()
            mock_r.translations = [mock_t]
            return mock_r

        mock_client.translate_text.side_effect = mock_translate

        original_client = translation._client
        translation._client = mock_client
        try:
            result = self.service.translate_text_by_sentence("es", "Hello. Bonjour.")
            assert result.detected_language_code is None
        finally:
            translation._client = original_client


class TestSplitIntoSentences:
    def test_empty_string(self):
        assert split_into_sentences("") == []

    def test_single_sentence(self):
        result = split_into_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_multiple_sentences(self):
        result = split_into_sentences("Hello. World! How?")
        assert len(result) == 3

    def test_commas_split(self):
        result = split_into_sentences("one, two, three")
        assert len(result) == 3

    def test_whitespace_only(self):
        result = split_into_sentences("   ")
        assert result == []


class TestDetectionCacheBehavior:
    """Test detection cache eviction and hit behavior."""

    def test_cache_hit_avoids_langdetect_call(self):
        detection_cache.clear()
        from utils import translation
        text = "This is a unique sentence for cache test behavior"
        # Prime cache
        detect_language(text, hint_language="en")
        assert text in detection_cache

        # Replace langdetect with one that would fail
        original = translation._detect_with_langdetect
        translation._detect_with_langdetect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not be called"))
        try:
            # Should hit cache, not call langdetect
            result = detect_language(text, hint_language="en")
            assert result == "en"
        finally:
            translation._detect_with_langdetect = original

    def test_cache_eviction_at_max_size(self):
        detection_cache.clear()
        from utils import translation

        # Mock langdetect to always return "en"
        original = translation._detect_with_langdetect
        translation._detect_with_langdetect = lambda text, hint: "en"
        try:
            # Fill cache to max
            for i in range(MAX_DETECTION_CACHE_SIZE + 5):
                detect_language(f"unique text number {i} for eviction test", hint_language="en")
            assert len(detection_cache) <= MAX_DETECTION_CACHE_SIZE
        finally:
            translation._detect_with_langdetect = original
            detection_cache.clear()


class TestTranscriptSegmentLanguageCache:
    """Test the pre-filter cache that uses detect_language."""

    def test_foreign_language_returns_false(self):
        cache = TranscriptSegmentLanguageCache()
        # Spanish text with English target — should return False
        result = cache.is_in_target_language("seg1", "Esta es una prueba en español para el test", "en")
        assert result is False

    def test_sticky_false(self):
        """Once a segment is determined to be foreign, it stays false."""
        cache = TranscriptSegmentLanguageCache()
        cache.is_in_target_language("seg1", "Esta es una prueba en español para el test", "en")
        # Even with new text, sticky false means it stays False
        result = cache.is_in_target_language("seg1", "Hello world", "en")
        assert result is False

    def test_empty_text_returns_true_when_no_prior(self):
        cache = TranscriptSegmentLanguageCache()
        result = cache.is_in_target_language("seg1", "", "en")
        assert result is True

    def test_delete_cache(self):
        cache = TranscriptSegmentLanguageCache()
        cache.is_in_target_language("seg1", "Esta es una prueba en español para el test", "en")
        assert "seg1" in cache.cache
        cache.delete_cache("seg1")
        assert "seg1" not in cache.cache

    def test_undetectable_language_returns_true(self):
        """If langdetect can't detect (unreliable hint), treat as target language."""
        cache = TranscriptSegmentLanguageCache()
        # hint_language "xx" is unreliable — detect_language returns None
        result = cache.is_in_target_language("seg1", "some text", "xx")
        assert result is True
