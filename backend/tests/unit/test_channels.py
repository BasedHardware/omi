import asyncio
from contextlib import nullcontext
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


def test_telegram_group_media_includes_participant_and_attachment_identity():
    payload = channel_chat.parse_telegram_update(
        {
            'update_id': 8,
            'message': {
                'message_id': 12,
                'from': {'id': 42, 'first_name': 'Ada', 'last_name': 'Lovelace'},
                'chat': {'id': -42, 'type': 'supergroup'},
                'caption': 'What is this?',
                'photo': [{'file_id': 'small'}, {'file_id': 'large'}],
            },
        }
    )
    assert payload is not None
    assert payload['channel_user_id'] == '42'
    assert payload['channel_chat_id'] == '-42'
    assert payload['sender_name'] == 'Ada Lovelace'
    assert payload['attachments'] == [
        {'source': 'telegram', 'file_id': 'large', 'filename': 'photo.jpg', 'mime_type': 'image/jpeg'}
    ]


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


def test_sendblue_and_twilio_parsers_preserve_media_urls():
    sendblue = channel_chat.parse_sendblue_inbound(
        {
            'message_handle': 'message-2',
            'from_number': '+15551234567',
            'group_id': 'group-1',
            'content': 'look',
            'media_url': 'https://cdn.sendblue.com/media/image.jpg',
            'media_type': 'image/jpeg',
        }
    )
    assert sendblue is not None
    assert sendblue['attachments'][0]['source'] == 'imessage'
    assert sendblue['attachments'][0]['url'].endswith('image.jpg')

    twilio = channel_chat.parse_twilio_sms_inbound(
        {
            'MessageSid': 'SM2',
            'From': '+15551234567',
            'To': '+15557654321',
            'Body': 'look',
            'NumMedia': '1',
            'MediaUrl0': 'https://api.twilio.com/2010-04-01/Accounts/AC/Messages/MM/Media/ME',
            'MediaContentType0': 'image/jpeg',
        }
    )
    assert twilio is not None
    assert twilio['attachments'][0]['source'] == 'twilio'
    assert twilio['attachments'][0]['mime_type'] == 'image/jpeg'


def test_twilio_conversations_parser_binds_the_room_and_expands_media():
    assert channel_chat.parse_twilio_conversation_inbound({'EventType': 'onMessageAdded', 'Author': 'system'}) is None
    payload = channel_chat.parse_twilio_conversation_inbound(
        {
            'EventType': 'onMessageAdded',
            'MessageSid': 'IM1',
            'ConversationSid': 'CH1',
            'ChatServiceSid': 'IS1',
            'Author': '+15551234567',
            'Body': 'look',
            'Media': '[{"Sid":"ME1","ContentType":"image/jpeg","Filename":"photo.jpg"}]',
        }
    )
    assert payload is not None
    assert payload['channel_user_id'] == '+15551234567'
    assert payload['channel_chat_id'] == 'CH1'
    assert payload['provider_mode'] == 'twilio_conversations'
    assert payload['attachments'][0]['url'] == 'https://mcs.us1.twilio.com/v1/Services/IS1/Media/ME1'


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


def test_group_link_tokens_bind_to_group_identity():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    token, _ = channels_db.issue_link_token('uid-1', 'telegram', now=now, firestore_client=client)
    binding = channels_db.consume_link_token('telegram', token, '42', '-42', now=now, firestore_client=client)
    assert binding['channel_user_id'] == '42'
    assert binding['channel_chat_id'] == '-42'
    assert channels_db.get_binding('telegram', '99', '-42', firestore_client=client)['uid'] == 'uid-1'
    assert channels_db.get_binding('telegram', '42', '42', firestore_client=client) is None


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
    assert 'https://app.omi.me/login?channel=sms&code=' + 'b' * 48 in result
    assert '/start ' + 'b' * 48 in result


def test_unlinked_channel_reply_uses_configured_sign_in_url(monkeypatch):
    expires_at = datetime(2026, 8, 2, 12, 15, tzinfo=timezone.utc)

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        if fn is channels_db.get_binding:
            return None
        if fn is channels_db.issue_claim_token:
            return 'c' * 48, expires_at
        raise AssertionError(fn)

    import routers.channels as channels_router

    monkeypatch.setenv('CHANNEL_SIGN_IN_URL', 'https://channels-dev.example/login/')
    monkeypatch.setattr(channels_router, 'run_blocking', fake_run_blocking)

    result = asyncio.run(
        channels_router._channel_reply(
            'telegram',
            {
                'channel_user_id': '42',
                'channel_chat_id': '42',
                'text': 'hello',
            },
        )
    )

    assert 'https://channels-dev.example/login?channel=telegram&code=' + 'c' * 48 in result


