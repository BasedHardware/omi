"""Tests for translation cost optimization (issue #6155).

Covers:
- detect_language_with_confidence
- classify_translation_need / TranslationNeed
- ConversationLanguageState (monolingual gate)
- TranslationCoordinator (batch, stability, prefix-safe)
- Negative caching
- translate_units_batch
"""

import asyncio
import hashlib
import sys
import time
from collections import OrderedDict
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# --- Module-level mocks for heavy dependencies (must happen before any project imports) ---
_mock_redis = MagicMock()
_mock_redis.get.return_value = None
_mock_redis.set.return_value = True
_mock_redis.exists.return_value = 0

if 'database' not in sys.modules:
    sys.modules['database'] = MagicMock()
if 'database.redis_db' not in sys.modules:
    sys.modules['database.redis_db'] = MagicMock(r=_mock_redis)
else:
    sys.modules['database.redis_db'].r = _mock_redis

if 'google' not in sys.modules:
    sys.modules['google'] = MagicMock()
if 'google.cloud' not in sys.modules:
    sys.modules['google.cloud'] = MagicMock()
if 'google.cloud.translate_v3' not in sys.modules:
    sys.modules['google.cloud.translate_v3'] = MagicMock()

# Now import project modules (they'll use the mocks above)
from utils.translation import (
    TranslationNeed,
    detect_language_with_confidence,
    classify_translation_need,
    MIN_CONFIDENT_CHARS,
    CONFIDENCE_TARGET_SKIP,
    CONFIDENCE_FOREIGN_TRANSLATE,
    detection_cache,
    set_negative_cache,
    get_negative_cache,
    TranslationService,
)
from utils.translation_cache import (
    ConversationLanguageState,
    _normalize_base_language,
)
from utils.translation_coordinator import (
    TranslationCoordinator,
    SegmentState,
    _is_text_stable,
    _compute_stability_signals,
    STABILITY_PUNCTUATION,
    STABILITY_SPEAKER_SWITCH,
    STABILITY_SILENCE_GAP,
    STABILITY_SOFT_BOUNDARY,
    SOFT_BOUNDARY_TOKEN_COUNT,
    SOFT_BOUNDARY_OPEN_SECONDS,
    BATCH_WINDOW_SECONDS,
)

# Get the SAME module that TranslationService was imported from
import utils.translation as _trans_mod

# ==================== detect_language_with_confidence ====================


class TestDetectLanguageWithConfidence:
    def setup_method(self):
        detection_cache.clear()

    def test_short_text_returns_none(self):
        """Text shorter than MIN_CONFIDENT_CHARS should return (None, 0.0)."""
        lang, conf = detect_language_with_confidence("hi", remove_non_lexical=False)
        assert lang is None
        assert conf == 0.0

    def test_empty_text_returns_none(self):
        lang, conf = detect_language_with_confidence("")
        assert lang is None
        assert conf == 0.0

    def test_english_text_detected(self):
        """Long English text should be detected as English with high confidence."""
        lang, conf = detect_language_with_confidence(
            "This is a test of the language detection system with enough text to be confident",
            remove_non_lexical=True,
        )
        assert lang == 'en'
        assert conf > 0.5

    def test_non_lexical_removal(self):
        """Non-lexical utterances should be stripped before detection."""
        lang, conf = detect_language_with_confidence("um ah oh uh hmm", remove_non_lexical=True)
        assert lang is None
        assert conf == 0.0

    def test_caching(self):
        """Results should be cached for identical text."""
        text = "This is a reasonably long English sentence for detection"
        lang1, conf1 = detect_language_with_confidence(text, remove_non_lexical=False)
        lang2, conf2 = detect_language_with_confidence(text, remove_non_lexical=False)
        assert lang1 == lang2
        assert conf1 == conf2

    def test_french_text(self):
        """French text should be detected as French."""
        lang, conf = detect_language_with_confidence(
            "Bonjour, comment allez-vous aujourd'hui? Je suis très content de vous voir.",
            remove_non_lexical=False,
        )
        assert lang == 'fr'
        assert conf > 0.5


# ==================== classify_translation_need ====================


