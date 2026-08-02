import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fake_firestore import MockFirestore

import database.channels as channels_db
import services.channel_chat as channel_chat
from models.chat import Message
from utils.retrieval.tools.channel_tools import manage_messaging_channels


def test_telegram_update_requires_a_safe_integer_and_keeps_one_to_one_identity():
    payload = channel_chat.parse_telegram_update(
        {
            'update_id': 7,
            'message': {
                'message_id': 11,
                'from': {'id': 42},
                'chat': {'id': 42},
                'text': '  hello  ',
            },
        }
    )
    assert payload == {
        'event_id': '7',
        'message_id': '11',
        'channel_user_id': '42',
        'channel_chat_id': '42',
        'text': 'hello',
    }
    with pytest.raises(ValueError):
        channel_chat.parse_telegram_update({'update_id': 1.5})


def test_sendblue_parser_drops_outbound_and_preserves_group_identity():
    assert channel_chat.parse_sendblue_inbound({'is_outbound': True}) is None
    payload = channel_chat.parse_sendblue_inbound(
        {
            'message_handle': 'message-1',
            'from_number': '+15551234567',
            'group_id': 'group-1',
            'content': 'hello',
        }
    )
    assert payload is not None
    assert payload['channel_user_id'] == '+15551234567'
    assert payload['channel_chat_id'] == 'group-1'


def test_twilio_sms_parser_uses_sender_identity_and_rejects_empty_messages():
    assert (
        channel_chat.parse_twilio_sms_inbound({'MessageSid': 'SM1', 'From': '+15551234567', 'To': '+15557654321'})
        is None
    )
    payload = channel_chat.parse_twilio_sms_inbound(
        {'MessageSid': 'SM1', 'From': '+15551234567', 'To': '+15557654321', 'Body': ' hello '}
    )
    assert payload == {
        'event_id': 'SM1',
        'message_id': 'SM1',
        'channel_user_id': '+15551234567',
        'channel_chat_id': '+15551234567',
        'text': 'hello',
    }


def test_webhook_secrets_are_fail_closed(monkeypatch):
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 'telegram-secret')
    monkeypatch.setenv('SENDBLUE_WEBHOOK_SIGNING_SECRET', 'sendblue-secret')
    monkeypatch.setenv('SENDBLUE_WEBHOOK_PATH_TOKEN', 'path-token')
    assert channel_chat.verify_telegram_webhook('telegram-secret')
    assert not channel_chat.verify_telegram_webhook('wrong')
    assert channel_chat.verify_sendblue_webhook('path-token', 'sendblue-secret')
    assert not channel_chat.verify_sendblue_webhook('wrong', 'sendblue-secret')
    monkeypatch.delenv('TELEGRAM_WEBHOOK_SECRET')
    assert not channel_chat.verify_telegram_webhook('telegram-secret')


def test_channel_reply_sanitizer_is_plain_text_and_bounded():
    assert channel_chat.sanitize_channel_reply('telegram', '**hello**\n- world') == 'hello\nworld'
    assert channel_chat.sanitize_channel_reply('imessage', 'x' * 2500).endswith('…')
    assert len(channel_chat.sanitize_channel_reply('imessage', 'x' * 2500)) == 2000
    assert len(channel_chat.sanitize_channel_reply('sms', 'x' * 2000)) == 1600


