from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
import redis

from config.translation import TranslationProvider
from tests.unit.translation_test_support import (
    DictTranslationStore,
    FakeProvider,
    build_service,
    profile,
    provider_error,
    translations,
)
from utils.translation import TranslationStatus
from utils.translation_core.cache import CachedTranslation, RedisTranslationStore, TranslationCache
from utils.translation_core.metrics import NoopTranslationMetrics
from utils.translation_core.planner import fingerprint_text
from utils.translation_core.providers import ProviderTranslation


@pytest.mark.parametrize(
    'provider_response',
    [
        [],
        translations(('Uno.', 'en'), ('Dos.', 'en'), ('Tres.', 'en')),
        [object(), object()],
        [
            ProviderTranslation(text=123, detected_language='en'),  # type: ignore[arg-type]
            ProviderTranslation(text='Dos.', detected_language='en'),
        ],
        [
            ProviderTranslation(text='Uno.', detected_language=None),  # type: ignore[arg-type]
            ProviderTranslation(text='Dos.', detected_language='en'),
        ],
        [
            ProviderTranslation(text='', detected_language='en'),
            ProviderTranslation(text='Dos.', detected_language='en'),
        ],
        [
            ProviderTranslation(text='   ', detected_language='en'),
            ProviderTranslation(text='Dos.', detected_language='en'),
        ],
    ],
    ids=[
        'truncated',
        'extra',
        'malformed-item',
        'non-string-text',
        'non-string-language',
        'empty-item',
        'blank-item',
    ],
)
def test_invalid_provider_response_fails_every_affected_unit_without_cache_writes(provider_response):
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[provider_response])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)

    outcomes = service.translate_outcomes('es', [('one', 'One.'), ('two', 'Two.')])

    assert [outcome.status for outcome in outcomes] == [TranslationStatus.failed, TranslationStatus.failed]
    assert [outcome.text for outcome in outcomes] == ['One.', 'Two.']
    assert store.puts == []


def test_successful_early_chunk_is_not_cached_when_later_chunk_fails():
    store = DictTranslationStore()
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[
            translations(('Uno.', 'en')),
            provider_error(TranslationProvider.google),
        ],
    )
    service, _cache = build_service(
        {TranslationProvider.google: provider},
        selected_profile=profile(max_batch_size=1),
        store=store,
    )

    outcomes = service.translate_outcomes('es', [('one', 'One.'), ('two', 'Two.')])

    assert [outcome.status for outcome in outcomes] == [TranslationStatus.failed, TranslationStatus.failed]
    assert store.puts == []
    assert store.values == {}


class FailingRedis:
    def get(self, key):
        raise redis.exceptions.ConnectionError('down')

    def exists(self, key):
        raise redis.exceptions.ConnectionError('down')

    def set(self, key, value, **kwargs):
        raise redis.exceptions.ConnectionError('down')


class BrokenRedisClient:
    def get(self, key):
        raise TypeError('client programming error')


class InterleavingMemory(OrderedDict[str, CachedTranslation]):
    """Expose the old pop/reinsert race deterministically."""

    def __init__(self, values: OrderedDict[str, CachedTranslation]) -> None:
        super().__init__(values)
        self.first_removed = Event()
        self.second_attempted = Event()
        self._pop_count = 0
        self._count_lock = Lock()

    def pop(self, key, default=None):
        with self._count_lock:
            self._pop_count += 1
            pop_index = self._pop_count
        value = super().pop(key, default)
        if pop_index == 1:
            self.first_removed.set()
            self.second_attempted.wait(timeout=0.2)
        else:
            self.second_attempted.set()
        return value


def test_redis_outage_fails_open_and_memory_cache_remains_usable():
    metrics = NoopTranslationMetrics()
    persistent = RedisTranslationStore(client_factory=FailingRedis)
    cache = TranslationCache(persistent=persistent, metrics=metrics)
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _ignored = build_service({TranslationProvider.google: provider}, cache=cache)

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert len(provider.calls) == 1


@pytest.mark.parametrize('error_type', [ValueError, TypeError])
def test_redis_client_construction_errors_fail_open_without_hiding_provider_result(error_type):
    def raising_factory():
        raise error_type('invalid Redis configuration')

    cache = TranslationCache(
        persistent=RedisTranslationStore(client_factory=raising_factory),
        metrics=NoopTranslationMetrics(),
    )
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _ignored = build_service({TranslationProvider.google: provider}, cache=cache)

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert len(provider.calls) == 1


