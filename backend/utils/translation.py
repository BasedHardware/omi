import os
import hashlib
import json
import re
import time
from collections import Counter, OrderedDict
from typing import Callable, Dict, List, Match, Optional, Pattern, Set, Tuple, TypedDict, Union, cast

from google.cloud import translate_v3
from langdetect import (  # langdetect ships no py.typed marker; symbols are untyped
    detect as langdetect_detect,  # type: ignore[reportUnknownVariableType]
    detect_langs as langdetect_detect_langs,  # type: ignore[reportUnknownVariableType]
    DetectorFactory,
)
from langdetect.lang_detect_exception import LangDetectException
from enum import Enum
import logging

import httpx

from database.redis_db import r
from models.transcript_segment import SENTENCE_FINDALL_RE

logger = logging.getLogger(__name__)

TRANSLATION_MODE = os.environ.get("TRANSLATION_MODE", "google")
HOSTED_TRANSLATION_API_URL = os.environ.get("HOSTED_TRANSLATION_API_URL", "")
TRANSLATION_SHADOW_SAMPLE_RATE = float(os.environ.get("TRANSLATION_SHADOW_SAMPLE_RATE", "1.0"))
TRANSLATION_SHADOW_TIMEOUT_SECONDS = float(os.environ.get("TRANSLATION_SHADOW_TIMEOUT_SECONDS", "2.0"))


# LRU Cache for language detection (local, free via langdetect)
detection_cache: "OrderedDict[str, Union[str, Tuple[str, float]]]" = OrderedDict()
MAX_DETECTION_CACHE_SIZE = 1000

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

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

# Construct the cloud client only when translation is actually requested. Importing
# the backend must remain safe in hermetic/local environments without Google ADC.
_client: Optional[translate_v3.TranslationServiceClient] = None


def _get_client() -> translate_v3.TranslationServiceClient:
    global _client
    if _client is None:
        _client = translate_v3.TranslationServiceClient()
    return _client


_parent = f"projects/{PROJECT_ID}/locations/global"
_mime_type = "text/plain"

# Initialize langdetect for consistent results
DetectorFactory.seed = 0

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
}

# Redis translation cache TTL (14 days)
TRANSLATION_CACHE_TTL = int(os.environ.get("TRANSLATION_CACHE_TTL", 60 * 60 * 24 * 14))

# Max sentences per batch API call (API supports up to 1024, use conservative limit)
MAX_BATCH_SIZE = 100


def _detect_with_langdetect(text: str, hint_language: Optional[str] = None) -> Optional[str]:
    # Normalize locale-tagged language (e.g. "en-US" -> "en") for langdetect compatibility
    base_hint = hint_language.split('-')[0] if hint_language else None
    if base_hint not in LANGDETECT_RELIABLE_LANGUAGES:
        return None
    try:
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

    detected_language: Optional[str] = None

    try:
        detected_language = _detect_with_langdetect(text_for_detection, hint_language)

        # Cache the result
        if detected_language:
            if len(detection_cache) >= MAX_DETECTION_CACHE_SIZE:
                detection_cache.popitem(last=False)
            detection_cache[text_for_detection] = detected_language
            return detected_language

    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return None

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
    except Exception as e:
        logger.error(f"Confident language detection error: {e}")
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
        # Country codes: U.S. → UⓐⓑⓒS. (internal period protected, trailing period kept)
        (re.compile(r'\b([A-Z])\.([A-Z])\.'), lambda m: m.group(1) + _ABBR + m.group(2) + '.'),
        # Extended multi-part acronyms: U.S.A. → UⓐⓑⓒSⓐⓑⓒA.
        (
            re.compile(r'\b([A-Z])\.([A-Z])\.([A-Z])\.'),
            lambda m: m.group(1) + _ABBR + m.group(2) + _ABBR + m.group(3) + '.',
        ),
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
    _last_token = prev_body.rsplit(None, 1)[-1] if prev_body else ''
    if len(_last_token) <= 8 and _last_token:
        # Must look like an abbreviation: single uppercase letter(s), title prefix,
        # latin abbrev, version/decimal pattern, or multi-part acronym
        is_abbrev_like = (
            _last_token.isupper()
            and len(_last_token) <= 5  # U.S.A., F.B.I., UK, Dr
            or _last_token in ('Dr', 'Mr', 'Mrs', 'Ms', 'St', 'Prof', 'Sr')  # Title abbrevs
            or _last_token in ('etc', 'vs')  # Latin abbrevs
            or (_last_token[0].isupper() and len(_last_token) > 1 and _last_token[1:].isdigit())  # v2, V3
        )
        if is_abbrev_like:
            # But DON'T merge if next starts capitalized and looks like a new sentence
            # (e.g., "U.K. She likes tea." → keep separate)
            if nxt_stripped and nxt_stripped[0].isupper() and ' ' in nxt_body:
                return False
            # Also don't merge after etc./vs. when next starts a new sentence
            if _last_token in ('etc', 'vs') and nxt_stripped and nxt_stripped[0].isupper():
                return False
            return True

    return False


