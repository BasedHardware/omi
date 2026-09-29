"""Pure runtime configuration contract for backend translation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
from os import environ as process_environ
from typing import Mapping


class TranslationProvider(str, Enum):
    gemini = 'gemini'
    # Internal compatibility alias: this must never produce "google" telemetry.
    google = 'gemini'
    nllb = 'nllb'

    @staticmethod
    def get_display_name(value: 'TranslationProvider') -> str:
        if value == TranslationProvider.gemini:
            return 'Gemini 2.5 Flash-Lite via LLM gateway'
        if value == TranslationProvider.nllb:
            return 'NLLB-200 (self-hosted)'
        return str(value)


@dataclass(frozen=True)
class TranslationProfile:
    """Resolved provider and cache policy for one translation call."""

    providers: tuple[TranslationProvider, ...]
    nllb_url: str
    nllb_timeout_seconds: float
    cache_ttl_seconds: int
    negative_cache_ttl_seconds: int
    configured_providers: tuple[TranslationProvider, ...] = ()
    max_batch_size: int = 100
    unsupported_tokens: tuple[str, ...] = ()
    unavailable_tokens: tuple[str, ...] = ()
    policy_version: str = 'legacy'
    max_output_tokens: int = 0
    deadline_seconds: float = 0.0

    @property
    def primary_provider(self) -> TranslationProvider:
        return self.providers[0]


def resolve_translation_profile(env: Mapping[str, str] | None = None) -> TranslationProfile:
    """Resolve mutable environment at the translation call boundary.

    The configured list is an ordered provider policy. Unavailable providers
    are filtered, unsupported tokens are retained as diagnostics, and NLLB is
    used when the list is empty or no configured provider is usable.
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
        if token in {TranslationProvider.gemini.value, 'google'}:
            provider = TranslationProvider.gemini
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

    providers = tuple(usable_providers) or (TranslationProvider.nllb,)

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
    if not isfinite(value):
        raise ValueError(f'{name} must be a finite number greater than zero')
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


def translation_profile_gate_enabled() -> bool:
    """Reversible admission prior; read mutable env at the decision boundary."""
    return process_environ.get('TRANSLATION_PROFILE_GATE_ENABLED', 'true').lower() == 'true'


def translation_output_guard_enabled() -> bool:
    """Conservative edit checks still have a recall rollback switch."""
    return process_environ.get('TRANSLATION_OUTPUT_GUARD_ENABLED', 'true').lower() == 'true'


@dataclass(frozen=True)
class OnDemandTranslationConfig:
    shadow_enabled: bool
    gate_enabled: bool
    lease_v1_enabled: bool
    gemini_enabled: bool
    onopen_enabled: bool
    cohort_percent: int
    uid_allowlist: frozenset[str]
    max_segments: int
    max_chars: int
    deadline_seconds: float
    max_output_tokens: int
    uid_daily_chars: int
    global_daily_chars: int

    def admits(self, uid: str) -> bool:
        if uid in self.uid_allowlist:
            return True
        bucket = int.from_bytes(sha256(uid.encode('utf-8')).digest()[:8], 'big') % 100
        return bucket < self.cohort_percent

    @property
    def spend_configured(self) -> bool:
        return self.uid_daily_chars > 0 and self.global_daily_chars > 0


def resolve_ondemand_config(env: Mapping[str, str] | None = None) -> OnDemandTranslationConfig:
    values = process_environ if env is None else env

    # Owner decision 2026-09-29: on-demand ships enabled at merge; every switch
    # is a kill switch back to legacy semantics (false restores exact legacy).
    switch_defaults = {
        'TRANSLATION_DEMAND_SHADOW_ENABLED': 'false',
        'TRANSLATION_DEMAND_GATE_ENABLED': 'true',
        'TRANSLATION_DEMAND_LEASE_V1_ENABLED': 'true',
        'TRANSLATION_ONDEMAND_GEMINI_ENABLED': 'true',
        'TRANSLATION_ONOPEN_ENABLED': 'true',
    }

    def switch(name: str) -> bool:
        raw = values.get(name, switch_defaults[name]).strip().lower()
        if raw not in {'true', 'false'}:
            raise ValueError(f'{name} must be true or false')
        return raw == 'true'

    def bounded_int(name: str, default: int, maximum: int, *, zero_allowed: bool = False) -> int:
        raw = values.get(name, str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f'{name} must be an integer') from error
        if value < (0 if zero_allowed else 1) or value > maximum:
            raise ValueError(f'{name} is outside its allowed range')
        return value

    deadline = _positive_float(
        values.get('TRANSLATION_ONDEMAND_DEADLINE_SECONDS', '3'), 'TRANSLATION_ONDEMAND_DEADLINE_SECONDS'
    )
    if deadline > 30:
        raise ValueError('TRANSLATION_ONDEMAND_DEADLINE_SECONDS must be at most 30')
    return OnDemandTranslationConfig(
        shadow_enabled=switch('TRANSLATION_DEMAND_SHADOW_ENABLED'),
        gate_enabled=switch('TRANSLATION_DEMAND_GATE_ENABLED'),
        lease_v1_enabled=switch('TRANSLATION_DEMAND_LEASE_V1_ENABLED'),
        gemini_enabled=switch('TRANSLATION_ONDEMAND_GEMINI_ENABLED'),
        onopen_enabled=switch('TRANSLATION_ONOPEN_ENABLED'),
        cohort_percent=bounded_int('TRANSLATION_ONDEMAND_COHORT_PERCENT', 100, 100, zero_allowed=True),
        uid_allowlist=frozenset(
            uid.strip() for uid in values.get('TRANSLATION_ONDEMAND_UID_ALLOWLIST', '').split(',') if uid.strip()
        ),
        max_segments=bounded_int('TRANSLATION_ONDEMAND_MAX_SEGMENTS', 50, 50),
        max_chars=bounded_int('TRANSLATION_ONDEMAND_MAX_CHARS', 12000, 12000),
        deadline_seconds=deadline,
        max_output_tokens=bounded_int('TRANSLATION_ONDEMAND_MAX_OUTPUT_TOKENS', 4096, 8192),
        uid_daily_chars=bounded_int('TRANSLATION_ONDEMAND_UID_DAILY_CHARS', 10_000_000, 10_000_000, zero_allowed=True),
        global_daily_chars=bounded_int(
            'TRANSLATION_ONDEMAND_GLOBAL_DAILY_CHARS', 1_000_000_000, 1_000_000_000, zero_allowed=True
        ),
    )


def viewed_translation_profile(legacy: TranslationProfile, config: OnDemandTranslationConfig) -> TranslationProfile:
    """Gemini-only quality policy; the configured gateway route remains authoritative."""
    return TranslationProfile(
        providers=(TranslationProvider.gemini,),
        nllb_url=legacy.nllb_url,
        nllb_timeout_seconds=legacy.nllb_timeout_seconds,
        cache_ttl_seconds=legacy.cache_ttl_seconds,
        negative_cache_ttl_seconds=legacy.negative_cache_ttl_seconds,
        max_batch_size=min(config.max_segments, 50),
        policy_version='viewed_v1',
        max_output_tokens=config.max_output_tokens,
        deadline_seconds=config.deadline_seconds,
    )