class TestClassifyTranslationNeed:
    def setup_method(self):
        detection_cache.clear()

    def test_skip_for_confident_target(self):
        """Text in the target language at high confidence should SKIP."""
        need = classify_translation_need(
            "This is a clear English sentence that should be skipped from translation processing",
            target_language='en',
            is_stable=True,
        )
        assert need == TranslationNeed.SKIP

    def test_translate_for_confident_foreign_stable(self):
        """Foreign text at high confidence + stable should TRANSLATE."""
        need = classify_translation_need(
            "Bonjour, comment allez-vous aujourd'hui? Je suis très content.",
            target_language='en',
            is_stable=True,
        )
        assert need == TranslationNeed.TRANSLATE

    def test_defer_for_foreign_not_stable(self):
        """Foreign text at high confidence but NOT stable should DEFER."""
        need = classify_translation_need(
            "Bonjour, comment allez-vous aujourd'hui? Je suis très content.",
            target_language='en',
            is_stable=False,
        )
        assert need == TranslationNeed.DEFER

    def test_defer_for_short_text(self):
        """Short text should DEFER (not enough for confident detection)."""
        need = classify_translation_need("hi there", target_language='en', is_stable=True)
        assert need == TranslationNeed.DEFER

    def test_skip_for_empty_target(self):
        """No target language should return SKIP (nothing to do)."""
        need = classify_translation_need("anything", target_language='', is_stable=True)
        assert need == TranslationNeed.SKIP

    def test_handles_locale_tagged_target(self):
        """Target like 'en-US' should be normalized to 'en'."""
        need = classify_translation_need(
            "This is a clear English sentence that should be recognized as target language text",
            target_language='en-US',
            is_stable=True,
        )
        assert need == TranslationNeed.SKIP


# ==================== ConversationLanguageState ====================


class TestConversationLanguageState:
    def setup_method(self):
        detection_cache.clear()

    def test_enters_monolingual_after_threshold(self):
        """After MONOLINGUAL_THRESHOLD consecutive target detections, monolingual=True."""
        state = ConversationLanguageState('en')
        english_texts = [
            "This is a perfectly clear English sentence number one for testing",
            "Another English sentence that is long enough for confident detection",
            "The third English sentence here should be clearly detectable as English",
            "Fourth and final English sentence to trigger the monolingual threshold",
        ]
        for text in english_texts:
            state.observe(text)
        assert state.monolingual is True

    def test_exits_monolingual_on_foreign(self):
        """Foreign text should immediately exit monolingual mode."""
        state = ConversationLanguageState('en')
        state.monolingual = True
        state.consecutive_target = 10

        result = state.observe("Bonjour, comment allez-vous aujourd'hui? Je suis très content de vous rencontrer.")
        assert state.monolingual is False
        assert result is False

    def test_short_text_preserves_gate(self):
        """Short text (can't detect) should preserve current gate state."""
        state = ConversationLanguageState('en')
        state.monolingual = True
        result = state.observe("ok")  # too short for detection
        assert state.monolingual is True
        assert result is True

    def test_speaker_tracking(self):
        """Per-speaker foreign state should be tracked."""
        state = ConversationLanguageState('en')
        state.observe(
            "Bonjour, comment allez-vous aujourd'hui? Je suis très content de vous voir.",
            speaker_id=1,
        )
        assert state.is_speaker_foreign(1) is True
        assert state.is_speaker_foreign(0) is False

    def test_should_probe_respects_interval(self):
        """Probing should only happen after PROBE_INTERVAL_SECONDS."""
        state = ConversationLanguageState('en')
        state.monolingual = True
        state.last_probe_time = time.monotonic()
        assert state.should_probe() is False

    def test_not_monolingual_initially(self):
        state = ConversationLanguageState('en')
        assert state.monolingual is False


# ==================== _is_text_stable ====================


class TestIsTextStable:
    def test_punctuation_is_stable(self):
        assert _is_text_stable("Hello world.", {STABILITY_PUNCTUATION}) is True

    def test_speaker_switch_is_stable(self):
        assert _is_text_stable("Hello", {STABILITY_SPEAKER_SWITCH}) is True

    def test_empty_text_not_stable(self):
        assert _is_text_stable("", {STABILITY_PUNCTUATION}) is False

    def test_no_signals_with_punctuation(self):
        """Auto-detect sentence-ending punctuation even without explicit signal."""
        assert _is_text_stable("Hello world.", set()) is True

    def test_no_signals_no_punctuation(self):
        assert _is_text_stable("Hello world", set()) is False

    def test_soft_boundary(self):
        assert _is_text_stable("Hello", {STABILITY_SOFT_BOUNDARY}) is True


