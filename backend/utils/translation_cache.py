import re
from typing import Dict, Tuple, Optional


class TranscriptSegmentLanguageCache:
    """
    A class to manage language detection caching for transcript segments.

    This cache stores information about whether a segment's text is in the target language
    and tracks text changes to optimize language detection.
    """

    def __init__(self):
        """Initialize an empty language detection cache."""
        # Cache structure: {segment_id: (text, is_target_language)}
        # is_target_language can be:
        # - True: text is in target language
        # - False: text is not in target language
        # - None: language has not been detected yet
        self.cache: Dict[str, Tuple[str, Optional[bool]]] = {}

    @staticmethod
    def get_text_difference(new_text: str, old_text: str) -> str:
        if not old_text:
            return new_text

        # Simple approach: if new text starts with old text, return the difference
        if new_text.startswith(old_text):
            return new_text[len(old_text):].strip()

        # If not a simple continuation, return the full new text
        return new_text

    def get_language_result(self, segment_id: str, text: str, target_language: str) -> Tuple[Optional[bool], Optional[str]]:
        if segment_id not in self.cache:
            return None, text

        cached_text, is_target_language = self.cache[segment_id]
        return is_target_language, self.get_text_difference(text, cached_text)

    def update_cache(self, segment_id: str, text: str, is_target_language: Optional[bool]) -> None:
        self.cache[segment_id] = (text, is_target_language)

    def delete_cache(self, segment_id: str) -> None:
        del self.cache[segment_id]
