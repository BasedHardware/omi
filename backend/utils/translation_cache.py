from typing import Dict, Optional

from utils.translation import detect_language


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
            return was_in_target_language is not False

        # Use free local langdetect only (no paid API calls)
        detected_lang = detect_language(text, remove_non_lexical=True, hint_language=target_language)
        if detected_lang and detected_lang != target_language:
            self.cache[segment_id] = False
            return False

        self.cache[segment_id] = True
        return True

    def update_from_translate_response(self, segment_id: str, detected_lang: str, target_language: str):
        """Update cache using detected_language_code from translate API response (free)."""
        if detected_lang and detected_lang == target_language:
            self.cache[segment_id] = True
        elif detected_lang:
            self.cache[segment_id] = False

    def delete_cache(self, segment_id: str) -> None:
        if segment_id in self.cache:
            del self.cache[segment_id]