def test_group_channel_reply_uses_group_binding_and_attributes_sender(monkeypatch):
    import routers.channels as channels_router

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        if fn is channels_db.get_binding:
            assert args == ('telegram', '42', '-42')
            return {'uid': 'uid-1'}
        raise AssertionError(fn)

    captured = {}

    async def fake_generate(uid, channel, text, *, attachments=None):
        captured.update({'uid': uid, 'channel': channel, 'text': text, 'attachments': attachments})
        return 'answer'

    monkeypatch.setattr(channels_router, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(channels_router, 'generate_channel_reply', fake_generate)
    result = asyncio.run(
        channels_router._channel_reply(
            'telegram',
            {
                'channel_user_id': '42',
                'channel_chat_id': '-42',
                'sender_name': 'Ada',
                'text': 'hello',
                'attachments': [{'source': 'telegram', 'file_id': 'file-1'}],
            },
        )
    )
    assert result == 'answer'
    assert captured == {
        'uid': 'uid-1',
        'channel': 'telegram',
        'text': 'Ada: hello',
        'attachments': [{'source': 'telegram', 'file_id': 'file-1'}],
    }


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

    monkeypatch.setenv('SENDBLUE_API_KEY_ID', 'key-id')
    monkeypatch.setenv('SENDBLUE_API_KEY_SECRET', 'key-secret')
    monkeypatch.setenv('SENDBLUE_NUMBER', '+15557654321')
    asyncio.run(channel_chat.send_channel_message('imessage', 'group-1', 'hello', is_group=True))
    assert requests[-1] == (
        'https://api.sendblue.com/api/send-group-message',
        {
            'headers': {
                'sb-api-key-id': 'key-id',
                'sb-api-secret-key': 'key-secret',
                'content-type': 'application/json',
            },
            'json': {'group_id': 'group-1', 'from_number': '+15557654321', 'content': 'hello'},
        },
    )

    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC' + '1' * 32)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'auth-token')
    conversation_sid = 'CH' + '2' * 32
    asyncio.run(
        channel_chat.send_channel_message(
            'sms', conversation_sid, 'hello', is_group=True, provider_mode='twilio_conversations'
        )
    )
    assert requests[-1] == (
        f'https://conversations.twilio.com/v1/Conversations/{conversation_sid}/Messages',
        {'auth': ('AC' + '1' * 32, 'auth-token'), 'data': {'Body': 'hello'}},
    )


def test_sms_delivery_reuses_twilio_service(monkeypatch):
    sent = []

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        sent.append((fn, args))
        return 'SM1'

    monkeypatch.setattr(channel_chat, 'run_blocking', fake_run_blocking)
    asyncio.run(channel_chat.send_channel_message('sms', '+15551234567', 'hello'))
    assert sent[0][0] is channel_chat.send_sms
    assert sent[0][1] == ('+15551234567', 'hello')


def test_media_context_describes_images_without_exposing_provider_urls(monkeypatch):
    async def fake_download(_attachment):
        return b'image-bytes', 'image/jpeg', 'photo.jpg'

    async def fake_describe(_uid, encoded, mime_type):
        assert encoded
        assert mime_type == 'image/jpeg'
        return 'A diagram on a white background.'

    import services.channel_media as channel_media

    monkeypatch.setattr(channel_media, '_download_attachment', fake_download)
    monkeypatch.setattr(channel_media, 'describe_image', fake_describe)
    result = asyncio.run(
        channel_media.build_media_context(
            'uid-1',
            [{'source': 'telegram', 'file_id': 'file-1', 'filename': 'photo.jpg', 'mime_type': 'image/jpeg'}],
        )
    )
    assert 'A diagram on a white background.' in result
    assert '[Vision analysis for image attachment: photo.jpg (image/jpeg)]' in result
    assert 'do not claim the image is unavailable' in result
    assert 'file-1' not in result


def test_describe_image_preserves_mime_type_in_data_url(monkeypatch):
    captured = {}

    class FakeVisionModel:
        async def ainvoke(self, messages, *, config=None, max_completion_tokens=None):
            captured.update({'messages': messages, 'config': config})
            return SimpleNamespace(content='A test image.')

    import utils.llm.openglass as openglass

    monkeypatch.setattr(openglass, 'get_llm', lambda _feature: FakeVisionModel())
    monkeypatch.setattr(openglass, 'track_usage', lambda *_args, **_kwargs: nullcontext())
    result = asyncio.run(openglass.describe_image('uid-1', 'encoded', 'image/png'))

    assert result == 'A test image.'
    assert captured['messages'][0]['content'][1]['image_url']['url'] == 'data:image/png;base64,encoded'


def test_group_binding_never_falls_back_to_the_sender_personal_binding():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    token, _ = channels_db.issue_link_token('uid-personal', 'telegram', now=now, firestore_client=client)
    channels_db.consume_link_token('telegram', token, '42', '42', now=now, firestore_client=client)

    assert channels_db.get_binding('telegram', '42', '42', firestore_client=client)['uid'] == 'uid-personal'
    assert channels_db.get_binding('telegram', '42', '-999', firestore_client=client) is None
    assert channels_db.revoke_binding('telegram', '42', '-999', now=now, firestore_client=client) is False
    assert channels_db.get_binding('telegram', '42', '42', firestore_client=client)['uid'] == 'uid-personal'


def test_revoking_a_channel_chunks_writes_under_the_firestore_batch_cap():
    commits = []

    class CappedBatch:
        def __init__(self, inner):
            self._inner = inner
            self._writes = 0

        def update(self, ref, payload):
            self._writes += 1
            if self._writes > channels_db.FIRESTORE_MAX_BATCH_WRITES:
                raise ValueError('maximum 500 writes allowed per request')
            self._inner.update(ref, payload)

        def commit(self):
            commits.append(self._writes)
            return self._inner.commit()

    class CappedClient:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def batch(self):
            return CappedBatch(self._inner.batch())

    inner = MockFirestore()
    client = CappedClient(inner)
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    total = channels_db.FIRESTORE_MAX_BATCH_WRITES + 3
    for index in range(total):
        inner.collection('channel_bindings').document(f'binding-{index}').set(
            {
                'channel': 'telegram',
                'uid': 'uid-1',
                'channel_user_id': str(index),
                'channel_chat_id': str(index),
                'linked_at': now,
                'revoked_at': None,
            }
        )

    assert channels_db.revoke_channel('uid-1', 'telegram', now=now, firestore_client=client) == total
    assert commits == [channels_db.FIRESTORE_MAX_BATCH_WRITES, 3]
    assert channels_db.list_bindings('uid-1', firestore_client=inner) == []


def test_a_stale_processing_claim_is_reclaimed_instead_of_dropped():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    assert channels_db.claim_webhook_event('telegram', 'update-9', now=now, firestore_client=client) == (True, None)

    created, existing = channels_db.claim_webhook_event('telegram', 'update-9', now=now, firestore_client=client)
    assert not created
    assert existing['status'] == 'processing'

    expired = now + channels_db.WEBHOOK_PROCESSING_LEASE
    created, existing = channels_db.claim_webhook_event('telegram', 'update-9', now=expired, firestore_client=client)
    assert created
    assert existing['status'] == 'processing'

    stored = (
        client.collection('channel_webhook_events')
        .document(channels_db._event_id('telegram', 'update-9'))
        .get()
        .to_dict()
    )
    assert stored['attempts'] == 2
    assert stored['lease_expires_at'] == expired + channels_db.WEBHOOK_PROCESSING_LEASE
    assert stored['received_at'] == now


def test_a_legacy_claim_is_dated_by_received_at_not_treated_as_expired():
    """Events written before leases existed must not all become reclaimable at once.

    A pre-lease document has no `lease_expires_at`. Reading that as "expired"
    would let a second handler take an event the first picked up seconds before
    this deployed, and the user gets the reply twice. `received_at` dates it.
    """
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    ref = client.collection('channel_webhook_events').document(channels_db._event_id('telegram', 'legacy-1'))
    ref.create(
        {
            'channel': 'telegram',
            'provider_event_id': 'legacy-1',
            'status': 'processing',
            'received_at': now,
            'updated_at': now,
        }
    )

    # Still inside the window the lease would have covered: leave it alone.
    fresh = now + channels_db.WEBHOOK_PROCESSING_LEASE / 2
    created, existing = channels_db.claim_webhook_event('telegram', 'legacy-1', now=fresh, firestore_client=client)
    assert not created
    assert existing['status'] == 'processing'

    # Past it, the claim is genuinely abandoned and can be reclaimed.
    stale = now + channels_db.WEBHOOK_PROCESSING_LEASE
    created, _ = channels_db.claim_webhook_event('telegram', 'legacy-1', now=stale, firestore_client=client)
    assert created


def test_an_undatable_claim_is_reclaimable_rather_than_held_forever():
    """No lease and no received_at: nothing can date it, so it must not stick."""
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    ref = client.collection('channel_webhook_events').document(channels_db._event_id('sms', 'orphan-1'))
    ref.create({'channel': 'sms', 'provider_event_id': 'orphan-1', 'status': 'processing'})

    created, _ = channels_db.claim_webhook_event('sms', 'orphan-1', now=now, firestore_client=client)
    assert created


def test_a_failed_claim_is_released_for_immediate_retry_but_a_ready_reply_is_kept():
    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    channels_db.claim_webhook_event('sms', 'SM1', now=now, firestore_client=client)
    assert channels_db.release_webhook_claim('sms', 'SM1', now=now, firestore_client=client) is True
    created, existing = channels_db.claim_webhook_event('sms', 'SM1', now=now, firestore_client=client)
    assert created
    assert existing['status'] == 'failed'

    channels_db.update_webhook_event('sms', 'SM1', {'status': 'ready', 'reply': 'hi'}, firestore_client=client)
    assert channels_db.release_webhook_claim('sms', 'SM1', now=now, firestore_client=client) is False
    created, existing = channels_db.claim_webhook_event('sms', 'SM1', now=now, firestore_client=client)
    assert not created
    assert existing['status'] == 'ready'


def test_a_failing_handler_releases_its_claim_so_the_provider_retry_is_processed(monkeypatch):
    import routers.channels as channels_router

    client = MockFirestore()
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        if fn is channels_db.claim_webhook_event:
            return channels_db.claim_webhook_event(*args, now=now, firestore_client=client)
        if fn is channels_db.release_webhook_claim:
            return channels_db.release_webhook_claim(*args, now=now, firestore_client=client)
        raise AssertionError(fn)

    async def exploding_reply(_channel, _payload):
        raise RuntimeError('core chat exploded')

    monkeypatch.setattr(channels_router, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(channels_router, '_channel_reply', exploding_reply)

    payload = {'event_id': 'update-77', 'channel_user_id': '42', 'channel_chat_id': '42', 'text': 'hello'}
    with pytest.raises(RuntimeError):
        asyncio.run(channels_router._handle_payload('telegram', payload))

    delivered = {}

    async def working_reply(_channel, _payload):
        return 'answer'

    async def fake_send_and_record(channel, event_id, chat_id, reply, **kwargs):
        delivered.update({'channel': channel, 'event_id': event_id, 'chat_id': chat_id, 'reply': reply})

    monkeypatch.setattr(channels_router, '_channel_reply', working_reply)
    monkeypatch.setattr(channels_router, '_send_and_record', fake_send_and_record)
    assert asyncio.run(channels_router._handle_payload('telegram', payload)) == {'status': 'delivered'}
    assert delivered['reply'] == 'answer'


def test_over_quota_channel_messages_never_reach_the_media_pipeline(monkeypatch):
    calls = []

    class QuotaExceeded(Exception):
        pass

    def fake_enforce_chat_quota(_uid, *, platform):
        calls.append(('quota', platform))
        raise QuotaExceeded()

    async def fake_build_media_context(_uid, _attachments):
        calls.append(('media', None))
        return 'described'

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(channel_chat, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(channel_chat, 'enforce_chat_quota', fake_enforce_chat_quota)
    monkeypatch.setattr(channel_chat, 'build_media_context', fake_build_media_context)

    with pytest.raises(QuotaExceeded):
        asyncio.run(
            channel_chat.generate_channel_reply(
                'uid-1', 'telegram', 'hello', attachments=[{'source': 'telegram', 'file_id': 'file-1'}]
            )
        )
    assert calls == [('quota', 'telegram')]


def test_sms_delivery_stays_off_the_reserved_auth_executor(monkeypatch):
    from utils.executors import critical_executor, postprocess_executor

    used = []

    async def fake_run_blocking(executor, fn, *args, **kwargs):
        used.append(executor)
        return 'SM1'

    monkeypatch.setattr(channel_chat, 'run_blocking', fake_run_blocking)
    asyncio.run(channel_chat.send_channel_message('sms', '+15551234567', 'hello'))
    assert used == [postprocess_executor]
    assert critical_executor not in used
