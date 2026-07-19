from __future__ import annotations

from typing import Any

import httpx
import pytest
from google.cloud import translate_v3

from config.translation import TranslationProvider, resolve_translation_profile
from tests.unit.translation_test_support import (
    DictTranslationStore,
    FakeProvider,
    FallbackRecorder,
    build_service,
    profile,
    provider_error,
    translations,
)
from utils.translation import TranslationService, TranslationStatus
from utils.translation_core.cache import TranslationCache
from utils.translation_core.metrics import NoopTranslationMetrics
from utils.translation_core.providers import (
    GoogleTranslationProvider,
    NllbTranslationProvider,
    TranslationProviderChain,
    TranslationProviderError,
)


def test_config_preserves_exact_ordered_provider_policy():
    nllb_only = resolve_translation_profile(
        {'TRANSLATION_SERVICE_MODELS': 'nllb', 'HOSTED_TRANSLATION_API_URL': 'http://nllb'}
    )
    nllb_google = resolve_translation_profile(
        {'TRANSLATION_SERVICE_MODELS': 'nllb,google', 'HOSTED_TRANSLATION_API_URL': 'http://nllb'}
    )
    google_nllb = resolve_translation_profile(
        {'TRANSLATION_SERVICE_MODELS': 'google,nllb', 'HOSTED_TRANSLATION_API_URL': 'http://nllb'}
    )

    assert nllb_only.providers == (TranslationProvider.nllb,)
    assert nllb_google.providers == (TranslationProvider.nllb, TranslationProvider.google)
    assert google_nllb.providers == (TranslationProvider.google, TranslationProvider.nllb)


def test_config_filters_unavailable_and_records_unsupported_tokens():
    resolved = resolve_translation_profile({'TRANSLATION_SERVICE_MODELS': 'unknown,nllb'})

    assert resolved.providers == (TranslationProvider.google,)
    assert resolved.configured_providers == (TranslationProvider.nllb,)
    assert resolved.unsupported_tokens == ('unknown',)
    assert resolved.unavailable_tokens == ('nllb',)


def test_empty_config_defaults_to_google():
    assert resolve_translation_profile({}).providers == (TranslationProvider.google,)


def test_filtered_configured_primary_records_recovered_fallback_after_google_succeeds():
    recorder = FallbackRecorder()
    resolved = resolve_translation_profile({'TRANSLATION_SERVICE_MODELS': 'nllb,google'})
    google = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service(
        {TranslationProvider.google: google},
        selected_profile=resolved,
        recorder=recorder,
    )

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert recorder.events[0].fields['from_mode'] == 'nllb'
    assert recorder.events[0].fields['to_mode'] == 'google'
    assert recorder.events[0].fields['reason'] == 'config_incomplete'
    assert recorder.events[0].fields['outcome'] == 'recovered'


def test_filtered_configured_primary_records_exhausted_when_google_fails():
    recorder = FallbackRecorder()
    resolved = resolve_translation_profile({'TRANSLATION_SERVICE_MODELS': 'nllb,google'})
    google = FakeProvider(
        TranslationProvider.google,
        responses=[provider_error(TranslationProvider.google)],
    )
    service, _cache = build_service(
        {TranslationProvider.google: google},
        selected_profile=resolved,
        recorder=recorder,
    )

    outcome = service.translate_outcomes('es', [('segment', 'Hello')])[0]

    assert outcome.status == TranslationStatus.failed
    assert recorder.events[0].fields['reason'] == 'config_incomplete'
    assert recorder.events[0].fields['outcome'] == 'exhausted'


def test_config_normalizes_case_whitespace_and_duplicate_providers():
    resolved = resolve_translation_profile(
        {
            'TRANSLATION_SERVICE_MODELS': ' NLLB, google, nllb, GOOGLE ',
            'HOSTED_TRANSLATION_API_URL': ' http://nllb ',
        }
    )

    assert resolved.providers == (TranslationProvider.nllb, TranslationProvider.google)
    assert resolved.nllb_url == 'http://nllb'


@pytest.mark.parametrize(
    ('name', 'value', 'message'),
    [
        ('TRANSLATION_NLLB_TIMEOUT_SECONDS', '0', 'must be greater than zero'),
        ('TRANSLATION_NLLB_TIMEOUT_SECONDS', 'invalid', 'must be a number'),
        ('TRANSLATION_CACHE_TTL', '-1', 'must be greater than zero'),
        ('TRANSLATION_NEGATIVE_CACHE_TTL', '1.5', 'must be an integer'),
    ],
)
def test_invalid_numeric_config_fails_at_the_call_boundary(name, value, message):
    with pytest.raises(ValueError, match=message):
        resolve_translation_profile({name: value})


