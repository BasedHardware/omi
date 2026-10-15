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
from config.plan_catalog import PAID_PLAN_TYPES


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


def test_digest_is_volatile_and_does_not_rewrite_history():
    from utils.messaging.context import assemble

    messages = [
        {'role': 'user', 'content': 'old'},
        {'role': 'assistant', 'content': 'answer'},
        {'role': 'user', 'content': 'current'},
    ]
    one = assemble(messages, digest='Activity elsewhere: first')
    two = assemble(messages, digest='Activity elsewhere: second')
    assert one[:-1] == two[:-1]
    assert 'first' in one[-1]['content'] and 'second' in two[-1]['content']
    assert messages[-1]['content'] == 'current'


def test_large_digest_is_capped_without_a_per_turn_summary_model():
    from utils.messaging.context import digest_text, DIGEST_CHARS

    rows = [{'text': 'word ' * 1500, 'sender': 'human', 'created_at': datetime.now(timezone.utc)}]
    result = digest_text(rows)
    assert len(result) <= DIGEST_CHARS
    assert 'search_chat_history' in result


def test_gateway_serializes_same_user_surface_and_reentry(monkeypatch, adapter):
    store = MemoryStore()
    body, headers = adapter.signed()
    message = adapter.parse(body)[0]
    proof = store.mint('u', adapter.channel, adapter.provider, 'token')['proof']
    store.consume(proof, message)
    monkeypatch.setattr(history, 'recent_activity', lambda uid, since="", exclude_session=None: [])
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

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

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
        assert store.jobs[second]['status'] == 'done'
        assert not await gateway.process(second)
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


def test_app_awareness_does_not_override_authoritative_message_window(monkeypatch):
    from types import SimpleNamespace
    from utils.messaging import app_awareness

    store = MemoryStore()
    monkeypatch.setattr(app_awareness, 'require_access', lambda uid: None)
    first = SimpleNamespace(id='human1', text='first', sender='human', created_at=datetime.now(timezone.utc))

    async def run():
        runtime, _, lease = await app_awareness.prepare(
            'u', SimpleNamespace(id='app'), [first], Principal('u'), store=store
        )
        assert runtime.evidence == ()
        assert runtime.tools[0].name == 'search_chat_history'
        assert not store.logs
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


@pytest.mark.parametrize('plan', sorted(PAID_PLAN_TYPES, key=lambda plan: plan.value))
def test_access_admits_every_valid_paid_plan(monkeypatch, plan):
    from database import users
    from models.users import Subscription, SubscriptionStatus
    from utils.messaging import access

    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'on')
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS_UIDS', 'u')
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    subscription = Subscription(
        plan=plan,
        status=SubscriptionStatus.active,
        current_period_end=int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp()),
    )
    monkeypatch.setattr(users, 'get_existing_user_subscription', lambda uid, **kwargs: subscription)
    access.require_access('u')


@pytest.mark.parametrize('plan', ['basic', 'free', 'expired', 'missing'])
def test_access_rejects_free_and_expired_subscriptions(monkeypatch, plan):
    from database import users
    from models.users import PlanType, Subscription, SubscriptionStatus
    from utils.messaging import access

    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'on')
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS_UIDS', 'u')
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    # Free uses the catalog's basic wire identity. Expired paid plans must be
    # downgraded by the real subscription authority, never trusted as paid.
    subscription = (
        None
        if plan == 'missing'
        else Subscription(
            plan=PlanType.architect if plan == 'expired' else PlanType.basic,
            status=SubscriptionStatus.inactive if plan == 'free' else SubscriptionStatus.active,
            current_period_end=int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp()),
        )
    )
    monkeypatch.setattr(users, 'get_existing_user_subscription', lambda uid, **kwargs: subscription)
    with pytest.raises(PermissionError, match='Paid plan required'):
        access.require_access('u')


@pytest.mark.parametrize('case', ['paid', 'basic', 'expired', 'outside-cohort', 'switch-off'])
def test_link_proof_http_admission(monkeypatch, case):
    from database import users
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.users import PlanType, Subscription, SubscriptionStatus
    from routers import messaging
    from utils.messaging import access

    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'off' if case == 'switch-off' else 'on')
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS_UIDS', 'other' if case == 'outside-cohort' else 'u')
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    subscription = Subscription(
        plan=PlanType.basic if case == 'basic' else PlanType.plus,
        status=SubscriptionStatus.active,
        current_period_end=int(
            (datetime.now(timezone.utc) + timedelta(days=-1 if case == 'expired' else 1)).timestamp()
        ),
    )
    monkeypatch.setattr(users, 'get_existing_user_subscription', lambda uid, **kwargs: subscription)
    store = MemoryStore()
    monkeypatch.setattr(messaging, 'MessagingStore', lambda: store)
    app = FastAPI()
    app.include_router(messaging.router)
    route = next(route for route in app.routes if route.path == '/v1/messaging/link-proofs')
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: 'u'
    with TestClient(app) as client:
        response = client.post(
            '/v1/messaging/link-proofs', json={'channel': 'telegram', 'provider': 'telegram', 'kind': 'token'}
        )
    assert response.status_code == (200 if case == 'paid' else 403)
    if case == 'paid':
        assert response.json()['proof']
    else:
        assert response.json()['detail'] == 'Messaging channels unavailable'


