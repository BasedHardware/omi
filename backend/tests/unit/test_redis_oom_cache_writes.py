"""Cache fills must not turn Redis saturation into failed product requests."""

import logging
from unittest.mock import Mock

import fakeredis
import pytest
from redis.exceptions import OutOfMemoryError, RedisError, ResponseError

from database import redis_db
from config.translation import TranslationProfile
from utils.observability import fallback
from utils.translation_core.cache import CachedTranslation, RedisTranslationStore, TranslationCache
from utils.translation_core.engine import TranslationEngine, TranslationStatus
from utils.translation_core.metrics import NoopTranslationMetrics
from utils.translation_core.planner import TranslationMode, TranslationUnit
from utils.translation_core.providers import ProviderBatch, ProviderTranslation, TranslationProvider

CACHE_WRITES = [
    (redis_db.set_generic_cache, ('path', {'ok': True}, 60)),
    (redis_db.set_app_cache_by_id, ('app', {'id': 'app'})),
    (redis_db.set_app_usage_count_cache, ('app', 5)),
    (redis_db.set_app_money_made_amount_cache, ('app', 1.5)),
    (redis_db.set_app_usage_history_cache, ('app', [{'count': 5}])),
    (redis_db.set_app_money_made_cache, ('app', {'amount': 1.5})),
    (redis_db.cache_signed_url, ('blob', 'https://example.test/signed')),
    (redis_db.set_user_data_protection_level, ('uid', 'standard')),
    (redis_db.set_speech_profile_duration, ('uid', 12.5)),
]


@pytest.fixture
def recorded(monkeypatch):
    events = []
    monkeypatch.setattr(fallback, 'record_fallback', lambda **kwargs: events.append(kwargs))
    return events


@pytest.mark.parametrize('write,args', CACHE_WRITES)
def test_cache_fills_skip_oom_with_telemetry(monkeypatch, caplog, recorded, write, args):
    client = fakeredis.FakeRedis()
    rejected = Mock(side_effect=OutOfMemoryError("command not allowed when used memory > 'maxmemory'"))
    monkeypatch.setattr(client, 'set', rejected)
    monkeypatch.setattr(redis_db, 'r', client)

    with caplog.at_level(logging.WARNING):
        assert write(*args) is None

    rejected.assert_called_once()
    assert 'redis cache write skipped reason=capacity_full' in caplog.text
    assert len(recorded) == 1
    assert recorded[0]['reason'] == 'capacity_full'
    assert recorded[0]['from_mode'] == 'cache_write'
    assert recorded[0]['to_mode'] == 'skip'
    assert recorded[0]['outcome'] == 'degraded'
    assert client.dbsize() == 0


@pytest.mark.parametrize('error_type', [RedisError, OutOfMemoryError])
@pytest.mark.parametrize('negative', [False, True])
def test_translation_writes_skip_redis_errors(monkeypatch, caplog, recorded, error_type, negative):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(client, 'set', Mock(side_effect=error_type('unavailable')))
    store = RedisTranslationStore(lambda: client)
    with caplog.at_level(logging.WARNING):
        if negative:
            assert store.put_negative('fingerprint', 'en', 60) is None
        else:
            assert store.put('fingerprint', 'en', CachedTranslation('Hello', 'es'), 60) is None
    assert store.get('fingerprint', 'en') is None
    assert store.is_negative('fingerprint', 'en') is False
    assert 'translation cache write skipped reason=' in caplog.text
    assert len(recorded) == 1
    assert recorded[0]['reason'] == ('capacity_full' if error_type is OutOfMemoryError else 'other')
    assert recorded[0]['outcome'] == 'degraded'


@pytest.mark.parametrize('error_type', [RedisError, OutOfMemoryError])
def test_translation_caller_returns_result_after_failed_cache_fill(monkeypatch, recorded, error_type):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(client, 'set', Mock(side_effect=error_type('unavailable')))
    store = RedisTranslationStore(lambda: client)
    cache = TranslationCache(store, NoopTranslationMetrics())
    profile = TranslationProfile(
        providers=(TranslationProvider.google,),
        nllb_url='',
        nllb_timeout_seconds=1,
        cache_ttl_seconds=60,
        negative_cache_ttl_seconds=60,
    )
    providers = Mock()
    providers.translate.return_value = ProviderBatch(
        provider=TranslationProvider.google,
        translations=(ProviderTranslation('Hello my friend.', 'es'),),
    )
    engine = TranslationEngine(cache, providers, lambda: profile)
    units = [TranslationUnit(ordinal=0, unit_id='unit', text='Hola mi amigo.')]

    outcome = engine.translate(units, 'en', mode=TranslationMode.whole_text)[0]
    assert outcome.status == TranslationStatus.translated
    assert outcome.text == 'Hello my friend.'
    assert recorded
    # This session retains its LRU result. A fresh session misses Redis and can recompute.
    cache.clear_memory()
    assert engine.translate(units, 'en', mode=TranslationMode.whole_text)[0].text == outcome.text
    assert providers.translate.call_count == 2


def test_cache_success_preserves_payload_and_ttl(monkeypatch, recorded):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(redis_db, 'r', client)
    redis_db.set_app_usage_count_cache('app', 5)
    assert redis_db.get_app_usage_count_cache('app') == 5
    assert 899 <= client.ttl('apps:app:usage_count') <= 900
    redis_db.set_speech_profile_duration('uid', 12.5)
    assert redis_db.get_speech_profile_duration('uid') == 12.5
    assert client.ttl('users:uid:speech_profile_duration') == -1
    assert recorded == []


def test_unrelated_response_errors_still_raise(monkeypatch):
    client = Mock()
    client.set.side_effect = ResponseError('ERR syntax')
    monkeypatch.setattr(redis_db, 'r', client)
    with pytest.raises(ResponseError):
        redis_db.cache_signed_url('blob', 'url')


def test_cache_oom_survives_telemetry_failure(monkeypatch):
    client = Mock()
    client.set.side_effect = OutOfMemoryError('full')
    monkeypatch.setattr(redis_db, 'r', client)
    monkeypatch.setattr(fallback, 'record_fallback', Mock(side_effect=RuntimeError('metrics unavailable')))
    assert redis_db.cache_signed_url('blob', 'url') is None
    assert RedisTranslationStore(lambda: client).put_negative('fingerprint', 'en', 60) is None


def test_app_review_cache_oom_still_propagates(monkeypatch):
    # Strict by design: the review cache is the read model for app reviews, so
    # OOM (and every other RedisError) must keep raising — never skip silently.
    client = Mock()
    rejected = Mock(side_effect=OutOfMemoryError("command not allowed when used memory > 'maxmemory'"))
    monkeypatch.setattr(redis_db, '_SET_APP_REVIEW_CACHE_LUA', rejected)
    with pytest.raises(OutOfMemoryError):
        redis_db.set_app_review_cache('app', 'uid', {'score': 5})
    rejected.assert_called_once()
