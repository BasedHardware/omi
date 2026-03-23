"""
NER-based speaker name detection using spaCy.

Extracts PERSON entities from transcript text as a fallback/improvement
over regex-based speaker identification patterns.

Uses spaCy's pre-trained NER model for fast, accurate named entity recognition.
Supports self-hosting with no external API calls.

Requirements:
    pip install spacy
    python -m spacy download en_core_web_sm  # or en_core_web_md for better accuracy

Usage:
    from utils.ner_speaker_detection import detect_persons_with_ner

    names = detect_persons_with_ner("Hello, I'm John and this is my friend Sarah")
    # Returns: ['John', 'Sarah']
"""

import logging
import re
from typing import List, Optional, Set

import spacy
from spacy.tokens import Doc

logger = logging.getLogger(__name__)

# Module-level model cache to avoid reloading on every call
_nlp_model: Optional[spacy.language.Language] = None
_model_name: str = "en_core_web_sm"
_model_load_error: Optional[str] = None

# Minimum name length to be considered valid
MIN_NAME_LENGTH = 2
# Maximum name length to filter out noise
MAX_NAME_LENGTH = 50

# Common false-positive entities that look like names but aren't speaker introductions
# These are typically organizations, products, or places incorrectly tagged as PERSON
KNOWN_FALSE_POSITIVE_PATTERNS: Set[str] = {
    # Common organizations/products often tagged as PERSON
    "google", "apple", "microsoft", "amazon", "facebook", "meta", "tesla",
    "openai", "chatgpt", "gpt", "claude", "gemini", "zoom", "slack",
    "spotify", "netflix", "uber", "airbnb", "twitter", "x.com",
    # Common app names
    "whatsapp", "instagram", "telegram", "discord", "signal",
    # Generic terms
    "team", "everyone", "somebody", "anybody", "someone", "all",
}

# Words that commonly precede a name in natural speech but aren't names themselves
COMMON_PREFIX_WORDS: Set[str] = {
    "hey", "hi", "hello", "hiya", "yo",
    "ok", "okay", "oh", "so", "well",
    "yeah", "yes", "no", "nope",
    "like", "just", "really", "actually",
    "dude", "man", "bro", "sis",
}


def _is_valid_person_name(name: str, context_before: str = "", context_after: str = "") -> bool:
    """
    Validate if a detected PERSON entity is likely a real person name.

    Args:
        name: The detected name
        context_before: Text preceding the name (for pattern checking)
        context_after: Text following the name (for pattern checking)

    Returns:
        True if the name passes validation filters
    """
    if not name or len(name) < MIN_NAME_LENGTH or len(name) > MAX_NAME_LENGTH:
        return False

    name_lower = name.lower().strip()

    # Filter known false positives
    if name_lower in KNOWN_FALSE_POSITIVE_PATTERNS:
        return False

    # Filter if the "name" is just common non-name words
    if name_lower in COMMON_PREFIX_WORDS:
        return False

    # Filter single character names (unless they're a known abbreviation)
    if len(name) == 1 and name.isalpha():
        return False

    # Filter names that are pure numbers or contain numbers (e.g., "Team 5")
    if any(c.isdigit() for c in name):
        return False

    # Filter names that are all lowercase (spaCy typically capitalizes PERSON entities)
    # Exception: allow names with apostrophes like "O'Brien"
    if name.islower() and "'" not in name:
        return False

    # Filter names that are all uppercase (likely acronyms)
    if name.isupper() and len(name) > 3:
        return False

    # Check for common name introduction patterns - if "name" appears after
    # words like "called" or "named", it's more likely to be a real name
    context_lower = context_before.lower()
    if any(p in context_lower for p in ["called ", "named ", "is ", "this is ", "i'm ", "i am "]):
        return True

    # Filter if preceded by just a greeting or filler word
    words_before = context_lower.split()[-3:] if context_before else []
    if words_before and all(w in COMMON_PREFIX_WORDS for w in words_before):
        # Could still be valid if the name is capitalized
        pass

    return True


def _get_context(doc: Doc, ent: spacy.tokensSpan, window: int = 10) -> tuple:
    """
    Get surrounding text context for an entity.

    Args:
        doc: The spaCy Doc
        ent: The entity span
        window: Number of tokens to include before/after

    Returns:
        Tuple of (context_before, context_after) strings
    """
    start_token = max(0, ent.start - window)
    end_token = min(len(doc), ent.end + window)

    before_tokens = doc[start_token:ent.start]
    after_tokens = doc[ent.end:end_token]

    context_before = before_tokens.text if before_tokens else ""
    context_after = after_tokens.text if after_tokens else ""

    return context_before, context_after


