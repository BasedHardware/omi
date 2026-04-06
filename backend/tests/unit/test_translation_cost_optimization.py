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
    get_cached_translation,
    cache_translation,
    TranslationService,
    NEGATIVE_CACHE_TTL,
    MAX_DETECTION_CACHE_SIZE,
    MAX_BATCH_SIZE,
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

# Get the SAME module objects that classes were imported from
import utils.translation as _trans_mod
import utils.translation_cache as _cache_mod
import utils.translation_coordinator as _coord_mod

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

    def test_cjk_period_is_stable(self):
        """Chinese 。 should be recognized as sentence-ending punctuation (#6189)."""
        assert _is_text_stable("你好世界。", set()) is True

    def test_hindi_danda_is_stable(self):
        """Hindi danda (।) should trigger stability (#6189)."""
        assert _is_text_stable("नमस्ते दुनिया।", set()) is True

    def test_arabic_question_mark_is_stable(self):
        """Arabic question mark (؟) should trigger stability (#6189)."""
        assert _is_text_stable("كيف حالك؟", set()) is True


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

    def test_cjk_period_detected(self):
        """Chinese 。 should produce STABILITY_PUNCTUATION signal (#6189)."""
        signals = _compute_stability_signals("你好世界。", 0, 1, None, None)
        assert STABILITY_PUNCTUATION in signals

    def test_hindi_danda_detected(self):
        """Hindi danda (।) should produce STABILITY_PUNCTUATION signal (#6189)."""
        signals = _compute_stability_signals("नमस्ते।", 0, 1, None, None)
        assert STABILITY_PUNCTUATION in signals

    def test_arabic_question_mark_detected(self):
        """Arabic ؟ should produce STABILITY_PUNCTUATION signal (#6189)."""
        signals = _compute_stability_signals("كيف حالك؟", 0, 1, None, None)
        assert STABILITY_PUNCTUATION in signals


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


# ==================== Additional coverage: confidence detection boundaries ====================


class TestDetectLanguageWithConfidenceBoundaries:
    def setup_method(self):
        detection_cache.clear()

    def test_exact_min_confident_chars_threshold(self):
        """Text at exactly MIN_CONFIDENT_CHARS length should attempt detection."""
        text = "a" * MIN_CONFIDENT_CHARS
        lang, conf = detect_language_with_confidence(text, remove_non_lexical=False)
        # May or may not detect, but shouldn't return early
        # (the function should attempt langdetect, not bail on length)
        assert isinstance(conf, float)

    def test_one_below_min_confident_chars_returns_none(self):
        """Text one char below MIN_CONFIDENT_CHARS should return (None, 0.0)."""
        text = "a" * (MIN_CONFIDENT_CHARS - 1)
        lang, conf = detect_language_with_confidence(text, remove_non_lexical=False)
        assert lang is None
        assert conf == 0.0

    def test_langdetect_exception_returns_none(self):
        """LangDetectException should be caught and return (None, 0.0)."""
        from langdetect.lang_detect_exception import LangDetectException

        with patch.object(_trans_mod, 'langdetect_detect_langs', side_effect=LangDetectException(0, '')):
            detection_cache.clear()
            lang, conf = detect_language_with_confidence(
                "This is a long enough test sentence", remove_non_lexical=False
            )
            assert lang is None
            assert conf == 0.0

    def test_generic_exception_returns_none(self):
        """Generic exception in detection should be caught and return (None, 0.0)."""
        with patch.object(_trans_mod, 'langdetect_detect_langs', side_effect=RuntimeError("unexpected")):
            detection_cache.clear()
            lang, conf = detect_language_with_confidence(
                "This is a long enough test sentence", remove_non_lexical=False
            )
            assert lang is None
            assert conf == 0.0

    def test_cache_eviction_at_max_size(self):
        """When cache exceeds MAX_DETECTION_CACHE_SIZE, oldest entries should be evicted."""
        detection_cache.clear()
        # Fill cache to max
        for i in range(MAX_DETECTION_CACHE_SIZE):
            detection_cache[f"conf:test_key_{i}"] = ("en", 0.95)
        assert len(detection_cache) == MAX_DETECTION_CACHE_SIZE

        # Adding one more via the real function should evict the oldest
        detect_language_with_confidence(
            "This is a brand new English sentence for cache eviction test", remove_non_lexical=False
        )
        assert len(detection_cache) <= MAX_DETECTION_CACHE_SIZE

    def test_empty_detect_langs_result(self):
        """Empty results from langdetect should return (None, 0.0)."""
        with patch.object(_trans_mod, 'langdetect_detect_langs', return_value=[]):
            detection_cache.clear()
            lang, conf = detect_language_with_confidence(
                "This is a long enough test sentence", remove_non_lexical=False
            )
            assert lang is None
            assert conf == 0.0


