"""Conservative, provider-independent checks for same-language rewrites.

This is an edit heuristic, not a semantic equivalence or language oracle. In
particular, foreign edits in a mostly target-language sentence must survive.
"""

from collections import Counter
import re

from config.translation import translation_output_guard_enabled
from utils.translation_language import detect_language_with_confidence

# Dice >= .80 permits one insertion into four tokens (including a negation).
NEAR_COPY_DICE = 0.80
# Only these unambiguously English grammatical edits can corroborate a bad
# short-source detection. Foreign lexical substitutions are never covered here.
_ENGLISH_EDITS = frozenset(
    {
        'a',
        'an',
        'the',
        'is',
        'are',
        'was',
        'were',
        'be',
        'been',
        'being',
        'do',
        'does',
        'did',
        'not',
        'it',
        'that',
        'this',
        'to',
    }
)


def _tokens(text: str) -> list[str]:
    text = text.casefold().replace('’', "'")
    text = re.sub(r"\b(can|will|shall)'t\b", r'\1 not', text)
    text = text.replace("n't", ' not')
    return re.findall(r'[^\W\d_]+', text, re.UNICODE)


def lexical_overlap(source: str, output: str) -> float:
    left, right = Counter(_tokens(source)), Counter(_tokens(output))
    total = sum(left.values()) + sum(right.values())
    return 2 * sum((left & right).values()) / total if total else 0.0


def output_rejection_reason(source: str, output: str, target: str) -> str | None:
    """Reject only supported no-op/rewrite classes; never trust provider language."""
    if not output.strip():
        return 'empty'
    if ' '.join(source.split()) == ' '.join(output.split()):
        return 'unchanged'
    if not translation_output_guard_enabled():
        return None
    if ' '.join(source.casefold().split()) == ' '.join(output.casefold().split()):
        return 'near_copy'
    if lexical_overlap(source, output) < NEAR_COPY_DICE:
        return None
    target = target.split('-')[0].lower()
    output_language, output_confidence = detect_language_with_confidence(output, remove_non_lexical=False)
    if output_language != target or output_confidence < 0.80:
        return None
    left, right = Counter(_tokens(source)), Counter(_tokens(output))
    removed, added = list((left - right).elements()), list((right - left).elements())
    # Grammar-only edits cover short English misdetections, including negation.
    if target == 'en' and set(removed + added) <= _ENGLISH_EDITS:
        return 'near_copy'
    source_language, source_confidence = detect_language_with_confidence(source, remove_non_lexical=False)
    if source_language != target or source_confidence < 0.90:
        return None
    # A whole sentence's dominant language cannot vouch for its foreign span.
    # Require independent target-language evidence for both lexical edit spans.
    for edited in (removed, added):
        if not edited:
            continue
        language, confidence = detect_language_with_confidence(' '.join(edited), remove_non_lexical=False)
        if language != target or confidence < 0.90:
            return None
    return 'near_copy'
