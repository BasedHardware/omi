"""Deterministic tier of the conversation relevance decision.

Pure and stdlib-only on purpose: the sync intake transaction, the read-side
visibility predicate, and the processing pipeline all apply these rules, and
several test harnesses load them with a stubbed ``utils`` package.

A verdict here is final for its side. ``None`` means the content is neither
obviously empty nor obviously substantial and the model tier decides. Duration
alone is never a discard reason: a five-second "call mom before five" matters.
"""

from __future__ import annotations

import re
from typing import Literal, Optional, Sequence

Verdict = Literal['keep', 'discard']

# Bumped whenever a rule changes, so stored decisions stay attributable.
RULES_VERSION = 1

# Above this many words the model is never asked; long speech is kept.
KEEP_WORD_COUNT = 100

# Non-lexical fillers and laughter. A transcript made only of these carries no
# content in any language the transcriber renders them for.
FILLER_TOKENS = frozenset(
    {'mm', 'hmm', 'hm', 'mhm', 'huh', 'uh', 'um', 'hmmh', 'mmh', 'hmmmh', 'hmmmmm', 'ha', 'haha', 'hahaha'}
)

_WORD = re.compile(r"[^\W_]+")


def transcript_words(texts: Sequence[str]) -> list[str]:
    return _WORD.findall(' '.join(text for text in texts if text).casefold())


def deterministic_relevance(texts: Sequence[str], speech_seconds: Optional[float]) -> tuple[Optional[Verdict], str]:
    """Return ``(verdict, rule)``; ``verdict`` is None when the model must decide.

    ``texts`` are transcript segment texts in order; ``speech_seconds`` is the
    summed segment duration, when known. ``rule`` is a stable snake_case id
    used as a metric label and stored with the decision.
    """
    words = transcript_words(texts)
    if not words:
        return 'discard', 'empty_transcript'
    if len(words) > KEEP_WORD_COUNT:
        return 'keep', 'long_transcript'
    if len(words) <= 12 and (speech_seconds is None or speech_seconds <= 15) and set(words) <= FILLER_TOKENS:
        return 'discard', 'filler_only'
    return None, 'ambiguous'
