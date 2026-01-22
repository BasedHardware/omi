def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Compute text similarity using character trigram Jaccard.
    Language-agnostic: works for all languages including CJK (Chinese, Japanese, Korean).

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score 0.0 to 1.0 (1.0 = identical)
    """

    def get_trigrams(text: str) -> set:
        # Normalize: lowercase and remove extra whitespace
        text = ' '.join(text.lower().split())
        if len(text) < 3:
            return {text} if text else set()
        return {text[i : i + 3] for i in range(len(text) - 2)}

    trigrams1 = get_trigrams(text1)
    trigrams2 = get_trigrams(text2)

    if not trigrams1 or not trigrams2:
        return 0.0

    intersection = trigrams1 & trigrams2
    union = trigrams1 | trigrams2
    return len(intersection) / len(union)


def compute_text_containment(transcript: str, expected: str) -> float:
    """
    Compute containment of transcript trigrams within expected text.
    Language-agnostic: works for all languages including CJK (Chinese, Japanese, Korean).

    Args:
        transcript: Transcript text to check for inclusion
        expected: Expected text to compare against

    Returns:
        Containment score 0.0 to 1.0 (1.0 = fully contained)
    """

    def normalize(text: str) -> str:
        return ' '.join(text.lower().split())

    def get_trigrams(text: str) -> set:
        text = normalize(text)
        if len(text) < 3:
            return {text} if text else set()
        return {text[i : i + 3] for i in range(len(text) - 2)}

    transcript = normalize(transcript)
    expected = normalize(expected)

    if not transcript:
        return 0.0
    if len(transcript) < 3:
        return 1.0 if transcript in expected else 0.0

    trigrams_transcript = get_trigrams(transcript)
    trigrams_expected = get_trigrams(expected)

    if not trigrams_transcript:
        return 0.0

    return len(trigrams_transcript & trigrams_expected) / len(trigrams_transcript)
