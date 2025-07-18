from typing import Dict, Tuple, Optional

from utils.translation import split_into_sentences, detect_language


class TranscriptSegmentLanguageCache:
    """
    A class to manage language detection caching for transcript segments.

    This cache stores information about whether a segment's text is in the target language
    and tracks text changes to optimize language detection by checking sentence by sentence.
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
    def _get_text_difference(new_text: str, old_text: str) -> str:
        if not old_text:
            return new_text

        # Simple approach: if new text starts with old text, return the difference
        if new_text.startswith(old_text):
            return new_text[len(old_text) :].strip()

        # If not a simple continuation, return the full new text for re-evaluation
        return new_text

    def is_in_target_language(self, segment_id: str, text: str, target_language: str) -> bool:
        """
        Determines if the segment text is in the target language.
        It performs sentence-level language detection on new text and caches the result for the segment.
        Returns True if no translation is needed, False otherwise.
        """
        cached_text, was_in_target_language = self.cache.get(segment_id, (None, None))

        # If we already determined it's not the target language, it remains so.
        # Update cache with the latest text.
        if was_in_target_language is False:
            if text != cached_text:
                self.cache[segment_id] = (text, False)
            return False

        diff_text = self._get_text_difference(text, cached_text)

        # If no new text to analyze, rely on the previous state.
        if not diff_text:
            return was_in_target_language is not False  # True or None results in True

        sentences = split_into_sentences(diff_text)
        if not sentences:
            return was_in_target_language is not False

        # Check each new sentence. If any is not in the target language, the whole segment is marked for translation.
        for sentence in sentences:
            detected_lang = detect_language(sentence)
            if detected_lang and detected_lang != target_language:
                self.cache[segment_id] = (text, False)
                return False

        # All new sentences are in the target language or undetectable.
        self.cache[segment_id] = (text, True)
        return True

    def delete_cache(self, segment_id: str) -> None:
        if segment_id in self.cache:
            del self.cache[segment_id]
