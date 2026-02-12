"""Tests for sentence splitting fix and batch translate (issue #4715).

Tests verify:
1. Commas no longer split sentences
2. Sentence-ending punctuation (.?!) still works
3. Batch translation sends one API call for multiple cache misses
"""

import hashlib
from collections import OrderedDict
from unittest.mock import MagicMock, patch, call
import sys

# Mock Google Cloud translate before importing
mock_translate_v3 = MagicMock()
sys.modules['google.cloud.translate_v3'] = mock_translate_v3
sys.modules['google.cloud'] = MagicMock()

sys.path.insert(0, '/home/claude/omi/omi-kenji/backend')
from utils.translation import split_into_sentences


class TestSplitIntoSentences:
    """Test the fixed sentence splitting logic."""

    def test_commas_do_not_split(self):
        """Commas should NOT cause sentence splits."""
        result = split_into_sentences("Hello, how are you, nice to meet you")
        assert len(result) == 1
        assert result[0] == "Hello, how are you, nice to meet you"

    def test_period_splits(self):
        """Periods should split sentences."""
        result = split_into_sentences("Hello world. How are you.")
        assert len(result) == 2
        assert result[0] == "Hello world."
        assert result[1] == "How are you."

    def test_question_mark_splits(self):
        """Question marks should split sentences."""
        result = split_into_sentences("How are you? I am fine.")
        assert len(result) == 2
        assert result[0] == "How are you?"
        assert result[1] == "I am fine."

    def test_exclamation_mark_splits(self):
        """Exclamation marks should split sentences."""
        result = split_into_sentences("Wow! That is great.")
        assert len(result) == 2
        assert result[0] == "Wow!"
        assert result[1] == "That is great."

    def test_newline_splits(self):
        """Newlines should split sentences."""
        result = split_into_sentences("First line\nSecond line")
        assert len(result) == 2

    def test_empty_string(self):
        """Empty string should return empty list."""
        assert split_into_sentences("") == []
        assert split_into_sentences(None) == []

    def test_no_punctuation(self):
        """Text without sentence-ending punctuation stays as one unit."""
        result = split_into_sentences("Hello how are you today")
        assert len(result) == 1
        assert result[0] == "Hello how are you today"

    def test_mixed_punctuation(self):
        """Multiple different punctuation marks should all split correctly."""
        result = split_into_sentences("Hello! How are you? I am fine.")
        assert len(result) == 3

    def test_comma_heavy_text_stays_together(self):
        """Real-world comma-heavy speech should stay as one sentence."""
        text = "Well, you know, like, I was thinking, maybe we could, you know, go somewhere"
        result = split_into_sentences(text)
        assert len(result) == 1

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped from sentences."""
        result = split_into_sentences("  Hello world.   How are you.  ")
        for s in result:
            assert s == s.strip()


class TestBatchTranslation:
    """Test that translate_text_by_sentence batches cache misses into one API call."""

    def _make_mock_response(self, translations):
        """Create a mock Google Translate API response."""
        mock_response = MagicMock()
        mock_translations = []
        for text in translations:
            mt = MagicMock()
            mt.translated_text = text
            mock_translations.append(mt)
        mock_response.translations = mock_translations
        return mock_response

    def test_all_misses_batched_into_one_call(self):
        """Multiple cache-miss sentences should be sent in one API call."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.return_value = self._make_mock_response(["Hola mundo.", "Como estas?"])
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()

            result = service.translate_text_by_sentence('es', "Hello world. How are you?")

            # Should be ONE API call with both sentences
            assert mock_client.translate_text.call_count == 1
            call_args = mock_client.translate_text.call_args
            contents = call_args.kwargs.get('contents', call_args[1].get('contents'))
            assert len(contents) == 2
            assert "Hola mundo." in result
            assert "Como estas?" in result
        finally:
            tm._client = original_client

    def test_cache_hit_skips_api(self):
        """Cached sentences should not be included in the API batch."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.return_value = self._make_mock_response(["Como estas?"])
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()

            # Pre-populate cache for "Hello world."
            text_hash = hashlib.md5("Hello world.".encode()).hexdigest()
            cache_key = service._get_cache_key(text_hash, 'es')
            service.translation_cache[cache_key] = "Hola mundo."

            result = service.translate_text_by_sentence('es', "Hello world. How are you?")

            # Only 1 sentence should be sent to API (the miss)
            assert mock_client.translate_text.call_count == 1
            call_args = mock_client.translate_text.call_args
            contents = call_args.kwargs.get('contents', call_args[1].get('contents'))
            assert len(contents) == 1
            assert contents[0] == "How are you?"
            assert "Hola mundo." in result
        finally:
            tm._client = original_client

    def test_all_cached_no_api_call(self):
        """If all sentences are cached, no API call should be made."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()

            # Pre-populate cache for both sentences
            for text, translation in [("Hello world.", "Hola mundo."), ("How are you?", "Como estas?")]:
                text_hash = hashlib.md5(text.encode()).hexdigest()
                cache_key = service._get_cache_key(text_hash, 'es')
                service.translation_cache[cache_key] = translation

            result = service.translate_text_by_sentence('es', "Hello world. How are you?")

            assert mock_client.translate_text.call_count == 0
            assert "Hola mundo." in result
            assert "Como estas?" in result
        finally:
            tm._client = original_client

    def test_sentence_order_preserved(self):
        """Translated sentences should maintain original order regardless of cache state."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.return_value = self._make_mock_response(["Bonjour!"])  # Only "Wow!" is a miss
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()

            # Cache 2nd and 3rd sentences, miss 1st
            for text, translation in [("That is great.", "C'est génial."), ("Goodbye.", "Au revoir.")]:
                text_hash = hashlib.md5(text.encode()).hexdigest()
                cache_key = service._get_cache_key(text_hash, 'fr')
                service.translation_cache[cache_key] = translation

            result = service.translate_text_by_sentence('fr', "Wow! That is great. Goodbye.")

            # Order should be: Bonjour! C'est génial. Au revoir.
            parts = result.split(' ')
            assert parts[0] == "Bonjour!"
            assert "C'est" in result
            assert "Au" in result
        finally:
            tm._client = original_client

    def test_api_error_falls_back_to_original(self):
        """If the batch API call fails, original text should be returned for missed sentences."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = Exception("API error")
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()

            result = service.translate_text_by_sentence('es', "Hello world. How are you?")

            # Should return original text since API failed
            assert "Hello world." in result
            assert "How are you?" in result
        finally:
            tm._client = original_client

    def test_empty_text(self):
        """Empty text should return empty string without API call."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()
            result = service.translate_text_by_sentence('es', "")
            assert result == ""
            assert mock_client.translate_text.call_count == 0
        finally:
            tm._client = original_client

    def test_single_sentence_no_split(self):
        """Single sentence without punctuation should still work."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.return_value = self._make_mock_response(["Hola mundo"])
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()
            result = service.translate_text_by_sentence('es', "Hello world")
            assert result == "Hola mundo"
            assert mock_client.translate_text.call_count == 1
        finally:
            tm._client = original_client

    def test_cache_populated_after_batch(self):
        """After batch translation, each sentence should be cached individually."""
        import utils.translation as tm

        original_client = tm._client
        mock_client = MagicMock()
        mock_client.translate_text.return_value = self._make_mock_response(["Hola mundo.", "Como estas?"])
        tm._client = mock_client

        try:
            from utils.translation import TranslationService

            service = TranslationService()
            service.translate_text_by_sentence('es', "Hello world. How are you?")

            # Both sentences should now be cached
            for text, expected in [("Hello world.", "Hola mundo."), ("How are you?", "Como estas?")]:
                text_hash = hashlib.md5(text.encode()).hexdigest()
                cache_key = service._get_cache_key(text_hash, 'es')
                assert cache_key in service.translation_cache
                assert service.translation_cache[cache_key] == expected
        finally:
            tm._client = original_client
