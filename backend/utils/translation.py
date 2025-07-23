import os
import hashlib
import re
from collections import OrderedDict
from typing import List

from google.cloud import translate_v3


# LRU Cache for language detection
detection_cache = OrderedDict()
MAX_DETECTION_CACHE_SIZE = 1000

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

# Initialize the translation client globally
_client = translate_v3.TranslationServiceClient()
_parent = f"projects/{PROJECT_ID}/locations/global"
_mime_type = "text/plain"


def detect_language(text: str) -> str | None:
    """
    Detects the language of the provided text using Google Cloud Translate API.
    Uses a cache to avoid redundant detections.

    Args:
        text: The text to detect language for

    Returns:
        The language code of the detected language (e.g., 'en', 'vi', 'fr') if confidence >= 1,
        or None if no language with sufficient confidence is found
    """
    if text in detection_cache:
        detection_cache.move_to_end(text)
        return detection_cache[text]

    try:
        # Call the Google Cloud Translate API to detect language
        response = _client.detect_language(parent=_parent, content=text, mime_type=_mime_type)

        detected_language = None
        # Return the language code only if confidence is >= 1
        if response.languages and len(response.languages) > 0:
            for language in response.languages:
                if language.confidence >= 1:
                    detected_language = language.language_code
                    break

        if len(detection_cache) >= MAX_DETECTION_CACHE_SIZE:
            detection_cache.popitem(last=False)
        detection_cache[text] = detected_language
        return detected_language
    except Exception as e:
        print(f"Language detection error: {e}")
        return None  # Return None on error


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

    def translate_text_by_sentence(self, dest_language: str, text: str) -> str:
        """
        Translates text by splitting it into sentences, translating each, and rejoining.
        Maximizes cache hits by translating sentence by sentence.
        """
        if not text:
            return ""

        sentences = split_into_sentences(text)
        translated_sentences = []
        for sentence in sentences:
            # Each sentence translation will hit the cache if seen before.
            translated_sentences.append(self.translate_text(dest_language, sentence))

        return ' '.join(translated_sentences)

    def translate_text(self, dest_language: str, text: str) -> str:
        """
        Translates text to the specified destination language using Google Cloud Translation API.
        Uses a cache to avoid redundant translations.

        Args:
            dest_language: The language code to translate to (e.g., 'en', 'es', 'fr')
            text: The text to translate

        Returns:
            The translated text as a string
        """
        # Generate hash for the text
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Check if translation is in cache
        cache_key = self._get_cache_key(text_hash, dest_language)
        if cache_key in self.translation_cache:
            # Move the item to the end of the OrderedDict to mark it as recently used
            translated_text = self.translation_cache.pop(cache_key)
            self.translation_cache[cache_key] = translated_text
            return translated_text

        try:
            # Not in cache, perform translation
            response = _client.translate_text(
                contents=[text],
                parent=_parent,
                mime_type=_mime_type,
                target_language_code=dest_language,
            )

            translated_text = response.translations[0].translated_text

            # Add to cache
            if len(self.translation_cache) >= self.MAX_CACHE_SIZE:
                # Remove oldest item (first item in OrderedDict)
                self.translation_cache.popitem(last=False)

            self.translation_cache[cache_key] = translated_text
            return translated_text
        except Exception as e:
            print(f"Translation error: {e}")
            return text  # Return original text if translation fails
