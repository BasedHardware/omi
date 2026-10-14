"""Real container decoding and authenticated modality-to-worker regressions; no provider IO."""

import asyncio
import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from PIL import Image

from config.messaging import channel_policy
from database import messaging
from testing.messaging.adapter_fakes import FixtureLedger, FixtureTransport, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging import access
from utils.messaging.adapters.linq import IMessageAdapter, LinqProvider
from utils.messaging.adapters.media import (
    ChatMediaStore,
    MediaPreparationError,
    decode_audio,
    normalize_image,
    contact_text,
    MAX_MEDIA_BYTES,
    VOICE_REPLY,
    DURATION_REPLY,
    SIZE_REPLY,
    FILE_REPLY,
)
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.contracts import InboundAttachment
from utils.messaging.gateway import Gateway, inbound_evidence

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'messaging' / 'adapters'


@pytest.fixture(params=['telegram', 'linq'])
def adapter(request):
    transport, ledger = FixtureTransport(), FixtureLedger()
    if request.param == 'telegram':
        return TelegramAdapter(
            '000:test', 'test_secret', streaming='none', transport=transport, ledger=ledger, sleep=no_sleep
        )
    provider = LinqProvider(
        'test', 'whsec_' + base64.b64encode(b'x' * 32).decode(), transport=transport, sleep=no_sleep
    )
    return IMessageAdapter(provider, transport=transport, ledger=ledger, sleep=no_sleep)


def parsed(adapter, kind='text', /, **fields: Any):
    value = json.loads((FIXTURES / (adapter.provider + '-' + kind + '.json')).read_bytes())
    target = value['message'] if adapter.channel == 'telegram' else value['data']
    target.update(fields)
    return adapter.parse(json.dumps(value).encode())


@pytest.mark.parametrize(
    'filename', ['voice.ogg', 'voice.m4a', 'voice.caf', 'voice.mp3', 'voice.wav', 'voice.webm', 'video.mp4']
)
def test_real_container_transcription_passes_only_pcm_to_stt(monkeypatch, filename):
    from utils.stt import pre_recorded

    calls = []

    def stt(data, *, sample_rate, channels, encoding, diarize):
        assert sample_rate == 16000 and channels == 1 and encoding == 'linear16' and diarize is False
        assert 3000 <= len(data) <= 6000 and len(data) % 2 == 0
        assert not data.startswith((b'OggS', b'RIFF', b'caff', b'\x1aE\xdf\xa3'))
        calls.append(data)
        return [{'word': 'test'}, {'punctuated_word': 'transcript.'}]

    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', stt)
    assert ChatMediaStore().transcribe((FIXTURES / 'audio' / filename).read_bytes()) == 'test transcript.'
    assert len(calls) == 1


def test_real_heic_conversion():
    attachment = InboundAttachment('id', 'iphone.HEIC', 'image/heic')
    converted, data = normalize_image(attachment, (FIXTURES / 'audio' / 'photo.heic').read_bytes())
    assert converted.name == 'iphone.jpg' and converted.mime_type == 'image/jpeg'
    with Image.open(BytesIO(data)) as image:
        assert image.format == 'JPEG' and image.size == (16, 12)


def test_invalid_audio_and_size_are_typed():
    with pytest.raises(MediaPreparationError) as failed:
        decode_audio(b'not audio')
    assert failed.value.reply == VOICE_REPLY
    with pytest.raises(MediaPreparationError) as failed:
        decode_audio(b'x' * (MAX_MEDIA_BYTES + 1))
    assert failed.value.reply == SIZE_REPLY


def test_decoded_duration_cap_is_enforced(monkeypatch):
    from utils.messaging.adapters import media

    # Run a real container through FFmpeg with a smaller local test cap.
    monkeypatch.setattr(media, 'MAX_MEDIA_SECONDS', 0.05)
    with pytest.raises(MediaPreparationError) as failed:
        decode_audio((FIXTURES / 'audio' / 'voice.ogg').read_bytes())
    assert failed.value.reply == DURATION_REPLY


@pytest.mark.parametrize('words', [[], [{'word': ''}]])
def test_empty_stt_is_typed(monkeypatch, words):
    from utils.stt import pre_recorded

    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', lambda *a, **k: words)
    with pytest.raises(MediaPreparationError) as failed:
        ChatMediaStore().transcribe((FIXTURES / 'audio' / 'voice.ogg').read_bytes())
    assert failed.value.reply == VOICE_REPLY


