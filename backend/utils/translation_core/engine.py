"""One canonical translation execution engine."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from config.translation import TranslationProfile, resolve_translation_profile
from utils.translation_core.cache import CachedTranslation, TranslationCache
from utils.translation_core.planner import (
    PlannedUnit,
    TranslationMode,
    TranslationUnit,
    build_translation_plan,
    fingerprint_text,
)
from utils.translation_core.providers import TranslationProviderChain, TranslationProviderError

logger = logging.getLogger(__name__)


class TranslationStatus(str, Enum):
    translated = 'translated'
    unchanged = 'unchanged'
    failed = 'failed'


@dataclass(frozen=True)
class TranslationOutcome:
    ordinal: int
    unit_id: str
    source_text: str
    text: str
    detected_language: str
    status: TranslationStatus
    error_reason: str | None = None


class TranslationEngine:
    def __init__(
        self,
        cache: TranslationCache,
        providers: TranslationProviderChain,
        profile_resolver: Callable[[], TranslationProfile] = resolve_translation_profile,
    ) -> None:
        self.cache = cache
        self._providers = providers
        self._profile_resolver = profile_resolver

    def translate(
        self,
        units: list[TranslationUnit],
        target_language: str,
        source_language: str = '',
        mode: TranslationMode = TranslationMode.sentence,
    ) -> list[TranslationOutcome]:
        if not units:
            return []

        profile = self._profile_resolver()
        self._report_config_diagnostics(profile)
        outcomes: dict[int, TranslationOutcome] = {}
        pending: list[TranslationUnit] = []

        for unit in units:
            full_fingerprint = fingerprint_text(unit.text)
            if not unit.text.strip():
                outcomes[unit.ordinal] = _unchanged(unit, '')
                continue
            cached = self.cache.get(full_fingerprint, target_language)
            if cached is not None:
                outcomes[unit.ordinal] = _outcome_from_value(unit, cached)
                continue
            if self.cache.is_negative(full_fingerprint, target_language):
                outcomes[unit.ordinal] = _unchanged(unit, _base_language(target_language))
                continue
            pending.append(unit)

        if not pending:
            return _ordered(units, outcomes)

        plan = build_translation_plan(pending, mode)
        segment_values: dict[str, CachedTranslation] = {}
        segment_text: dict[str, str] = {segment.fingerprint: segment.text for segment in plan.unique_segments}
        missing: list[tuple[str, str]] = []

        for segment in plan.unique_segments:
            cached = self.cache.get(segment.fingerprint, target_language)
            if cached is not None:
                segment_values[segment.fingerprint] = cached
            elif self.cache.is_negative(segment.fingerprint, target_language):
                segment_values[segment.fingerprint] = CachedTranslation(
                    text=segment.text,
                    detected_language=_base_language(target_language),
                )
            else:
                missing.append((segment.fingerprint, segment.text))

        staged: dict[str, CachedTranslation] = {}
        provider_failure: TranslationProviderError | None = None
        if missing:
            try:
                for start in range(0, len(missing), profile.max_batch_size):
                    chunk = missing[start : start + profile.max_batch_size]
                    batch = self._providers.translate(
                        [text for _fingerprint_value, text in chunk],
                        target_language,
                        source_language,
                        profile,
                        mode.value,
                    )
                    for (fingerprint, _text), translation in zip(chunk, batch.translations):
                        staged[fingerprint] = CachedTranslation(
                            text=translation.text,
                            detected_language=translation.detected_language,
                        )
            except TranslationProviderError as error:
                provider_failure = error

        # Provider results become visible to either cache layer only after every
        # requested chunk has returned a complete, valid response.
        if provider_failure is None:
            for fingerprint, value in staged.items():
                self.cache.put(fingerprint, target_language, value, profile)
            segment_values.update(staged)

        for planned_unit in plan.units:
            if not planned_unit.segment_fingerprints:
                outcomes[planned_unit.unit.ordinal] = _unchanged(planned_unit.unit, '')
                continue
            if any(fingerprint not in segment_values for fingerprint in planned_unit.segment_fingerprints):
                outcomes[planned_unit.unit.ordinal] = _failed(
                    planned_unit.unit,
                    provider_failure.reason if provider_failure is not None else 'incomplete_plan',
                )
                continue
            outcome = _reconstruct(planned_unit, segment_values, segment_text)
            outcomes[planned_unit.unit.ordinal] = outcome
            full_value = CachedTranslation(text=outcome.text, detected_language=outcome.detected_language)
            if len(planned_unit.segment_fingerprints) != 1 or (
                planned_unit.full_fingerprint != planned_unit.segment_fingerprints[0]
            ):
                self.cache.put(planned_unit.full_fingerprint, target_language, full_value, profile)

        return _ordered(units, outcomes)

    @staticmethod
    def _report_config_diagnostics(profile: TranslationProfile) -> None:
        if profile.unsupported_tokens:
            logger.warning('Ignoring unsupported translation providers: %s', ','.join(profile.unsupported_tokens))
        if profile.unavailable_tokens:
            logger.warning('Ignoring unavailable translation providers: %s', ','.join(profile.unavailable_tokens))


def _reconstruct(
    planned_unit: PlannedUnit,
    values: dict[str, CachedTranslation],
    segment_text: dict[str, str],
) -> TranslationOutcome:
    translated_parts = [values[fingerprint].text for fingerprint in planned_unit.segment_fingerprints]
    detected_languages = [
        values[fingerprint].detected_language
        for fingerprint in planned_unit.segment_fingerprints
        if values[fingerprint].detected_language
    ]
    detected_language = Counter(detected_languages).most_common(1)[0][0] if detected_languages else ''
    translated_text = ' '.join(translated_parts)
    if any(not segment_text[fingerprint] for fingerprint in planned_unit.segment_fingerprints):
        return _failed(planned_unit.unit, 'empty_segment')
    return _outcome_from_value(
        planned_unit.unit,
        CachedTranslation(text=translated_text, detected_language=detected_language),
    )


def _outcome_from_value(unit: TranslationUnit, value: CachedTranslation) -> TranslationOutcome:
    status = (
        TranslationStatus.unchanged
        if _normalize_text(unit.text) == _normalize_text(value.text)
        else TranslationStatus.translated
    )
    return TranslationOutcome(
        ordinal=unit.ordinal,
        unit_id=unit.unit_id,
        source_text=unit.text,
        text=value.text,
        detected_language=value.detected_language,
        status=status,
    )


def _unchanged(unit: TranslationUnit, detected_language: str) -> TranslationOutcome:
    return TranslationOutcome(
        ordinal=unit.ordinal,
        unit_id=unit.unit_id,
        source_text=unit.text,
        text=unit.text,
        detected_language=detected_language,
        status=TranslationStatus.unchanged,
    )


def _failed(unit: TranslationUnit, reason: str) -> TranslationOutcome:
    return TranslationOutcome(
        ordinal=unit.ordinal,
        unit_id=unit.unit_id,
        source_text=unit.text,
        text=unit.text,
        detected_language='',
        status=TranslationStatus.failed,
        error_reason=reason,
    )


def _ordered(units: list[TranslationUnit], outcomes: dict[int, TranslationOutcome]) -> list[TranslationOutcome]:
    return [outcomes[unit.ordinal] for unit in units]


def _normalize_text(text: str) -> str:
    return ' '.join(text.split())


def _base_language(language: str) -> str:
    return language.split('-', 1)[0].lower()