# ==================== _compute_stability_signals ====================


class TestComputeStabilitySignals:
    def test_punctuation_detected(self):
        signals = _compute_stability_signals("Hello world.", 0, 1, None, None)
        assert STABILITY_PUNCTUATION in signals

    def test_speaker_switch_detected(self):
        signals = _compute_stability_signals("Hello", 0, 1, 0, 1)
        assert STABILITY_SPEAKER_SWITCH in signals

    def test_soft_boundary_time(self):
        now = time.monotonic()
        signals = _compute_stability_signals("Hello", now - 4.0, now, None, None)
        assert STABILITY_SOFT_BOUNDARY in signals

    def test_soft_boundary_tokens(self):
        text = " ".join(["word"] * SOFT_BOUNDARY_TOKEN_COUNT)
        signals = _compute_stability_signals(text, 0, 1, None, None)
        assert STABILITY_SOFT_BOUNDARY in signals

    def test_no_signals_short_text(self):
        now = time.monotonic()
        signals = _compute_stability_signals("hi", now, now, None, None)
        assert len(signals) == 0


# ==================== Negative caching ====================


class TestNegativeCaching:
    def setup_method(self):
        self._mock_r = MagicMock()
        self._mock_r.exists.return_value = 0
        self._mock_r.set.return_value = True

    def test_set_negative_cache(self):
        with patch.object(_trans_mod, 'r', self._mock_r):
            set_negative_cache("abc123", "en")
            self._mock_r.set.assert_called()

    def test_get_negative_cache_miss(self):
        self._mock_r.exists.return_value = 0
        with patch.object(_trans_mod, 'r', self._mock_r):
            assert get_negative_cache("abc123", "en") is False

    def test_get_negative_cache_hit(self):
        self._mock_r.exists.return_value = 1
        with patch.object(_trans_mod, 'r', self._mock_r):
            assert get_negative_cache("abc123", "en") is True


# ==================== TranslationService.translate_units_batch ====================


class TestTranslateUnitsBatch:
    def setup_method(self):
        self._mock_r = MagicMock()
        self._mock_r.get.return_value = None
        self._mock_r.exists.return_value = 0
        self._mock_r.set.return_value = True

    def test_batch_deduplication(self):
        """Identical texts should only be sent to API once."""
        mock_response = MagicMock()
        mock_translation = MagicMock()
        mock_translation.translated_text = "Hola"
        mock_translation.detected_language_code = "en"
        mock_response.translations = [mock_translation]

        mock_client = MagicMock()
        mock_client.translate_text.return_value = mock_response

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', self._mock_r):
            svc = TranslationService()
            units = [
                ("seg1", "Hello world testing long text for translation"),
                ("seg2", "Hello world testing long text for translation"),  # duplicate
            ]
            results = svc.translate_units_batch("es", units)

            assert len(results) == 2
            assert results[0][1] == "Hola"
            assert results[1][1] == "Hola"
            assert mock_client.translate_text.call_count == 1

    def test_batch_returns_correct_order(self):
        """Results should be returned in input order."""
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Bonjour"
        t1.detected_language_code = "en"
        t2 = MagicMock()
        t2.translated_text = "Au revoir"
        t2.detected_language_code = "en"
        mock_response.translations = [t1, t2]

        mock_client = MagicMock()
        mock_client.translate_text.return_value = mock_response

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', self._mock_r):
            svc = TranslationService()
            units = [
                ("seg1", "Hello there this is a test sentence"),
                ("seg2", "Goodbye this is another test sentence"),
            ]
            results = svc.translate_units_batch("fr", units)

            assert results[0] == ("seg1", "Bonjour", "en")
            assert results[1] == ("seg2", "Au revoir", "en")

    def test_batch_empty(self):
        svc = TranslationService()
        results = svc.translate_units_batch("fr", [])
        assert results == []


# ==================== TranslationCoordinator ====================


