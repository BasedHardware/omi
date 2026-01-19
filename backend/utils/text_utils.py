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
