import re
from collections import OrderedDict
from enum import Enum
from typing import Callable, List, Match, Optional, Pattern, Tuple, Union, cast

from langdetect import (  # langdetect ships no py.typed marker; symbols are untyped
    detect as langdetect_detect,  # type: ignore[reportUnknownVariableType]
    detect_langs as langdetect_detect_langs,  # type: ignore[reportUnknownVariableType]
    DetectorFactory,
)
from langdetect.lang_detect_exception import LangDetectException

from models.transcript_segment import SENTENCE_FINDALL_RE

# LRU Cache for language detection (local, free via langdetect)
detection_cache: "OrderedDict[str, Union[str, Tuple[str, float]]]" = OrderedDict()
MAX_DETECTION_CACHE_SIZE = 1000

# A set of common English non-lexical utterances that can confuse language detectors.
# This list helps prevent misclassification of short, ambiguous sounds.
_non_lexical_utterances = {
    # Hesitations and fillers
    'ah',
    'aha',
    'ahem',
    'eh',
    'er',
    'erm',
    'ew',
    'ha',
    'hah',
    'harrumph',
    'hee',
    'heh',
    'hm',
    'hmm',
    'hmmm',
    'ho',
    'huh',
    'mm',
    'mmm',
    'mhm',
    'mhmm',
    'oh',
    'ooh',
    'um',
    'uh',
    'uh-huh',
    'uh-oh',
    'whoa',
    # Interjections and exclamations
    'ack',
    'aah',
    'ach',
    'agreed',
    'argh',
    'aw',
    'aww',
    'bam',
    'bah',
    'boo',
    'brr',
    'cheers',
    'congrats',
    'dang',
    'darn',
    'duh',
    'eek',
    'eep',
    'encore',
    'gosh',
    'grr',
    'gulp',
    'haha',
    'hehe',
    'hey',
    'hooray',
    'hurrah',
    'huzzah',
    'jeez',
    'meh',
    'ouch',
    'ow',
    'oy',
    'phew',
    'pfft',
    'pish',
    'psst',
    'shh',
    'shoo',
    'tsk',
    'tut-tut',
    'ugh',
    'wahoo',
    'whew',
    'whoops',
    'wow',
    'yahoo',
    'yay',
    'yeah',
    # Common short responses that can be language-agnostic
    'yep',
    'yup',
    'yo',
    'yikes',
    'yowza',
    'zing',
}

# Pre-compile the regex pattern for non-lexical utterances for efficiency.
_non_lexical_utterances_pattern = re.compile(
    r'\b(' + '|'.join(re.escape(word) for word in _non_lexical_utterances) + r')\b', re.IGNORECASE
)

_detector_seeded = False


def _ensure_detector_seeded() -> None:
    """Apply deterministic langdetect configuration at the call boundary."""
    global _detector_seeded
    if not _detector_seeded:
        DetectorFactory.seed = 0
        _detector_seeded = True


# Languages with 100% accuracy in langdetect
LANGDETECT_RELIABLE_LANGUAGES = {
    'af',
    'ar',
    'bg',
    'bn',
    'ca',
    'cs',
    'cy',
    'da',
    'de',
    'el',
    'en',
    'es',
    'et',
    'fa',
    'fi',
    'fr',
    'gu',
    'he',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'ko',
    'lt',
    'lv',
    'mk',
    'ml',
    'mr',
    'ne',
    'nl',
    'no',
    'pa',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sl',
    'so',
    'sq',
    'sv',
    'sw',
    'ta',
    'te',
    'th',
    'tl',
    'tr',
    'uk',
    'ur',
    'vi',
    'zh',
}

NLLB_SUPPORTED_SOURCE_LANGUAGES = {
    'en',
    'es',
    'zh',
    'hi',
    'pt',
    'ru',
    'ja',
    'de',
    'ar',
    'fr',
    'it',
    'ko',
    'nl',
    'th',
    'tr',
    'uk',
    'ur',
    'vi',
}


def _detect_with_langdetect(text: str, hint_language: Optional[str] = None) -> Optional[str]:
    # Normalize locale-tagged language (e.g. "en-US" -> "en") for langdetect compatibility
    base_hint = hint_language.split('-')[0] if hint_language else None
    if base_hint not in LANGDETECT_RELIABLE_LANGUAGES:
        return None
    try:
        _ensure_detector_seeded()
        return cast(str, langdetect_detect(text))
    except LangDetectException:
        return None


def detect_language(text: str, remove_non_lexical: bool = False, hint_language: Optional[str] = None) -> Optional[str]:
    """Detect language using free local langdetect library only (no paid API calls)."""
    text_for_detection = text
    if remove_non_lexical:
        cleaned_text = _non_lexical_utterances_pattern.sub('', text)
        text_for_detection = re.sub(r'\s+', ' ', cleaned_text).strip()

    if not text_for_detection:
        return None

    if text_for_detection in detection_cache:
        detection_cache.move_to_end(text_for_detection)
        return cast(str, detection_cache[text_for_detection])

    detected_language = _detect_with_langdetect(text_for_detection, hint_language)

    if detected_language:
        if len(detection_cache) >= MAX_DETECTION_CACHE_SIZE:
            detection_cache.popitem(last=False)
        detection_cache[text_for_detection] = detected_language
        return detected_language

    return detected_language


