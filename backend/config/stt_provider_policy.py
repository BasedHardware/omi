"""Authoritative serving policy for every speech-to-text provider.

This module is deliberately code-owned rather than environment-owned: changing a
provider's serving availability requires one reviewed change here. Deployment
manifests may choose ordering, but cannot reactivate a provider absent from this
policy. Add a provider to selected surfaces below only after its credentials,
traffic contract, and regression coverage are ready.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Mapping


class STTServingSurface(str, Enum):
    STREAMING = 'streaming'
    PRERECORDED = 'prerecorded'
    PTT = 'ptt'


DEEPGRAM_CLOUD_PROVIDER: Final = 'deepgram_cloud'
DEEPGRAM_SELF_HOSTED_PROVIDER: Final = 'deepgram_self_hosted'
MODULATE_PROVIDER: Final = 'modulate'
PARAKEET_PROVIDER: Final = 'parakeet'

# Velma-2 is the live fallback for every language we can safely send to its
# automatic-detection mode. Keep this capability at the policy boundary rather
# than beside one caller: a user may choose multi-language mode independently
# of their primary language.
MODULATE_SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset(
    {
        'multi',
        'en',
        'af',
        'sq',
        'ar',
        'az',
        'eu',
        'be',
        'bn',
        'bs',
        'bg',
        'ca',
        'zh',
        'hr',
        'cs',
        'da',
        'nl',
        'et',
        'fi',
        'fr',
        'gl',
        'de',
        'el',
        'gu',
        'he',
        'hi',
        'hu',
        'id',
        'it',
        'ja',
        'kn',
        'kk',
        'ko',
        'lv',
        'lt',
        'mk',
        'ms',
        'ml',
        'mr',
        'no',
        'fa',
        'pl',
        'pt',
        'pa',
        'ro',
        'ru',
        'sr',
        'sk',
        'sl',
        'es',
        'sw',
        'sv',
        'tl',
        'ta',
        'te',
        'th',
        'tr',
        'uk',
        'ur',
        'vi',
        'cy',
    }
)

# This is the single source of truth for provider enablement. Cloud Deepgram is
# intentionally absent from every serving surface. Self-hosted Deepgram is a
# distinct product and remains available only to the streaming runtime that has
# its explicit self-hosted endpoint configured. Future availability changes
# start here, after provider wiring and regression coverage are ready.
PROVIDER_SERVING_SURFACES: Final[Mapping[str, frozenset[STTServingSurface]]] = {
    DEEPGRAM_CLOUD_PROVIDER: frozenset(),
    DEEPGRAM_SELF_HOSTED_PROVIDER: frozenset({STTServingSurface.STREAMING}),
    MODULATE_PROVIDER: frozenset(
        {
            STTServingSurface.STREAMING,
            STTServingSurface.PRERECORDED,
            STTServingSurface.PTT,
        }
    ),
    PARAKEET_PROVIDER: frozenset(
        {
            STTServingSurface.STREAMING,
            STTServingSurface.PRERECORDED,
            STTServingSurface.PTT,
        }
    ),
}

# Defaults are also policy-owned so a deployment fallback cannot drift from the
# providers approved above. A deployment's literal ordering is checked against
# these values by validate-backend-runtime-env.py.
DEFAULT_MODELS_BY_SURFACE: Final[Mapping[STTServingSurface, tuple[str, ...]]] = {
    STTServingSurface.STREAMING: ('parakeet', 'modulate-velma-2'),
    STTServingSurface.PRERECORDED: ('parakeet', 'modulate-velma-2'),
    STTServingSurface.PTT: ('parakeet', 'modulate-velma-2'),
}

# The Parakeet deployment has distinct batch and real-time models. The batch
# `parakeet-tdt-0.6b-v3` model can detect 25 languages, while streaming and
# PTT both use the English-only `parakeet-rnnt-1.1b` model. Keep capabilities
# tied to the deployed model rather than to the provider token, so a model
# change must update this policy and its regression coverage together.
PARAKEET_MODEL_BY_SURFACE: Final[Mapping[STTServingSurface, str]] = {
    STTServingSurface.STREAMING: 'nvidia/parakeet-rnnt-1.1b',
    STTServingSurface.PTT: 'nvidia/parakeet-rnnt-1.1b',
    STTServingSurface.PRERECORDED: 'nvidia/parakeet-tdt-0.6b-v3',
}
PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL: Final[Mapping[str, frozenset[str]]] = {
    'nvidia/parakeet-rnnt-1.1b': frozenset({'en'}),
    'nvidia/parakeet-tdt-0.6b-v3': frozenset(
        {
            'multi',
            'bg',
            'hr',
            'cs',
            'da',
            'nl',
            'en',
            'et',
            'fi',
            'fr',
            'de',
            'el',
            'hu',
            'it',
            'lt',
            'lv',
            'mt',
            'pl',
            'pt',
            'ro',
            'ru',
            'sk',
            'sl',
            'es',
            'sv',
            'uk',
        }
    ),
}


def parakeet_supports_language(surface: STTServingSurface, language: str) -> bool:
    """Return whether the deployed Parakeet model supports a normalized language."""
    model = PARAKEET_MODEL_BY_SURFACE[surface]
    return language.strip().lower() in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[model]


def normalized_stt_language(language: str | None) -> str:
    """Return the base language code accepted by provider capability maps."""
    if not language:
        return ''
    return language.split('-')[0].split('_')[0].lower()


def modulate_supports_language(language: str | None) -> bool:
    """Return whether Velma-2 accepts a language code on a serving surface."""
    return normalized_stt_language(language) in MODULATE_SUPPORTED_LANGUAGES


def supports_live_multilingual_mode(language: str | None) -> bool:
    """Return whether a live user language can enter Modulate auto-detection."""
    return modulate_supports_language(language)


def provider_for_model_token(model: str) -> str | None:
    """Return the provider owning a known model token.

    Deepgram model tokens identify the retained self-hosted deployment. Their
    selection still requires the runtime's explicit self-hosted endpoint; they
    never imply permission to contact the hosted Deepgram API.
    """
    normalized = model.strip().lower()
    if normalized == 'parakeet':
        return PARAKEET_PROVIDER
    if normalized == 'modulate-velma-2':
        return MODULATE_PROVIDER
    if normalized in {'deepgram', 'nova-2', 'nova-3', 'dg-nova-2', 'dg-nova-3'}:
        return DEEPGRAM_SELF_HOSTED_PROVIDER
    return None


def provider_is_enabled(provider: str, surface: STTServingSurface) -> bool:
    """Return whether a provider may serve the specified product surface."""
    return surface in PROVIDER_SERVING_SURFACES.get(provider, frozenset())


def model_is_enabled(model: str, surface: STTServingSurface) -> bool:
    provider = provider_for_model_token(model)
    return provider is not None and provider_is_enabled(provider, surface)


def default_models_for_surface(surface: STTServingSurface) -> tuple[str, ...]:
    """Return the canonical model ordering for one serving surface."""
    return tuple(model for model in DEFAULT_MODELS_BY_SURFACE[surface] if model_is_enabled(model, surface))


def canonical_model_config(surface: STTServingSurface) -> str:
    """Return the deployment-safe comma-separated model preference."""
    return ','.join(default_models_for_surface(surface))
