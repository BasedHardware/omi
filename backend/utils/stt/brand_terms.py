"""Normalize evidenced Omi variants (1590 Omi, 293 OMI, 235 omi, 142 Omie, 15 omie, 8 Omies/omies, 1 OMIs, 3 spelled letters); ambiguous forms need provider-side biasing, not text rewriting."""

import re
from typing import Any

_SPELLED_LETTERS = re.compile(r"o\.?\s+m\.?\s+i", re.IGNORECASE)
_BRAND_TERM = re.compile(
    r"(?<![\w./@#-])(?:o\.?\s+m\.?\s+i|omies|omie(?:['’]s)?|omis|omi(?:['’]s)?)(?![\w/@_-]|\.(?=\w)|-(?=\w))",
    re.IGNORECASE,
)


def normalize_brand_terms(text: str) -> str:
    """Standardize standalone Omi brand mentions while preserving surrounding text."""
    if not text:
        return text

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if _SPELLED_LETTERS.fullmatch(token):
            return 'Omi'
        lowered = token.lower().replace('’', "'")
        if lowered in {'omies', 'omis'}:
            return 'Omis'
        if lowered in {"omie's", "omi's"}:
            return "Omi's"
        return 'Omi'

    return _BRAND_TERM.sub(replace, text)


def normalize_brand_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize segment text in place and return the original list."""
    for segment in segments:
        text = segment.get('text')
        if isinstance(text, str):
            segment['text'] = normalize_brand_terms(text)
    return segments