def test_nllb_failure_recovers_through_google_with_shared_fallback_event():
    recorder = FallbackRecorder()
    nllb = FakeProvider(
        TranslationProvider.nllb,
        responses=[provider_error(TranslationProvider.nllb, 'timeout')],
    )
    google = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service(
        {TranslationProvider.nllb: nllb, TranslationProvider.google: google},
        selected_profile=profile((TranslationProvider.nllb, TranslationProvider.google)),
        recorder=recorder,
    )

    outcomes = service.translate_outcomes('es', [('segment', 'Hello')])

    assert outcomes[0].text == 'Hola'
    assert recorder.events[0].fields['from_mode'] == 'nllb'
    assert recorder.events[0].fields['to_mode'] == 'google'
    assert recorder.events[0].fields['reason'] == 'timeout'
    assert recorder.events[0].fields['outcome'] == 'recovered'


def test_nllb_only_failure_does_not_invent_google_fallback():
    recorder = FallbackRecorder()
    nllb = FakeProvider(
        TranslationProvider.nllb,
        responses=[provider_error(TranslationProvider.nllb)],
    )
    service, _cache = build_service(
        {TranslationProvider.nllb: nllb},
        selected_profile=profile((TranslationProvider.nllb,)),
        recorder=recorder,
    )

    outcomes = service.translate_outcomes('es', [('segment', 'Hello')])

    assert outcomes[0].status == TranslationStatus.failed
    assert recorder.events == []


def test_exhausted_provider_chain_records_truthful_outcome():
    recorder = FallbackRecorder()
    store = DictTranslationStore()
    nllb = FakeProvider(
        TranslationProvider.nllb,
        responses=[provider_error(TranslationProvider.nllb, 'provider_5xx')],
    )
    google = FakeProvider(
        TranslationProvider.google,
        responses=[provider_error(TranslationProvider.google)],
    )
    service, _cache = build_service(
        {TranslationProvider.nllb: nllb, TranslationProvider.google: google},
        selected_profile=profile((TranslationProvider.nllb, TranslationProvider.google)),
        store=store,
        recorder=recorder,
    )

    outcomes = service.translate_outcomes('es', [('segment', 'Hello')])

    assert outcomes[0].status == TranslationStatus.failed
    assert outcomes[0].text == 'Hello'
    assert store.puts == []
    assert recorder.events[0].fields['outcome'] == 'exhausted'
    assert recorder.events[0].fields['from_mode'] == 'nllb'
    assert recorder.events[0].fields['to_mode'] == 'google'


def test_google_first_can_recover_through_nllb_when_configured():
    recorder = FallbackRecorder()
    google = FakeProvider(
        TranslationProvider.google,
        responses=[provider_error(TranslationProvider.google)],
    )
    nllb = FakeProvider(TranslationProvider.nllb, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service(
        {TranslationProvider.google: google, TranslationProvider.nllb: nllb},
        selected_profile=profile((TranslationProvider.google, TranslationProvider.nllb)),
        recorder=recorder,
    )

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert recorder.events[0].fields['from_mode'] == 'google'
    assert recorder.events[0].fields['to_mode'] == 'nllb'


def test_invalid_primary_response_recovers_through_configured_fallback():
    recorder = FallbackRecorder()
    nllb = FakeProvider(TranslationProvider.nllb, responses=[[]])
    google = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service(
        {TranslationProvider.nllb: nllb, TranslationProvider.google: google},
        selected_profile=profile((TranslationProvider.nllb, TranslationProvider.google)),
        recorder=recorder,
    )

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert recorder.events[0].fields['reason'] == 'invalid_response'
    assert recorder.events[0].fields['outcome'] == 'recovered'


def test_missing_primary_adapter_recovers_without_changing_config_order():
    recorder = FallbackRecorder()
    google = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service(
        {TranslationProvider.google: google},
        selected_profile=profile((TranslationProvider.nllb, TranslationProvider.google)),
        recorder=recorder,
    )

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert recorder.events[0].fields['from_mode'] == 'nllb'
    assert recorder.events[0].fields['reason'] == 'config_incomplete'


def test_profile_is_resolved_at_each_call_boundary(monkeypatch):
    metrics = NoopTranslationMetrics()
    google = FakeProvider(TranslationProvider.google, responses=[translations(('Google result', 'en'))])
    nllb = FakeProvider(TranslationProvider.nllb, responses=[translations(('NLLB result', 'en'))])
    chain = TranslationProviderChain(
        providers={TranslationProvider.google: google, TranslationProvider.nllb: nllb},
        metrics=metrics,
        fallback_recorder=FallbackRecorder(),
    )
    service = TranslationService(
        cache=TranslationCache(persistent=None, metrics=metrics),
        provider_chain=chain,
        metrics=metrics,
    )

    monkeypatch.setenv('TRANSLATION_SERVICE_MODELS', 'nllb')
    monkeypatch.setenv('HOSTED_TRANSLATION_API_URL', 'http://nllb')
    assert service.translate_text('es', 'First') == ('NLLB result', 'en')

    monkeypatch.setenv('TRANSLATION_SERVICE_MODELS', 'google')
    assert service.translate_text('es', 'Second') == ('Google result', 'en')
    assert len(nllb.calls) == 1
    assert len(google.calls) == 1


class FakeResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.request = httpx.Request('POST', 'http://nllb.test/v1/translate')

    def json(self) -> object:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError('provider failed', request=self.request, response=self.to_response())

    def to_response(self) -> httpx.Response:
        return httpx.Response(self.status_code, request=self.request)


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, path: str, json: dict[str, Any]) -> FakeResponse:
        self.calls.append((path, json))
        return self.response

    def close(self) -> None:
        return None


