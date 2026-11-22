"""Count transcript words for the v3 processing and Home minimums."""

from unicodedata import normalize

import regex

MIN_TASK_WORDS = 20
MIN_HOME_WORDS = 300

_SCRIPT_LETTER = regex.compile(r'(?V1)[\p{L}&&[\p{scx=Han}\p{scx=Hiragana}\p{scx=Katakana}\p{scx=Hangul}\p{scx=Thai}]]')


def has_unspaced_script(text: str) -> bool:
    return not text.isascii() and _SCRIPT_LETTER.search(text) is not None


def text_word_count(text: str) -> int:
    """Count each target-script letter and each intervening whitespace word."""
    tokens = text.split()
    if not has_unspaced_script(text):
        return len(tokens)
    count = 0
    for token in tokens:
        # NFC keeps a decomposed Hangul syllable equivalent to a composed one.
        parts = _SCRIPT_LETTER.split(normalize('NFC', token))
        if len(parts) == 1:
            count += 1
        else:
            count += len(parts) - 1
            count += sum(any(char.isalnum() for char in part) for part in parts)
    return count
