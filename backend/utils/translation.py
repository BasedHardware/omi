import os
import hashlib
import re
from collections import OrderedDict
from typing import List, NamedTuple, Optional

from google.cloud import translate_v3
from langdetect import detect as langdetect_detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException


class TranslationResult(NamedTuple):
    text: str
    detected_language_code: Optional[str] = None


# LRU Cache for language detection
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


def _detect_with_langdetect(text: str, hint_language: str = None) -> str | None:
    if hint_language not in LANGDETECT_RELIABLE_LANGUAGES:
        return None
    try:
        return langdetect_detect(text)
    except LangDetectException:
        return None


def detect_language(text: str, remove_non_lexical: bool = False, hint_language: str = None) -> str | None:
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
        print(f"Language detection error: {e}")
        return None

    return detected_language


def split_into_sentences(text: str) -> List[str]:
    """Splits text into sentences based on punctuation."""
    if not text:
        return []
    # Find all sequences of characters that are not .?!,, followed by an optional .?!,, and optional whitespace.
    sentences = re.findall(r'[^.?!,]+(?:[.?!,]\s*|\s*$)', text)
    return [s.strip() for s in sentences if s.strip()]


class TranslationService:
    def __init__(self):
        self.translation_cache = OrderedDict()
        self.MAX_CACHE_SIZE = 1000

    def _get_cache_key(self, text_hash: str, dest_language: str) -> str:
        """Generate a cache key from text hash and language"""
        return f"{text_hash}:{dest_language}"

    def translate_text_by_sentence(self, dest_language: str, text: str) -> TranslationResult:
        """
        Translates text by splitting it into sentences, translating each, and rejoining.
        Maximizes cache hits by translating sentence by sentence.
        Returns TranslationResult with detected_language_code if all sentences agree.
        """
        if not text:
            return TranslationResult(text="")

        sentences = split_into_sentences(text)
        results = []
        for sentence in sentences:
            results.append(self.translate_text(dest_language, sentence))

        translated_text = ' '.join(r.text for r in results)

        # Aggregate detected language: use it only if all sentences agree
        detected_langs = {r.detected_language_code for r in results if r.detected_language_code}
        detected_language_code = detected_langs.pop() if len(detected_langs) == 1 else None

        return TranslationResult(text=translated_text, detected_language_code=detected_language_code)

    def translate_text(self, dest_language: str, text: str) -> TranslationResult:
        """
        Translates text to the specified destination language using Google Cloud Translation API.
        Uses a cache to avoid redundant translations.

        Args:
            dest_language: The language code to translate to (e.g., 'en', 'es', 'fr')
            text: The text to translate

        Returns:
            TranslationResult with translated text and detected source language code
        """
        # Generate hash for the text
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Check if translation is in cache
        cache_key = self._get_cache_key(text_hash, dest_language)
        if cache_key in self.translation_cache:
            # Move the item to the end of the OrderedDict to mark it as recently used
            cached = self.translation_cache.pop(cache_key)
            self.translation_cache[cache_key] = cached
            return cached

        try:
            # Not in cache, perform translation
            response = _client.translate_text(
                contents=[text],
                parent=_parent,
                mime_type=_mime_type,
                target_language_code=dest_language,
            )

            translation = response.translations[0]
            result = TranslationResult(
                text=translation.translated_text,
                detected_language_code=translation.detected_language_code or None,
            )

            # Add to cache
            if len(self.translation_cache) >= self.MAX_CACHE_SIZE:
                # Remove oldest item (first item in OrderedDict)
                self.translation_cache.popitem(last=False)

            self.translation_cache[cache_key] = result
            return result
        except Exception as e:
            print(f"Translation error: {e}")
            return TranslationResult(text=text)  # Return original text if translation fails
