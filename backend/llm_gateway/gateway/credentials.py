from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import Field, field_validator

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.schemas import CredentialMode, CredentialPolicy, FailureClass, StrictBaseModel

BYOK_UNSUPPORTED_PROVIDER_FAILURE = FailureClass.BYOK_UNSUPPORTED_PROVIDER.value

BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES = frozenset(
    {
        FailureClass.MISSING_BYOK_KEY.value,
        FailureClass.BYOK_AUTH.value,
        FailureClass.BYOK_QUOTA.value,
        FailureClass.BYOK_RATE_LIMIT.value,
        BYOK_UNSUPPORTED_PROVIDER_FAILURE,
    }
)


class CredentialSource(str, Enum):
    OMI_MANAGED = 'omi_managed'
    SERVICE_FORWARDED_BYOK = 'service_forwarded_byok'
    INTERNAL_KEY_REFERENCE = 'internal_key_reference'


class ProviderKeyPresence(StrictBaseModel):
    provider: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_-]*$')
    present: bool
    key_ref: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator('provider', mode='before')
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()


class CredentialContext(StrictBaseModel):
    mode: CredentialMode
    source: CredentialSource
    caller: ServiceCaller
    provider_keys: dict[str, ProviderKeyPresence] = Field(default_factory=dict)

    def has_provider_key(self, provider: str) -> bool:
        key_presence = self.provider_keys.get(provider.strip().lower())
        return key_presence.present if key_presence is not None else False

    def safe_model_dump(self) -> dict[str, Any]:
        return self.model_dump(mode='json')


def build_omi_managed_credential_context(caller: ServiceCaller) -> CredentialContext:
    return CredentialContext(mode=CredentialMode.OMI_PAID, source=CredentialSource.OMI_MANAGED, caller=caller)


def build_byok_credential_context(
    caller: ServiceCaller,
    provider_keys: Mapping[str, str | None],
    *,
    key_refs: Mapping[str, str | None] | None = None,
) -> CredentialContext:
    presences: dict[str, ProviderKeyPresence] = {}
    normalized_key_refs = _normalize_optional_mapping(key_refs)
    for provider, raw_key in provider_keys.items():
        normalized_provider = provider.strip().lower()
        key_ref = normalized_key_refs.get(normalized_provider)
        presences[normalized_provider] = ProviderKeyPresence(
            provider=normalized_provider,
            present=bool(raw_key.strip()) if raw_key is not None else False,
            key_ref=key_ref,
        )

    return CredentialContext(
        mode=CredentialMode.BYOK,
        source=CredentialSource.SERVICE_FORWARDED_BYOK,
        caller=caller,
        provider_keys=presences,
    )


def build_key_reference_credential_context(
    caller: ServiceCaller,
    key_refs: Mapping[str, str | None],
) -> CredentialContext:
    presences: dict[str, ProviderKeyPresence] = {}
    for provider, key_ref in key_refs.items():
        normalized_provider = provider.strip().lower()
        stripped_key_ref = key_ref.strip() if isinstance(key_ref, str) else key_ref
        # Whitespace-only refs are treated as absent so they do not pass
        # BYOK key-availability checks.
        normalized_key_ref = stripped_key_ref or None
        presences[normalized_provider] = ProviderKeyPresence(
            provider=normalized_provider,
            present=bool(normalized_key_ref),
            key_ref=normalized_key_ref,
        )

    return CredentialContext(
        mode=CredentialMode.BYOK,
        source=CredentialSource.INTERNAL_KEY_REFERENCE,
        caller=caller,
        provider_keys=presences,
    )


def is_byok_failure_class(failure_class: FailureClass | str) -> bool:
    return _failure_class_value(failure_class) in BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES


def is_fallback_eligible_by_default(
    failure_class: FailureClass | str,
    credential_policy: CredentialPolicy,
) -> bool:
    failure_value = _failure_class_value(failure_class)
    if credential_policy.mode == CredentialMode.BYOK and failure_value in BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES:
        return False
    if failure_value in {_failure_class_value(item) for item in credential_policy.never_fallback_failure_classes}:
        return False
    return failure_value in {_failure_class_value(item) for item in credential_policy.fallback_eligible_failure_classes}


def _failure_class_value(failure_class: FailureClass | str) -> str:
    if isinstance(failure_class, FailureClass):
        return failure_class.value
    return failure_class


def _normalize_optional_mapping(values: Mapping[str, str | None] | None) -> dict[str, str | None]:
    if values is None:
        return {}
    return {key.strip().lower(): value for key, value in values.items()}
