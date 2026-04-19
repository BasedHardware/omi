import os
import hashlib
import json
import re
from collections import Counter, OrderedDict
from typing import List, Optional, Tuple

from google.cloud import translate_v3
from langdetect import detect as langdetect_detect, detect_langs as langdetect_detect_langs, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from enum import Enum
import logging

from database.redis_db import r
from models.transcript_segment import SENTENCE_FINDALL_RE

logger = logging.getLogger(__name__)


def resolve_translation_language(
    translate_param: str,
    single_language_mode: bool,
    stt_language: str,
    language: str,
    user_language_preference: str,
) -> Optional[str]:
    """Determine the target translation language for a listen session.

    Precedence (highest to lowest):
    1. translate=disabled → None (client explicitly opted out)
    2. single_language_mode=True → None (user prefers single-language accuracy)
    3. translate param empty/unknown (legacy clients) → use settings-based default
    4. stt_language != 'multi' → None (single-language STT, no translation needed)
    5. No user_language_preference → None (no target language to translate to)
    6. Otherwise → user_language_preference or language
    """
    # Client explicitly disabled translation
    if translate_param == 'disabled':
        return None

    # User prefers single-language mode (higher accuracy, no translation)
    if single_language_mode:
        return None

    # For legacy clients (empty translate param), fall through to settings-based logic
    # For clients sending translate=enabled, also fall through

    # Single-language STT doesn't produce multi-language output
    if stt_language != 'multi':
        return None

    # Determine target language
    if language == 'multi':
        return user_language_preference if user_language_preference else None
    else:
        return language


# LRU Cache for language detection (local, free via langdetect)
detection_cache = OrderedDict()
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

# Initialize the translation client globally
_client = translate_v3.TranslationServiceClient()
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


def _detect_with_langdetect(text: str, hint_language: str = None) -> str | None:
    # Normalize locale-tagged language (e.g. "en-US" -> "en") for langdetect compatibility
    base_hint = hint_language.split('-')[0] if hint_language else None
    if base_hint not in LANGDETECT_RELIABLE_LANGUAGES:
        return None
    try:
        return langdetect_detect(text)
    except LangDetectException:
        return None


