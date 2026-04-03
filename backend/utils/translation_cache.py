import time
from typing import Dict, Optional

from utils.translation import (
    detect_language,
    detect_language_with_confidence,
    CONFIDENCE_TARGET_SKIP,
    CONFIDENCE_FOREIGN_TRANSLATE,
)


def _normalize_base_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    return language.split('-')[0].lower()


def should_persist_translation(
    source_text: str, translated_text: str, detected_lang: Optional[str], target_language: Optional[str]
) -> bool:
    """
    Persist only when translation materially changes text.

    This prevents no-op "translations" (for example English->English) from
    creating a translation badge in the UI.
    """
    normalized_source = " ".join(source_text.split())
    normalized_translated = " ".join((translated_text or "").split())
    if normalized_source != normalized_translated:
        return True

    detected_base = _normalize_base_language(detected_lang)
    target_base = _normalize_base_language(target_language)
    # Explicit no-op when API confirms source is already in target language.
    if detected_base and target_base and detected_base == target_base:
        return False

    # Conservative default for unchanged text: don't persist no-op translation.
    return False


class TranscriptSegmentLanguageCache:
    """
    Tracks per-segment language detection state using free local detection only.
    Once a segment is detected as non-target-language, it stays that way
    (the segment will be translated).
    """

    def __init__(self):
        self.cache: Dict[str, Optional[bool]] = {}

    def is_in_target_language(self, segment_id: str, text: str, target_language: str) -> bool:
        was_in_target_language = self.cache.get(segment_id, None)
        if was_in_target_language is False:
            return False

        if not text:
            return was_in_target_language is not False

        # Use free local langdetect only (no paid API calls)
        # target_language should already be base-normalized (e.g. "en" not "en-US")
        detected_lang = detect_language(text, remove_non_lexical=True, hint_language=target_language)
        if detected_lang and detected_lang != target_language:
            self.cache[segment_id] = False
            return False

        if detected_lang and detected_lang == target_language:
            self.cache[segment_id] = True
            return True

        # Detection inconclusive (None) — don't assume target language, let translate API decide
        # Don't cache unknown state; segment will be sent to translate API which detects for free
        return False

    def update_from_translate_response(self, segment_id: str, detected_lang: str, target_language: str):
        """Update cache using detected_language_code from translate API response (free).
        target_language should be base-normalized (e.g. "en" not "en-US").
        """
        # Normalize detected_lang to base tag for comparison
        detected_base = _normalize_base_language(detected_lang)
        target_base = _normalize_base_language(target_language)
        if detected_base and target_base and detected_base == target_base:
            self.cache[segment_id] = True
        elif detected_base:
            self.cache[segment_id] = False

    def delete_cache(self, segment_id: str) -> None:
        if segment_id in self.cache:
            del self.cache[segment_id]


class ConversationLanguageState:
    """Conversation-level + speaker-level language state for the monolingual gate.

    Replaces per-segment detection with conversation-wide tracking:
    - After MONOLINGUAL_THRESHOLD consecutive confident target-language detections,
      enter monolingual mode (skip translation entirely).
    - Exit immediately on any confident foreign-language detection.
    - Periodic probes in monolingual mode to detect code-switching.
    """

    MONOLINGUAL_THRESHOLD = 4  # consecutive confident target detections to enter mono mode
    PROBE_INTERVAL_SECONDS = 30.0  # re-check language every N seconds during monolingual mode

    def __init__(self, target_language: str):
        self.target_base = _normalize_base_language(target_language) or ''
        self.consecutive_target = 0
        self.monolingual = False
        self.last_probe_time = 0.0
        # Per-speaker tracking for multi-speaker conversations
        self.speaker_state: Dict[int, bool] = {}  # speaker_id -> is_foreign

    def observe(self, text: str, speaker_id: Optional[int] = None) -> bool:
        """Observe a segment and return True if translation should be skipped.

        Returns True = skip translation (monolingual gate active).
        Returns False = translation may be needed.
        """
        detected_lang, confidence = detect_language_with_confidence(text, remove_non_lexical=True)

        if detected_lang is None:
            # Can't detect — don't break the gate, don't increment
            return self.monolingual

        detected_base = _normalize_base_language(detected_lang) or ''

        if detected_base == self.target_base and confidence >= CONFIDENCE_TARGET_SKIP:
            self.consecutive_target += 1
            if speaker_id is not None:
                self.speaker_state.pop(speaker_id, None)  # not foreign
            if self.consecutive_target >= self.MONOLINGUAL_THRESHOLD:
                self.monolingual = True
            return self.monolingual

        if confidence >= CONFIDENCE_FOREIGN_TRANSLATE and detected_base != self.target_base:
            # Foreign detected — exit monolingual mode immediately
            self.consecutive_target = 0
            self.monolingual = False
            if speaker_id is not None:
                self.speaker_state[speaker_id] = True  # mark as foreign
            return False

        # Low confidence — don't change gate state, but don't skip either
        return False

    def should_probe(self) -> bool:
        """In monolingual mode, periodically allow a detection check."""
        if not self.monolingual:
            return False
        now = time.monotonic()
        if now - self.last_probe_time >= self.PROBE_INTERVAL_SECONDS:
            self.last_probe_time = now
            return True
        return False

    def is_speaker_foreign(self, speaker_id: int) -> bool:
        """Check if a specific speaker was last detected as foreign."""
        return self.speaker_state.get(speaker_id, False)
