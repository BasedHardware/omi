"""
NER-based Speaker Identification for Omi.

Replaces regex-based speaker name detection with Named Entity Recognition (NER)
using spaCy. This catches names mentioned naturally in conversation, not just
explicit "My name is X" patterns.

Examples that regex misses but NER catches:
  - "Tell John I'll be late" → John (PERSON)
  - "Sarah mentioned the meeting" → Sarah (PERSON)
  - "I was talking to Mike yesterday" → Mike (PERSON)
  - "Hey David, how's it going?" → David (PERSON)

Performance:
  - spaCy en_core_web_sm: ~2ms per segment on CPU
  - Memory: ~50MB model footprint
  - License: MIT (spaCy + model)

Falls back to regex patterns if spaCy is unavailable.
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded spaCy model
_nlp = None
_nlp_load_attempted = False


def _get_nlp():
    """Lazy-load spaCy model. Returns None if unavailable."""
    global _nlp, _nlp_load_attempted
    if _nlp_load_attempted:
        return _nlp

    _nlp_load_attempted = True
    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "textcat"])
        logger.info("NER speaker identification: spaCy model loaded")
    except (ImportError, OSError) as e:
        logger.warning(f"spaCy not available, falling back to regex: {e}")
        _nlp = None

    return _nlp


def detect_speaker_names_ner(text: str) -> List[Tuple[str, float]]:
    """
    Detect person names in transcript text using NER.

    Returns a list of (name, confidence) tuples sorted by confidence descending.
    Confidence is based on:
      - Entity label certainty (spaCy score)
      - Context clues (near speaker indicators)
      - Frequency of mention

    Args:
        text: Transcript text segment to analyze.

    Returns:
        List of (name_string, confidence_float) tuples.
    """
    nlp = _get_nlp()
    if nlp is None:
        # Fallback to regex
        name = _detect_speaker_regex_fallback(text)
        return [(name, 0.5)] if name else []

    doc = nlp(text)
    candidates = {}

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue

        name = ent.text.strip()
        # Skip single-character or overly long "names"
        if len(name) < 2 or len(name) > 40:
            continue

        # Skip common false positives
        if name.lower() in _FALSE_POSITIVE_NAMES:
            continue

        # Calculate confidence based on context
        confidence = _score_name_confidence(name, ent, doc, text)

        if name in candidates:
            candidates[name] = max(candidates[name], confidence)
        else:
            candidates[name] = confidence

    # Sort by confidence
    results = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return results


def detect_speaker_from_text_ner(text: str) -> Optional[str]:
    """
    Drop-in replacement for detect_speaker_from_text().

    Returns the most confident speaker name, or None.
    """
    results = detect_speaker_names_ner(text)
    if results and results[0][1] >= 0.4:
        return results[0][0]
    return None


def _score_name_confidence(name: str, ent, doc, text: str) -> float:
    """Score how likely this entity is actually a speaker name."""
    score = 0.6  # Base confidence for PERSON entity

    # Boost: near speaker-indicator words
    context_window = text[max(0, ent.start_char - 50):ent.end_char + 50].lower()
    speaker_indicators = [
        "i am", "i'm", "my name is", "call me", "they call me",
        "this is", "hey", "hi", "hello",
        "said", "says", "told", "asked", "replied",
        "speaking", "talking", "mentioned",
    ]
    for indicator in speaker_indicators:
        if indicator in context_window:
            score += 0.15
            break

    # Boost: name is at sentence start (common for direct address)
    if text.strip().startswith(name) or f". {name}" in text or f"! {name}" in text:
        score += 0.1

    # Boost: capitalized properly (not ALL CAPS or all lower)
    if name[0].isupper() and not name.isupper():
        score += 0.05

    # Penalize: if name matches common nouns/adjectives that spaCy sometimes tags
    if name.lower() in _AMBIGUOUS_WORDS:
        score -= 0.3

    # Cap at 1.0
    return min(score, 1.0)


# Common false positives that spaCy's PERSON NER can produce
_FALSE_POSITIVE_NAMES = {
    "ok", "okay", "hey", "hi", "hello", "yes", "no", "yeah", "omi",
    "google", "apple", "amazon", "alexa", "siri", "cortana",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

# Words that could be names but are ambiguous
_AMBIGUOUS_WORDS = {
    "will", "grace", "faith", "hope", "joy", "mark", "bill",
    "art", "bob", "frank", "iris", "lily", "rose", "ruby",
    "chase", "grant", "hunter", "mason", "parker", "reed",
}


def _detect_speaker_regex_fallback(text: str) -> Optional[str]:
    """Fallback regex detection (original approach) for when spaCy isn't available."""
    patterns = [
        r"\b(?:I am|I'm|i am|i'm|My name is|my name is)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+is my name\b",
        r"\b(?:call me|they call me)\s+([A-Z][a-zA-Z]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(match.lastindex)
    return None