def test_redis_store_does_not_hide_unexpected_programming_errors():
    def raising_factory():
        raise RuntimeError('programming error')

    store = RedisTranslationStore(client_factory=raising_factory)

    with pytest.raises(RuntimeError, match='programming error'):
        store.get('fingerprint', 'es')

    broken_client_store = RedisTranslationStore(client_factory=BrokenRedisClient)
    with pytest.raises(TypeError, match='client programming error'):
        broken_client_store.get('fingerprint', 'es')


def test_negative_cache_uses_same_fingerprint_policy_as_positive_cache():
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)
    fingerprint = fingerprint_text('Already English')
    service.set_negative_cache(fingerprint, 'en')

    outcomes = service.translate_outcomes('en', [('segment', 'Already English')])

    assert outcomes[0].status == TranslationStatus.unchanged
    assert outcomes[0].detected_language == 'en'
    assert provider.calls == []


def test_cached_and_failed_units_never_form_a_partial_mixed_translation():
    store = DictTranslationStore()
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[provider_error(TranslationProvider.google)],
    )
    service, cache = build_service({TranslationProvider.google: provider}, store=store)
    active_profile = profile()
    cache.put(fingerprint_text('Cached.'), 'fr', CachedTranslation('En cache.', 'en'), active_profile)
    outcomes = service.translate_outcomes('fr', [('unit', 'Cached. Missing.')])

    assert outcomes[0].status == TranslationStatus.failed
    assert outcomes[0].text == 'Cached. Missing.'


def test_invalid_response_does_not_poison_memory_and_is_retried():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[[], translations(('Hola', 'en'))],
    )
    service, _cache = build_service({TranslationProvider.google: provider})

    assert service.translate_outcomes('es', [('segment', 'Hello')])[0].status == TranslationStatus.failed
    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert len(provider.calls) == 2


def test_lru_eviction_is_bounded_and_evicted_text_is_retried():
    cache = TranslationCache(persistent=None, metrics=NoopTranslationMetrics(), max_entries=1)
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[
            translations(('Uno', 'en')),
            translations(('Dos', 'en')),
            translations(('Uno otra vez', 'en')),
        ],
    )
    service, _ignored = build_service({TranslationProvider.google: provider}, cache=cache)

    assert service.translate_text('es', 'One') == ('Uno', 'en')
    assert service.translate_text('es', 'Two') == ('Dos', 'en')
    assert service.translate_text('es', 'One') == ('Uno otra vez', 'en')
    assert len(provider.calls) == 3


def test_concurrent_lru_hits_cannot_observe_the_pop_reinsert_window():
    cache = TranslationCache(persistent=None, metrics=NoopTranslationMetrics())
    expected = CachedTranslation('Hola', 'en')
    cache.put('fingerprint', 'es', expected, profile())
    cache._memory = InterleavingMemory(cache._memory)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(cache.get, 'fingerprint', 'es')
        assert cache._memory.first_removed.wait(timeout=1.0)
        second = executor.submit(cache.get, 'fingerprint', 'es')
        assert [first.result(timeout=1.0), second.result(timeout=1.0)] == [expected, expected]


class RecordingRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.sets: list[tuple[str, object, int]] = []

    def get(self, key):
        return self.values.get(key)

    def exists(self, key):
        return key in self.values

    def set(self, key, value, *, ex):
        self.values[key] = value
        self.sets.append((key, value, ex))


def test_redis_store_uses_compatible_keys_payloads_and_ttls():
    client = RecordingRedis()
    store = RedisTranslationStore(client_factory=lambda: client)
    value = CachedTranslation('Hola', 'en')

    store.put('fingerprint', 'es', value, ttl_seconds=600)
    store.put_negative('fingerprint', 'es', ttl_seconds=300)

    assert store.get('fingerprint', 'es') == value
    assert store.is_negative('fingerprint', 'es')
    assert client.sets[0][0] == 'translate:v1:fingerprint:es'
    assert client.sets[0][2] == 600
    assert client.sets[1] == ('translate:v2:neg:fingerprint:es', '1', 300)


@pytest.mark.parametrize(
    'raw',
    ['not-json', '[]', '{"text": 3}', '{"text": "   ", "detected_lang": "en"}', b'\xff'],
)
def test_malformed_redis_payload_is_a_cache_miss(raw):
    client = RecordingRedis()
    client.values['translate:v1:fingerprint:es'] = raw
    store = RedisTranslationStore(client_factory=lambda: client)

    assert store.get('fingerprint', 'es') is None
