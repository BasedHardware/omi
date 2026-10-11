import time
from typing import Dict, Optional

from config.translation import translation_profile_gate_enabled
from utils.translation_core.quality import output_rejection_reason
from utils.translation_language import expected_foreign_language

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
    return output_rejection_reason(source_text, translated_text, target_language or '') is None


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
            return True

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
        self.established_languages: set[str] = set()
        # Per-speaker tracking for multi-speaker conversations
        self.speaker_state: Dict[int, bool] = {}  # speaker_id -> is_foreign

    def observe(self, text: str, speaker_id: Optional[int] = None) -> bool:
        """Observe a segment and return True if translation should be skipped.

        Returns True = skip translation (monolingual gate active).
        Returns False = translation may be needed.
        """
        detected_lang, confidence = detect_language_with_confidence(text, remove_non_lexical=True)
        return self.observe_detection(detected_lang, confidence, speaker_id=speaker_id)

    def observe_detection(
        self,
        detected_lang: Optional[str],
        confidence: float,
        speaker_id: Optional[int] = None,
    ) -> bool:
        """Apply an already-computed local or provider language detection."""

        if not detected_lang:
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

    def source_is_plausible(self, text: str, expected_languages: tuple[str, ...]) -> bool:
        """A short fragment cannot teach its own prior or poison shared caches.

        Expected languages are spoken-language hints, not reading preferences.
        A substantial confident sample admits an unlisted language immediately.
        Without a profile, require substantial Latin-script evidence or a clear
        non-Latin script. Short ambiguous Latin fragments defer until a longer
        sample establishes their language in this conversation.
        """
        if not translation_profile_gate_enabled():
            return True
        language, confidence = detect_language_with_confidence(text)
        base = _normalize_base_language(language)
        if expected_foreign_language(text, self.target_base, expected_languages):
            return True
        if not base:
            return True  # the ordinary confidence/stability gate still defers
        if base == self.target_base or base in self.established_languages:
            return True
        if base in {_normalize_base_language(code) for code in expected_languages}:
            raw_language, raw_confidence = detect_language_with_confidence(text, remove_non_lexical=False)
            return _normalize_base_language(raw_language) == base and raw_confidence >= CONFIDENCE_FOREIGN_TRANSLATE
        alphabetic = [char for char in text if char.isalpha()]
        if not expected_languages and alphabetic:
            non_latin = sum(ord(char) > 0x024F for char in alphabetic)
            if non_latin >= 6 and non_latin * 5 >= len(alphabetic) * 3 and confidence >= 0.95:
                self.established_languages.add(base)
                return True
        if confidence >= 0.95 and len(alphabetic) >= 40:
            raw_language, raw_confidence = detect_language_with_confidence(text, remove_non_lexical=False)
            if _normalize_base_language(raw_language) == base and raw_confidence >= 0.95:
                self.established_languages.add(base)
                return True
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