# --- Confidence-based language detection (issue #6155) ---

# Minimum number of lexical characters required for confident detection.
# Below this threshold, langdetect is unreliable on streaming text.
MIN_CONFIDENT_CHARS = 12

# Confidence thresholds for language detection probabilities.
CONFIDENCE_TARGET_SKIP = 0.90  # Skip translation if target language detected at this confidence
CONFIDENCE_FOREIGN_TRANSLATE = 0.80  # Translate if foreign language detected at this confidence


class TranslationNeed(str, Enum):
    """Result of classify_translation_need()."""

    SKIP = 'skip'  # Confident target language — no translation needed
    TRANSLATE = 'translate'  # Confident foreign language — should translate
    DEFER = 'defer'  # Uncertain — wait for more text or closing signal


def detect_language_with_confidence(
    text: str, remove_non_lexical: bool = True, hint_language: Optional[str] = None
) -> Tuple[Optional[str], float]:
    """Detect language with confidence score using langdetect.detect_langs().

    Returns (language_code, confidence) where confidence is 0.0-1.0.
    Returns (None, 0.0) if detection fails or text is too short.
    """
    text_for_detection = text
    if remove_non_lexical:
        cleaned_text = _non_lexical_utterances_pattern.sub('', text)
        text_for_detection = re.sub(r'\s+', ' ', cleaned_text).strip()

    if not text_for_detection or len(text_for_detection) < MIN_CONFIDENT_CHARS:
        return (None, 0.0)

    # Check cache first (reuse existing detection_cache)
    cache_key = f"conf:{text_for_detection}"
    if cache_key in detection_cache:
        detection_cache.move_to_end(cache_key)
        return cast(Tuple[str, float], detection_cache[cache_key])

    try:
        _ensure_detector_seeded()
        results = langdetect_detect_langs(text_for_detection)
        if not results:
            return (None, 0.0)

        top = results[0]
        result: Tuple[str, float] = (cast(str, top.lang), cast(float, top.prob))  # type: ignore[reportUnknownMemberType]  # langdetect Language.lang/prob untyped

        # Cache the result
        if len(detection_cache) >= MAX_DETECTION_CACHE_SIZE:
            detection_cache.popitem(last=False)
        detection_cache[cache_key] = result
        return result
    except LangDetectException:
        return (None, 0.0)


def classify_translation_need(text: str, target_language: str, is_stable: bool = False) -> TranslationNeed:
    """Classify whether text needs translation based on confidence-based detection.

    Args:
        text: The segment text to classify.
        target_language: The user's target language (e.g., 'en').
        is_stable: Whether the text is considered stable (sentence-complete, etc.).

    Returns:
        TranslationNeed.SKIP — confident target language, no translation needed.
        TranslationNeed.TRANSLATE — confident foreign language and stable text.
        TranslationNeed.DEFER — uncertain, wait for more text or closing signal.
    """
    target_base = target_language.split('-')[0].lower() if target_language else None
    if not target_base:
        return TranslationNeed.SKIP

    detected_lang, confidence = detect_language_with_confidence(text, remove_non_lexical=True)

    if detected_lang is None:
        # Too short or detection failed — defer
        return TranslationNeed.DEFER

    detected_base = detected_lang.split('-')[0].lower()

    if detected_base == target_base:
        if confidence >= CONFIDENCE_TARGET_SKIP:
            return TranslationNeed.SKIP
        # Low-confidence same language — defer, don't waste money
        return TranslationNeed.DEFER

    # Detected a different language
    if confidence >= CONFIDENCE_FOREIGN_TRANSLATE:
        if is_stable:
            return TranslationNeed.TRANSLATE
        # Foreign but not stable yet — defer until stable
        return TranslationNeed.DEFER

    # Low-confidence foreign — defer
    return TranslationNeed.DEFER


