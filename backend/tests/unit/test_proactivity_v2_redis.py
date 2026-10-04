"""V2 Redis authority must not relocate legacy or Vertex reservation state."""

from unittest.mock import Mock

import pytest

from config.proactivity_v2 import AttemptEnvelope, ProactivityDenied
from database import proactivity as ledger
from database import proactivity_budget as money
from database import proactivity_redis as v2
from utils.llm import vertex_reservation_state as vertex


@pytest.fixture(autouse=True)
def isolated_clients(monkeypatch):
    v2._client.cache_clear()
    for key in ('HOST', 'PORT', 'PASSWORD'):
        monkeypatch.delenv(f'PROACTIVITY_REDIS_{key}', raising=False)
    yield
    v2._client.cache_clear()


def bind_v2(monkeypatch):
    monkeypatch.setenv('PROACTIVITY_REDIS_HOST', 'v2.example')
    monkeypatch.setenv('PROACTIVITY_REDIS_PORT', '13151')
    monkeypatch.setenv('PROACTIVITY_REDIS_PASSWORD', 'synthetic-v2')
    monkeypatch.setenv('REDIS_DB_HOST', 'legacy.example')
    monkeypatch.setenv('REDIS_DB_PORT', '12345')
    monkeypatch.setenv('REDIS_DB_PASSWORD', 'synthetic-legacy')


def test_unconfigured_v2_reuses_existing_host_client(monkeypatch):
    normal = object()
    monkeypatch.setattr(v2.redis_db, 'r', normal)
    factory = Mock()
    monkeypatch.setattr(v2.redis, 'Redis', factory)
    assert v2.get_client() is normal
    factory.assert_not_called()


def test_explicit_v2_client_is_lazy_cached_and_does_not_change_normal_client(monkeypatch):
    bind_v2(monkeypatch)
    normal = v2.redis_db.r
    factory = Mock()
    monkeypatch.setattr(v2.redis, 'Redis', factory)
    client = v2.get_client()
    assert v2.get_client() is client
    factory.assert_called_once_with(
        host='v2.example',
        port=13151,
        password='synthetic-v2',
        username='default',
        health_check_interval=30,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
    assert v2.redis_db.r is normal


def test_explicit_v2_never_inherits_legacy_port_or_password(monkeypatch):
    bind_v2(monkeypatch)
    monkeypatch.delenv('PROACTIVITY_REDIS_PORT')
    monkeypatch.delenv('PROACTIVITY_REDIS_PASSWORD')
    factory = Mock()
    monkeypatch.setattr(v2.redis, 'Redis', factory)
    v2.get_client()
    assert factory.call_args.kwargs['port'] == 6379
    assert factory.call_args.kwargs['password'] is None


def test_budget_admission_uses_v2_connection(monkeypatch):
    bind_v2(monkeypatch)
    client = Mock()
    client.set.return_value = False
    factory = Mock(return_value=client)
    monkeypatch.setattr(v2.redis, 'Redis', factory)
    authority = money.BudgetAuthority(firestore_client=object())
    assert authority.redis is client
    with pytest.raises(ProactivityDenied, match='duplicate'):
        authority.reserve(
            uid='synthetic',
            item_id='item',
            producer='conversation_mentor_v2',
            call_id='call',
            envelope=AttemptEnvelope('openai', 'gpt-6-luna', 'gate', 2000, 'hash', 'gate'),
        )
    assert ':admission:' in client.set.call_args.args[0]
    assert factory.call_args.kwargs['host'] == 'v2.example'


def test_push_day_cap_uses_v2_connection(monkeypatch):
    bind_v2(monkeypatch)
    client = Mock()
    client.eval.return_value = 0
    monkeypatch.setattr(v2.redis, 'Redis', Mock(return_value=client))
    with pytest.raises(ProactivityDenied, match='push_limit'):
        ledger.claim_push(uid='synthetic', item_id='a' * 32, firestore_client=Mock())
    assert ':push:' in client.eval.call_args.args[2]


def test_mentor_v2_stamp_uses_v2_connection(monkeypatch):
    bind_v2(monkeypatch)
    client = Mock()
    monkeypatch.setattr(v2.redis, 'Redis', Mock(return_value=client))
    v2.set_mentor_sent_at('synthetic', app_id='mentor', ts=123, ttl=30)
    client.set.assert_called_once_with('synthetic:mentor:proactive_noti_sent_at', 123, ex=30)


def test_vertex_keeps_existing_redis_connection_when_v2_is_configured(monkeypatch):
    bind_v2(monkeypatch)
    factory = Mock()
    monkeypatch.setattr(vertex, 'Redis', factory)
    assert vertex.ReservationState().client() is factory.return_value
    factory.assert_called_once_with(
        host='legacy.example',
        port=12345,
        password='synthetic-legacy',
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        decode_responses=True,
    )


def test_vertex_remains_process_local_without_normal_redis(monkeypatch):
    bind_v2(monkeypatch)
    monkeypatch.delenv('REDIS_DB_HOST')
    factory = Mock()
    monkeypatch.setattr(vertex, 'Redis', factory)
    assert vertex.ReservationState().client() is None
    factory.assert_not_called()


def test_invalid_v2_port_does_not_fall_back_to_legacy_store(monkeypatch):
    bind_v2(monkeypatch)
    monkeypatch.setenv('PROACTIVITY_REDIS_PORT', 'invalid')
    with pytest.raises(ValueError):
        v2.get_client()


def test_v2_connection_failure_denies_budget_without_using_legacy_store(monkeypatch):
    bind_v2(monkeypatch)
    client = Mock()
    client.set.side_effect = ConnectionError('synthetic outage')
    monkeypatch.setattr(v2.redis, 'Redis', Mock(return_value=client))
    normal = Mock()
    monkeypatch.setattr(v2.redis_db, 'r', normal)
    authority = money.BudgetAuthority(firestore_client=object())
    with pytest.raises(ProactivityDenied, match='unavailable'):
        authority.reserve(
            uid='synthetic',
            item_id='item',
            producer='conversation_mentor_v2',
            call_id='call',
            envelope=AttemptEnvelope('openai', 'gpt-6-luna', 'gate', 2000, 'hash', 'gate'),
        )
    normal.set.assert_not_called()