def _load_model(model: str = _model_name) -> Optional[spacy.language.Language]:
    """
    Load spaCy NER model with caching.

    Args:
        model: Model name to load (default: en_core_web_sm)

    Returns:
        Loaded spaCy model or None if loading fails
    """
    global _nlp_model, _model_name, _model_load_error

    if _model_load_error:
        # Don't retry if we already tried and failed
        return None

    if _nlp_model is not None and _model_name == model:
        return _nlp_model

    try:
        logger.info(f"Loading spaCy NER model: {model}")
        _nlp_model = spacy.load(model)
        _model_name = model
        logger.info(f"Successfully loaded spaCy NER model: {model}")
        return _nlp_model
    except OSError as e:
        _model_load_error = str(e)
        logger.warning(
            f"spaCy NER model '{model}' not found. "
            f"Install with: pip install spacy && python -m spacy download {model}. "
            f"NER speaker detection will be unavailable. Error: {e}"
        )
        return None
    except Exception as e:
        _model_load_error = str(e)
        logger.error(f"Failed to load spaCy NER model '{model}': {e}")
        return None


def is_ner_available() -> bool:
    """
    Check if spaCy NER model is available.

    Returns:
        True if the model can be loaded, False otherwise
    """
    return _load_model() is not None


def detect_persons_with_ner(
    text: str,
    model: str = _model_name,
    max_persons: int = 3,
) -> List[str]:
    """
    Detect person names in text using spaCy NER.

    Extracts PERSON entities from text, filters false positives,
    and returns a list of unique person names found.

    Args:
        text: Input transcript/text to analyze
        model: spaCy model name to use (default: en_core_web_sm)
        max_persons: Maximum number of persons to return (default: 3)

    Returns:
        List of unique person names detected, filtered and title-cased.
        Returns empty list if no valid person names found or NER unavailable.

    Examples:
        >>> detect_persons_with_ner("Hi, I'm Sarah and this is my friend John")
        ['Sarah', 'John']

        >>> detect_persons_with_ner("We're using Google Docs for the project")
        []
    """
    if not text or not isinstance(text, str):
        return []

    # Clean text - remove excessive whitespace
    text = " ".join(text.split())
    if len(text) < 5:
        return []

    nlp = _load_model(model)
    if nlp is None:
        return []

    try:
        doc = nlp(text)
    except Exception as e:
        logger.warning(f"spaCy NER processing failed: {e}")
        return []

    found_names: List[str] = []
    seen_lower: Set[str] = set()

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue

        name = ent.text.strip()
        context_before, context_after = _get_context(doc, ent)

        if not _is_valid_person_name(name, context_before, context_after):
            continue

        # Normalize: title case, handle hyphenated/apostrophe names
        normalized = _normalize_name(name)
        if not normalized:
            continue

        # Deduplicate (case-insensitive)
        if normalized.lower() in seen_lower:
            continue

        # Additional context-based filtering
        # Skip names that are clearly describing someone not present
        # (e.g., "President Biden" -> just "Biden")
        if "president" in context_before.lower() or "minister" in context_before.lower():
            # Extract just the name part
            words = normalized.split()
            if len(words) > 1 and words[0].lower() in ["president", "minister", "dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs."]:
                normalized = " ".join(words[1:])

        if not normalized or len(normalized) < MIN_NAME_LENGTH:
            continue

        found_names.append(normalized)
        seen_lower.add(normalized.lower())

        if len(found_names) >= max_persons:
            break

    return found_names


def _normalize_name(name: str) -> str:
    """
    Normalize a detected name for storage/comparison.

    Handles:
    - Title casing
    - Hyphenated names
    - Names with apostrophes
    - Removes extra whitespace

    Args:
        name: Raw name from NER

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    # Remove leading/trailing whitespace and punctuation
    name = name.strip().strip('.,;:')

    if not name:
        return ""

    # Title case each word, preserving hyphens and apostrophes
    words = name.split()
    normalized_words = []
    for word in words:
        if not word:
            continue
        # Preserve internal capitalization for hyphenated words
        if "-" in word:
            parts = [w.capitalize() for w in word.split("-")]
            normalized_words.append("-".join(parts))
        elif "'" in word:
            # Handle apostrophes like O'Brien, D'Artagnan
            parts = word.split("'")
            normalized_words.append("'".join(p.capitalize() for p in parts))
        else:
            normalized_words.append(word.capitalize())

    result = " ".join(normalized_words)

    # Final cleanup
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def get_ner_stats() -> dict:
    """
    Get statistics about the NER model availability and status.

    Returns:
        Dict with model_name, available, load_error keys
    """
    return {
        "model_name": _model_name,
        "available": _nlp_model is not None,
        "load_error": _model_load_error,
    }
