"""Public translation façade backed by one canonical planner/executor.

Callers keep importing ``utils.translation``. Provider selection, cache policy,
planning, strict response validation, and reconstruction live in focused,
injectable modules under ``utils.translation_core``.
"""

from __future__ import annotations

from threading import BoundedSemaphore
from typing import Callable

from config.translation import TranslationProfile, TranslationProvider, resolve_translation_profile
from utils.observability.fallback import record_fallback
from utils.translation_core.cache import (
    CachedTranslation,
    TranslationCache,
    get_default_translation_store,
    viewed_cache_fingerprint,
)
from utils.translation_core.engine import (
    TranslationEngine,
    TranslationOutcome,
    TranslationStatus,
)
from utils.translation_core.metrics import TranslationMetrics, get_translation_metrics
from utils.translation_core.planner import TranslationMode, TranslationUnit
from utils.translation_core.providers import (
    TranslationProviderChain,
    default_provider_chain,
    get_default_provider_chain,
)
from utils.translation_language import (
    CONFIDENCE_FOREIGN_TRANSLATE,
    CONFIDENCE_TARGET_SKIP,
    LANGDETECT_RELIABLE_LANGUAGES,
    MIN_CONFIDENT_CHARS,
    NLLB_SUPPORTED_SOURCE_LANGUAGES,
    TranslationNeed,
    classify_translation_need,
    detect_language,
    detect_language_with_confidence,
    split_into_sentences,
)

# Detail pages reserve only six of eight viewed slots so live work can enter.
VIEWED_PROVIDER_CAPACITY = BoundedSemaphore(8)
VIEWED_REST_CAPACITY = BoundedSemaphore(6)


class TranslationService:
    """Compatible outer API over typed translation outcomes."""

    def __init__(
        self,
        *,
        engine: TranslationEngine | None = None,
        cache: TranslationCache | None = None,
        provider_chain: TranslationProviderChain | None = None,
        profile_resolver: Callable[[], TranslationProfile] = resolve_translation_profile,
        metrics: TranslationMetrics | None = None,
        fallback_recorder: Callable[..., None] = record_fallback,
    ) -> None:
        self._profile_resolver = profile_resolver
        if engine is not None:
            self._engine = engine
            self.cache = engine.cache
            return

        selected_metrics = metrics or get_translation_metrics()
        self.cache = cache or TranslationCache(
            persistent=get_default_translation_store(),
            metrics=selected_metrics,
        )
        if provider_chain is not None:
            selected_chain = provider_chain
        elif metrics is None and fallback_recorder is record_fallback:
            selected_chain = get_default_provider_chain()
        else:
            selected_chain = default_provider_chain(selected_metrics, fallback_recorder)
        self._engine = TranslationEngine(
            cache=self.cache,
            providers=selected_chain,
            profile_resolver=profile_resolver,
        )

    def translate_outcomes(
        self,
        dest_language: str,
        units: list[tuple[str, str]],
        source_language: str = '',
        *,
        mode: TranslationMode = TranslationMode.sentence,
        profile: TranslationProfile | None = None,
    ) -> list[TranslationOutcome]:
        canonical_units = [
            TranslationUnit(ordinal=ordinal, unit_id=unit_id, text=text)
            for ordinal, (unit_id, text) in enumerate(units)
        ]
        if profile is not None and profile.policy_version == 'viewed_v1':
            if not VIEWED_PROVIDER_CAPACITY.acquire(blocking=False):
                return [
                    TranslationOutcome(
                        unit.ordinal,
                        unit.unit_id,
                        unit.text,
                        unit.text,
                        '',
                        TranslationStatus.failed,
                        'provider_saturated',
                    )
                    for unit in canonical_units
                ]
            try:
                return self._engine.translate(
                    canonical_units,
                    target_language=dest_language,
                    source_language=source_language,
                    mode=mode,
                    profile=profile,
                )
            finally:
                VIEWED_PROVIDER_CAPACITY.release()
        return self._engine.translate(
            canonical_units,
            target_language=dest_language,
            source_language=source_language,
            mode=mode,
            profile=profile,
        )

    def translate_units_batch(
        self,
        dest_language: str,
        units: list[tuple[str, str]],
        source_language: str = '',
    ) -> list[tuple[str, str, str]]:
        outcomes = self.translate_outcomes(
            dest_language,
            units,
            source_language,
            mode=TranslationMode.sentence,
        )
        return [(outcome.unit_id, outcome.text, outcome.detected_language) for outcome in outcomes]

    def translate_text_by_sentence(
        self,
        dest_language: str,
        text: str,
        source_language: str = '',
    ) -> tuple[str, str]:
        outcome = self.translate_outcomes(
            dest_language,
            [('text', text)],
            source_language,
            mode=TranslationMode.sentence,
        )[0]
        return outcome.text, outcome.detected_language

    def translate_text(self, dest_language: str, text: str, source_language: str = '') -> tuple[str, str]:
        outcome = self.translate_outcomes(
            dest_language,
            [('text', text)],
            source_language,
            mode=TranslationMode.whole_text,
        )[0]
        return outcome.text, outcome.detected_language

    def get_cached_translation(self, fingerprint: str, target_language: str) -> dict[str, str] | None:
        cached = self.cache.get(fingerprint, target_language)
        if cached is None:
            return None
        return {'text': cached.text, 'detected_lang': cached.detected_language}

    def cache_translation(
        self,
        fingerprint: str,
        target_language: str,
        translated_text: str,
        detected_language: str,
    ) -> None:
        self.cache.put(
            fingerprint,
            target_language,
            CachedTranslation(translated_text, detected_language),
            self._profile_resolver(),
        )

    def get_negative_cache(self, fingerprint: str, target_language: str) -> bool:
        return self.cache.is_negative(fingerprint, target_language)

    def set_negative_cache(
        self,
        fingerprint: str,
        target_language: str,
        *,
        profile: TranslationProfile | None = None,
        source_language: str = '',
        mode: TranslationMode = TranslationMode.whole_text,
    ) -> None:
        selected = profile or self._profile_resolver()
        key = (
            fingerprint
            if selected.policy_version == 'legacy'
            else viewed_cache_fingerprint(
                fingerprint, source_language, target_language, mode.value, selected.policy_version
            )
        )
        self.cache.put_negative(key, target_language, selected)

    def clear_session_cache(self) -> None:
        """Release per-session translation state while retaining shared Redis data."""
        self.cache.clear_memory()


__all__ = [
    'CONFIDENCE_FOREIGN_TRANSLATE',
    'CONFIDENCE_TARGET_SKIP',
    'LANGDETECT_RELIABLE_LANGUAGES',
    'MIN_CONFIDENT_CHARS',
    'NLLB_SUPPORTED_SOURCE_LANGUAGES',
    'TranslationMode',
    'TranslationNeed',
    'TranslationOutcome',
    'TranslationProfile',
    'TranslationProvider',
    'TranslationService',
    'TranslationStatus',
    'classify_translation_need',
    'detect_language',
    'detect_language_with_confidence',
    'resolve_translation_profile',
    'split_into_sentences',
]
