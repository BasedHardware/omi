"""Receiver integration for the opt-in single authority; legacy remains default."""

import asyncio
from types import SimpleNamespace

import pytest

from routers.listen import provider_routing as adapter
from routers.listen.receiver import ListenReceiver
from utils.stt.streaming import STTService


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(adapter, 'get_byok_keys', lambda: {})
    monkeypatch.setenv('STT_SERVICE_MODELS', 'soniox,dg-nova-3,modulate-velma-2')
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.delenv('STT_ROUTING_POLICY_JSON', raising=False)
    return SimpleNamespace(
        language='en',
        stt_language='en',
        multi_lang_enabled=False,
        is_multi_channel=False,
        use_custom_stt=False,
        vocabulary=[],
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        stt_service=STTService.modulate,
        stt_model='velma-2',
    )


@pytest.mark.parametrize('mode', ['', 'legacy', 'bad-value'])
def test_default_does_not_construct_health_or_replace_legacy(host, monkeypatch, mode):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setattr(adapter, 'health_store', lambda namespace: pytest.fail('legacy touched health'))
    assert adapter.routing_for_listen(host) is None


@pytest.mark.parametrize('field', ['is_multi_channel', 'use_custom_stt'])
def test_unmigrated_surfaces_keep_legacy_path(host, monkeypatch, field):
    monkeypatch.setenv('STT_ROUTING_MODE', 'ordered')
    setattr(host, field, True)
    assert adapter.routing_for_listen(host) is None


def test_byok_never_uses_shared_managed_health(host, monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'health')
    monkeypatch.setattr(adapter, 'get_byok_keys', lambda: {'soniox': 'test'})
    assert adapter.routing_for_listen(host) is None


@pytest.mark.parametrize('policy', ['null', '[]', '[{"token":"soniox","priority":"bad"}]', 'bad-json'])
def test_bad_policy_fails_open_to_config_order(host, monkeypatch, policy):
    monkeypatch.setenv('STT_ROUTING_MODE', 'ordered')
    monkeypatch.setenv('STT_ROUTING_POLICY_JSON', policy)
    route = adapter.routing_for_listen(host)
    assert [item.service for item in route.route.candidates] == ['soniox', 'deepgram', 'modulate']


@pytest.mark.anyio
async def test_receiver_connect_and_replacement_share_ranked_list(host, monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'ordered')
    attempts, callbacks, content = [], {}, []

    class Socket:
        is_connection_dead = False
        typed_death_reason = None

        def finish(self):
            self.finished = True

    def connector(service):
        async def connect(callback, *args, **kwargs):
            attempts.append(service)
            callbacks[service] = callback
            return Socket()

        return connect

    monkeypatch.setattr(adapter, 'process_audio_soniox', connector('soniox'))
    monkeypatch.setattr(adapter, 'process_audio_dg', connector('deepgram'))
    host.provider_routing = adapter.routing_for_listen(host)
    receiver = ListenReceiver(host, [], {})
    receiver.stt_socket = await receiver._create_stt_socket(content.extend, 16000, content.extend)
    assert host.stt_service == STTService.soniox
    dead = receiver.stt_socket
    dead.is_connection_dead = True
    await asyncio.gather(receiver._failover_stt_socket(), receiver._failover_stt_socket())
    assert attempts == ['soniox', 'deepgram']
    assert receiver.stt_socket is not dead and dead.finished
    callbacks['deepgram']([{'text': 'serving'}])
    assert content == [{'text': 'serving', 'stt_provider': 'deepgram'}]


def test_invalid_redis_configuration_still_returns_the_ordered_route(host, monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'health')
    monkeypatch.setenv('STT_HEALTH_NAMESPACE', 'test:managed:streaming')

    def invalid_client(namespace):
        raise ValueError('invalid port')

    monkeypatch.setattr(adapter, 'health_store', invalid_client)
    routing = adapter.routing_for_listen(host)
    assert routing.route.health is None
    assert routing.route.next_candidate().service == 'soniox'