def _redis_cache_key(text_hash: str, dest_lang: str) -> str:
    return f"translate:v1:{text_hash}:{dest_lang}"


def _redis_negative_cache_key(text_hash: str, dest_lang: str) -> str:
    """Key for negative cache — records that text does NOT need translation."""
    return f"translate:v2:neg:{text_hash}:{dest_lang}"


NEGATIVE_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days for negative cache


class _SentInfo(TypedDict):
    """Sentence-level dedup info used by translate_units_batch."""

    text: str
    indices: List[Tuple[int, int]]


def get_negative_cache(text_hash: str, dest_lang: str) -> bool:
    """Check if text is negatively cached (known to not need translation). Returns True if cached."""
    try:
        key = _redis_negative_cache_key(text_hash, dest_lang)
        return r.exists(key) == 1
    except Exception as e:
        logger.warning(f"Redis negative cache read error: {e}")
    return False


def set_negative_cache(text_hash: str, dest_lang: str):
    """Mark text as not needing translation in Redis."""
    try:
        key = _redis_negative_cache_key(text_hash, dest_lang)
        r.set(key, "1", ex=NEGATIVE_CACHE_TTL)
    except Exception as e:
        logger.warning(f"Redis negative cache write error: {e}")


def get_cached_translation(text_hash: str, dest_lang: str) -> Optional[Dict[str, str]]:
    """Get translation from Redis cache. Returns {"text": ..., "detected_lang": ...} or None."""
    try:
        key = _redis_cache_key(text_hash, dest_lang)
        cached = r.get(key)
        if cached:
            loaded: object = json.loads(cached)
            if isinstance(loaded, dict):
                return cast(Dict[str, str], loaded)
    except Exception as e:
        logger.warning(f"Redis translation cache read error: {e}")
    return None


def cache_translation(text_hash: str, dest_lang: str, translated_text: str, detected_lang: str):
    """Store translation in Redis cache with TTL."""
    try:
        key = _redis_cache_key(text_hash, dest_lang)
        value = json.dumps({"text": translated_text, "detected_lang": detected_lang})
        r.set(key, value, ex=TRANSLATION_CACHE_TTL)
    except Exception as e:
        logger.warning(f"Redis translation cache write error: {e}")