@pytest.mark.parametrize(
    'mime,name',
    [('audio/x-caf', 'memo.caf'), ('audio/amr', 'memo.amr'), ('audio/mp4', 'memo.m4a'), ('video/mp4', 'clip.mp4')],
)
def test_linq_media_audio_routed_to_transcription(adapter, mime, name):
    if adapter.channel != 'imessage':
        return
    msg = parsed(
        adapter, parts=[{'type': 'media', 'url': 'https://cdn.linqapp.com/test', 'filename': name, 'mime_type': mime}]
    )[0]
    assert msg.attachments[0].voice


@pytest.mark.parametrize('field', ['voice', 'audio', 'video', 'video_note', 'document'])
def test_telegram_audio_fields_and_image_documents(adapter, field):
    if adapter.channel != 'telegram':
        return
    msg = parsed(
        adapter,
        text='',
        **{
            field: {
                'file_id': 'file',
                'mime_type': 'image/jpeg' if field == 'document' else 'audio/ogg',
                'file_name': 'image.jpg' if field == 'document' else 'memo.ogg',
                'duration': 2,
            }
        },
    )[0]
    assert msg.attachments[0].voice == (field != 'document')
    assert msg.attachments[0].duration_seconds == 2


@pytest.mark.parametrize(
    'field', ['poll', 'dice', 'game', 'invoice', 'successful_payment', 'new_chat_members', 'unknown_service']
)
def test_non_turn_telegram_events_are_silent(adapter, field):
    if adapter.channel == 'telegram':
        assert parsed(adapter, text='', **{field: {'value': 1}}) == ()


@pytest.mark.parametrize('event', ['message.reaction', 'message.delivered', 'message.read', 'poll.vote', 'unknown'])
def test_linq_non_message_events_are_silent(adapter, event):
    if adapter.channel == 'imessage':
        body = json.loads((FIXTURES / 'linq-text.json').read_bytes())
        body['event_type'] = event
        assert adapter.parse(json.dumps(body).encode()) == ()


def test_location_contacts_quotes_are_untrusted_context(adapter):
    if adapter.channel == 'telegram':
        message = parsed(
            adapter,
            text='What about this?',
            venue={'location': {'latitude': 1, 'longitude': 2}, 'title': 'Place', 'address': 'Street'},
            contact={'first_name': 'Name', 'phone_number': '+123'},
            reply_to_message={'text': 'Quoted text'},
        )[0]
    else:
        message = parsed(
            adapter,
            parts=[
                {'type': 'text', 'value': 'What about this?'},
                {'type': 'location', 'latitude': 1, 'longitude': 2, 'name': 'Place', 'address': 'Street'},
            ],
            reply_to={'text': 'Quoted text'},
        )[0]
    evidence = inbound_evidence(message)
    assert 'Quoted text' in evidence and 'Shared location' in evidence and '1,2' in evidence
    assert 'untrusted' in evidence
    card = contact_text(b'BEGIN:VCARD\r\nFN:Name\r\nTEL:+123\r\nEMAIL:name@example.test\r\nEND:VCARD')
    assert 'Name' in card and '+123' in card and 'name@example.test' in card and 'do not save unless asked' in card


