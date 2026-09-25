"""Content evidence that two captures heard the same speech (#3244).

Wall-clock overlap only proposes a pair: on production dual-surface accounts
most window-overlapping pairs carry little shared text, and live timelines can
sit minutes apart. Grouping therefore requires the captures to share word
trigrams. Containment is measured against the smaller transcript, so a capture
that also heard speech the other did not (the pendant in the room, the laptop's
remote participants) still confirms on the part both heard.

Thresholds come from the 2026-09-23 baseline (omi-knowledge-base project
`cross-surface-continuity`): unrelated same-user cross-surface pairs reached a
trigram containment p99 of 0.13, while same-speech pairs clustered at 0.2-0.8.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

MIN_WORDS = 30
MIN_SHARED_TRIGRAMS = 15
MIN_CONTAINMENT = 0.25

_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)


@dataclass(frozen=True)
class SharedSpeech:
    containment: float
    shared_trigrams: int
    min_words: int

    def confirms(self) -> bool:
        return (
            self.min_words >= _threshold('CROSS_DEVICE_GROUP_MIN_WORDS', MIN_WORDS)
            and self.shared_trigrams >= _threshold('CROSS_DEVICE_GROUP_MIN_SHARED_TRIGRAMS', MIN_SHARED_TRIGRAMS)
            and self.containment >= _threshold('CROSS_DEVICE_GROUP_MIN_CONTAINMENT', MIN_CONTAINMENT, 1.0)
        )

    def evidence(self) -> dict:
        """Numeric-only record; never carries transcript text."""
        return {
            'method': 'shared_speech',
            'containment': round(self.containment, 4),
            'shared_trigrams': self.shared_trigrams,
            'min_words': self.min_words,
        }


def _threshold(name: str, default: float, maximum: float = math.inf) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError('invalid shared-speech threshold')
    return value


def _segment_text(segment: Any) -> str:
    text = segment.get('text') if isinstance(segment, Mapping) else getattr(segment, 'text', None)
    return text if isinstance(text, str) else ''


def transcript_words(segments: Iterable[Any] | None) -> list[str]:
    return [word for segment in segments or () for word in _WORD.findall(_segment_text(segment).lower())]


def _trigrams(words: list[str]) -> set[tuple[str, str, str]]:
    return {(words[i], words[i + 1], words[i + 2]) for i in range(len(words) - 2)}


def measure_shared_speech(first: Iterable[Any] | None, second: Iterable[Any] | None) -> SharedSpeech:
    a, b = transcript_words(first), transcript_words(second)
    grams_a, grams_b = _trigrams(a), _trigrams(b)
    smaller, larger = (grams_a, grams_b) if len(grams_a) <= len(grams_b) else (grams_b, grams_a)
    shared = len(smaller & larger)
    containment = shared / len(smaller) if smaller else 0.0
    return SharedSpeech(containment=containment, shared_trigrams=shared, min_words=min(len(a), len(b)))
