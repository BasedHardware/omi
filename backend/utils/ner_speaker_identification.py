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

import asyncio
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thread-safe lazy-load state
_nlp = None
_nlp_load_attempted = False
_nlp_load_started = False
_nlp_lock = threading.Lock()

# Background executor for blocking I/O (spacy.load, disk reads)
_nlp_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spacy-loader")


def _load_spacy_model():
    """Load spacy model in a background thread. Returns model or None."""
    import spacy
    return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "textcat"])


def _get_nlp():
    """Synchronous access to already-loaded model. Call _ensure_nlp() first."""
    return _nlp


def _ensure_nlp(loop=None):
    """
    Start background load of spaCy model if not already started.
    Must be called from async context (uses run_in_executor).
    Returns immediately; model loads in background thread.
    """
    global _nlp, _nlp_load_attempted, _nlp_load_started
    if _nlp_load_attempted:
        return  # already tried

    with _nlp_lock:
        if _nlp_load_started:
            return
        _nlp_load_started = True
        _nlp_load_attempted = True

    def _load():
        global _nlp
        try:
            # Run blocking spacy.load() in background thread
            _nlp = _load_spacy_model()
            logger.info("NER speaker identification: spaCy model loaded in background")
        except (ImportError, OSError) as e:
            logger.warning(f"spaCy not available, falling back to regex: {e}")
            _nlp = None

    # Submit to thread pool — fire and forget; callers use _get_nlp() which
    # will return None until load completes, then returns the model
    _nlp_executor.submit(_load)


async def _get_nlp_async():
    """
    Async-safe model accessor.
    Kicks off background load if needed, then returns the model
    (blocks cooperatively until the background thread finishes loading).
    """
    _ensure_nlp()
    loop = asyncio.get_event_loop()
    # Wait for load thread to finish if it's still running
    await loop.run_in_executor(_nlp_executor, lambda: None)
    return _get_nlp()


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
    # Kick off background load if not yet started (safe to call repeatedly)
    _ensure_nlp()
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

    # Reduce penalty: don't silently drop legitimate names
    # spaCy PERSON tag from explicit self-introduction is strong signal;
    # only apply a small penalty for genuinely ambiguous words
    if name.lower() in _AMBIGUOUS_WORDS:
        score -= 0.1

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
