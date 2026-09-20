"""Pure streaming registry and deterministic routing policy. No environment or IO."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping

from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    PARAKEET_MODEL_BY_SURFACE,
    STTServingSurface,
    provider_is_enabled,
)

deepgram_nova3_multi_languages = {
    "multi",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "fr",
    "fr-CA",
    "de",
    "hi",
    "ru",
    "pt",
    "pt-BR",
    "pt-PT",
    "ja",
    "it",
    "nl",
}
deepgram_nova3_languages = {
    "ar",
    "ar-AE",
    "ar-SA",
    "ar-QA",
    "ar-KW",
    "ar-SY",
    "ar-LB",
    "ar-PS",
    "ar-JO",
    "ar-EG",
    "ar-SD",
    "ar-TD",
    "ar-MA",
    "ar-DZ",
    "ar-TN",
    "ar-IQ",
    "ar-IR",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "da",
    "da-DK",
    "de",
    "de-CH",
    "el",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "et",
    "fa",
    "fi",
    "fr",
    "fr-CA",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-KR",
    "lt",
    "lv",
    "mk",
    "mr",
    "ms",
    "nl",
    "nl-BE",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sv-SE",
    "ta",
    "te",
    "th",
    "th-TH",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
    "zh-CN",
    "zh-Hans",
    "zh-HK",
    "zh-Hant",
    "zh-TW",
}


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    service: str
    model: str
    languages: frozenset[str] | None
    features: frozenset[str]
    cost_class: str
    surfaces: frozenset[str] = frozenset({'streaming'})
    max_channels: int = 1


STREAMING_REGISTRY = {
    'modulate-velma-2': ProviderSpec(
        'modulate', 'modulate', 'velma-2', MODULATE_SUPPORTED_LANGUAGES, frozenset({'diarization'}), 'managed_low'
    ),
    'soniox': ProviderSpec('soniox', 'soniox', 'soniox', None, frozenset({'diarization'}), 'managed_standard'),
    'dg-nova-3': ProviderSpec(
        'deepgram_cloud',
        'deepgram',
        'nova-3',
        frozenset(deepgram_nova3_languages | deepgram_nova3_multi_languages),
        frozenset({'diarization', 'custom_vocabulary'}),
        'managed_standard',
    ),
    'dg-nova-2': ProviderSpec(
        'deepgram_cloud',
        'deepgram',
        'nova-2',
        frozenset(deepgram_nova3_languages | deepgram_nova3_multi_languages),
        frozenset({'diarization', 'custom_vocabulary'}),
        'managed_standard',
    ),
    'parakeet': ProviderSpec(
        'parakeet',
        'parakeet',
        'parakeet',
        PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.STREAMING]],
        frozenset({'diarization'}),
        'self_hosted',
    ),
}


@dataclass(frozen=True)
class RoutingRequest:
    language: str
    configured: frozenset[str]
    surface: str = 'streaming'
    features: frozenset[str] = frozenset()
    channels: int = 1


@dataclass(frozen=True)
class Preference:
    token: str
    priority: int
    weight: float = 1.0


@dataclass(frozen=True)
class Selection:
    candidates: tuple[ProviderSpec, ...]
    skipped: tuple[tuple[str, str], ...]


def eligibility(request: RoutingRequest, provider: ProviderSpec) -> str | None:
    if request.surface not in provider.surfaces or not provider_is_enabled(
        provider.provider, STTServingSurface(request.surface)
    ):
        return 'capability_mismatch'
    if provider.provider not in request.configured:
        return 'config_incomplete'
    if (
        request.surface not in provider.surfaces
        or request.channels > provider.max_channels
        or not request.features <= provider.features
        or provider.languages is not None
        and request.language not in provider.languages
    ):
        return 'capability_mismatch'
    return None


def rank_candidates(
    request: RoutingRequest,
    registry: Mapping[str, ProviderSpec],
    policy: tuple[Preference, ...],
    health: Mapping[str, bool],
    seed: int,
) -> Selection:
    """Each provider appears at most once; weights apply only within equal priority.

    Unknown/missing health means eligible (fail open to configuration order).
    Health only represents admission, never socket or transcript success.
    """
    rng = random.Random(seed)
    ranked: list[tuple[int, float, ProviderSpec]] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for preference in policy:
        spec = registry.get(preference.token)
        if spec is None:
            skipped.append(('unknown', 'config_incomplete'))
            continue
        reason = eligibility(request, spec)
        if reason is None and (not math.isfinite(preference.weight) or preference.weight <= 0):
            reason = 'policy'
        if reason is None and not health.get(spec.provider, True):
            reason = 'circuit_open'
        if reason is None and spec.provider in seen:
            reason = 'policy'
        if reason:
            skipped.append((spec.provider, reason))
            continue
        seen.add(spec.provider)
        ranked.append((preference.priority, -math.log(max(rng.random(), 1e-15)) / preference.weight, spec))
    ranked.sort(key=lambda row: (row[0], row[1], row[2].provider))
    return Selection(tuple(row[2] for row in ranked), tuple(skipped))
