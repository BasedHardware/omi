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
)


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
