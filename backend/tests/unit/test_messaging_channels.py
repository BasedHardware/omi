"""Channel foundation contracts using only in-process stores, adapters and providers."""

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest
from langchain_core.tools import StructuredTool
from testing.messaging.adapter_contract import AdapterContract
from testing.messaging.loopback import LoopbackAdapter, ScriptedProvider
from testing.messaging.store import MemoryStore
from utils.llm.shaped_agent import Mount, Budget, Turn, run_loop
from utils.messaging.contracts import Principal, ReentryEvent
from utils.messaging.projection import ToolProjection
from utils.messaging.gateway import Gateway
from utils.messaging import history


@pytest.fixture
def adapter():
    return LoopbackAdapter()


@pytest.fixture
def signed_message(adapter):
    return adapter.signed


class TestLoopbackContract(AdapterContract):
    pass


def test_projection_advertises_and_executes_surface_tool_and_scopes_principals():
    calls = []

    async def send_file(name: str) -> str:
        """Deliver a file to this surface."""
        calls.append(name)
        return 'sent'

    surface = StructuredTool.from_function(coroutine=send_file)
    device = replace_tool_name(surface, 'device_only')
    principal = Principal('u', frozenset({'send_file'}), datetime.now(timezone.utc) + timedelta(minutes=2), 'task')
    projection = ToolProjection.build((device,), (surface,), (), device_names={'device_only'}, principal=principal)
    assert set(projection.registry) == {'send_file'}
    provider = ScriptedProvider(
        Turn(tool_calls=({'name': 'send_file', 'args': {'name': 'report'}},)), Turn(value='done')
    )

    async def execute(calls):
        result = await projection.authorize('u', calls[0]['name']).ainvoke(calls[0]['args'])
        return [{'role': 'tool', 'content': result}]

    result = asyncio.run(
        run_loop(Mount(tools=tuple(projection.registry), budget=Budget(turns=2, tool_calls=1)), [], provider, execute)
    )
    assert result.value == 'done' and calls == ['report']
    for uid, tool in [('other', 'send_file'), ('u', 'device_only'), ('u', 'unknown')]:
        with pytest.raises(PermissionError):
            projection.authorize(uid, tool)
    with pytest.raises(PermissionError):
        replace(principal, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)).authorize('u', 'send_file')


def replace_tool_name(tool, name):
    return tool.model_copy(update={'name': name})


def test_all_core_tools_are_in_projection():
    from utils.retrieval.agentic import CORE_TOOLS

    projection = ToolProjection.build(CORE_TOOLS, (), (), principal=Principal('u'))
    assert set(projection.registry) == {t.name for t in CORE_TOOLS}


def test_digest_append_only_and_byte_prefix_stable(monkeypatch):
    store = MemoryStore()
    session = {'id': 'session'}
    store.append_event(
        'u',
        'session',
        {'id': 'old', 'at': '2026-01-01T00:00:00+00:00', 'role': 'user', 'content': 'unchanged earlier request'},
    )
    old = store.events('u', 'session')
    rows = [
        {
            'id': 'other',
            'chat_session_id': 'elsewhere',
            'text': 'verbatim activity',
            'sender': 'human',
            'created_at': datetime.now(timezone.utc),
        }
    ]
    monkeypatch.setattr(history, 'recent_activity', lambda uid: rows)
    mount = Mount(instructions='stable', skills=('channel skill',), cache_breakpoint=True)
    before = mount.messages([{'role': e['role'], 'content': e['content']} for e in old])
    asyncio.run(history.append_digest(store, 'u', session, old))
    current = store.events('u', 'session')
    after = mount.messages([{'role': e['role'], 'content': e['content']} for e in current])
    assert json.dumps(after[: len(before)]).encode() == json.dumps(before).encode()
    assert current[: len(old)] == old
    assert 'verbatim activity' in current[-1]['content']
    assert current[-1]['kind'] == 'digest'


def test_long_digest_uses_summary_once(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(
        history,
        'recent_activity',
        lambda uid: [
            {
                'id': 'other',
                'chat_session_id': 'elsewhere',
                'text': 'word ' * 1500,
                'sender': 'human',
                'created_at': datetime.now(timezone.utc),
            }
        ],
    )
    calls = []

    async def summary(uid, text):
        calls.append(text)
        return 'short digest'

    asyncio.run(history.append_digest(store, 'u', {'id': 's'}, [], summary=summary))
    assert len(calls) == 1
    assert store.events('u', 's')[0]['content'].endswith('short digest')


def test_gateway_serializes_same_user_surface_and_reentry(monkeypatch, adapter):
    store = MemoryStore()
    body, headers = adapter.signed()
    message = adapter.parse(body)[0]
    proof = store.mint('u', adapter.channel, adapter.provider, 'token')['proof']
    store.consume(proof, message)
    monkeypatch.setattr(history, 'recent_activity', lambda uid: [])
    entered, proceed = None, None
    active = 0
    maximum = 0

    def turn(*args, **kwargs):
        async def stream():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            entered.set()
            await proceed.wait()
            active -= 1
            yield 'done: ' + base64.b64encode(json.dumps({'text': 'answer'}).encode()).decode() + '\n\n'

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)

    async def run():
        nonlocal entered, proceed
        entered, proceed = asyncio.Event(), asyncio.Event()
        first = (await gateway.webhook(body, headers))['jobs'][0]
        second = (await gateway.webhook(*adapter.signed(provider_message_id='second')))['jobs'][0]
        running = asyncio.create_task(gateway.process(first))
        await entered.wait()
        assert not await gateway.process(second)
        assert store.jobs[second]['status'] == 'pending'
        proceed.set()
        await running
        assert await gateway.process(second)
        principal = Principal('u', frozenset(), datetime.now(timezone.utc) + timedelta(minutes=5), 'task')
        await gateway.reenter(message, ReentryEvent('result', 'finished task', 'task'), principal=principal)
        count = len(adapter.sent)
        await gateway.reenter(message, ReentryEvent('result', 'finished task', 'task'), principal=principal)
        assert len(adapter.sent) == count

    asyncio.run(run())
    assert maximum == 1
    assert not store.leases


