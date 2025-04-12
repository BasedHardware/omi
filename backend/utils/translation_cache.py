import re
from typing import Dict, Tuple, Optional

# Cache structure: {segment_id: (cleaned_text, is_target_language)}
# is_target_language can be:
# - True: text is in target language
# - False: text is not in target language
# - None: language has not been detected yet
language_detection_cache: Dict[str, Tuple[str, Optional[bool]]] = {}

def get_text_difference(new_text: str, old_text: str) -> str:
    """
    Extract the difference between new text and old text.
    Returns the part of new_text that's not in old_text.
    """
    if not old_text:
        return new_text

    # Simple approach: if new text starts with old text, return the difference
    if new_text.startswith(old_text):
        return new_text[len(old_text):].strip()

    # If not a simple continuation, return the full new text
    return new_text

def get_cached_language_result(segment_id: str, text: str, target_language: str) -> Tuple[Optional[bool], Optional[str]]:
    """
    Check if we have a cached result for this segment.

    Returns:
        Tuple[Optional[bool], Optional[str]]: 
        - is_target_language: True if text is in target language, False if not, None if not detected
        - diff_text: The difference text to check if partial detection is needed
    """
    if segment_id not in language_detection_cache:
        return None, text

    cached_text, is_target_language = language_detection_cache[segment_id]
    return is_target_language, get_text_difference(text, cached_text)

def update_cache(segment_id: str, text: str, is_target_language: Optional[bool]) -> None:
    language_detection_cache[segment_id] = (text, is_target_language)