@pytest.mark.parametrize(
    'failure,expected',
    [
        ('size', SIZE_REPLY),
        ('duration', DURATION_REPLY),
        ('decode', VOICE_REPLY),
        ('empty', VOICE_REPLY),
        ('stt', VOICE_REPLY),
        ('unsupported', FILE_REPLY),
        ('download', "I couldn't download that attachment. Could you send it again?"),
    ],
)
def test_media_failure_worker_sends_one_specific_reply_and_releases(adapter, monkeypatch, failure, expected):
    from utils.stt import pre_recorded

    incoming = parsed(adapter, 'voice')[0]
    attachment = incoming.attachments[0]
    if failure == 'size':
        attachment = replace(attachment, size=MAX_MEDIA_BYTES + 1)
    elif failure == 'duration':
        attachment = replace(attachment, duration_seconds=601)
    elif failure == 'unsupported':
        attachment = replace(attachment, voice=False, mime_type='application/zip', name='file.zip')
    incoming = replace(incoming, attachments=(attachment,))

    async def download(attachment):
        if failure == 'download':
            raise RuntimeError('provider failure')
        return b'broken' if failure == 'decode' else (FIXTURES / 'audio' / 'voice.ogg').read_bytes()

    monkeypatch.setattr(adapter, 'download', download)

    def stt(*args, **kwargs):
        if failure == 'stt':
            raise RuntimeError('network failure')
        return []

    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', stt)
    adapter.media = ChatMediaStore()
    if failure == 'unsupported':
        from utils.other.chat_file import UnsupportedChatFileError

        def ingest(*args):
            raise UnsupportedChatFileError('unsupported')

        monkeypatch.setattr(adapter.media, 'ingest', ingest)
    store = MemoryStore()
    store.identities[(incoming.channel, incoming.provider, incoming.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(incoming)
    sent = []

    async def send(message, **kwargs):
        sent.append(kwargs['text'])

    monkeypatch.setattr(adapter, 'send', send)

    async def turn(*args, **kwargs):
        raise AssertionError('Media refusal must not invoke an LLM')

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda *a: None, rate_limit=lambda *a: None)
    asyncio.run(gateway.process(path))
    assert sent == [expected] and not store.leases and store.jobs[path]['status'] == 'done'
    assert all('Sorry, I could not finish' not in text for text in sent)


@pytest.mark.parametrize('text', ['🙂', '❤️', '👍🏽'])
def test_emoji_ack_skips_llm(adapter, text):
    incoming = (
        parsed(adapter, text=text)[0]
        if adapter.channel == 'telegram'
        else parsed(adapter, parts=[{'type': 'text', 'value': text}])[0]
    )
    assert incoming.command == 'ack'


def test_album_has_one_durable_job_and_no_early_claim(adapter):
    if adapter.channel != 'telegram':
        return
    first = replace(parsed(adapter, 'photo')[0], media_group_id='album')
    second = replace(first, provider_message_id='11', text='second caption')
    store = MemoryStore()
    path = store.enqueue(first)
    assert store.enqueue(second) == path and store.enqueue(first) is None
    assert store.claim_next(path) is None
    now = datetime.now(timezone.utc) + timedelta(seconds=4)
    claimed = store.claim_next(path, now=now)
    assert claimed is not None
    claimed_path, payload = claimed
    assert claimed_path == path and len(payload['attachments']) == 2
    assert 'second caption' in payload['text'] and payload['provider_message_id'] == '11'
    assert store.claim_next(path, now=now) is None
    store.complete(path)
    assert store.enqueue(second) is None


def test_exact_prod_policy_all_paid_telegram_legacy_imessage_without_seat_io(monkeypatch):
    manifest = yaml.safe_load((Path(__file__).parents[2] / 'deploy/runtime_env/prod.overlay.yaml').read_text())

    def find(value):
        if isinstance(value, dict):
            if 'OMI_MESSAGING_CHANNEL_POLICY' in value:
                return value['OMI_MESSAGING_CHANNEL_POLICY']['value']
            for nested in value.values():
                found = find(nested)
                if found:
                    return found
        return None

    policy = find(manifest)
    assert policy
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', policy)
    monkeypatch.delenv('OMI_MESSAGING_KILL_SWITCH_DOC', raising=False)
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda uid, **kw: SimpleNamespace(plan='plus'))
    store = messaging.MessagingStore(firestore_client=MagicMock())

    def capacity(*args):
        raise AssertionError('No capacity IO allowed')

    monkeypatch.setattr(store, 'capacity', capacity)
    david = 'vi7SA9ckQCe4ccobWNxlbdcNdC23'
    access.require_access('paid-outsider', 'telegram')
    with pytest.raises(access.AccessDenied):
        access.require_access('paid-outsider', 'imessage')
    for channel in ('telegram', 'imessage'):
        access.require_access(david, channel)
        store.check_capacity(david, channel)
        store.assert_link_capacity(SimpleNamespace(channel=channel), {'uid': david})
    assert channel_policy('imessage')['seat_cap'] is None and channel_policy('imessage')['plans'] is None
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda uid, **kw: SimpleNamespace(plan='basic'))
    with pytest.raises(access.AccessDenied):
        access.require_access(david, 'telegram')