def detect_language(text: str, remove_non_lexical: bool = False, hint_language: str = None) -> str | None:
    """Detect language using free local langdetect library only (no paid API calls)."""
    text_for_detection = text
    if remove_non_lexical:
        cleaned_text = _non_lexical_utterances_pattern.sub('', text)
        text_for_detection = re.sub(r'\s+', ' ', cleaned_text).strip()

    if not text_for_detection:
        return None

    if text_for_detection in detection_cache:
        detection_cache.move_to_end(text_for_detection)
        return detection_cache[text_for_detection]

    detected_language = None

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
    text: str, remove_non_lexical: bool = True, hint_language: str = None
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
        return detection_cache[cache_key]

    try:
        results = langdetect_detect_langs(text_for_detection)
        if not results:
            return (None, 0.0)

        top = results[0]
        result = (top.lang, top.prob)

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
    """
    if not text:
        return []

    result = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        sentences = SENTENCE_FINDALL_RE.findall(line)
        result.extend(s.strip() for s in sentences if s.strip())
    return result


def _redis_cache_key(text_hash: str, dest_lang: str) -> str:
    return f"translate:v1:{text_hash}:{dest_lang}"


def _redis_negative_cache_key(text_hash: str, dest_lang: str) -> str:
    """Key for negative cache — records that text does NOT need translation."""
    return f"translate:v2:neg:{text_hash}:{dest_lang}"


NEGATIVE_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days for negative cache


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


def get_cached_translation(text_hash: str, dest_lang: str) -> Optional[dict]:
    """Get translation from Redis cache. Returns {"text": ..., "detected_lang": ...} or None."""
    try:
        key = _redis_cache_key(text_hash, dest_lang)
        cached = r.get(key)
        if cached:
            return json.loads(cached)
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
    def __init__(self):
        self.translation_cache = OrderedDict()
        self.MAX_CACHE_SIZE = 1000

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
        results = [None] * len(sentences)
        uncached_indices = []
        detected_langs = []

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
            uncached_sentences = [sentences[i] for i in uncached_indices]
            logger.info(
                f"translate_batch api_call sentences={len(uncached_sentences)} "
                f"cached={len(sentences) - len(uncached_sentences)}/{len(sentences)}"
            )

            # Batch in chunks of MAX_BATCH_SIZE
            for chunk_start in range(0, len(uncached_sentences), MAX_BATCH_SIZE):
                chunk_end = min(chunk_start + MAX_BATCH_SIZE, len(uncached_sentences))
                chunk = uncached_sentences[chunk_start:chunk_end]
                chunk_indices = uncached_indices[chunk_start:chunk_end]

                try:
                    response = _client.translate_text(
                        contents=chunk,
                        parent=_parent,
                        mime_type=_mime_type,
                        target_language_code=dest_language,
                    )

                    for j, translation in enumerate(response.translations):
                        idx = chunk_indices[j]
                        translated_text = translation.translated_text
                        detected_lang = translation.detected_language_code or ""
                        results[idx] = translated_text
                        detected_langs.append(detected_lang)

                        # Cache in memory and Redis
                        text_hash = hashlib.md5(sentences[idx].encode()).hexdigest()
                        self._set_memory_cache(text_hash, dest_language, translated_text, detected_lang)
                        cache_translation(text_hash, dest_language, translated_text, detected_lang)

                except Exception as e:
                    logger.error(f"Batch translation error: {e}")
                    for idx in chunk_indices:
                        if results[idx] is None:
                            results[idx] = sentences[idx]

        # Determine dominant detected language
        dominant_lang = ""
        if detected_langs:
            lang_counts = Counter(lang for lang in detected_langs if lang)
            if lang_counts:
                dominant_lang = lang_counts.most_common(1)[0][0]

        translated_text = ' '.join(r for r in results if r is not None)
        return (translated_text, dominant_lang)

    def translate_units_batch(self, dest_language: str, units: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
        """Translate a batch of (unit_id, text) pairs in minimal GCP API calls.

        Deduplicates identical texts, checks all cache layers, and batches
        only truly uncached texts into a single API call.

        Returns list of (unit_id, translated_text, detected_lang) in input order.
        """
        if not units:
            return []

        # Build deduplicated mapping: text_hash -> (text, [indices])
        results = [None] * len(units)
        hash_to_info = {}  # text_hash -> {'text': str, 'indices': [int]}

        for i, (unit_id, text) in enumerate(units):
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash not in hash_to_info:
                hash_to_info[text_hash] = {'text': text, 'indices': [], 'hash': text_hash}
            hash_to_info[text_hash]['indices'].append(i)

        # Phase 1: Check caches for each unique text
        uncached_hashes = []
        for text_hash, info in hash_to_info.items():
            # Check negative cache first
            if get_negative_cache(text_hash, dest_language):
                for idx in info['indices']:
                    results[idx] = (units[idx][0], info['text'], '')  # return original text
                continue

            # Check memory cache
            cached = self._check_memory_cache(text_hash, dest_language)
            if cached:
                for idx in info['indices']:
                    results[idx] = (units[idx][0], cached[0], cached[1])
                continue

            # Check Redis cache
            redis_cached = get_cached_translation(text_hash, dest_language)
            if redis_cached:
                translated = redis_cached["text"]
                detected = redis_cached.get("detected_lang", "")
                self._set_memory_cache(text_hash, dest_language, translated, detected)
                for idx in info['indices']:
                    results[idx] = (units[idx][0], translated, detected)
                continue

            uncached_hashes.append(text_hash)

        # Phase 2: Batch translate uncached texts
        if uncached_hashes:
            uncached_texts = [hash_to_info[h]['text'] for h in uncached_hashes]

            for chunk_start in range(0, len(uncached_texts), MAX_BATCH_SIZE):
                chunk_end = min(chunk_start + MAX_BATCH_SIZE, len(uncached_texts))
                chunk = uncached_texts[chunk_start:chunk_end]
                chunk_hashes = uncached_hashes[chunk_start:chunk_end]

                try:
                    response = _client.translate_text(
                        contents=chunk,
                        parent=_parent,
                        mime_type=_mime_type,
                        target_language_code=dest_language,
                    )

                    for j, translation in enumerate(response.translations):
                        text_hash = chunk_hashes[j]
                        translated_text = translation.translated_text
                        detected_lang = translation.detected_language_code or ""
                        info = hash_to_info[text_hash]

                        self._set_memory_cache(text_hash, dest_language, translated_text, detected_lang)
                        cache_translation(text_hash, dest_language, translated_text, detected_lang)

                        for idx in info['indices']:
                            results[idx] = (units[idx][0], translated_text, detected_lang)

                except Exception as e:
                    logger.error(f"Batch translation error: {e}")
                    for h in chunk_hashes:
                        info = hash_to_info[h]
                        for idx in info['indices']:
                            if results[idx] is None:
                                results[idx] = (units[idx][0], info['text'], '')

        # Fill any remaining None results (shouldn't happen, but be safe)
        for i in range(len(results)):
            if results[i] is None:
                results[i] = (units[i][0], units[i][1], '')

        return results

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
            result = (redis_cached["text"], redis_cached.get("detected_lang", ""))
            self._set_memory_cache(text_hash, dest_language, result[0], result[1])
            return result

        try:
            response = _client.translate_text(
                contents=[text],
                parent=_parent,
                mime_type=_mime_type,
                target_language_code=dest_language,
            )

            translated_text = response.translations[0].translated_text
            detected_lang = response.translations[0].detected_language_code or ""

            # Cache in memory and Redis
            self._set_memory_cache(text_hash, dest_language, translated_text, detected_lang)
            cache_translation(text_hash, dest_language, translated_text, detected_lang)

            return (translated_text, detected_lang)
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return (text, "")
