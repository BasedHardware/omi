"""Exercise the real WebSocket runtime boundary with Redis unavailable."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
import pytest

from config.policy.listen import current_listen_policy, resolve_listen_policy
from routers.listen.contracts import ListenRequest, ListenSessionState
from routers.listen import policy as store
from routers.listen.runtime import ListenSessionRuntime
from utils.stt.live_metrics import WINDOW_CANARY_OUTCOME
import routers.listen.runtime as runtime_module


@pytest.fixture(autouse=True)
def clear_pin():
    token = current_listen_policy.set(None)
    yield
    current_listen_policy.reset(token)


def test_redis_down_socket_reaches_bootstrap_and_pin_is_reset(monkeypatch):
    class Down:
        async def get(self, key):
            raise ConnectionError('unavailable')

    @asynccontextmanager
    async def down_client(injected=None):
        yield Down()

    monkeypatch.setattr(store, '_client', down_client)
    monkeypatch.setattr(ListenSessionRuntime, '_admit', AsyncMock(return_value=True))
    records = []

    async def bootstrap(self):
        policy = await store.initialize_session_policy(self)
        current_listen_policy.set(policy)
        records.append(self.state.policy_source)
        assert current_listen_policy.get() is self.state.listen_policy
        await self.request.websocket.send_json({'proceeded': True, 'source': self.state.policy_source})
        return False

    monkeypatch.setattr(ListenSessionRuntime, '_bootstrap', bootstrap)
    app = FastAPI()

    @app.websocket('/listen')
    async def listen(websocket: WebSocket):
        await websocket.accept()
        runtime = ListenSessionRuntime(
            ListenRequest(websocket, 'owner', client_conversation_id='00000000-0000-4000-8000-000000000001')
        )
        await runtime.run()
        assert current_listen_policy.get() is None
        await websocket.close()

    with TestClient(app) as client, client.websocket_connect('/listen') as websocket:
        assert websocket.receive_json() == {'proceeded': True, 'source': 'fallback'}
    assert records == ['fallback']


def test_session_end_metric_uses_state_outside_context_after_env_flip(monkeypatch):
    policy = resolve_listen_policy('owner', flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100'})
    runtime = object.__new__(ListenSessionRuntime)
    runtime.state = ListenSessionState(listen_policy=policy, live_transcript_delivered=True)
    runtime.request = SimpleNamespace(uid='owner', source='omi', client_conversation_id='conversation')
    runtime.client_device_context = SimpleNamespace(platform='ios')
    runtime.use_custom_stt = False
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    monkeypatch.setattr(runtime_module, 'record_live_session_transcript_outcome', Mock())
    monkeypatch.setattr(runtime_module, 'session_recovery_enabled', lambda _: False)
    record = Mock()
    monkeypatch.setattr(runtime_module, 'record_metric', record)
    runtime._record_session_transcript_outcome()
    window = [c.args for c in record.call_args_list if c.args[0] is WINDOW_CANARY_OUTCOME]
    assert len(window) == 1 and window[0][1]['arm'] == 'window'


@pytest.mark.asyncio
@pytest.mark.parametrize('reconnect_identity', ['conversation', 'rotated-recording'])
async def test_alias_persists_once_without_overwriting_existing(monkeypatch, reconnect_identity):
    policy = resolve_listen_policy('owner', flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100'})
    data = {}

    class Redis:
        async def set(self, key, value, *, nx, ex):
            assert nx and ex == store.POLICY_TTL_SECONDS
            data.setdefault(key, value)

    @asynccontextmanager
    async def client(injected=None):
        yield injected if injected is not None else Redis()

    monkeypatch.setattr(store, '_client', client)
    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        state=ListenSessionState(listen_policy=policy),
        recording_session_id='rotated-recording',
    )
    await store.persist_conversation_policy(host, 'conversation')
    host.state.listen_policy = resolve_listen_policy('owner', flags={})
    await store.persist_conversation_policy(host, 'conversation')
    result, source = await store.load_listen_policy(
        'owner',
        reconnect_identity,
        resolver=lambda: None,
        redis_client=SimpleNamespace(
            get=AsyncMock(return_value=data[store.policy_key('owner', reconnect_identity)]),
            expire=AsyncMock(),
        ),
    )
    assert source == 'redis' and result == policy


@pytest.mark.asyncio
async def test_legacy_reconnect_uses_existing_conversation_before_selection(monkeypatch):
    from datetime import datetime, timezone
    import utils.conversations.process_conversation as processing
    from utils.stt import streaming

    row = {
        'id': 'existing-conversation',
        'source': 'omi',
        'client_device_id': 'device',
        'finished_at': datetime.now(timezone.utc),
        'status': 'in_progress',
    }
    saved = resolve_listen_policy('owner', flags={'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100'})
    read = AsyncMock(return_value=row)
    load = AsyncMock(return_value=(saved, 'redis'))
    monkeypatch.setattr(store, 'load_listen_policy', load)
    host = SimpleNamespace(
        client_conversation_id=None,
        recording_session_id='new-socket-id',
        is_multi_channel=False,
        request=SimpleNamespace(uid='owner', source='omi', onboarding_mode=False, conversation_timeout=120),
        client_device_context=SimpleNamespace(client_device_id='device'),
        persistence=SimpleNamespace(call=read),
        state=ListenSessionState(),
    )
    result = await store.initialize_session_policy(host)
    assert result is saved and host.state.policy_source == 'redis'
    assert load.call_args.args == ('owner', 'existing-conversation')
    assert host._policy_resume_candidate is row
    read.assert_awaited_once_with(processing.retrieve_in_progress_conversation, 'owner')