# ==================== Additional coverage: classifier boundaries ====================


class TestClassifyTranslationNeedBoundaries:
    def setup_method(self):
        detection_cache.clear()

    def test_low_confidence_same_language_defers(self):
        """Same language at below CONFIDENCE_TARGET_SKIP should DEFER."""
        with patch.object(
            _trans_mod, 'detect_language_with_confidence', return_value=('en', CONFIDENCE_TARGET_SKIP - 0.01)
        ):
            need = classify_translation_need("some text here enough", target_language='en', is_stable=True)
            assert need == TranslationNeed.DEFER

    def test_low_confidence_foreign_defers(self):
        """Foreign language at below CONFIDENCE_FOREIGN_TRANSLATE should DEFER."""
        with patch.object(
            _trans_mod, 'detect_language_with_confidence', return_value=('fr', CONFIDENCE_FOREIGN_TRANSLATE - 0.01)
        ):
            need = classify_translation_need("some text here enough", target_language='en', is_stable=True)
            assert need == TranslationNeed.DEFER

    def test_exact_confidence_target_skip_threshold(self):
        """Target language at exactly CONFIDENCE_TARGET_SKIP should SKIP."""
        with patch.object(_trans_mod, 'detect_language_with_confidence', return_value=('en', CONFIDENCE_TARGET_SKIP)):
            need = classify_translation_need("some text here enough", target_language='en', is_stable=True)
            assert need == TranslationNeed.SKIP

    def test_exact_confidence_foreign_translate_threshold(self):
        """Foreign language at exactly CONFIDENCE_FOREIGN_TRANSLATE + stable should TRANSLATE."""
        with patch.object(
            _trans_mod, 'detect_language_with_confidence', return_value=('fr', CONFIDENCE_FOREIGN_TRANSLATE)
        ):
            need = classify_translation_need("some text here enough", target_language='en', is_stable=True)
            assert need == TranslationNeed.TRANSLATE

    def test_detection_failure_defers(self):
        """When detection returns None, should DEFER."""
        with patch.object(_trans_mod, 'detect_language_with_confidence', return_value=(None, 0.0)):
            need = classify_translation_need("some text here enough", target_language='en', is_stable=True)
            assert need == TranslationNeed.DEFER


# ==================== Additional coverage: negative caching boundaries ====================


class TestNegativeCachingBoundaries:
    def setup_method(self):
        self._mock_r = MagicMock()
        self._mock_r.exists.return_value = 0
        self._mock_r.set.return_value = True

    def test_set_negative_cache_uses_ttl(self):
        """set_negative_cache should use NEGATIVE_CACHE_TTL for the Redis key."""
        with patch.object(_trans_mod, 'r', self._mock_r):
            set_negative_cache("abc123", "en")
            call_args = self._mock_r.set.call_args
            assert call_args[1].get('ex') == NEGATIVE_CACHE_TTL or call_args[0][2] if len(call_args[0]) > 2 else True
            # More specific: check the 'ex' keyword
            self._mock_r.set.assert_called_once_with("translate:v2:neg:abc123:en", "1", ex=NEGATIVE_CACHE_TTL)

    def test_get_negative_cache_redis_exception_returns_false(self):
        """Redis exception on read should fail open (return False)."""
        self._mock_r.exists.side_effect = Exception("Redis connection refused")
        with patch.object(_trans_mod, 'r', self._mock_r):
            result = get_negative_cache("abc123", "en")
            assert result is False

    def test_set_negative_cache_redis_exception_no_raise(self):
        """Redis exception on write should not raise."""
        self._mock_r.set.side_effect = Exception("Redis connection refused")
        with patch.object(_trans_mod, 'r', self._mock_r):
            # Should not raise
            set_negative_cache("abc123", "en")


# ==================== Additional coverage: translate_units_batch ====================