@pytest.mark.parametrize('cap', ['none', 'OFF', True, -1, {}, None])
def test_invalid_seat_disable_spellings_fail_closed(monkeypatch, cap):
    monkeypatch.setenv(
        'OMI_MESSAGING_CHANNEL_POLICY', json.dumps({'imessage': {'enabled': True, 'cohort': '*', 'seat_cap': cap}})
    )
    assert channel_policy('imessage')['enabled'] is False


@pytest.mark.parametrize('suffix', ['pdf', 'txt', 'csv', 'docx', 'xlsx', 'pptx'])
def test_documents_use_real_file_chat_allowlist(suffix):
    from utils.other.chat_file import File

    file = File('fixture.' + suffix)
    file.get_mime_type()
    assert file.is_document()


@pytest.mark.parametrize('kind', ['sticker', 'animation'])
def test_telegram_entertainment_acknowledges_without_attachments(adapter, kind):
    if adapter.channel == 'telegram':
        message = parsed(adapter, text='', **{kind: {'file_id': 'fixture'}})[0]
        assert message.command == 'ack' and not message.attachments


def test_linq_gif_sticker_and_unknown_part_classification(adapter):
    if adapter.channel == 'imessage':
        for fields in ({'mime_type': 'image/gif'}, {'mime_type': 'image/png', 'sticker': True}):
            message = parsed(adapter, parts=[{'type': 'media', 'url': 'https://cdn.linqapp.com/test', **fields}])[0]
            assert message.command == 'ack' and not message.attachments
        assert parsed(adapter, parts=[{'type': 'imessage_app', 'value': 'unknown'}])[0].command == 'unsupported'
        assert parsed(adapter, parts=[{'type': 'tapback', 'value': 'like'}]) == ()


def test_linq_id_only_reply_resolves_bounded_accepted_event(adapter, monkeypatch):
    if adapter.channel != 'imessage':
        return
    message = parsed(
        adapter, parts=[{'type': 'text', 'value': 'What about this one?'}], reply_to={'message_id': 'original'}
    )[0]
    assert message.quoted_message_id == 'original'
    store = MemoryStore()
    link = dict(uid='u', active=True, generation='g')
    store.identities[(message.channel, message.provider, message.external_user_id)] = link
    session = store.session('u', message, link)
    store.append_event(
        'u', session['id'], {'id': 'prior', 'provider_message_ids': ['original'], 'content': 'Original quoted text'}
    )
    path = store.enqueue(message)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    seen = []

    async def turn(uid, session, message, *args, **kwargs):
        seen.append(inbound_evidence(message))

    monkeypatch.setattr(gateway, '_turn', turn)
    asyncio.run(gateway.process(path))
    assert len(seen) == 1 and 'Original quoted text' in seen[0]


