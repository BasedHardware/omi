"""Pure runtime contract for pre-recorded speech-to-text providers.

Keep model-token routing and provider configuration requirements here so runtime
selection and deployment validation cannot drift apart.  This module deliberately
does not construct clients, read files, or snapshot environment values at import.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from config.stt_provider_policy import (
    DEEPGRAM_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    default_models_for_surface,
    provider_for_model_token as policy_provider_for_model_token,
    provider_is_enabled,
)

STT_PRERECORDED_MODEL_ENV = 'STT_PRERECORDED_MODEL'
# Compatibility export for callers. Its value is owned by stt_provider_policy.
DEFAULT_STT_PRERECORDED_MODELS = default_models_for_surface(STTServingSurface.PRERECORDED)


class TranscriptionOutcome(str, Enum):
    """Closed, low-cardinality vocabulary for every accepted transcription."""

    SUCCESS = 'success'
    EXPECTED_SILENCE = 'expected_silence'
    EMPTY_UNEXPECTED = 'empty_unexpected'
    TIMEOUT = 'timeout'
    UPSTREAM_ERROR = 'upstream_error'
    CONFIG_ERROR = 'config_error'
    INVALID_INPUT = 'invalid_input'


class PrerecordedSTTService:
    DEEPGRAM = 'deepgram'
    MODULATE = 'modulate'
    PARAKEET = 'parakeet'


class PrerecordedSTTConfigurationError(RuntimeError):
    """A selected pre-recorded STT provider is not configured on this runtime."""

    def __init__(self, provider: str, missing_env: str):
        self.provider = provider
        self.missing_env = missing_env
        super().__init__(f'{provider} pre-recorded STT requires {missing_env}')


@dataclass(frozen=True)
class ProviderEnvironmentContract:
    """Environment required before invoking one provider.

    ``required_when_model_source_is_opaque`` covers deployment manifests where the
    selected model is secret-backed and therefore unavailable to a static checker.
    Every dependency an opaque selection can activate opts in; request-scoped BYOK
    remains a runtime bypass, not a substitute for background-process credentials.
    """

    required_env: tuple[str, ...] = ()
    required_when_model_source_is_opaque: bool = False


PROVIDER_ENVIRONMENT_CONTRACTS: Mapping[str, ProviderEnvironmentContract] = {
    PrerecordedSTTService.DEEPGRAM: ProviderEnvironmentContract(
        required_env=('DEEPGRAM_API_KEY',),
        required_when_model_source_is_opaque=True,
    ),
    PrerecordedSTTService.MODULATE: ProviderEnvironmentContract(
        required_env=('MODULATE_API_KEY',),
        required_when_model_source_is_opaque=True,
    ),
    # The Parakeet model token and its separately deployed endpoint must move as one
    # contract.  Validate the endpoint even when the token itself is secret-backed.
    PrerecordedSTTService.PARAKEET: ProviderEnvironmentContract(
        required_env=('HOSTED_PARAKEET_API_URL',),
        required_when_model_source_is_opaque=True,
    ),
}


def parse_prerecorded_models(raw: str | None) -> tuple[str, ...]:
    """Parse the configured model preference, defaulting to non-Deepgram providers."""
    if raw is None:
        return DEFAULT_STT_PRERECORDED_MODELS
    models = tuple(model.strip() for model in raw.split(',') if model.strip())
    return models or DEFAULT_STT_PRERECORDED_MODELS


def get_prerecorded_models(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Read the current model preference instead of freezing it during import."""
    source = os.environ if env is None else env
    return parse_prerecorded_models(source.get(STT_PRERECORDED_MODEL_ENV))


def provider_for_model_token(model: str) -> str | None:
    provider = policy_provider_for_model_token(model)
    if provider == MODULATE_PROVIDER:
        return PrerecordedSTTService.MODULATE
    if provider == PARAKEET_PROVIDER:
        return PrerecordedSTTService.PARAKEET
    if provider == DEEPGRAM_PROVIDER:
        return PrerecordedSTTService.DEEPGRAM
    return None


def providers_for_model_config(raw: str) -> tuple[str, ...]:
    """Return every non-retired provider a literal config can activate, including fallback."""
    providers: list[str] = []
    for model in parse_prerecorded_models(raw):
        provider = provider_for_model_token(model)
        if (
            provider is not None
            and provider_is_enabled(provider, STTServingSurface.PRERECORDED)
            and provider not in providers
        ):
            providers.append(provider)
    # Retired/unknown tokens and unsupported languages fall through to the
    # non-Deepgram defaults. Include both because language capability decides
    # which one serves the request.
    for model in DEFAULT_STT_PRERECORDED_MODELS:
        provider = provider_for_model_token(model)
        if (
            provider is not None
            and provider_is_enabled(provider, STTServingSurface.PRERECORDED)
            and provider not in providers
        ):
            providers.append(provider)
    return tuple(providers)


def required_env_for_provider(provider: str) -> tuple[str, ...]:
    contract = PROVIDER_ENVIRONMENT_CONTRACTS.get(provider)
    return contract.required_env if contract is not None else ()


def required_env_for_model_config(raw: str | None, *, source_is_opaque: bool = False) -> tuple[str, ...]:
    """Return deployment requirements for a literal or opaque model selection."""
    if source_is_opaque:
        providers = tuple(
            provider
            for provider, contract in PROVIDER_ENVIRONMENT_CONTRACTS.items()
            if contract.required_when_model_source_is_opaque
            and provider_is_enabled(provider, STTServingSurface.PRERECORDED)
        )
    else:
        providers = providers_for_model_config(raw or '')

    required: list[str] = []
    for provider in providers:
        for env_name in required_env_for_provider(provider):
            if env_name not in required:
                required.append(env_name)
    return tuple(required)


def missing_provider_environment(provider: str, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    source = os.environ if env is None else env
    return tuple(name for name in required_env_for_provider(provider) if not (source.get(name) or '').strip())


def require_provider_environment(provider: str, env: Mapping[str, str] | None = None) -> None:
    missing = missing_provider_environment(provider, env)
    if missing:
        raise PrerecordedSTTConfigurationError(provider, missing[0])