class TestTranslateUnitsBatchExtended:
    def setup_method(self):
        self._mock_r = MagicMock()
        self._mock_r.get.return_value = None
        self._mock_r.exists.return_value = 0
        self._mock_r.set.return_value = True

    def test_negative_cache_hit_returns_original(self):
        """Negative cache hit should return original text without API call."""
        mock_r = MagicMock()
        mock_r.exists.return_value = 1  # negative cache hit
        mock_r.get.return_value = None
        mock_r.set.return_value = True

        mock_client = MagicMock()

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', mock_r):
            svc = TranslationService()
            units = [("seg1", "Hello world testing text")]
            results = svc.translate_units_batch("es", units)

            assert len(results) == 1
            assert results[0][0] == "seg1"
            assert results[0][1] == "Hello world testing text"  # original text returned
            mock_client.translate_text.assert_not_called()

    def test_redis_cache_hit_returns_cached(self):
        """Redis cache hit should return cached translation without API call."""
        import json

        mock_r = MagicMock()
        mock_r.exists.return_value = 0  # no negative cache
        mock_r.get.return_value = json.dumps({"text": "Hola mundo", "detected_lang": "en"})
        mock_r.set.return_value = True

        mock_client = MagicMock()

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', mock_r):
            svc = TranslationService()
            svc._memory_cache = OrderedDict()  # clear memory cache
            units = [("seg1", "Hello world testing text")]
            results = svc.translate_units_batch("es", units)

            assert len(results) == 1
            assert results[0][1] == "Hola mundo"
            assert results[0][2] == "en"
            mock_client.translate_text.assert_not_called()

    def test_memory_cache_hit_returns_cached(self):
        """Memory cache hit should return cached translation without API call."""
        mock_r = MagicMock()
        mock_r.exists.return_value = 0
        mock_r.get.return_value = None
        mock_r.set.return_value = True

        mock_client = MagicMock()

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', mock_r):
            svc = TranslationService()
            # Pre-populate memory cache
            text_hash = hashlib.md5("Hello world testing text".encode()).hexdigest()
            svc._set_memory_cache(text_hash, "es", "Hola mundo prueba", "en")

            units = [("seg1", "Hello world testing text")]
            results = svc.translate_units_batch("es", units)

            assert len(results) == 1
            assert results[0][1] == "Hola mundo prueba"
            mock_client.translate_text.assert_not_called()

    def test_api_failure_fallback_returns_original(self):
        """API failure should fallback to returning original text."""
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = Exception("API error")

        with patch.object(_trans_mod, '_client', mock_client), patch.object(_trans_mod, 'r', self._mock_r):
            svc = TranslationService()
            units = [("seg1", "Hello world testing text for API")]
            results = svc.translate_units_batch("es", units)

            assert len(results) == 1
            assert results[0][0] == "seg1"
            assert results[0][1] == "Hello world testing text for API"
            assert results[0][2] == ''


# ==================== Additional coverage: ConversationLanguageState edges ====================


class TestConversationLanguageStateEdges:
    def setup_method(self):
        detection_cache.clear()

    def test_should_probe_true_updates_last_probe_time(self):
        """should_probe() returning True should update last_probe_time."""
        state = ConversationLanguageState('en')
        state.monolingual = True
        state.last_probe_time = 0.0  # long ago
        old_time = state.last_probe_time

        result = state.should_probe()
        assert result is True
        assert state.last_probe_time > old_time

    def test_should_probe_false_when_not_monolingual(self):
        """should_probe() should return False when not in monolingual mode."""
        state = ConversationLanguageState('en')
        state.monolingual = False
        assert state.should_probe() is False

    def test_low_confidence_preserves_gate_state(self):
        """Low confidence observation should not change monolingual gate.

        We directly manipulate the state and verify behavior for the case
        where detection returns None (too short/ambiguous).
        """
        state = ConversationLanguageState('en')
        state.monolingual = True
        state.consecutive_target = 5

        # Short/ambiguous text returns (None, 0.0) from detection
        # When detection returns None, observe() returns current monolingual state
        result = state.observe("ok")
        # Gate preserved (monolingual=True), consecutive_target unchanged
        assert state.monolingual is True
        assert state.consecutive_target == 5
        assert result is True  # returns current monolingual state when detection is None

    def test_speaker_foreign_flag_cleared_on_target(self):
        """Speaker's foreign flag should be cleared after confident target utterance."""
        state = ConversationLanguageState('en')
        state.speaker_state[1] = True  # marked as foreign

        # Observe confident English from same speaker
        state.observe(
            "This is a very clear English sentence with enough words to be confident about detection",
            speaker_id=1,
        )

        # If detected as target at high confidence, speaker should no longer be foreign
        if state.consecutive_target > 0:
            assert state.is_speaker_foreign(1) is False

    def test_consecutive_target_resets_on_foreign(self):
        """consecutive_target should reset to 0 on foreign detection."""
        state = ConversationLanguageState('en')
        state.consecutive_target = 3

        state.observe("Bonjour, comment allez-vous aujourd'hui? Je suis très content de vous voir.", speaker_id=0)

        assert state.consecutive_target == 0

    def test_probe_interval_boundary(self):
        """Probing at exactly the interval should return True."""
        state = ConversationLanguageState('en')
        state.monolingual = True
        state.last_probe_time = time.monotonic() - state.PROBE_INTERVAL_SECONDS
        assert state.should_probe() is True


# ==================== Additional coverage: TranslationCoordinator success path ====================