def test_no_cap_consume_skips_capacity_documents(monkeypatch):
    # Only transaction transport is synthetic; execute the production redemption.
    client, tx = MagicMock(), MagicMock()
    client.transaction.return_value = tx
    now = datetime.now(timezone.utc)
    proof = client.collection.return_value.document.return_value
    proof.get.return_value.to_dict.return_value = dict(
        uid='u', channel='imessage', provider='linq', expires_at=now + timedelta(minutes=5)
    )
    store = messaging.MessagingStore(firestore_client=client)
    identity = MagicMock()
    identity.get.return_value.to_dict.return_value = {}
    identity.id = 'link'
    monkeypatch.setattr(store, 'identity', lambda *a: identity)
    user = MagicMock()
    user.get.return_value.to_dict.return_value = {'name': 'fixture'}
    monkeypatch.setattr(store, 'user', lambda *a: user)
    monkeypatch.setattr(messaging, 'account_deletion_document', lambda *a, **k: MagicMock())
    monkeypatch.setattr(messaging, '_deletion_blocks', lambda *a: False)
    monkeypatch.setattr(messaging.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', '{"imessage":{"enabled":true,"cohort":["u"],"seat_cap":"off"}}')

    def capacity(*a):
        raise AssertionError('must not consult seats')

    monkeypatch.setattr(store, 'capacity', capacity)
    message = SimpleNamespace(channel='imessage', provider='linq', external_user_id='sender', display_name=None)
    assert store.consume('proof', message, now=now)['uid'] == 'u'


def test_production_claim_respects_album_ready_clock(monkeypatch):
    client, tx = MagicMock(), MagicMock()
    client.transaction.return_value = tx
    ref = client.document.return_value
    ref.parent.parent.id = 'identity'
    ref.path = 'channel_identities/identity/inbox/album'
    now = datetime.now(timezone.utc)
    snapshot = MagicMock()
    snapshot.reference.path = ref.path
    snapshot.to_dict.return_value = dict(
        status='pending', created_at=now, payload='{"text":"album"}', album_ready_at=now + timedelta(seconds=1.2)
    )
    ref.parent.where.return_value.order_by.return_value.stream.return_value = [snapshot]
    monkeypatch.setattr(messaging.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(messaging.encryption, 'decrypt', lambda value, uid: value)
    store = messaging.MessagingStore(firestore_client=client)
    assert store.claim_next(ref.path, now=now) is None and not tx.update.called
    assert store.claim_next(ref.path, now=now + timedelta(seconds=2)) == (ref.path, {'text': 'album'})
    assert tx.update.call_count == 1


def test_linq_unknown_parts_are_silent(adapter):
    if adapter.channel == 'imessage':
        assert parsed(adapter, parts=[{'type': 'unknown_service'}]) == ()


def test_null_plan_policy_does_not_hide_behind_seat_off(monkeypatch):
    monkeypatch.setenv(
        'OMI_MESSAGING_CHANNEL_POLICY', '{"imessage":{"enabled":true,"cohort":"*","seat_cap":"off","plans":null}}'
    )
    assert channel_policy('imessage')['enabled'] is False


def test_ack_worker_has_one_light_reply_and_no_model_turn(adapter, monkeypatch):
    message = (
        parsed(adapter, text='🙂')[0]
        if adapter.channel == 'telegram'
        else parsed(adapter, parts=[{'type': 'text', 'value': '🙂'}])[0]
    )
    store = MemoryStore()
    store.identities[(message.channel, message.provider, message.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(message)
    sent, limited = [], []

    async def send(message, **kwargs):
        sent.append(kwargs['text'])

    monkeypatch.setattr(adapter, 'send', send)

    def turn(*a, **k):
        raise AssertionError('Acknowledgements must skip the model')

    gateway = Gateway(
        adapter, store=store, turn=turn, admission=lambda *a: None, rate_limit=lambda uid: limited.append(uid)
    )
    assert asyncio.run(gateway.process(path)) is True
    assert sent == ['Got it 🙂'] and limited == ['u'] and not store.leases


def test_album_worker_runs_one_turn_with_both_photos(adapter, monkeypatch):
    if adapter.channel != 'telegram':
        return
    from database import chat
    from utils.messaging.contracts import Artifact

    first = replace(parsed(adapter, 'photo')[0], media_group_id='album')
    second = replace(first, provider_message_id='11')
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(first)
    assert store.enqueue(second) == path
    store.jobs[path]['album_ready_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    calls = []

    def ingest(uid, attachment, data):
        calls.append(attachment.reference)
        return Artifact('file-' + str(len(calls)), 'image/jpeg', len(data), 'photo.jpg')

    monkeypatch.setattr(adapter.media, 'ingest', ingest)
    monkeypatch.setattr(chat, 'add_files_to_chat_session', lambda *a: None)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    turns = []

    async def turn(uid, session, message, *a, **k):
        turns.append(message)

    monkeypatch.setattr(gateway, '_turn', turn)
    assert asyncio.run(gateway.process(path)) is True
    assert len(turns) == 1 and len(turns[0].media) == 2 and not store.leases


def test_delivered_media_refusal_is_not_followed_by_generic_apology(adapter, monkeypatch):
    from utils.stt import pre_recorded

    message = parsed(adapter, 'voice')[0]
    store = MemoryStore()
    store.identities[(message.channel, message.provider, message.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(message)

    async def download(attachment):
        return (FIXTURES / 'audio' / 'voice.ogg').read_bytes()

    monkeypatch.setattr(adapter, 'download', download)
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', lambda *a, **k: [])

    def complete(path):
        raise RuntimeError('Tombstone unavailable')

    monkeypatch.setattr(store, 'complete', complete)
    sent = []

    async def send(message, **kwargs):
        sent.append(kwargs['text'])

    monkeypatch.setattr(adapter, 'send', send)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    asyncio.run(gateway.process(path))
    assert sent == [VOICE_REPLY] and not store.leases
