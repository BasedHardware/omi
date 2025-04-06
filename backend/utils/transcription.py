import os
import hashlib
from collections import OrderedDict
from google.cloud import translate_v3

# LRU Cache for translations with a maximum size of 1000 entries
translation_cache = OrderedDict()
MAX_CACHE_SIZE = 1000
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

client = translate_v3.TranslationServiceClient()
parent = f"projects/{PROJECT_ID}/locations/global"
mime_type = "text/plain"

def get_cache_key(text_hash: str, dest_language: str) -> str:
    """Generate a cache key from text hash and language"""
    return f"{text_hash}:{dest_language}"

def translate_text(dest_language: str, text: str) -> str:
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
    cache_key = get_cache_key(text_hash, dest_language)
    if cache_key in translation_cache:
        # Move the item to the end of the OrderedDict to mark it as recently used
        translated_text = translation_cache.pop(cache_key)
        translation_cache[cache_key] = translated_text
        return translated_text

    try:
        # Not in cache, perform translation
        response = client.translate_text(
            contents=[text],
            parent=parent,
            mime_type=mime_type,
            target_language_code=dest_language,
        )

        translated_text = response.translations[0].translated_text

        # Add to cache
        if len(translation_cache) >= MAX_CACHE_SIZE:
            # Remove oldest item (first item in OrderedDict)
            translation_cache.popitem(last=False)

        translation_cache[cache_key] = translated_text
        return translated_text
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Return original text if translation fails