def split_into_sentences(text: str) -> List[str]:
    """Splits text into sentences based on sentence-ending punctuation and newlines.

    Recognizes Unicode sentence enders for CJK, Arabic, Hindi, and other non-English languages.
    Protects common abbreviations (Mr., Dr., U.S., 3.14, etc.) from being split
    by temporarily replacing them with placeholders before splitting.
    """
    if not text:
        return []

    # Placeholder strategy: replace internal periods in multi-part abbreviations
    # before sentence splitting, then restore them after. Combined with a
    # post-split merge step to handle false boundaries at abbreviation tails.
    #
    # Handles: U.S., U.K., 3.14, e.g., i.e., etc., vs.
    # Does NOT attempt to resolve single-period titles (Dr./Mr.) followed by
    # proper nouns — that requires NLP-level disambiguation.

    _ABBR = 'ⓐⓑⓒ'  # country code internal period
    _DEC = 'ⓓⓔⓕ'  # decimal point
    _LAT = 'ⓛⓐⓣ'  # latin abbrev internal period

    _ABBREV_PATTERNS: List[Tuple[Pattern[str], Union[str, Callable[[Match[str]], str]]]] = [
        # Extended multi-part acronyms: U.S.A. → UⓐⓑⓒSⓐⓑⓒA.
        (
            re.compile(r'\b([A-Z])\.([A-Z])\.([A-Z])\.'),
            lambda m: m.group(1) + _ABBR + m.group(2) + _ABBR + m.group(3) + '.',
        ),
        # Country codes: U.S. → UⓐⓑⓒS. (internal period protected, trailing period kept)
        (re.compile(r'\b([A-Z])\.([A-Z])\.'), lambda m: m.group(1) + _ABBR + m.group(2) + '.'),
        # Decimal/version numbers: 3.14 → 3ⓓⓔⓕ14
        (re.compile(r'(?<=\d)\.(?=\d)'), _DEC),
        # Latin abbreviations: e.g. → eⓛⓐⓣg.
        (re.compile(r'\b([a-z])\.([a-z])\.'), lambda m: m.group(1) + _LAT + m.group(2) + '.'),
        # etc. → etcⓛⓐⓣ
        (re.compile(r'\betc\.'), 'etc' + _LAT),
        # vs. → vsⓛⓐⓣ
        (re.compile(r'\bvs\.'), 'vs' + _LAT),
    ]

    result: List[str] = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Phase 1: Replace abbreviation internals with placeholders
        protected = line
        for pattern, replacement in _ABBREV_PATTERNS:
            protected = pattern.sub(replacement, protected)

        # Phase 2: Split on sentence boundaries
        raw = SENTENCE_FINDALL_RE.findall(protected)

        # Phase 3: Restore placeholders
        restored_list: List[str] = []
        for s in raw:
            s = s.strip()
            if not s:
                continue
            restored = s.replace(_ABBR, '.').replace(_DEC, '.').replace(_LAT, '.')
            restored_list.append(restored)

        # Phase 4: Merge false splits at abbreviation boundaries
        merged: List[str] = []
        for seg in restored_list:
            if merged and _should_merge(merged[-1], seg):
                merged[-1] = merged[-1] + ' ' + seg
            else:
                merged.append(seg)
        result.extend(merged)
    return result


def _should_merge(prev: str, nxt: str) -> bool:
    """Decide whether to merge prev segment into the next one.

    Returns True when prev ends with a sentence-ending punctuation mark but
    appears to be a fragment rather than a complete sentence (e.g., an
    abbreviation tail like 'U.S.' or a short title like 'Dr.').

    This function is pure regex-based (no PySBD) and thread-safe.
    """
    if not prev or prev[-1] not in '.!?。！？؟۔।॥':
        return False
    if not nxt:
        return False

    # Next segment starts with a capitalized word — likely a real new sentence.
    # Exception: single lowercase word/fragment that's clearly not a sentence.
    nxt_body = nxt.rstrip('.!?。！؟؟۔।॥ ')
    nxt_stripped = nxt.lstrip()

    # Only merge lowercase continuations that look like abbreviation fragments
    # (e.g., "Smith" after "Dr.", "García" after "Sr.") — NOT full sentences
    # like "Gracias." after "Sí." or "thanks." after "I agree."
    if len(nxt_body) <= 15 and nxt_stripped and nxt_stripped[0].islower():
        # Must be a single token (name/word), not a multi-word phrase
        if ' ' not in nxt_body:
            return True

    # Prev ends with a known abbreviation pattern (short token + period)
    # Only merge if prev looks like an abbreviation (Dr., Mr., U.S., etc.)
    # NOT for generic short sentences followed by real text
    prev_body = prev.rstrip('.!?。！؟۔। ')
    # Extract the last token — embedded abbreviations like "I spoke to Dr."
    # have a long prev_body but the trailing token is still a title/latin abbrev.
    last_token = prev_body.rsplit(None, 1)[-1] if prev_body else ''
    if len(last_token) <= 8 and last_token:
        # Titles require a following name, which normally starts with a capital.
        if last_token in {'Dr', 'Mr', 'Mrs', 'Ms', 'St', 'Prof', 'Sr'}:
            return True

        # Must look like an abbreviation: single uppercase letter(s), title prefix,
        # latin abbrev, version/decimal pattern, or multi-part acronym
        is_abbrev_like = (
            last_token.isupper()
            and len(last_token) <= 5  # U.S.A., F.B.I., UK
            or last_token in ('etc', 'vs')  # Latin abbrevs
            or (last_token[0].isupper() and len(last_token) > 1 and last_token[1:].isdigit())  # v2, V3
        )
        if is_abbrev_like:
            # But DON'T merge if next starts capitalized and looks like a new sentence
            # (e.g., "U.K. She likes tea." → keep separate)
            if nxt_stripped and nxt_stripped[0].isupper() and ' ' in nxt_body:
                return False
            # Also don't merge after etc./vs. when next starts a new sentence
            if last_token in ('etc', 'vs') and nxt_stripped and nxt_stripped[0].isupper():
                return False
            return True

    return False
