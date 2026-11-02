"""One length policy shared by the notes packet, prompt and output contract."""


def length_guide(words: int) -> str:
    """Body-length target scaled to the transcript: about 1.3-1.4x the one-shot notes on long meetings."""
    if words < 500:
        return 'Use 1-2 sections and about 80-150 words in total.'
    if words < 1500:
        return 'Use 3-4 sections and about 250-400 words in total; never more than 450.'
    if words < 5000:
        return 'Use 4-6 sections and about 550-800 words in total; never more than 900.'
    return 'Use 5-7 sections and about 750-1000 words in total; never more than 1100.'


def length_floor(words: int) -> int:
    """Below this a long meeting's note is missing threads the owner wanted."""
    if words < 1500:
        return 0
    if words < 5000:
        return 480
    return 650


def length_ceiling(words: int) -> int:
    if words < 500:
        return 170
    if words < 1500:
        return 450
    if words < 5000:
        return 900
    return 1100
