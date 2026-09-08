"""Pure ordinal-preserving translation planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from utils.translation_language import split_into_sentences


class TranslationMode(str, Enum):
    whole_text = 'whole_text'
    sentence = 'sentence'


@dataclass(frozen=True)
class TranslationUnit:
    ordinal: int
    unit_id: str
    text: str


@dataclass(frozen=True)
class PlannedUnit:
    unit: TranslationUnit
    full_fingerprint: str
    segment_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class PlannedSegment:
    fingerprint: str
    text: str


@dataclass(frozen=True)
class TranslationPlan:
    units: tuple[PlannedUnit, ...]
    unique_segments: tuple[PlannedSegment, ...]


def build_translation_plan(units: list[TranslationUnit], mode: TranslationMode) -> TranslationPlan:
    planned_units: list[PlannedUnit] = []
    unique_segments: dict[str, PlannedSegment] = {}

    for unit in units:
        parts = _parts(unit.text, mode)
        fingerprints: list[str] = []
        for part in parts:
            fingerprint = fingerprint_text(part)
            fingerprints.append(fingerprint)
            unique_segments.setdefault(fingerprint, PlannedSegment(fingerprint=fingerprint, text=part))
        planned_units.append(
            PlannedUnit(
                unit=unit,
                full_fingerprint=fingerprint_text(unit.text),
                segment_fingerprints=tuple(fingerprints),
            )
        )

    return TranslationPlan(units=tuple(planned_units), unique_segments=tuple(unique_segments.values()))


def fingerprint_text(text: str) -> str:
    """Keep the existing MD5 cache identity; this is not a security digest."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def _parts(text: str, mode: TranslationMode) -> list[str]:
    if not text:
        return []
    if mode == TranslationMode.whole_text:
        return [text]
    return split_into_sentences(text)