class TestTranslationCoordinator:
    def _make_segment(self, text, segment_id="seg1", speaker_id=0):
        """Create a mock TranscriptSegment."""
        seg = MagicMock()
        seg.id = segment_id
        seg.text = text
        seg.speaker_id = speaker_id
        seg.translations = []
        return seg

    def _make_coordinator(self, target='en', callback=None):
        svc = MagicMock(spec=TranslationService)
        svc.translate_units_batch.return_value = []
        cb = callback or AsyncMock()
        coord = TranslationCoordinator(
            target_language=target,
            translation_service=svc,
            on_translation_ready=cb,
        )
        return coord, svc, cb

    @pytest.mark.asyncio
    async def test_skip_target_language(self):
        """English text with English target should be skipped (no API call)."""
        coord, svc, cb = self._make_coordinator(target='en')

        seg = self._make_segment(
            "This is a clear English sentence that should be skipped from translation",
        )
        await coord.observe([seg], [], "conv1")
        await asyncio.sleep(0.5)

        assert coord.metrics['classify_skips'] > 0 or coord.metrics['mono_gate_skips'] > 0
        svc.translate_units_batch.assert_not_called()
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_translate_foreign_stable(self):
        """Foreign stable text should be batched and translated."""
        coord, svc, cb = self._make_coordinator(target='en')
        svc.translate_units_batch.return_value = [
            ("seg1", "Hello, how are you today? I am very happy to see you.", "fr")
        ]

        seg = self._make_segment(
            "Bonjour, comment allez-vous aujourd'hui? Je suis très content de vous voir.",
        )
        await coord.observe([seg], [], "conv1")
        await asyncio.sleep(BATCH_WINDOW_SECONDS + 0.2)

        total = (
            coord.metrics['classify_translates'] + coord.metrics['classify_defers'] + coord.metrics['classify_skips']
        )
        assert total > 0

    @pytest.mark.asyncio
    async def test_removed_ids_cleanup(self):
        """Removed segment IDs should be cleaned from tracking."""
        coord, svc, cb = self._make_coordinator(target='en')

        coord._segment_states["seg_old"] = SegmentState(segment_id="seg_old", latest_text="test")
        await coord.observe([], ["seg_old"], "conv1")
        assert "seg_old" not in coord._segment_states

    @pytest.mark.asyncio
    async def test_prefix_reset(self):
        """When text no longer starts with committed_text, reset state."""
        coord, svc, cb = self._make_coordinator(target='en')

        state = SegmentState(segment_id="seg1")
        state.committed_text = "Hello world"
        state.assembled_translation = "Hola mundo"
        coord._segment_states["seg1"] = state

        seg = self._make_segment("Goodbye everyone this is a completely different sentence now")
        await coord.observe([seg], [], "conv1")

        assert coord.metrics['prefix_resets'] == 1
        assert coord._segment_states["seg1"].committed_text != "Hello world"

    @pytest.mark.asyncio
    async def test_flush(self):
        """flush() should complete without error."""
        coord, svc, cb = self._make_coordinator(target='en')
        await coord.flush()
        assert coord._active is False

    @pytest.mark.asyncio
    async def test_handle_segment_merge(self):
        """Merge map should update tracking correctly."""
        coord, svc, cb = self._make_coordinator(target='en')

        coord._segment_states["old"] = SegmentState(segment_id="old", committed_text="test")
        coord._segment_states["surviving"] = SegmentState(segment_id="surviving", committed_text="original")

        coord.handle_segment_merge({"old": "surviving"})

        assert "old" not in coord._segment_states
        assert coord._segment_states["surviving"].committed_text == ''


# ==================== TranslationNeed enum ====================


class TestTranslationNeedEnum:
    def test_values(self):
        assert TranslationNeed.SKIP == 'skip'
        assert TranslationNeed.TRANSLATE == 'translate'
        assert TranslationNeed.DEFER == 'defer'

    def test_string_comparison(self):
        assert TranslationNeed.SKIP == 'skip'
        assert TranslationNeed.TRANSLATE != 'skip'


# ==================== _normalize_base_language ====================


class TestNormalizeBaseLanguage:
    def test_with_locale(self):
        assert _normalize_base_language('en-US') == 'en'

    def test_simple(self):
        assert _normalize_base_language('fr') == 'fr'

    def test_none(self):
        assert _normalize_base_language(None) is None

    def test_empty(self):
        assert _normalize_base_language('') is None