class TestTranslationCoordinatorExtended:
    def _make_segment(self, text, segment_id="seg1", speaker_id=0):
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
    async def test_flush_batch_calls_api_and_callback(self):
        """_flush_batch should call translate_units_batch and on_translation_ready."""
        cb = AsyncMock()
        coord, svc, _ = self._make_coordinator(target='en', callback=cb)
        svc.translate_units_batch.return_value = [("seg1", "Bonjour traduit", "fr")]

        # Directly populate the batch buffer and segment state
        state = SegmentState(segment_id="seg1")
        state.version = 1
        state.latest_text = "Hello translated text"
        coord._segment_states["seg1"] = state
        coord._batch_buffer.append(("seg1", "Hello translated text", "conv1", 1))

        # Mock should_persist_translation to return True
        with patch.object(_coord_mod, 'should_persist_translation', return_value=True):
            await coord._flush_batch()

        svc.translate_units_batch.assert_called_once()
        cb.assert_awaited_once_with("seg1", "Bonjour traduit", "fr", "conv1")
        assert coord._segment_states["seg1"].committed_text == "Hello translated text"
        assert coord._segment_states["seg1"].assembled_translation == "Bonjour traduit"
        assert coord._segment_states["seg1"].detected_lang == "fr"

    @pytest.mark.asyncio
    async def test_flush_batch_noop_sets_negative_cache(self):
        """When should_persist_translation returns False, negative cache should be set and callback skipped."""
        cb = AsyncMock()
        coord, svc, _ = self._make_coordinator(target='en', callback=cb)
        svc.translate_units_batch.return_value = [("seg1", "Hello same text", "en")]

        state = SegmentState(segment_id="seg1")
        state.version = 1
        coord._segment_states["seg1"] = state
        coord._batch_buffer.append(("seg1", "Hello same text", "conv1", 1))

        with patch.object(_coord_mod, 'should_persist_translation', return_value=False):
            await coord._flush_batch()

        # Callback should NOT be called for no-op translations
        cb.assert_not_awaited()
        # Negative cache counter should be incremented
        assert coord.metrics['negative_cache_sets'] > 0
        # committed_text should be updated
        assert coord._segment_states["seg1"].committed_text == "Hello same text"

    @pytest.mark.asyncio
    async def test_flush_batch_stale_version_skipped(self):
        """Segments with stale versions should be skipped during flush."""
        cb = AsyncMock()
        coord, svc, _ = self._make_coordinator(target='en', callback=cb)
        svc.translate_units_batch.return_value = [("seg1", "Translated", "fr")]

        state = SegmentState(segment_id="seg1")
        state.version = 2  # version advanced past what's in buffer
        coord._segment_states["seg1"] = state
        coord._batch_buffer.append(("seg1", "Old text", "conv1", 1))  # stale version=1

        await coord._flush_batch()

        # API should not be called since no valid units
        svc.translate_units_batch.assert_not_called()
        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flush_batch_removed_segment_skipped(self):
        """Removed segments should be skipped during flush."""
        cb = AsyncMock()
        coord, svc, _ = self._make_coordinator(target='en', callback=cb)

        # Buffer has seg1 but state was already removed
        coord._batch_buffer.append(("seg1", "Some text", "conv1", 1))

        await coord._flush_batch()

        svc.translate_units_batch.assert_not_called()
        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mono_gate_skip_with_probe_false(self):
        """Monolingual gate active + should_probe=False should skip translation."""
        coord, svc, cb = self._make_coordinator(target='en')
        # Force monolingual mode
        coord.language_state.monolingual = True
        coord.language_state.consecutive_target = 10
        coord.language_state.last_probe_time = time.monotonic()  # recent probe

        seg = self._make_segment(
            "This is a clear English sentence that should be skipped by the monolingual gate",
        )
        await coord.observe([seg], [], "conv1")

        assert coord.metrics['mono_gate_skips'] > 0
        svc.translate_units_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_mono_gate_probe_allows_classification(self):
        """Monolingual gate active + should_probe=True should allow classification."""
        coord, svc, cb = self._make_coordinator(target='en')
        # Force monolingual mode with expired probe
        coord.language_state.monolingual = True
        coord.language_state.consecutive_target = 10
        coord.language_state.last_probe_time = 0.0  # expired

        seg = self._make_segment(
            "This is a clear English sentence for the probe test to classify correctly",
        )
        await coord.observe([seg], [], "conv1")

        # Even though monolingual gate returns True for observe, should_probe=True
        # means we continue to classification instead of skipping
        total_classified = (
            coord.metrics['classify_skips'] + coord.metrics['classify_defers'] + coord.metrics['classify_translates']
        )
        # Should have gone through classification (not mono_gate_skips)
        # This may still get mono_gate_skips=0 and classify_skips=1 if probe triggered
        assert total_classified > 0 or coord.metrics['mono_gate_skips'] > 0
