"""Provider fixtures and Stage A contracts; all network IO is replayed."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from testing.messaging.adapter_contract import AdapterContract
from testing.messaging.adapter_fakes import FixtureTransport, FixtureLedger, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.adapters.linq import LinqProvider, IMessageAdapter
from utils.messaging.adapters.rendering import source_phrases, split_text
from utils.messaging.adapters.transport import Transport, DeliveryUncertain, ProviderError
from utils.messaging.contracts import Artifact, Principal
from utils.messaging.gateway import Gateway
from utils.messaging.outbound import ChannelReplySink
from utils.messaging.projection import SurfaceRuntime, surface_runtime, ToolProjection

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'messaging' / 'adapters'
SECRET = b'synthetic-test-signing-secret-32'


def fixture(provider, kind='text'):
    return (FIXTURES / f'{provider}-{kind}.json').read_bytes()


def signed(adapter, body, *, timestamp=None):
    if adapter.channel == 'telegram':
        return body, {'X-Telegram-Bot-Api-Secret-Token': 'fixture_secret'}
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    value = base64.b64encode(
        hmac.new(SECRET, b'fixture-id.' + stamp.encode() + b'.' + body, hashlib.sha256).digest()
    ).decode()
    return body, {'webhook-id': 'fixture-id', 'webhook-timestamp': stamp, 'webhook-signature': 'v1,' + value}


@pytest.fixture(params=['telegram', 'linq'])
def adapter(request, monkeypatch):
    transport, ledger = FixtureTransport(), FixtureLedger()
    if request.param == 'telegram':
        result = TelegramAdapter(
            '000:fixture-token', 'fixture_secret', transport=transport, ledger=ledger, sleep=no_sleep
        )
    else:
        provider = LinqProvider(
            'fixture-api-key',
            'whsec_' + base64.b64encode(SECRET).decode(),
            transport=transport,
            sleep=no_sleep,
            upload_hosts={'uploads.linqapp.com'},
        )
        result = IMessageAdapter(provider, transport=transport, ledger=ledger, sleep=no_sleep)
    result.sent = []
    send = result.send

    async def record(message, *, text=None, artifact=None, draft=False):
        result.sent.append(dict(message=message, text=text, artifact=artifact, draft=draft))
        await send(message, text=text, artifact=artifact, draft=draft)

    async def owned_bytes(artifact):
        return b'abc'

    # Artifact ownership is exercised independently; the contract's artifact is synthetic.
    monkeypatch.setattr(result, 'owned_bytes', owned_bytes)
    monkeypatch.setattr(result, 'send', record)
    return result


@pytest.fixture
def signed_message(adapter):
    provider = 'telegram' if adapter.channel == 'telegram' else 'linq'

    def create():
        body = fixture(provider)
        # A direct contract sink does not enqueue an inbound job. Pre-credit its
        # synthetic initiating message, as the worker would do before any send.
        message = adapter.parse(body)[0]
        adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
        return signed(adapter, body)

    return create


class TestProviderContracts(AdapterContract):
    pass


@pytest.mark.parametrize(
    'kind',
    ['text', 'voice', 'photo', 'document', 'edited', 'start', 'unlink', 'unknown_sender', 'duplicate', 'bad_signature'],
)
def test_golden_payloads(adapter, kind):
    provider = 'telegram' if adapter.channel == 'telegram' else 'linq'
    body = fixture(provider, kind)
    body, headers = signed(adapter, body)
    if kind == 'bad_signature':
        headers = {name: 'invalid' for name in headers}
        assert not adapter.verify_webhook(body, headers)
        return
    assert adapter.verify_webhook(body, headers)
    messages = adapter.parse(body)
    if kind == 'edited':
        assert not messages
        return
    assert len(messages) == 1
    message = messages[0]
    assert (message.channel, message.provider) == (adapter.channel, adapter.provider)
    if kind in ('voice', 'photo', 'document'):
        assert len(message.attachments) == 1
        assert message.attachments[0].voice == (kind == 'voice')
    if kind == 'start':
        assert message.link_proof
    if kind == 'unlink':
        assert message.unlink
    if kind == 'duplicate':
        assert message.provider_message_id == adapter.parse(fixture(provider))[0].provider_message_id


def test_linq_signatures_rotation_raw_body_and_replay(adapter):
    if adapter.channel != 'imessage':
        return
    body, headers = signed(adapter, fixture('linq'))
    assert not adapter.verify_webhook(body + b' ', headers)
    headers['webhook-signature'] = 'v1,invalid ' + headers['webhook-signature']
    assert adapter.verify_webhook(body, headers)
    for age in (-301, 301):
        body, headers = signed(adapter, body, timestamp=int(time.time()) + age)
        assert not adapter.verify_webhook(body, headers)
    assert not adapter.verify_webhook(
        body, {'X-Webhook-Signature': 'fake', 'X-Webhook-Timestamp': str(int(time.time()))}
    )


def test_groups_bots_outbound_edits_are_not_turns(adapter):
    if adapter.channel == 'telegram':
        value = json.loads(fixture('telegram'))
        value['message']['chat']['type'] = 'group'
        assert not adapter.parse(json.dumps(value).encode())
        value['message']['chat']['type'] = 'private'
        value['message']['from']['is_bot'] = True
    else:
        value = json.loads(fixture('linq'))
        value['data']['chat']['is_group'] = True
        assert not adapter.parse(json.dumps(value).encode())
        value['data']['chat']['is_group'] = False
        value['data']['direction'] = 'outbound'
    assert not adapter.parse(json.dumps(value).encode())


def test_linq_link_code_is_extracted_from_surrounding_text(adapter):
    if adapter.channel != 'imessage':
        return
    code = '0123456789ABCDEF0123456789ABCDEF'
    value = json.loads(fixture('linq', 'start'))
    value['data']['parts'][0]['value'] = f'Your Omi code is {code}. Tap to connect.'
    message = adapter.parse(json.dumps(value).encode())[0]
    assert message.link_proof == code
    assert not message.unlink
    value['data']['parts'][0]['value'] = f'{code} and {code}'
    assert adapter.parse(json.dumps(value).encode())[0].link_proof is None
    value['data']['parts'][0]['value'] = code + 'AA'
    assert adapter.parse(json.dumps(value).encode())[0].link_proof is None


def test_telegram_username_is_a_display_handle(adapter):
    if adapter.channel != 'telegram':
        return
    value = json.loads(fixture('telegram'))
    value['message']['from']['username'] = '@OmiFriend'
    assert adapter.parse(json.dumps(value).encode())[0].display_name == '@OmiFriend'
    value['message']['from'].pop('username')
    assert adapter.parse(json.dumps(value).encode())[0].display_name is None


def test_voice_notes_off_does_not_run_a_turn(adapter):
    if adapter.channel != 'telegram':
        return
    from utils.messaging.contracts import ChannelMessage, InboundAttachment

    store = MemoryStore()
    message = ChannelMessage(
        adapter.channel,
        adapter.provider,
        'fixture-user',
        'fixture-chat',
        'voice-1',
        '',
        datetime.now(timezone.utc),
        attachments=(InboundAttachment('file', 'voice.ogg', 'audio/ogg', 12, True),),
    )
    store.identities[(message.channel, message.provider, message.external_user_id)] = dict(
        uid='user', active=True, generation='gen', voice_notes=False
    )
    path = store.enqueue(message)
    turns = []

    async def turn(*args, **kwargs):
        turns.append(args)

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)
    asyncio.run(gateway.process(path))
    assert turns == []
    assert 'Voice notes are turned off' in adapter.sent[-1]['text']


def test_linq_legacy_payload_version(adapter):
    if adapter.channel != 'imessage':
        return
    value = json.loads(fixture('linq'))
    value['webhook_version'] = '2025-01-01'
    value['data'] = dict(
        chat_id='fixture-chat',
        **{'from': '+12025550101'},
        is_group=False,
        is_from_me=False,
        message=dict(id='fixture-message', parts=[dict(type='text', value='legacy')]),
    )
    assert adapter.parse(json.dumps(value).encode())[0].text == 'legacy'


def test_renderers_escape_split_and_citations(adapter):
    text = 'A [1] source. **Hello** _world_! ' + '😀' * 5000
    parts = adapter.render(text)
    assert len(parts) > 1
    assert all(len(p.encode('utf-16-le')) // 2 <= adapter.capabilities.max_text_len for p in parts)
    assert '[1]' not in ''.join(parts)
    assert not any(p.endswith('\\') for p in parts)
    assert source_phrases('See [1]', [{'title': 'Weekly review'}]) == 'See (from Weekly review)'
    assert ''.join(split_text('a b\n😀' * 10, 8)) == 'a b\n😀' * 10


def test_telegram_stable_draft_and_final_committed(adapter):
    if adapter.channel != 'telegram':
        return
    message = adapter.parse(fixture('telegram'))[0]

    async def run():
        await adapter.admitted(message)
        await adapter.send(message, text='hello', draft=True)
        await adapter.send(message, text='hello again', draft=True)
        await adapter.send(message, text='hello again')

    asyncio.run(run())
    calls = adapter.transport.calls
    assert calls[0][1].endswith('/sendMessageDraft') and calls[1][1].endswith('/sendMessageDraft')
    assert calls[0][2]['json']['draft_id'] == calls[1][2]['json']['draft_id'] != 0
    assert calls[-1][1].endswith('/sendMessage')


def responses(*names):
    data = json.loads((FIXTURES / 'responses.json').read_text())
    return [(data[name]['status'], data[name]['body'], data[name]['headers']) for name in names]


def test_replayed_429_then_success(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('rate_limit', 'telegram_ok' if adapter.channel == 'telegram' else 'linq_ok')
    delays = []

    async def sleep(delay):
        delays.append(delay)

    adapter.sleep = sleep
    if adapter.channel == 'imessage':
        adapter.client.sleep = sleep

    async def run():
        await adapter.admitted(message)
        await adapter.send(message, text='safe')

    asyncio.run(run())
    assert len(adapter.transport.calls) == 2 and 2 in delays
    assert adapter.ledger.sent == 1


def test_ambiguous_5xx_fail_closed_or_idempotent(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('server_error', 'linq_ok')

    async def run():
        await adapter.admitted(message)
        if adapter.channel == 'telegram':
            with pytest.raises(DeliveryUncertain):
                await adapter.send(message, text='safe')
            with pytest.raises(RuntimeError, match='reconciliation'):
                await adapter.send(message, text='safe')
            assert len(adapter.transport.calls) == 1
        else:
            await adapter.send(message, text='safe')
            assert len(adapter.transport.calls) == 2
            assert (
                adapter.transport.calls[0][2]['json']['idempotency_key']
                == adapter.transport.calls[1][2]['json']['idempotency_key']
            )

    asyncio.run(run())


def test_linq_ratio_all_messages_count_typing_does_not(adapter):
    if adapter.channel != 'imessage':
        return
    message = adapter.parse(fixture('linq'))[0]

    async def run():
        with pytest.raises(PermissionError):
            await adapter.send(message, text='no unsolicited sends')
        await adapter.admitted(message)
        await adapter.admitted(message)
        await adapter.typing(message)
        assert adapter.ledger.sent == 0
        for i in range(3):
            await adapter.send(message, text=f'status {i}')
        with pytest.raises(PermissionError):
            await adapter.send(message, text='fourth')
        assert adapter.ledger.sent == 3

    asyncio.run(run())


def test_tools_advertise_and_execute_only_on_guarded_linked_chat(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    checks = []

    async def guard():
        checks.append(True)

    sink = ChannelReplySink(adapter, message, guard=guard)
    tools = adapter.tools(sink)
    projection = ToolProjection.build((), tools, (), principal=Principal('test'))
    assert all('chat_id' not in tool.args for tool in tools)

    async def run():
        await adapter.admitted(message)
        reaction = '👍' if adapter.channel == 'telegram' else 'like'
        await projection.authorize('test', adapter.channel + '_react').ainvoke({'emoji': reaction})

    asyncio.run(run())
    assert len(checks) >= 2
    with pytest.raises(PermissionError):
        projection.authorize('other', adapter.channel + '_react')


def test_followups_buttons_and_citation_source_prose(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {
                'text': 'Found [1].',
                'conversations': [{'title': 'Daily standup'}],
                'follow_up_suggestions': ['Explain more', 'x' * 80],
            }
        )

    asyncio.run(run())
    payload = adapter.transport.calls[-1][2]['json']
    if adapter.channel == 'telegram':
        assert payload['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'ask:Explain more'
        assert 'Daily standup' in payload['text']
    else:
        assert 'Daily standup' in payload['parts'][0]['value']
        assert 'Explain more' not in str(payload)


def test_media_fetch_bounds_and_ssrf(monkeypatch):
    # No network occurs: validation happens before the shared client is requested.
    transport = Transport()
    for url in [
        'http://cdn.linqapp.com/x',
        'https://127.0.0.1/x',
        'https://cdn.linqapp.com.evil/x',
        'https://user@cdn.linqapp.com/x',
    ]:
        with pytest.raises(PermissionError):
            asyncio.run(transport.download(url, allowed_hosts={'cdn.linqapp.com'}))


def test_real_followup_wire_block_and_source_title(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {
                'text': 'See [1].',
                'memories': [{'structured': {'title': 'Team meeting'}}],
                'content_blocks': [{'type': 'followUp', 'id': 'synthetic:followup', 'text': 'What changed?'}],
            }
        )

    asyncio.run(run())
    payload = adapter.transport.calls[-1][2]['json']
    if adapter.channel == 'telegram':
        assert payload['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'ask:What changed?'
        assert 'Team meeting' in payload['text']
    else:
        assert 'What changed?' not in str(payload)
        assert 'Team meeting' in payload['parts'][0]['value']


def test_revocation_during_429_backoff_blocks_retry(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('rate_limit', 'telegram_ok')
    active = True

    async def guard():
        if not active:
            raise PermissionError('Link revoked')

    async def sleep(delay):
        nonlocal active
        active = False

    adapter.sleep = sleep
    if adapter.channel == 'imessage':
        adapter.client.sleep = sleep

    async def run():
        await adapter.admitted(message)
        with pytest.raises(PermissionError, match='revoked'):
            await ChannelReplySink(adapter, message, guard=guard).finish('hello')

    asyncio.run(run())
    assert len(adapter.transport.calls) == 1


def test_media_prepare_stt_and_searchable_file_ids(adapter, monkeypatch):
    from database import chat
    from utils.messaging.adapters.media import ChatMediaStore
    from utils.stt import pre_recorded

    calls = []
    media = ChatMediaStore()
    monkeypatch.setattr(
        pre_recorded,
        'prerecorded_from_bytes',
        lambda data, **kwargs: [{'word': 'voice'}, {'punctuated_word': 'transcribed.'}],
    )

    def ingest(uid, attachment, data):
        calls.append(('ingest', uid, attachment.mime_type, data))
        return Artifact('owned-file-id', attachment.mime_type, len(data), attachment.name)

    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(
        chat, 'add_files_to_chat_session', lambda uid, session, ids: calls.append(('session', uid, session, ids))
    )
    adapter.media = media
    checks = []

    async def guard():
        checks.append(True)

    async def run():
        voice = adapter.parse(fixture(adapter.provider, 'voice'))[0]
        result = await adapter.prepare(voice, 'test', {'id': 'surface-session'}, guard)
        assert 'voice transcribed.' in result.text and not result.attachments
        document = adapter.parse(fixture(adapter.provider, 'document'))[0]
        result = await adapter.prepare(document, 'test', {'id': 'surface-session'}, guard)
        assert result.media[0].file_store_ref == 'owned-file-id'

    asyncio.run(run())
    assert ('session', 'test', 'surface-session', ['owned-file-id']) in calls
    assert len(checks) >= 4


def test_owned_artifact_rejects_foreign_ids_metadata_and_oversize(monkeypatch):
    from database import chat
    from utils.messaging.adapters.media import ChatMediaStore
    from utils.other import chat_file

    artifact = Artifact('file', 'text/plain', 3, 'a.txt')
    store = ChatMediaStore()
    queried = []

    def rows(uid, ids):
        queried.append((uid, ids))
        return []

    monkeypatch.setattr(chat, 'get_chat_files', rows)
    with pytest.raises(PermissionError):
        store.resolve('test', artifact)
    assert queried == [('test', ['file'])]
    monkeypatch.setattr(chat, 'get_chat_files', lambda *a: [{'name': 'a.txt', 'mime_type': 'image/jpeg'}])
    with pytest.raises(PermissionError):
        store.resolve('test', artifact)
    monkeypatch.setattr(chat, 'get_chat_files', lambda *a: [{'name': 'a.txt', 'mime_type': 'text/plain'}])
    monkeypatch.setattr(chat_file, 'download_owned_chat_file', lambda *a, **k: b'wrong size')
    with pytest.raises(ValueError):
        store.resolve('test', artifact)


def test_chart_exclusion_uses_same_authority_and_keeps_app():
    from utils.messaging.projection import project_runtime_tools
    from langchain_core.tools import StructuredTool

    def chart(data: str) -> str:
        """Render a chart."""
        return data

    tool = StructuredTool.from_function(name='create_chart_tool', func=chart)
    channel = SurfaceRuntime('channel:test', '', Principal('test'))
    projection = project_runtime_tools(channel, [tool], [], [], [])
    assert not projection.registry
    with pytest.raises(PermissionError):
        projection.authorize('test', 'create_chart_tool')
    app = replace(channel, surface='app')
    assert project_runtime_tools(app, [tool], [], [], []).authorize('test', 'create_chart_tool') is tool


def test_off_by_default_runtime_and_live_config_safety(monkeypatch):
    from utils.messaging.adapters.runtime import configured_adapters
    from testing.messaging.live_adapters import validate_config

    monkeypatch.delenv('OMI_MESSAGING_CHANNELS', raising=False)
    monkeypatch.setenv('OMI_TELEGRAM_ENABLED', 'on')
    assert configured_adapters() == ()
    config = dict(
        test_uid='synthetic-test',
        test_account_verified=True,
        telegram_test_user_id='101',
        linq_test_handle='+12025550101',
        telegram_dev_bot_id='100',
        linq_dev_line='+12025550102',
        webhook_origin='https://qa.example.test',
        secret_project='based-hardware-dev',
    )
    assert validate_config(config) == config
    for field, value in [
        ('test_account_verified', False),
        ('secret_project', 'based-hardware'),
        ('webhook_origin', 'https://api.omi.me'),
    ]:
        with pytest.raises(ValueError):
            validate_config({**config, field: value})


def test_app_writes_do_not_create_undo_or_channel_capture(monkeypatch):
    from utils.messaging import undo
    from utils.retrieval.tools import preference_tools

    called = []
    monkeypatch.setattr(preference_tools, 'capture_memory_write', lambda **kwargs: called.append(kwargs))
    token = surface_runtime.set(SurfaceRuntime('channel:test', '', Principal('test')))
    try:
        preference_tools._capture_app_memory_write(content='synthetic')
        assert not called
    finally:
        surface_runtime.reset(token)
    assert undo.record_write('test', 'task', 'id', None, {}) == ''
    preference_tools._capture_app_memory_write(content='synthetic')
    assert len(called) == 1


def test_adapter_http_routes_authenticate_before_admission(adapter, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import messaging

    gateway = Gateway(adapter, store=MemoryStore(), turn=lambda *a, **k: pytest.fail('Turn before HTTP ACK'))
    monkeypatch.setattr(messaging, '_gateways', {'provider-test': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    body, headers = signed(adapter, fixture(adapter.provider))
    with TestClient(app) as client:
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers=headers).status_code == 202
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers=headers).status_code == 202
        assert len(gateway.store.jobs) == 1
        assert not adapter.transport.calls
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers={}).status_code == 401
        assert client.post('/v1/messaging/webhooks/missing', content=body, headers=headers).status_code == 404
        assert (
            client.post('/v1/messaging/webhooks/provider-test', content=b'x' * 1_000_001, headers=headers).status_code
            == 413
        )


def test_memory_inverse_uses_universal_service_and_fails_closed(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from database import _client
    from utils.memory import canonical_memory_adapter, memory_service
    from utils.messaging.undo import apply_inverse

    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: object())
    item = SimpleNamespace(content='after', superseded_by=None, status=SimpleNamespace(value='active'))
    monkeypatch.setattr(canonical_memory_adapter, 'read_canonical_memory_item', lambda *a, **k: item)
    service = MagicMock()
    monkeypatch.setattr(memory_service, 'MemoryService', lambda **kwargs: service)
    payload = {'kind': 'memory', 'object_id': 'owned', 'before': 'before', 'after': 'after'}
    apply_inverse('test', payload)
    assert service.update_external_memory_content.call_args.args == ('test', 'owned', 'before')
    apply_inverse('test', {**payload, 'before': None})
    assert service.delete_external_memory.call_args.args == ('test', 'owned')
    item.content = 'concurrent change'
    with pytest.raises(PermissionError):
        apply_inverse('test', payload)
    assert service.update_external_memory_content.call_count == 1
    apply_inverse('test', {'kind': 'memory_closed', 'object_id': 'owned', 'operation_id': 'synthetic-op'})
    service.reopen_standalone_closed_ledger_fact.assert_called_once_with('test', 'owned', 'synthetic-op')


def test_provider_http_logs_filter_credential_urls():
    import logging
    from utils.messaging.adapters.transport import ProviderLogFilter

    filter_ = ProviderLogFilter()
    record = logging.LogRecord(
        'httpx', logging.INFO, '', 0, 'HTTP POST %s', ('https://api.telegram.org/botSECRET/sendMessage',), None
    )
    assert not filter_.filter(record)
    assert filter_.filter(logging.LogRecord('httpx', logging.INFO, '', 0, 'unrelated request', (), None))
