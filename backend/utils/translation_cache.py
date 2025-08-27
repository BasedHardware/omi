from typing import Dict, Tuple, Optional

from utils.translation import split_into_sentences, detect_language


class TranscriptSegmentLanguageCache:
    """
    A class to manage language detection caching for transcript segments.
    """

    def __init__(self):
        self.cache: Dict[str, Optional[bool]] = {}

    def is_in_target_language(self, segment_id: str, text: str, target_language: str) -> bool:
        # If we already determined it's not the target language, it remains so.
        was_in_target_language = self.cache.get(segment_id, None)
        if was_in_target_language is False:
            return False

        # If no new text to analyze, rely on the previous state.
        # True or None results in True
        if not text:
            return was_in_target_language is not False

        # Use full text detection for better accuracy and performance
        detected_lang = detect_language(text, remove_non_lexical=True, hint_language=target_language)
        if detected_lang and detected_lang != target_language:
            self.cache[segment_id] = False
            return False

        # All text is in the target language or undetectable.
        self.cache[segment_id] = True
        return True

    def delete_cache(self, segment_id: str) -> None:
        if segment_id in self.cache:
            del self.cache[segment_id]