class TranslationService:
    def __init__(self) -> None:
        self.translation_cache: OrderedDict[str, Tuple[str, str]] = OrderedDict()
        self.MAX_CACHE_SIZE = 1000
        self._shadow_client: Optional[httpx.Client] = None

    def _get_shadow_client(self) -> httpx.Client:
        if self._shadow_client is None:
            self._shadow_client = httpx.Client(
                base_url=HOSTED_TRANSLATION_API_URL,
                timeout=TRANSLATION_SHADOW_TIMEOUT_SECONDS,
            )
        return self._shadow_client

    def _translate_google_batch(self, contents: List[str], dest_language: str) -> List[Tuple[str, str]]:
        response = _get_client().translate_text(  # type: ignore[reportUnknownMemberType]
            contents=contents,
            parent=_parent,
            mime_type=_mime_type,
            target_language_code=dest_language,
        )
        return [
            (translation.translated_text, translation.detected_language_code or "")
            for translation in response.translations
        ]

    def _run_shadow_compare(
        self,
        callsite: str,
        dest_language: str,
        source_texts: List[str],
        google_results: List[Tuple[str, str]],
    ) -> None:
        if TRANSLATION_MODE != "shadow" or not HOSTED_TRANSLATION_API_URL:
            return
        import random

        if TRANSLATION_SHADOW_SAMPLE_RATE < 1.0 and random.random() > TRANSLATION_SHADOW_SAMPLE_RATE:
            return
        try:
            source_lang = ""
            if google_results:
                lang_counts: Counter[str] = Counter(det for _, det in google_results if det)
                if lang_counts:
                    source_lang = lang_counts.most_common(1)[0][0]

            client = self._get_shadow_client()
            t0 = time.monotonic()
            resp = client.post(
                "/v1/translate",
                json={
                    "contents": source_texts,
                    "target_language_code": dest_language,
                    "source_language_code": source_lang or None,
                },
            )
            nllb_latency = time.monotonic() - t0

            if resp.status_code != 200:
                logger.warning(
                    "translation_shadow_error callsite=%s target=%s count=%d status=%d",
                    callsite,
                    dest_language,
                    len(source_texts),
                    resp.status_code,
                )
                return

            nllb_data = resp.json()
            nllb_translations = nllb_data.get("translations", [])

            exact_matches = 0
            total = min(len(google_results), len(nllb_translations))
            total_google_chars = 0
            total_nllb_chars = 0
            for i in range(total):
                g_text = google_results[i][0]
                n_text = nllb_translations[i].get("translated_text", "")
                total_google_chars += len(g_text)
                total_nllb_chars += len(n_text)
                if g_text.strip() == n_text.strip():
                    exact_matches += 1

            exact_match_ratio = exact_matches / total if total > 0 else 0.0
            len_ratio = total_nllb_chars / total_google_chars if total_google_chars > 0 else 0.0

            logger.info(
                "translation_shadow_compare callsite=%s target=%s count=%d "
                "google_detected=%s exact_match_ratio=%.2f len_ratio=%.2f "
                "nllb_latency_ms=%.1f nllb_model=%s",
                callsite,
                dest_language,
                total,
                source_lang,
                exact_match_ratio,
                len_ratio,
                nllb_latency * 1000,
                nllb_data.get("model", "unknown"),
            )
        except Exception as e:
            logger.warning(
                "translation_shadow_error callsite=%s target=%s count=%d error_type=%s",
                callsite,
                dest_language,
                len(source_texts),
                type(e).__name__,
            )

    def _schedule_shadow_compare(
        self,
        callsite: str,
        dest_language: str,
        source_texts: List[str],
        google_results: List[Tuple[str, str]],
    ) -> None:
        if TRANSLATION_MODE != "shadow" or not HOSTED_TRANSLATION_API_URL:
            return
        from utils.executors import postprocess_executor, submit_with_context

        submit_with_context(
            postprocess_executor,
            self._run_shadow_compare,
            callsite,
            dest_language,
            source_texts,
            google_results,
        )

    def _get_cache_key(self, text_hash: str, dest_language: str) -> str:
        return f"{text_hash}:{dest_language}"

    def _check_memory_cache(self, text_hash: str, dest_language: str) -> Optional[Tuple[str, str]]:
        """Check in-memory LRU cache. Returns (translated_text, detected_lang) or None."""
        cache_key = self._get_cache_key(text_hash, dest_language)
        if cache_key in self.translation_cache:
            entry = self.translation_cache.pop(cache_key)
            self.translation_cache[cache_key] = entry
            return entry
        return None

    def _set_memory_cache(self, text_hash: str, dest_language: str, translated_text: str, detected_lang: str):
        """Store in in-memory LRU cache."""
        cache_key = self._get_cache_key(text_hash, dest_language)
        if len(self.translation_cache) >= self.MAX_CACHE_SIZE:
            self.translation_cache.popitem(last=False)
        self.translation_cache[cache_key] = (translated_text, detected_lang)

    def translate_text_by_sentence(self, dest_language: str, text: str) -> Tuple[str, str]:
        """
        Translates text by splitting into sentences, batching uncached sentences
        into a single API call, and rejoining.

        Returns:
            (translated_text, detected_language_code) tuple.
            detected_language_code is the dominant detected language from the batch.
        """
        if not text:
            return ("", "")

        sentences = split_into_sentences(text)
        if not sentences:
            return ("", "")

        # Phase 1: Check caches (memory -> Redis) for each sentence
        results: List[Optional[str]] = [None] * len(sentences)
        uncached_indices: List[int] = []
        detected_langs: List[str] = []

        for i, sentence in enumerate(sentences):
            text_hash = hashlib.md5(sentence.encode()).hexdigest()

            # Check memory cache
            cached = self._check_memory_cache(text_hash, dest_language)
            if cached:
                results[i] = cached[0]
                detected_langs.append(cached[1])
                logger.info(f"translate_cache [memory_hit] sentence={i}")
                continue

            # Check Redis cache
            redis_cached = get_cached_translation(text_hash, dest_language)
            if redis_cached:
                results[i] = redis_cached["text"]
                detected_lang = redis_cached.get("detected_lang", "")
                detected_langs.append(detected_lang)
                self._set_memory_cache(text_hash, dest_language, redis_cached["text"], detected_lang)
                logger.info(f"translate_cache [redis_hit] sentence={i}")
                continue

            uncached_indices.append(i)

        # Phase 2: Batch translate uncached sentences
        if uncached_indices:
            uncached_sentences: List[str] = [sentences[i] for i in uncached_indices]
            logger.info(
                f"translate_batch api_call sentences={len(uncached_sentences)} "
                f"cached={len(sentences) - len(uncached_sentences)}/{len(sentences)}"
            )

            # Batch in chunks of MAX_BATCH_SIZE
            for chunk_start in range(0, len(uncached_sentences), MAX_BATCH_SIZE):
                chunk_end = min(chunk_start + MAX_BATCH_SIZE, len(uncached_sentences))
                chunk: List[str] = uncached_sentences[chunk_start:chunk_end]
                chunk_indices: List[int] = uncached_indices[chunk_start:chunk_end]

                try:
                    google_results = self._translate_google_batch(chunk, dest_language)

                    for j, (trans_text, det_lang) in enumerate(google_results):
                        idx = chunk_indices[j]
                        results[idx] = trans_text
                        detected_langs.append(det_lang)

                        text_hash = hashlib.md5(sentences[idx].encode()).hexdigest()
                        self._set_memory_cache(text_hash, dest_language, trans_text, det_lang)
                        cache_translation(text_hash, dest_language, trans_text, det_lang)

                    self._schedule_shadow_compare("translate_text_by_sentence", dest_language, chunk, google_results)

                except Exception as e:
                    logger.error(f"Batch translation error: {e}")
                    for idx in chunk_indices:
                        if results[idx] is None:
                            results[idx] = sentences[idx]

        # Determine dominant detected language
        dominant_lang: str = ""
        if detected_langs:
            lang_counts: Counter[str] = Counter(lang for lang in detected_langs if lang)
            if lang_counts:
                dominant_lang = lang_counts.most_common(1)[0][0]

        translated_text = ' '.join(r for r in results if r is not None)
        return (translated_text, dominant_lang)

    def translate_units_batch(self, dest_language: str, units: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
        """Translate a batch of (unit_id, text) pairs in minimal GCP API calls.

        Splits each text into sentences, checks all cache layers PER SENTENCE,
        batches only truly uncached sentences into a single API call, then
        reassembles per-unit results.

        This sentence-level dedup means that if two different units share
        a common sentence (e.g., "How are you?"), only the first occurrence
        triggers an API call — subsequent units get the cached result.

        Returns list of (unit_id, translated_text, detected_lang) in input order.
        """
        if not units:
            return []

        # Phase -1: Check full-text caches for each unit before sentence splitting.
        # This preserves hits from the pre-DD-008 batch path and from
        # translate_text() calls that wrote full-text entries.
        full_text_results: Dict[str, Tuple[str, str]] = {}
        for unit_id, text in units:
            text_hash = hashlib.md5(text.encode()).hexdigest()
            # Check negative cache first — skip if previously determined
            # to not need translation (e.g., same source/target language)
            if get_negative_cache(text_hash, dest_language):
                full_text_results[unit_id] = (text, dest_language)
                continue
            # Check memory LRU next (cheapest positive cache)
            lru_hit = self._check_memory_cache(text_hash, dest_language)
            if lru_hit:
                full_text_results[unit_id] = lru_hit
                continue
            # Check Redis full-text key
            redis_hit = get_cached_translation(text_hash, dest_language)
            if redis_hit:
                translated = redis_hit["text"]
                detected = redis_hit.get("detected_lang", "")
                self._set_memory_cache(text_hash, dest_language, translated, detected)
                full_text_results[unit_id] = (translated, detected)
                continue

        # If every unit hit the full-text cache, return immediately.
        if len(full_text_results) == len(units):
            return [(uid, *full_text_results[uid]) for uid, _ in units]

        # Phase 0: Split each unit's text into sentences (only for cache-miss units)
        # Units that hit full-text cache in Phase -1 skip sentence splitting entirely.
        # unit_sentences[i] = list of (sentence_text, sentence_hash) for unit i
        unit_sentences: List[Tuple[str, str, List[Tuple[str, str]]]] = []
        for unit_id, text in units:
            if unit_id in full_text_results:
                continue  # Already have a full-text cache hit — no need to split
            sentences = split_into_sentences(text)
            hashed = [(s, hashlib.md5(s.encode()).hexdigest()) for s in sentences]
            unit_sentences.append((unit_id, text, hashed))

        # Build global sentence-level dedup map:
        # sent_hash -> {'text': str, 'indices': [(unit_idx, sent_idx), ...]}
        sent_hash_to_info: Dict[str, _SentInfo] = {}
        for unit_idx, (_, _, sentences) in enumerate(unit_sentences):
            for sent_idx, (sent_text, sent_hash) in enumerate(sentences):
                if sent_hash not in sent_hash_to_info:
                    sent_hash_to_info[sent_hash] = {
                        'text': sent_text,
                        'indices': [],
                    }
                sent_hash_to_info[sent_hash]['indices'].append((unit_idx, sent_idx))

        # Phase 1: Check caches for each unique sentence
        # sent_translation[hash] = (translated_text, detected_lang) or None
        sent_translation: Dict[str, Tuple[str, str]] = {}  # hash -> (str, str)
        uncached_sent_hashes: List[str] = []

        for sent_hash, info in sent_hash_to_info.items():
            # Check negative cache first
            if get_negative_cache(sent_hash, dest_language):
                sent_translation[sent_hash] = (info['text'], '')  # return original
                continue

            # Check memory cache
            cached = self._check_memory_cache(sent_hash, dest_language)
            if cached:
                sent_translation[sent_hash] = cached
                continue

            # Check Redis cache
            redis_cached = get_cached_translation(sent_hash, dest_language)
            if redis_cached:
                translated = redis_cached["text"]
                detected = redis_cached.get("detected_lang", "")
                self._set_memory_cache(sent_hash, dest_language, translated, detected)
                sent_translation[sent_hash] = (translated, detected)
                continue

            uncached_sent_hashes.append(sent_hash)

        # Phase 2: Batch translate uncached sentences
        _failed_sent_hashes: Set[str] = set()  # track which sentences fell back to original text
        if uncached_sent_hashes:
            uncached_texts: List[str] = [sent_hash_to_info[h]['text'] for h in uncached_sent_hashes]

            for chunk_start in range(0, len(uncached_texts), MAX_BATCH_SIZE):
                chunk_end = min(chunk_start + MAX_BATCH_SIZE, len(uncached_texts))
                chunk: List[str] = uncached_texts[chunk_start:chunk_end]
                chunk_hashes: List[str] = uncached_sent_hashes[chunk_start:chunk_end]

                try:
                    google_results = self._translate_google_batch(chunk, dest_language)

                    for j, (trans_text, det_lang) in enumerate(google_results):
                        sent_hash = chunk_hashes[j]
                        self._set_memory_cache(sent_hash, dest_language, trans_text, det_lang)
                        cache_translation(sent_hash, dest_language, trans_text, det_lang)
                        sent_translation[sent_hash] = (trans_text, det_lang)

                    self._schedule_shadow_compare("translate_units_batch", dest_language, chunk, google_results)

                except Exception as e:
                    logger.error(f"Sentence-level batch translation error: {e}")
                    for h in chunk_hashes:
                        if h not in sent_translation:
                            sent_translation[h] = (sent_hash_to_info[h]['text'], '')
                            _failed_sent_hashes.add(h)

        # Phase 3: Reassemble per-unit results from sentence translations.
        # Results are emitted in the same order as the input `units` list
        # so downstream consumers can rely on positional mapping.
        results: List[Optional[Tuple[str, str, str]]] = [None] * len(units)  # pre-allocate for in-order assembly

        # Map each unit_id back to its original index in `units` (needed because
        # unit_sentences is compacted — cache-hit units are excluded).
        _unit_id_to_orig_idx = {uid: i for i, (uid, _) in enumerate(units)}

        for unit_idx, (unit_id, original_text, sentences) in enumerate(unit_sentences):
            orig_idx = _unit_id_to_orig_idx[unit_id]
            if not sentences:
                results[orig_idx] = (unit_id, original_text, '')
                continue

            translated_parts: List[str] = []
            detected_langs: List[str] = []
            _fallback_sent_hashes: Set[str] = set()
            for sent_text, sent_hash in sentences:
                if sent_hash in sent_translation:
                    trans_text, det_lang = sent_translation[sent_hash]
                    translated_parts.append(trans_text)
                    if det_lang:
                        detected_langs.append(det_lang)
                else:
                    # Fallback: should not happen, but use original text
                    translated_parts.append(sent_text)
                    _fallback_sent_hashes.add(sent_hash)

            assembled = ' '.join(translated_parts)
            # Dominant detected language from constituent sentences
            dominant_lang: str = ''
            if detected_langs:
                lang_counts: Counter[str] = Counter(detected_langs)
                dominant_lang = lang_counts.most_common(1)[0][0]

            text_hash = hashlib.md5(original_text.encode()).hexdigest()
            # Only persist to any cache if NO sentence fell back to original text
            # (avoids poisoning both in-memory LRU and Redis with untranslated output).
            # This covers both exception-path failures (_failed_sent_hashes) and
            # quiet fallbacks where a sentence hash was never populated.
            _any_failure = any(sh in _failed_sent_hashes for _, sh in sentences) or bool(_fallback_sent_hashes)
            if not _any_failure:
                self._set_memory_cache(text_hash, dest_language, assembled, dominant_lang)
                cache_translation(text_hash, dest_language, assembled, dominant_lang)

            # When any sentence fell back or failed, return original text rather
            # than a partial/mixed assembly — otherwise the caller persists the
            # incomplete translation and advances committed_text, preventing
            # retry on transient API failures.
            if _any_failure:
                results[orig_idx] = (unit_id, original_text, '')
            else:
                results[orig_idx] = (unit_id, assembled, dominant_lang)

        # Fill in any units that hit the full-text cache in Phase -1
        # (they were skipped during sentence splitting)
        for unit_idx, (unit_id, _) in enumerate(units):
            if results[unit_idx] is None and unit_id in full_text_results:
                trans, det = full_text_results[unit_id]
                results[unit_idx] = (unit_id, trans, det)

        # Safety: replace any remaining gaps with original-text fallbacks
        final_results: List[Tuple[str, str, str]] = []
        for idx, r in enumerate(results):
            if r is not None:
                final_results.append(r)
            else:
                uid, orig_text = units[idx]
                final_results.append((uid, orig_text, ''))

        return final_results

    def translate_text(self, dest_language: str, text: str) -> Tuple[str, str]:
        """
        Translates text to the specified destination language using Google Cloud Translation API.
        Uses multi-level cache: in-memory LRU -> Redis -> API.

        Returns:
            (translated_text, detected_language_code) tuple.
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Check memory cache
        cached = self._check_memory_cache(text_hash, dest_language)
        if cached:
            return cached

        # Check Redis cache
        redis_cached = get_cached_translation(text_hash, dest_language)
        if redis_cached:
            result: Tuple[str, str] = (redis_cached["text"], redis_cached.get("detected_lang", ""))
            self._set_memory_cache(text_hash, dest_language, result[0], result[1])
            return result

        try:
            google_results = self._translate_google_batch([text], dest_language)
            translated_text, detected_lang = google_results[0]

            self._set_memory_cache(text_hash, dest_language, translated_text, detected_lang)
            cache_translation(text_hash, dest_language, translated_text, detected_lang)

            self._schedule_shadow_compare("translate_text", dest_language, [text], google_results)

            return (translated_text, detected_lang)
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return (text, "")
