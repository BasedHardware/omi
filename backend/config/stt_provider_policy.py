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
SONIOX_PROVIDER: Final = 'soniox'

DEEPGRAM_PROVIDERS: Final[tuple[str, ...]] = (DEEPGRAM_CLOUD_PROVIDER, DEEPGRAM_SELF_HOSTED_PROVIDER)
DEEPGRAM_MODEL_TOKENS: Final[frozenset[str]] = frozenset({'deepgram', 'nova-2', 'nova-3', 'dg-nova-2', 'dg-nova-3'})

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

# This is the single source of truth for provider enablement. Cloud Deepgram
# serves the live surfaces; batch stays on Parakeet/Velma. Self-hosted Deepgram
# is a distinct product, available only to a runtime with its explicit endpoint
# configured. Future availability changes start here.
PROVIDER_SERVING_SURFACES: Final[Mapping[str, frozenset[STTServingSurface]]] = {
    # PTT is streaming-only in transcribe_voice_message_stream, which dispatches
    # Parakeet and Modulate and raises on anything else. Admitting Deepgram here
    # would select a provider that surface cannot connect.
    DEEPGRAM_CLOUD_PROVIDER: frozenset({STTServingSurface.STREAMING}),
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
    # Streaming only: transcribe_voice_message_stream dispatches Parakeet and
    # Modulate alone, and the batch path has no Soniox client.
    SONIOX_PROVIDER: frozenset({STTServingSurface.STREAMING}),
}

# Defaults are also policy-owned so a deployment fallback cannot drift from the
# providers approved above. A deployment's literal ordering is checked against
# these values by validate-backend-runtime-env.py.
#
# Parakeet is the bounded-capacity last resort: the Parakeet service owns the
# hard stream gate (see parakeet/admission.py), so every listener converges on
# one cap per serving pod instead of listener-local counters.
DEFAULT_MODELS_BY_SURFACE: Final[Mapping[STTServingSurface, tuple[str, ...]]] = {
    # Velma-2 leads on cost, and its failures are now recoverable: a mid-session
    # error frame hands the stream to Soniox rather than ending it (#12459), which
    # is what the second slot is for. Deepgram stays last so a BYOK user still
    # resolves a `dg-*` model — dropping it would strip them of Deepgram entirely.
    # Parakeet stays last rather than being dropped: a client can ask for it by
    # name (`?stt_service=parakeet`), and that preference is only honorable while
    # the model is listed here.
    STTServingSurface.STREAMING: ('modulate-velma-2', 'soniox', 'dg-nova-3', 'parakeet'),
    # Batch work is queued, so Parakeet's bounded GPU means waiting rather than the
    # user-visible failure it causes on the streaming surface. Prefer the self-hosted
    # provider here and keep Velma as the overflow.
    STTServingSurface.PRERECORDED: ('parakeet', 'modulate-velma-2'),
    STTServingSurface.PTT: ('modulate-velma-2', 'parakeet'),
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


# Soniox rejects any ``language_hints`` entry outside this vocabulary with
# ``400 invalid_request Invalid language hint`` at the config frame, killing the
# socket after the WebSocket upgrade already succeeded (prod backend-listen,
# Loop S sensor 2026-09-02/03: ~16/24h, one window every 30 minutes for 6+ h).
# Source: https://soniox.com/docs/stt/concepts/supported-languages (single
# unified model; the page's per-model authority is the authenticated Get-models
# endpoint, which lists the same languages). Kept beside the other capability
# tables so a provider vocabulary change is one reviewed change here. Note the
# 'multi' sentinel is deliberately absent: it is ours, not an ISO code, and
# auto-detect sessions must send no hint at all.
SONIOX_SUPPORTED_LANGUAGE_HINTS: Final[frozenset[str]] = frozenset(
    {
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
        'en',
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


def soniox_accepts_language_hint(language: str | None) -> bool:
    """Return whether Soniox's documented vocabulary accepts this base code as a hint.

    Selection treats Soniox as serviceable for every language because the model
    identifies the language itself; this gate governs only the *hint* field, the
    one part of the config frame the provider validates against a closed set.
    """
    return normalized_stt_language(language) in SONIOX_SUPPORTED_LANGUAGE_HINTS


def modulate_supports_language(language: str | None) -> bool:
    """Return whether Velma-2 accepts a language code on a serving surface."""
    return normalized_stt_language(language) in MODULATE_SUPPORTED_LANGUAGES


def supports_live_multilingual_mode(language: str | None) -> bool:
    """Return whether a live user language can enter Modulate auto-detection."""
    return modulate_supports_language(language)


def provider_for_model_token(model: str) -> str | None:
    """Return the provider owning a known model token.

    A Deepgram token names the model, not the deployment serving it. Report the
    hosted identity; use ``deepgram_provider_for_runtime`` where it matters.
    """
    normalized = model.strip().lower()
    if normalized == 'parakeet':
        return PARAKEET_PROVIDER
    if normalized == 'modulate-velma-2':
        return MODULATE_PROVIDER
    if normalized == 'soniox':
        return SONIOX_PROVIDER
    if normalized in DEEPGRAM_MODEL_TOKENS:
        return DEEPGRAM_CLOUD_PROVIDER
    return None


def deepgram_provider_for_runtime(self_hosted: bool) -> str:
    """Return which Deepgram provider a runtime is actually serving from."""
    return DEEPGRAM_SELF_HOSTED_PROVIDER if self_hosted else DEEPGRAM_CLOUD_PROVIDER


def provider_is_enabled(provider: str, surface: STTServingSurface) -> bool:
    """Return whether a provider may serve the specified product surface."""
    return surface in PROVIDER_SERVING_SURFACES.get(provider, frozenset())


def model_is_enabled(model: str, surface: STTServingSurface) -> bool:
    """Return whether a model token may serve a surface.

    A Deepgram token is admissible when either deployment is allowed. Selection
    re-checks the runtime's own provider, so this cannot reach a withheld one.
    """
    provider = provider_for_model_token(model)
    if provider is None:
        return False
    if provider in DEEPGRAM_PROVIDERS:
        return any(provider_is_enabled(candidate, surface) for candidate in DEEPGRAM_PROVIDERS)
    return provider_is_enabled(provider, surface)


def default_models_for_surface(surface: STTServingSurface) -> tuple[str, ...]:
    """Return the canonical model ordering for one serving surface."""
    return tuple(model for model in DEFAULT_MODELS_BY_SURFACE[surface] if model_is_enabled(model, surface))


def canonical_model_config(surface: STTServingSurface) -> str:
    """Return the deployment-safe comma-separated model preference."""
    return ','.join(default_models_for_surface(surface))


def provider_for_service(service: object) -> str | None:
    """Return the provider token a serving ``STTService`` belongs to.

    The inverse of ``provider_for_model_token`` for callers holding a resolved
    service rather than a configured model string, so a mid-session failover can
    exclude the provider that just died.
    """
    value = getattr(service, 'value', service)
    if value == 'modulate':
        return MODULATE_PROVIDER
    if value == 'soniox':
        return SONIOX_PROVIDER
    if value == 'parakeet':
        return PARAKEET_PROVIDER
    if value == 'deepgram':
        return DEEPGRAM_CLOUD_PROVIDER
    return None