def test_nllb_adapter_validates_and_maps_response_without_network():
    client = FakeHttpClient(
        FakeResponse({'translations': [{'translated_text': 'Hola', 'detected_language_code': 'en'}]})
    )
    provider = NllbTranslationProvider(client_factory=lambda _profile: client)

    results = provider.translate(['Hello'], 'es', 'en', profile((TranslationProvider.nllb,)))

    assert results == translations(('Hola', 'en'))
    assert client.calls == [
        (
            '/v1/translate',
            {
                'contents': ['Hello'],
                'target_language_code': 'es',
                'source_language_code': 'en',
            },
        )
    ]


@pytest.mark.parametrize(
    ('status_code', 'reason'),
    [(429, 'provider_429'), (503, 'provider_5xx'), (400, 'other')],
)
def test_nllb_adapter_classifies_http_failures(status_code, reason):
    client = FakeHttpClient(FakeResponse({}, status_code=status_code))
    provider = NllbTranslationProvider(client_factory=lambda _profile: client)

    with pytest.raises(TranslationProviderError) as raised:
        provider.translate(['Hello'], 'es', 'en', profile((TranslationProvider.nllb,)))

    assert raised.value.reason == reason


@pytest.mark.parametrize(
    'body',
    [None, {}, {'translations': None}, {'translations': ['bad-item']}, {'translations': [{'translated_text': 3}]}],
)
def test_nllb_adapter_rejects_malformed_payloads(body):
    provider = NllbTranslationProvider(client_factory=lambda _profile: FakeHttpClient(FakeResponse(body)))

    with pytest.raises(TranslationProviderError, match='response|item|fields') as raised:
        provider.translate(['Hello'], 'es', 'en', profile((TranslationProvider.nllb,)))

    assert raised.value.reason == 'invalid_response'


def test_nllb_adapter_detects_supported_source_only_when_not_supplied(monkeypatch):
    client = FakeHttpClient(
        FakeResponse({'translations': [{'translated_text': 'Hello', 'detected_language_code': 'fr'}]})
    )
    provider = NllbTranslationProvider(client_factory=lambda _profile: client)
    monkeypatch.setattr(
        'utils.translation_core.providers.detect_language_with_confidence',
        lambda *_args, **_kwargs: ('fr', 0.99),
    )

    provider.translate(
        ['Bonjour, ceci est une phrase suffisamment longue.'],
        'en',
        '',
        profile((TranslationProvider.nllb,)),
    )

    assert client.calls[0][1]['source_language_code'] == 'fr'


class FakeGoogleClient:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def translate_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_google_adapter_maps_request_and_response_without_network():
    # The real proto-plus response exposes RepeatedComposite, not a list.
    response = translate_v3.TranslateTextResponse(translations=[translate_v3.Translation(translated_text='Hola')])
    client = FakeGoogleClient(response)
    provider = GoogleTranslationProvider(client_factory=lambda: client)

    result = provider.translate(['Hello'], 'es', 'en', profile())

    assert result == translations(('Hola', ''))
    assert client.calls == [
        {
            'contents': ['Hello'],
            'parent': 'projects/test-project/locations/global',
            'mime_type': 'text/plain',
            'target_language_code': 'es',
            'source_language_code': 'en',
        }
    ]


def test_google_adapter_wraps_sdk_failures_as_typed_provider_errors():
    provider = GoogleTranslationProvider(client_factory=lambda: FakeGoogleClient(error=RuntimeError('boom')))

    with pytest.raises(TranslationProviderError) as raised:
        provider.translate(['Hello'], 'es', 'en', profile())

    assert raised.value.provider == TranslationProvider.google
    assert raised.value.reason == 'other'