def test_real_shaped_executor_uses_advertised_surface_projection(monkeypatch):
    from types import SimpleNamespace
    from utils.retrieval import agentic
    from utils.messaging.projection import SurfaceRuntime, surface_runtime
    from utils.messaging.contracts import ChannelCapabilities

    captured, effects = [], []

    async def deliver_file(name: str) -> str:
        """Deliver an artifact through this surface."""
        effects.append(name)
        return 'delivered'

    tool = StructuredTool.from_function(coroutine=deliver_file)
    principal = Principal('u', frozenset({'deliver_file'}), datetime.now(timezone.utc) + timedelta(minutes=1), 'task')
    projection = ToolProjection.build((), (tool,), (), principal=principal)

    class Model:
        def bind(self, **kwargs):
            assert [t['function']['name'] for t in kwargs['tools']] == list(projection.registry)
            return self

        async def astream(self, messages):
            captured.append(json.loads(json.dumps(messages)))
            calls = [{'id': 'call', 'name': 'deliver_file', 'args': {'name': 'report'}}] if len(captured) == 1 else []
            yield SimpleNamespace(
                content='' if calls else 'Delivered', tool_calls=calls, tool_call_chunks=[], additional_kwargs={}
            )

    monkeypatch.setattr(agentic, 'get_llm', lambda *a, **kw: Model())
    runtime = SurfaceRuntime(
        'channel:opaque',
        ChannelCapabilities().skill(),
        principal,
        evidence=({'role': 'user', 'content': 'send report'},),
    )

    async def run():
        token = surface_runtime.set(runtime)
        try:
            await agentic._run_shaped_chat_stream(
                'LEGACY PROMPT MUST NOT LEAK',
                [],
                [agentic._langchain_tool_to_openai(tool)],
                dict(projection.registry),
                agentic.AsyncStreamingCallback(),
                [],
                agentic.AgentSafetyGuard(),
                {'user_id': 'u', 'tool_projection': projection},
            )
        finally:
            surface_runtime.reset(token)

    asyncio.run(run())
    assert effects == ['report']
    assert 'LEGACY PROMPT MUST NOT LEAK' not in json.dumps(captured)
    assert 'Channel delivery skill' in captured[0][0]['content'][0]['text']
    assert captured[1][-1]['role'] == 'tool'


def test_app_return_appends_channel_activity_without_rewriting_prefix(monkeypatch):
    from types import SimpleNamespace
    from utils.messaging import app_awareness

    store = MemoryStore()
    monkeypatch.setattr(app_awareness, 'MessagingStore', lambda: store)
    monkeypatch.setattr(app_awareness, 'require_access', lambda uid: None)
    other = []
    monkeypatch.setattr(history, 'recent_activity', lambda uid: other)
    first = SimpleNamespace(id='human1', text='first', sender='human', created_at=datetime.now(timezone.utc))

    async def run():
        one, _, lease = await app_awareness.prepare('u', SimpleNamespace(id='app-session'), [first], Principal('u'))
        store.release('u', 'app', lease)
        other.append(
            {
                'id': 'channel-answer',
                'chat_session_id': 'channel',
                'text': 'elsewhere',
                'sender': 'ai',
                'created_at': datetime.now(timezone.utc),
            }
        )
        second = SimpleNamespace(id='human2', text='second', sender='human', created_at=datetime.now(timezone.utc))
        two, _, lease = await app_awareness.prepare(
            'u', SimpleNamespace(id='app-session'), [first, second], Principal('u')
        )
        assert two.evidence[: len(one.evidence)] == one.evidence
        assert 'elsewhere' in two.evidence[-2]['content']
        store.release('u', 'app', lease)

    asyncio.run(run())


def test_access_uses_existing_subscription_authority_and_defaults_off(monkeypatch):
    from utils.messaging import access
    from models.users import PlanType
    from types import SimpleNamespace

    monkeypatch.delenv('OMI_MESSAGING_CHANNELS', raising=False)
    monkeypatch.delenv('OMI_MESSAGING_CHANNELS_UIDS', raising=False)
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    calls = []

    def subscription(uid, *, provision):
        calls.append((uid, provision))
        return SimpleNamespace(plan=PlanType.architect)

    monkeypatch.setattr(access, 'get_user_valid_subscription', subscription)
    with pytest.raises(PermissionError):
        access.require_access('u')
    assert not calls
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'on')
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS_UIDS', 'u')
    access.require_access('u')
    assert calls == [('u', False)]
    with pytest.raises(PermissionError):
        access.require_access('different')
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda *a, **k: SimpleNamespace(plan=PlanType.basic))
    with pytest.raises(PermissionError):
        access.require_access('u')
