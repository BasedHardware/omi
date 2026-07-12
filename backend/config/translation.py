"""Pure runtime configuration contract for backend translation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from os import environ as process_environ
from typing import Mapping


class TranslationProvider(str, Enum):
    google = 'google'
    nllb = 'nllb'

    @staticmethod
    def get_display_name(value: 'TranslationProvider') -> str:
        if value == TranslationProvider.google:
            return 'Google Cloud Translation V3'
        if value == TranslationProvider.nllb:
            return 'NLLB-200 (self-hosted)'
        return str(value)


@dataclass(frozen=True)
class TranslationProfile:
    """Resolved provider and cache policy for one translation call."""

    providers: tuple[TranslationProvider, ...]
    nllb_url: str
    nllb_timeout_seconds: float
    google_project_id: str | None
    cache_ttl_seconds: int
    negative_cache_ttl_seconds: int
    configured_providers: tuple[TranslationProvider, ...] = ()
    max_batch_size: int = 100
    unsupported_tokens: tuple[str, ...] = ()
    unavailable_tokens: tuple[str, ...] = ()

    @property
    def primary_provider(self) -> TranslationProvider:
        return self.providers[0]


def resolve_translation_profile(env: Mapping[str, str] | None = None) -> TranslationProfile:
    """Resolve mutable environment at the translation call boundary.

    The configured list is an ordered provider policy. Unavailable providers
    are filtered, unsupported tokens are retained as diagnostics, and Google is
    used only when the list is empty or no configured provider is usable.
    """

    values = process_environ if env is None else env
    nllb_url = values.get('HOSTED_TRANSLATION_API_URL', '').strip()
    raw_models = values.get('TRANSLATION_SERVICE_MODELS', '').strip()

    configured_providers: list[TranslationProvider] = []
    usable_providers: list[TranslationProvider] = []
    unsupported_tokens: list[str] = []
    unavailable_tokens: list[str] = []
    for raw_token in raw_models.split(',') if raw_models else ():
        token = raw_token.strip().lower()
        if not token:
            continue
        if token == TranslationProvider.google.value:
            provider = TranslationProvider.google
        elif token == TranslationProvider.nllb.value:
            provider = TranslationProvider.nllb
        else:
            if token not in unsupported_tokens:
                unsupported_tokens.append(token)
            continue
        if provider not in configured_providers:
            configured_providers.append(provider)
        if provider == TranslationProvider.nllb and not nllb_url:
            if token not in unavailable_tokens:
                unavailable_tokens.append(token)
            continue
        if provider not in usable_providers:
            usable_providers.append(provider)

    providers = tuple(usable_providers) or (TranslationProvider.google,)

    timeout = _positive_float(values.get('TRANSLATION_NLLB_TIMEOUT_SECONDS', '5.0'), 'TRANSLATION_NLLB_TIMEOUT_SECONDS')
    cache_ttl = _positive_int(values.get('TRANSLATION_CACHE_TTL', str(60 * 60 * 24 * 14)), 'TRANSLATION_CACHE_TTL')
    negative_ttl = _positive_int(
        values.get('TRANSLATION_NEGATIVE_CACHE_TTL', str(60 * 60 * 24 * 7)),
        'TRANSLATION_NEGATIVE_CACHE_TTL',
    )

    return TranslationProfile(
        providers=providers,
        nllb_url=nllb_url,
        nllb_timeout_seconds=timeout,
        google_project_id=values.get('GOOGLE_CLOUD_PROJECT') or None,
        cache_ttl_seconds=cache_ttl,
        negative_cache_ttl_seconds=negative_ttl,
        configured_providers=tuple(configured_providers),
        unsupported_tokens=tuple(unsupported_tokens),
        unavailable_tokens=tuple(unavailable_tokens),
    )


def _positive_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be a number') from error
    if value <= 0:
        raise ValueError(f'{name} must be greater than zero')
    return value


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be an integer') from error
    if value <= 0:
        raise ValueError(f'{name} must be greater than zero')
    return value
