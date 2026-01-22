def _normalize_text(text: str) -> str:
    """Normalize text: lowercase and collapse whitespace."""
    return ' '.join(text.lower().split())


def _get_trigrams(text: str) -> set:
    """Get character trigrams from normalized text."""
    text = _normalize_text(text)
    if len(text) < 3:
        return {text} if text else set()
    return {text[i : i + 3] for i in range(len(text) - 2)}


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Compute text similarity using character trigram Jaccard.
    Language-agnostic: works for all languages including CJK.

    Returns:
        Similarity score 0.0 to 1.0 (1.0 = identical)
    """
    trigrams1 = _get_trigrams(text1)
    trigrams2 = _get_trigrams(text2)

    if not trigrams1 or not trigrams2:
        return 0.0

    return len(trigrams1 & trigrams2) / len(trigrams1 | trigrams2)


def compute_text_containment(transcript: str, expected: str) -> float:
    """
    Compute containment of transcript trigrams within expected text.
    Language-agnostic: works for all languages including CJK.

    Args:
        transcript: Transcript text to check for containment
        expected: Expected text that should contain the transcript

    Returns:
        Containment score 0.0 to 1.0 (1.0 = fully contained)
    """
    transcript_norm = _normalize_text(transcript)
    expected_norm = _normalize_text(expected)

    if not transcript_norm:
        return 0.0
    if len(transcript_norm) < 3:
        return 1.0 if transcript_norm in expected_norm else 0.0

    trigrams_transcript = _get_trigrams(transcript)
    trigrams_expected = _get_trigrams(expected)

    if not trigrams_transcript:
        return 0.0

    return len(trigrams_transcript & trigrams_expected) / len(trigrams_transcript)
