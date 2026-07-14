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

STT_PRERECORDED_MODEL_ENV = 'STT_PRERECORDED_MODEL'
DEFAULT_STT_PRERECORDED_MODELS = ('dg-nova-3',)


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
    # Runtime may bypass the process key for an individual Deepgram BYOK request,
    # but a deployment whose opaque preference can select Deepgram still needs the
    # process credential for background/sync work with no user credential context.
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
    """Parse a model preference list, retaining the historical Deepgram default."""
    if raw is None:
        return DEFAULT_STT_PRERECORDED_MODELS
    models = tuple(model.strip() for model in raw.split(',') if model.strip())
    return models or DEFAULT_STT_PRERECORDED_MODELS


def get_prerecorded_models(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Read the current model preference instead of freezing it during import."""
    source = os.environ if env is None else env
    return parse_prerecorded_models(source.get(STT_PRERECORDED_MODEL_ENV))


def provider_for_model_token(model: str) -> str | None:
    if model.startswith('dg-'):
        return PrerecordedSTTService.DEEPGRAM
    if model == 'modulate-velma-2':
        return PrerecordedSTTService.MODULATE
    if model == 'parakeet':
        return PrerecordedSTTService.PARAKEET
    return None


def providers_for_model_config(raw: str) -> tuple[str, ...]:
    """Return every provider a literal config can activate, including fallback."""
    providers: list[str] = []
    for model in parse_prerecorded_models(raw):
        provider = provider_for_model_token(model)
        if provider is not None and provider not in providers:
            providers.append(provider)
    # Both routing entry points ultimately fall back to Deepgram for an unknown
    # token or a language unsupported by earlier preferences.
    if PrerecordedSTTService.DEEPGRAM not in providers:
        providers.append(PrerecordedSTTService.DEEPGRAM)
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
