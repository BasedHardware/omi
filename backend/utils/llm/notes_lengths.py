"""One length policy shared by the notes packet, prompt and output contract."""

import math

from config.notes_detail import (
    NOTES_DETAIL_FROM_WORDS,
    NOTES_DETAIL_WORD_RATIO,
    NOTES_DETAIL_MIN_TARGET_WORDS,
    NOTES_DETAIL_MAX_WORDS,
    NOTES_DETAIL_WORDS_PER_SECTION,
    NOTES_DETAIL_MAX_SECTIONS,
    notes_scaled_detail_enabled,
)


def scaled_length_range(words: int) -> tuple[int, int] | None:
    if not notes_scaled_detail_enabled() or words < NOTES_DETAIL_FROM_WORDS:
        return None
    target = min(NOTES_DETAIL_MAX_WORDS, max(NOTES_DETAIL_MIN_TARGET_WORDS, words * NOTES_DETAIL_WORD_RATIO))
    return round(target * 0.85), min(NOTES_DETAIL_MAX_WORDS, round(target * 1.15))


def length_guide(words: int) -> str:
    """Body-length target scaled to the transcript: about 1.3-1.4x the one-shot notes on long meetings."""
    scaled = scaled_length_range(words)
    if scaled:
        sections = min(NOTES_DETAIL_MAX_SECTIONS, max(7, math.ceil(words / NOTES_DETAIL_WORDS_PER_SECTION)))
        return (
            f'Use 5-{sections} sections and about {scaled[0]}-{scaled[1]} words in total. '
            'Cover every substantive thread; preserve reasons, constraints and decisions. '
            'Stay shorter for repetition or sparse evidence; never pad unsupported detail.'
        )
    if words < 500:
        return 'Use 1-2 sections and about 80-150 words in total.'
    if words < 1500:
        return 'Use 3-4 sections and about 250-400 words in total; never more than 450.'
    if words < 5000:
        return 'Use 4-6 sections and about 550-800 words in total; never more than 900.'
    return 'Use 5-7 sections and about 750-1000 words in total; never more than 1100.'


def length_floor(words: int) -> int:
    """Below this a long meeting's note is missing threads the owner wanted."""
    scaled = scaled_length_range(words)
    if scaled:
        return max(650, round(scaled[0] * 0.8))
    if words < 1500:
        return 0
    if words < 5000:
        return 480
    return 650


def length_ceiling(words: int) -> int:
    scaled = scaled_length_range(words)
    if scaled:
        return scaled[1]
    if words < 500:
        return 170
    if words < 1500:
        return 450
    if words < 5000:
        return 900
    return 1100