def test_core_chat_turn_persists_external_messages_and_uses_channel_platform(monkeypatch):
    persisted = []

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        if fn is channel_chat._persist_human_and_history:
            return (
                [Message(id='human', text='hello', created_at=datetime.now(timezone.utc), sender='human', type='text')],
                SimpleNamespace(id='session'),
                'human',
            )
        if fn is channel_chat.chat_db.add_message:
            persisted.append(args[1])
            return args[1]
        return None

    async def fake_stream(uid, messages, **kwargs):
        assert uid == 'uid-1'
        assert kwargs['platform'] == 'telegram'
        kwargs['callback_data']['answer'] = 'plain answer'
        kwargs['callback_data']['memories_found'] = []
        yield None

    monkeypatch.setattr(channel_chat, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(channel_chat, 'execute_chat_stream', fake_stream)
    monkeypatch.setattr(channel_chat, 'set_usage_context', lambda *_: object())
    monkeypatch.setattr(channel_chat, 'reset_usage_context', lambda *_: None)

    import asyncio

    result = asyncio.run(channel_chat.generate_channel_reply('uid-1', 'telegram', 'hello'))
    assert result == 'plain answer'
    assert len(persisted) == 1
    assert persisted[0]['from_external_integration'] is True
    assert persisted[0]['message_source'] == 'channel:telegram'


def test_core_chat_tool_issues_a_link_code(monkeypatch):
    expires_at = datetime(2026, 8, 2, 12, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(
        channels_db,
        'issue_link_token',
        lambda uid, channel: ('a' * 48, expires_at),
    )
    result = manage_messaging_channels.func(
        action='link',
        channel='Telegram',
        config={'configurable': {'user_id': 'uid-1'}},
    )
    assert '/start ' + 'a' * 48 in result
    assert '12:15 UTC' in result


def test_link_tokens_are_hashed_and_webhook_events_are_idempotent():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    token, _ = channels_db.issue_link_token('uid-1', 'telegram', now=now, firestore_client=client)
    token_documents = list(client.collection('channel_link_tokens').stream())
    assert token_documents[0].to_dict()['uid'] == 'uid-1'
    assert token not in token_documents[0].to_dict()

    assert (
        channels_db.consume_link_token('telegram', token, '42', '42', now=now, firestore_client=client)['uid']
        == 'uid-1'
    )
    assert channels_db.get_binding('telegram', '42', firestore_client=client)['uid'] == 'uid-1'

    assert channels_db.claim_webhook_event('telegram', 'update-1', now=now, firestore_client=client) == (True, None)
    created, existing = channels_db.claim_webhook_event('telegram', 'update-1', now=now, firestore_client=client)
    assert not created
    assert existing['status'] == 'processing'


def test_claim_tokens_bind_the_external_identity_once():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    token, _ = channels_db.issue_claim_token('sms', '+15551234567', '+15551234567', now=now, firestore_client=client)
    binding = channels_db.claim_link_token('uid-1', 'sms', token, now=now, firestore_client=client)
    assert binding['uid'] == 'uid-1'
    assert channels_db.get_binding('sms', '+15551234567', firestore_client=client)['uid'] == 'uid-1'
    with pytest.raises(channels_db.ChannelLinkError):
        channels_db.claim_link_token('uid-1', 'sms', token, now=now, firestore_client=client)


def test_unlinked_channel_reply_contains_a_one_time_sign_in_link(monkeypatch):
    expires_at = datetime(2026, 8, 2, 12, 15, tzinfo=timezone.utc)

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        if fn is channels_db.get_binding:
            return None
        if fn is channels_db.issue_claim_token:
            return 'b' * 48, expires_at
        raise AssertionError(fn)

    from routers.channels import _channel_reply

    import routers.channels as channels_router

    monkeypatch.setattr(channels_router, 'run_blocking', fake_run_blocking)

    result = asyncio.run(
        _channel_reply(
            'sms',
            {
                'channel_user_id': '+15551234567',
                'channel_chat_id': '+15551234567',
                'text': 'hello',
            },
        )
    )
    assert 'https://omi.me/login?channel=sms&code=' + 'b' * 48 in result
    assert '/start ' + 'b' * 48 in result


def test_provider_delivery_uses_provider_specific_auth(monkeypatch):
    requests = []

    class Response:
        status_code = 200

    class Client:
        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    monkeypatch.setattr(channel_chat, 'get_webhook_client', lambda: Client())
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'telegram-token')
    asyncio.run(channel_chat.send_channel_message('telegram', '42', 'hello'))
    assert requests == [
        (
            'https://api.telegram.org/bottelegram-token/sendMessage',
            {'json': {'chat_id': '42', 'text': 'hello'}},
        )
    ]

    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')
    with pytest.raises(channel_chat.ChannelProviderError):
        asyncio.run(channel_chat.send_channel_message('telegram', '42', 'hello'))


def test_sms_delivery_reuses_twilio_service(monkeypatch):
    sent = []

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        sent.append((fn, args))
        return 'SM1'

    monkeypatch.setattr(channel_chat, 'run_blocking', fake_run_blocking)
    asyncio.run(channel_chat.send_channel_message('sms', '+15551234567', 'hello'))
    assert sent[0][0] is channel_chat.send_sms
    assert sent[0][1] == ('+15551234567', 'hello')
