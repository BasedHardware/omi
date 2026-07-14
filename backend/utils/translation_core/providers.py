"""Injected provider adapters and strict ordered fallback execution."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Mapping, Protocol, cast

import httpx
from google.cloud import translate_v3

from config.translation import TranslationProfile, TranslationProvider
from utils.observability.fallback import record_fallback
from utils.translation_core.metrics import TranslationMetrics, get_translation_metrics
from utils.translation_language import (
    LANGDETECT_RELIABLE_LANGUAGES,
    NLLB_SUPPORTED_SOURCE_LANGUAGES,
    detect_language_with_confidence,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderTranslation:
    text: str
    detected_language: str = ''


@dataclass(frozen=True)
class ProviderBatch:
    provider: TranslationProvider
    translations: tuple[ProviderTranslation, ...]


class TranslationProviderPort(Protocol):
    provider: TranslationProvider

    def translate(
        self,
        contents: list[str],
        target_language: str,
        source_language: str,
        profile: TranslationProfile,
    ) -> list[ProviderTranslation]:
        ...


class TranslationProviderError(RuntimeError):
    def __init__(self, provider: TranslationProvider, reason: str, message: str):
        self.provider = provider
        self.reason = reason
        super().__init__(message)


class GoogleTranslationProvider:
    provider = TranslationProvider.google

    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or translate_v3.TranslationServiceClient
        self._client: Any | None = None
        self._client_lock = Lock()

    def translate(
        self,
        contents: list[str],
        target_language: str,
        source_language: str,
        profile: TranslationProfile,
    ) -> list[ProviderTranslation]:
        request: dict[str, object] = {
            'contents': contents,
            'parent': f'projects/{profile.google_project_id}/locations/global',
            'mime_type': 'text/plain',
            'target_language_code': target_language,
        }
        if source_language:
            request['source_language_code'] = source_language
        try:
            response = self._get_client().translate_text(**request)
        except Exception as error:
            raise TranslationProviderError(self.provider, 'other', 'Google translation request failed') from error

        raw_translations: object = getattr(response, 'translations', None)
        if not isinstance(raw_translations, Sequence) or isinstance(raw_translations, (str, bytes)):
            raise TranslationProviderError(self.provider, 'invalid_response', 'Google response has no translations')
        translations: list[ProviderTranslation] = []
        for item in cast(Sequence[object], raw_translations):
            text: object = getattr(item, 'translated_text', '')
            detected: object = getattr(item, 'detected_language_code', '') or ''
            if not isinstance(text, str) or not isinstance(detected, str):
                raise TranslationProviderError(
                    self.provider, 'invalid_response', 'Google translation fields are malformed'
                )
            translations.append(ProviderTranslation(text=text, detected_language=detected))
        return translations

    def _get_client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._client_factory()
        return self._client


class NllbTranslationProvider:
    provider = TranslationProvider.nllb

    def __init__(self, client_factory: Callable[[TranslationProfile], Any] | None = None) -> None:
        self._client_factory = client_factory or _create_nllb_client
        self._clients: dict[tuple[str, float], Any] = {}
        self._clients_lock = Lock()

    def translate(
        self,
        contents: list[str],
        target_language: str,
        source_language: str,
        profile: TranslationProfile,
    ) -> list[ProviderTranslation]:
        source = source_language or _detect_nllb_source(contents)
        payload: dict[str, object] = {
            'contents': contents,
            'target_language_code': target_language,
        }
        if source:
            payload['source_language_code'] = source

        try:
            response = self._get_client(profile).post('/v1/translate', json=payload)
            response.raise_for_status()
            body: object = response.json()
        except httpx.TimeoutException as error:
            raise TranslationProviderError(self.provider, 'timeout', 'NLLB translation timed out') from error
        except httpx.HTTPStatusError as error:
            reason = _http_reason(error.response.status_code)
            raise TranslationProviderError(self.provider, reason, 'NLLB translation request failed') from error
        except (httpx.RequestError, ValueError, TypeError) as error:
            raise TranslationProviderError(self.provider, 'other', 'NLLB translation request failed') from error

        if not isinstance(body, dict):
            raise TranslationProviderError(self.provider, 'invalid_response', 'NLLB response has no translations')
        payload_body = cast(dict[object, object], body)
        raw_translations = payload_body.get('translations')
        if not isinstance(raw_translations, list):
            raise TranslationProviderError(self.provider, 'invalid_response', 'NLLB response has no translations')

        translations: list[ProviderTranslation] = []
        for item in cast(list[object], raw_translations):
            if not isinstance(item, dict):
                raise TranslationProviderError(self.provider, 'invalid_response', 'NLLB translation item is malformed')
            payload_item = cast(dict[object, object], item)
            text = payload_item.get('translated_text', '')
            detected = payload_item.get('detected_language_code', '')
            if not isinstance(text, str) or not isinstance(detected, str):
                raise TranslationProviderError(
                    self.provider, 'invalid_response', 'NLLB translation fields are malformed'
                )
            translations.append(ProviderTranslation(text=text, detected_language=detected))
        return translations

    def _get_client(self, profile: TranslationProfile) -> Any:
        client_profile = (profile.nllb_url, profile.nllb_timeout_seconds)
        client = self._clients.get(client_profile)
        if client is None:
            with self._clients_lock:
                client = self._clients.get(client_profile)
                if client is None:
                    client = self._client_factory(profile)
                    self._clients[client_profile] = client
        return client


class TranslationProviderChain:
    def __init__(
        self,
        providers: Mapping[TranslationProvider, TranslationProviderPort],
        metrics: TranslationMetrics,
        fallback_recorder: Callable[..., None] = record_fallback,
    ) -> None:
        self._providers = dict(providers)
        self._metrics = metrics
        self._fallback_recorder = fallback_recorder

    def translate(
        self,
        contents: list[str],
        target_language: str,
        source_language: str,
        profile: TranslationProfile,
        method: str,
    ) -> ProviderBatch:
        first_failure, first_failed_provider = _configuration_failure(profile)
        if first_failure is not None and first_failed_provider is not None:
            self._metrics.error(first_failed_provider.value, 'config_error')

        for index, provider_name in enumerate(profile.providers):
            provider = self._providers.get(provider_name)
            if provider is None:
                failure = TranslationProviderError(
                    provider_name, 'config_incomplete', 'Provider adapter is unavailable'
                )
                self._metrics.error(provider_name.value, 'config_error')
            else:
                started_at = time.monotonic()
                try:
                    translations = provider.translate(contents, target_language, source_language, profile)
                    _validate_provider_output(provider_name, contents, translations)
                except TranslationProviderError as error:
                    failure = error
                    self._metrics.error(provider_name.value, _metric_error(error.reason))
                else:
                    self._metrics.batch(provider_name.value, target_language, len(contents))
                    self._metrics.success(
                        provider_name.value,
                        target_language,
                        method,
                        sum(len(content) for content in contents),
                        len(contents),
                        time.monotonic() - started_at,
                    )
                    if first_failure is not None and first_failed_provider is not None:
                        self._record_fallback(
                            first_failed_provider,
                            provider_name,
                            first_failure.reason,
                            'recovered',
                        )
                    return ProviderBatch(provider=provider_name, translations=tuple(translations))

            if first_failure is None:
                first_failure = failure
                first_failed_provider = provider_name
            if index == len(profile.providers) - 1:
                if first_failed_provider is not None and first_failed_provider != provider_name:
                    self._record_fallback(first_failed_provider, provider_name, first_failure.reason, 'exhausted')
                raise failure

        raise TranslationProviderError(
            TranslationProvider.google, 'config_incomplete', 'No translation provider configured'
        )

    def _record_fallback(
        self,
        from_provider: TranslationProvider,
        to_provider: TranslationProvider,
        reason: str,
        outcome: str,
    ) -> None:
        self._fallback_recorder(
            component='other',
            from_mode=from_provider.value,
            to_mode=to_provider.value,
            reason=reason,
            outcome=outcome,
            log=logger,
        )


def default_provider_chain(
    metrics: TranslationMetrics,
    fallback_recorder: Callable[..., None] = record_fallback,
) -> TranslationProviderChain:
    return TranslationProviderChain(
        providers={
            TranslationProvider.google: GoogleTranslationProvider(),
            TranslationProvider.nllb: NllbTranslationProvider(),
        },
        metrics=metrics,
        fallback_recorder=fallback_recorder,
    )


_default_provider_chain: TranslationProviderChain | None = None
_default_provider_chain_lock = Lock()


def get_default_provider_chain() -> TranslationProviderChain:
    """Return process-scoped lazy provider adapters shared by all sessions."""
    global _default_provider_chain
    if _default_provider_chain is None:
        with _default_provider_chain_lock:
            if _default_provider_chain is None:
                _default_provider_chain = default_provider_chain(get_translation_metrics())
    return _default_provider_chain


def _create_nllb_client(profile: TranslationProfile) -> httpx.Client:
    return httpx.Client(base_url=profile.nllb_url, timeout=profile.nllb_timeout_seconds)


def _detect_nllb_source(contents: list[str]) -> str:
    combined = ' '.join(contents)
    if len(combined) < 20:
        return ''
    detected, _confidence = detect_language_with_confidence(combined, remove_non_lexical=False)
    if not detected:
        return ''
    base = detected.split('-', 1)[0].lower()
    if base not in LANGDETECT_RELIABLE_LANGUAGES or base not in NLLB_SUPPORTED_SOURCE_LANGUAGES:
        return ''
    return detected


def _validate_provider_output(
    provider: TranslationProvider,
    contents: list[str],
    translations: Sequence[object],
) -> None:
    if len(translations) != len(contents):
        raise TranslationProviderError(provider, 'invalid_response', 'Translation response cardinality mismatch')
    for source, translation in zip(contents, translations):
        if not isinstance(translation, ProviderTranslation):
            raise TranslationProviderError(provider, 'invalid_response', 'Translation response item is malformed')
        if not _is_string(translation.text) or not _is_string(translation.detected_language):
            raise TranslationProviderError(provider, 'invalid_response', 'Translation response fields are malformed')
        if source and not translation.text.strip():
            raise TranslationProviderError(provider, 'invalid_response', 'Translation response item is empty')


def _configuration_failure(
    profile: TranslationProfile,
) -> tuple[TranslationProviderError | None, TranslationProvider | None]:
    """Represent a filtered configured primary as the chain's first failure."""
    selected = profile.primary_provider
    unavailable = frozenset(profile.unavailable_tokens)
    for configured in profile.configured_providers:
        if configured == selected:
            return None, None
        if configured.value in unavailable:
            return (
                TranslationProviderError(
                    configured,
                    'config_incomplete',
                    'Configured translation provider is unavailable',
                ),
                configured,
            )
    return None, None


def _is_string(value: object) -> bool:
    return isinstance(value, str)


def _http_reason(status_code: int) -> str:
    if status_code == 429:
        return 'provider_429'
    if status_code >= 500:
        return 'provider_5xx'
    return 'other'


def _metric_error(reason: str) -> str:
    return 'invalid_response' if reason == 'invalid_response' else 'api_error'