def test_public_link_fields_come_from_config_without_a_channel_branch(monkeypatch):
    from config.messaging import public_link_fields

    monkeypatch.delenv('OMI_MESSAGING_LINK_TARGETS', raising=False)
    assert public_link_fields('telegram', 'proof') == (None, None)
    monkeypatch.setenv(
        'OMI_MESSAGING_LINK_TARGETS',
        json.dumps(
            {
                'telegram': {
                    'address': 'OmiBot',
                    'deep_link_template': 'https://t.me/{address}?start={proof}',
                },
                'imessage': {'address': '+15555550100'},
            }
        ),
    )
    assert public_link_fields('telegram', 'a b') == ('https://t.me/OmiBot?start=a%20b', 'OmiBot')
    assert public_link_fields('imessage', 'CODE') == (None, '+15555550100')
    assert public_link_fields('unknown', 'CODE') == (None, None)
    monkeypatch.setenv('OMI_MESSAGING_LINK_TARGETS', '{')
    assert public_link_fields('telegram', 'proof') == (None, None)


def test_channel_retrieval_drops_private_and_restricted_memories():
    from types import SimpleNamespace
    from utils.messaging.memory_privacy import is_channel_private_memory, omit_channel_private
    from utils.messaging.projection import SurfaceRuntime, surface_runtime
    from utils.messaging.contracts import Principal

    public = SimpleNamespace(visibility='public', sensitivity_labels=[], content='likes tea')
    marked = SimpleNamespace(visibility='private', sensitivity_labels=[], content='secret note')
    health = SimpleNamespace(visibility='public', sensitivity_labels=['health'], content='blood pressure')
    assert not is_channel_private_memory(public)
    assert is_channel_private_memory(marked)
    assert is_channel_private_memory(health)
    rows = [public, marked, health]
    assert omit_channel_private(rows) == rows
    token = surface_runtime.set(SurfaceRuntime('channel:opaque', '', Principal('u'), withhold_private_memories=True))
    try:
        assert omit_channel_private(rows) == [public]
        assert omit_channel_private(rows, {'withhold_private_memories': False}) == [public]
    finally:
        surface_runtime.reset(token)
    assert omit_channel_private(rows, {'withhold_private_memories': True}) == [public]


def test_invalid_link_proof_completes_without_a_distinct_reply(adapter):
    store = MemoryStore()
    body, headers = adapter.signed(link_proof='not-a-real-proof', text='/start not-a-real-proof')
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        path = (await gateway.webhook(body, headers))['jobs'][0]
        assert await gateway.process(path)
        assert store.jobs[path]['status'] == 'done'

    asyncio.run(run())
    assert [item['text'] for item in adapter.sent] == ['Link your account in Omi to chat here.']


def test_history_search_uses_the_closed_over_owner(monkeypatch):
    seen = []

    def scan(uid, batch_size):
        seen.append(uid)
        if uid == 'owner':
            return iter(
                [{'id': 'mine', 'text': 'needle', 'chat_session_id': 's', 'created_at': datetime.now(timezone.utc)}]
            )
        return iter(
            [{'id': 'theirs', 'text': 'needle', 'chat_session_id': 's', 'created_at': datetime.now(timezone.utc)}]
        )

    monkeypatch.setattr(history.chat_db, 'iter_all_messages', scan)
    assert [row['id'] for row in history.search_history('owner', 'needle')] == ['mine']
    assert seen == ['owner']


def test_explicit_history_search_scans_beyond_first_page(monkeypatch):
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    rows = [
        dict(id=str(i), created_at=now - timedelta(seconds=i), text='needle' if i == 140 else 'other')
        for i in range(160)
    ]
    monkeypatch.setattr(history.chat_db, 'iter_all_messages', lambda uid, batch_size: iter(rows))
    assert history.search_history('u', 'needle')[0]['id'] == '140'


def test_link_availability_reports_reason_per_channel(monkeypatch):
    from routers import messaging as router
    from utils.messaging.access import AccessDenied

    def require_access(uid, channel):
        if channel == 'imessage':
            raise AccessDenied('channel_plan', 'Operator or Architect plan required for iMessage')

    class Store:
        def seat_state(self, uid, channel):
            return None

        def waitlisted(self, uid, channel):
            raise AssertionError('only read for a full channel')

    monkeypatch.setattr(router, 'require_access', require_access)
    assert router._availability(Store(), 'uid') == {
        'telegram': {'available': True, 'reason': None, 'waitlisted': False},
        'imessage': {'available': False, 'reason': 'channel_plan', 'waitlisted': False},
    }


def test_link_availability_seat_cap_waitlist_and_failures(monkeypatch):
    from routers import messaging as router

    class Store:
        def seat_state(self, uid, channel):
            if channel == 'telegram':
                raise RuntimeError('firestore down')
            return 'seat_cap'

        def waitlisted(self, uid, channel):
            return True

    monkeypatch.setattr(router, 'require_access', lambda uid, channel: None)
    result = router._availability(Store(), 'uid')
    assert result['telegram'] == {'available': False, 'reason': 'unavailable', 'waitlisted': False}
    assert result['imessage'] == {'available': False, 'reason': 'seat_cap', 'waitlisted': True}
