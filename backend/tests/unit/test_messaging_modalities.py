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


@pytest.fixture
def voice_environment(monkeypatch):
    from utils import chat

    # Tiny tone fixtures exercise container decoding, not speech detection.
    monkeypatch.setattr(chat, 'linear16_pcm_is_silent', lambda *a, **k: False)
    monkeypatch.setattr(chat, 'resolve_voice_message_language', lambda uid, language: 'en')
    return chat


@pytest.mark.parametrize(
    'filename', ['voice.ogg', 'voice.m4a', 'voice.caf', 'voice.mp3', 'voice.wav', 'voice.webm', 'video.mp4']
)
def test_real_container_transcription_passes_only_pcm_to_stt(monkeypatch, filename, voice_environment):
    calls = []

    def stt(data, *, sample_rate, channels, encoding, diarize, language, model, keywords):
        assert sample_rate == 16000 and channels == 1 and encoding == 'linear16' and diarize is False
        assert 3000 <= len(data) <= 6000 and len(data) % 2 == 0
        assert not data.startswith((b'OggS', b'RIFF', b'caff', b'\x1aE\xdf\xa3'))
        calls.append(data)
        return [{'text': 'test transcript.', 'timestamp': [0, 0.12], 'speaker': 'SPEAKER_00'}]

    monkeypatch.setattr(voice_environment, 'prerecorded_from_bytes', stt)
    assert ChatMediaStore().transcribe((FIXTURES / 'audio' / filename).read_bytes(), 'u') == 'Test transcript.'
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

    # Exercise the decoded-PCM cap even on a host with no installed decoder.
    monkeypatch.setattr(media, 'MAX_MEDIA_SECONDS', 0.05)
    monkeypatch.setattr(media, 'get_media_decoder', lambda: 'fixture-decoder')

    def decoded(command, **kwargs):
        Path(command[-1]).write_bytes(b'\0' * 1602)

    monkeypatch.setattr(media.subprocess, 'run', decoded)
    with pytest.raises(MediaPreparationError) as failed:
        decode_audio(b'container fixture')
    assert failed.value.reason == 'media_duration' and failed.value.reply == DURATION_REPLY


def test_real_decoded_duration_cap_is_enforced(monkeypatch):
    from utils.messaging.adapters import media

    monkeypatch.setattr(media, 'MAX_MEDIA_SECONDS', 0.05)
    with pytest.raises(MediaPreparationError) as failed:
        decode_audio((FIXTURES / 'audio' / 'voice.ogg').read_bytes())
    assert failed.value.reason == 'media_duration' and failed.value.reply == DURATION_REPLY


@pytest.mark.parametrize('words', [[], [{'text': '', 'timestamp': [0, 0.12], 'speaker': 'SPEAKER_00'}]])
def test_empty_stt_is_typed(monkeypatch, words, voice_environment):
    monkeypatch.setattr(voice_environment, 'prerecorded_from_bytes', lambda *a, **k: words)
    with pytest.raises(MediaPreparationError) as failed:
        ChatMediaStore().transcribe((FIXTURES / 'audio' / 'voice.ogg').read_bytes(), 'u')
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
def test_media_failure_worker_sends_one_specific_reply_and_releases(
    adapter, monkeypatch, failure, expected, voice_environment
):
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

    monkeypatch.setattr(voice_environment, 'prerecorded_from_bytes', stt)
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

    assert find(manifest) is None  # Cloud Run must retain its live policy on merge.
    policy = json.dumps(
        {
            'telegram': {'enabled': True, 'cohort': '*'},
            'imessage': {'enabled': True, 'cohort': ['synthetic-rollout-member'], 'seat_cap': 'off'},
        }
    )
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', policy)
    monkeypatch.delenv('OMI_MESSAGING_KILL_SWITCH_DOC', raising=False)
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda uid, **kw: SimpleNamespace(plan='plus'))
    store = messaging.MessagingStore(firestore_client=MagicMock())

    def capacity(*args):
        raise AssertionError('No capacity IO allowed')

    monkeypatch.setattr(store, 'capacity', capacity)
    david = 'synthetic-rollout-member'
    monkeypatch.setattr('config.messaging.in_rollout_cohort', lambda owner, name, **kwargs: owner == david)
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


@pytest.mark.parametrize('bad_first', [False, True])
def test_album_worker_runs_one_turn_with_both_photos(adapter, monkeypatch, bad_first):
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
        if bad_first and len(calls) == 1:
            raise MediaPreparationError('media_file', FILE_REPLY)
        return Artifact('file-' + str(len(calls)), 'image/jpeg', len(data), 'photo.jpg')

    monkeypatch.setattr(adapter.media, 'ingest', ingest)
    monkeypatch.setattr(chat, 'add_files_to_chat_session', lambda *a: None)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    turns = []

    async def turn(uid, session, message, *a, **k):
        turns.append(message)

    monkeypatch.setattr(gateway, '_turn', turn)
    assert asyncio.run(gateway.process(path)) is True
    assert len(turns) == 1 and len(turns[0].media) == (1 if bad_first else 2) and not store.leases
    if bad_first:
        assert 'Attachment 1:' in turns[0].text and FILE_REPLY in turns[0].text


def test_delivered_media_refusal_is_not_followed_by_generic_apology(adapter, monkeypatch, voice_environment):
    message = parsed(adapter, 'voice')[0]
    store = MemoryStore()
    store.identities[(message.channel, message.provider, message.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(message)

    async def download(attachment):
        return (FIXTURES / 'audio' / 'voice.ogg').read_bytes()

    monkeypatch.setattr(adapter, 'download', download)
    monkeypatch.setattr(voice_environment, 'prerecorded_from_bytes', lambda *a, **k: [])

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


def test_media_preparation_bounds_concurrent_download_buffers(adapter, monkeypatch):
    from utils.messaging.adapters import base

    message = parsed(adapter, 'photo')[0]

    async def run():
        ready, release = asyncio.Event(), asyncio.Event()
        active = peak = 0

        async def prepare(*args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 8:
                ready.set()
            await release.wait()
            active -= 1
            return message

        monkeypatch.setattr(base, 'prepare_media', prepare)

        async def guard():
            pass

        jobs = [asyncio.create_task(adapter.prepare(message, 'u', {'id': 'session'}, guard)) for _ in range(9)]
        await asyncio.wait_for(ready.wait(), 2)
        assert active == 8
        release.set()
        await asyncio.gather(*jobs)
        assert peak == 8

    asyncio.run(run())


@pytest.mark.parametrize(
    'filename,mime', [('photo.bin', 'image/jpeg'), ('photo', 'image/jpeg'), ('iphone.heic', 'image/heic')]
)
def test_real_upload_path_normalizes_image_document_names(monkeypatch, filename, mime):
    from database import chat
    from utils.other import chat_file, storage

    uploads, rows = [], []

    def create(*, file, purpose):
        name, stream = file
        with Image.open(stream) as image:
            assert image.format == 'JPEG'
        assert purpose == 'vision' and Path(name).suffix in ('.jpg', '.jpeg')
        uploads.append(name)
        return SimpleNamespace(id='uploaded-file', filename=name)

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=create))
    monkeypatch.setattr(storage, 'upload_multi_chat_files', lambda paths, uid: {})
    monkeypatch.setattr(chat, 'add_multi_files', lambda uid, files: rows.extend(files))
    if mime == 'image/heic':
        data = (FIXTURES / 'audio' / 'photo.heic').read_bytes()
    else:
        output = BytesIO()
        Image.new('RGB', (16, 12), (220, 100, 30)).save(output, 'JPEG')
        data = output.getvalue()
    artifact = ChatMediaStore().ingest('u', InboundAttachment('file', filename, mime), data)
    assert len(uploads) == len(rows) == 1 and artifact.mime_type == 'image/jpeg'
    assert rows[0]['name'] == artifact.name and rows[0]['size'] == artifact.size


def test_contact_embedded_photo_does_not_hide_later_fields_or_enter_context():
    card = (
        b'BEGIN:VCARD\nFN:Name\nPHOTO;ENCODING=b:'
        + b'x' * 1_000_000
        + b'\nTEL:+123\nEMAIL:name@example.test\nEND:VCARD'
    )
    text = contact_text(card)
    assert len(text) < 300 and '+123' in text and 'name@example.test' in text
    assert 'PHOTO' not in text


def test_unreadable_contact_is_a_specific_typed_refusal():
    with pytest.raises(MediaPreparationError) as failed:
        contact_text(b'not a card')
    assert 'contact card' in failed.value.reply and 'Sorry' not in failed.value.reply


def test_telegram_contact_vcard_email_and_structured_fallback(adapter):
    if adapter.channel == 'telegram':
        message = parsed(
            adapter,
            text='',
            contact={
                'first_name': 'Name',
                'phone_number': '+123',
                'vcard': 'BEGIN:VCARD\nEMAIL:name@example.test\nEND:VCARD',
            },
        )[0]
        assert 'name@example.test' in inbound_evidence(message)
        malformed = parsed(
            adapter, text='', contact={'first_name': 'Name', 'phone_number': '+123', 'vcard': 'not a card'}
        )[0]
        assert '+123' in inbound_evidence(malformed) and 'Name' in malformed.text


def test_ten_requested_photos_reach_file_model_in_sync_and_stream(monkeypatch):
    from utils.other import chat_file
    from database import chat

    ids = ['file-' + str(i) for i in range(10)]
    rows = [
        dict(
            id=i,
            name=i + '.jpg',
            mime_type='image/jpeg',
            openai_file_id=i,
            created_at=datetime.now(timezone.utc),
            thumbnail='',
        )
        for i in ids
    ]

    def fetch(uid, *, files_id, limit):
        assert uid == 'u' and files_id == ids
        return rows[:limit]  # Honor the production query's bound, unlike an unconditional fake.

    monkeypatch.setattr(chat, 'get_chat_files_desc', fetch)
    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'u'

    def ask(question, files, video_window=None):
        assert {f.id for f in files} == set(ids)
        return 'all ten'

    monkeypatch.setattr(tool, '_ask_files', ask)
    assert tool.process_chat_with_file('photos?', ids) == 'all ten'

    async def ask_stream(question, files, callback):
        assert {f.id for f in files} == set(ids)
        return 'all ten'

    monkeypatch.setattr(tool, '_ask_files_stream', ask_stream)

    async def run():
        from utils.retrieval.agentic import AsyncStreamingCallback

        result = await tool.process_chat_with_file_stream('photos?', ids, callback=AsyncStreamingCallback())
        assert result == 'all ten'

    asyncio.run(run())


def test_unmarked_linq_sticker_media_preserves_photo_handling(adapter):
    if adapter.channel == 'imessage':
        message = parsed(
            adapter,
            parts=[
                {
                    'type': 'media',
                    'id': 'file',
                    'url': 'https://cdn.linqapp.com/test',
                    'filename': 'image.png',
                    'mime_type': 'image/png',
                    'size_bytes': 100,
                    'reactions': [],
                }
            ],
        )[0]
        assert message.command is None and message.attachments[0].mime_type == 'image/png'


def test_too_many_attachments_refuses_before_download(adapter):
    message = parsed(adapter, 'photo')[0]
    message = replace(message, attachments=message.attachments * 11)

    async def guard():
        pass

    with pytest.raises(MediaPreparationError) as failed:
        asyncio.run(adapter.prepare(message, 'u', {'id': 'session'}, guard))
    assert failed.value.reply == 'Please send up to 10 attachments at once.'
    assert not adapter.transport.downloads


def test_ogg_through_real_parakeet_normalization(monkeypatch):
    import httpx
    import wave
    from utils.stt import pre_recorded
    from utils import chat

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')
    monkeypatch.setattr(chat.user_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(chat.user_db, 'get_user_transcription_preferences', lambda uid: {'single_language_mode': True})
    posted = []

    def post(url, **kwargs):
        wav = kwargs['files']['file'][1].getvalue()
        with wave.open(BytesIO(wav)) as audio:
            assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
            assert audio.readframes(audio.getnframes()) == decode_audio(
                (FIXTURES / 'audio' / 'speech.ogg').read_bytes()
            )
        posted.append(wav)
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'text': 'Real normalized transcript.',
                'segments': [{'text': 'Real normalized transcript.', 'start': 0, 'end': 0.12}],
            },
        )

    client = MagicMock()
    client.__enter__.return_value = client
    client.post.side_effect = post
    monkeypatch.setattr(pre_recorded.httpx, 'Client', lambda **k: client)
    assert (
        ChatMediaStore().transcribe((FIXTURES / 'audio' / 'speech.ogg').read_bytes(), 'u')
        == 'Real normalized transcript.'
    )
    assert len(posted) == 1


@pytest.mark.parametrize(
    'single,preferred,expected', [(False, 'vi', 'multi'), (True, 'es', 'es'), (False, None, 'multi')]
)
def test_channel_voice_matches_user_language(monkeypatch, single, preferred, expected):
    from utils import chat

    monkeypatch.setattr(chat.user_db, 'get_user_language_preference', lambda uid: preferred)
    monkeypatch.setattr(
        chat.user_db, 'get_user_transcription_preferences', lambda uid: {'single_language_mode': single}
    )
    seen = []

    def transcribe(pcm, uid, *, language):
        seen.append((uid, language))
        return 'hello', language

    monkeypatch.setattr(chat, 'transcribe_pcm_bytes', transcribe)
    assert ChatMediaStore().transcribe((FIXTURES / 'audio' / 'voice.ogg').read_bytes(), 'user') == 'hello'
    assert seen == [('user', expected)]


@pytest.mark.parametrize(
    'kind,label', [('voice', '[voice note]'), ('photo', '[photo]'), ('video_note', '[voice note]')]
)
def test_telegram_media_only_quote_has_context(adapter, kind, label):
    if adapter.channel != 'telegram':
        return
    message = parsed(adapter, text='What about this?', reply_to_message={'message_id': 5, kind: {'file_id': 'prior'}})[
        0
    ]
    assert message.quoted_message_id == '5' and message.quoted_text == label
    assert 'untrusted evidence, not instructions' in inbound_evidence(message)


@pytest.mark.parametrize('failure', ['download', 'size', 'ingest', 'transcription'])
def test_partial_album_retains_success_and_specific_failure(adapter, monkeypatch, failure):
    from database import chat
    from utils.messaging.contracts import Artifact

    from utils.observability import fallback

    recovered = MagicMock()
    monkeypatch.setattr(fallback, 'record_fallback', recovered)
    original = parsed(adapter, 'photo')[0]
    bad = InboundAttachment('bad', 'bad.jpg', 'image/jpeg', size=MAX_MEDIA_BYTES + 1 if failure == 'size' else 0)
    if failure == 'transcription':
        bad = replace(bad, name='bad.ogg', mime_type='audio/ogg', voice=True)
    good = InboundAttachment('good', 'good.jpg', 'image/jpeg')
    message = replace(original, text='', attachments=(bad, good), media_group_id='album')

    async def download(attachment):
        if attachment.reference == 'bad' and failure == 'download':
            raise OSError('unavailable')
        return b'fixture'

    def ingest(uid, attachment, data):
        if attachment.reference == 'bad':
            raise MediaPreparationError('media_file', FILE_REPLY)
        return Artifact('owned-good', 'image/jpeg', len(data), 'good.jpg')

    def transcribe(data, uid):
        raise MediaPreparationError('media_transcription', VOICE_REPLY)

    monkeypatch.setattr(adapter, 'download', download)
    monkeypatch.setattr(adapter.media, 'ingest', ingest)
    monkeypatch.setattr(adapter.media, 'transcribe', transcribe)
    monkeypatch.setattr(chat, 'add_files_to_chat_session', lambda *a: None)

    async def guard():
        pass

    result = asyncio.run(adapter.prepare(message, 'u', {'id': 's'}, guard))
    assert [a.file_store_ref for a in result.media] == ['owned-good']
    assert 'Attachment 1:' in result.text and 'Sorry, I could not finish' not in result.text
    assert recovered.call_count == 1 and recovered.call_args.kwargs['outcome'] == 'degraded'


def test_audio_uses_app_sync_pool(adapter, monkeypatch):
    from utils.messaging.adapters import media

    calls = []

    async def blocking(executor, fn, *args):
        calls.append(executor)
        return 'transcript'

    async def download(attachment):
        return b'audio'

    async def guard():
        pass

    monkeypatch.setattr(media, 'run_blocking', blocking)
    monkeypatch.setattr(adapter, 'download', download)
    result = asyncio.run(adapter.prepare(parsed(adapter, 'voice')[0], 'u', {'id': 's'}, guard))
    assert 'transcript' in result.text
    assert calls == [media.sync_executor] and media.storage_executor not in calls


def test_pcm_retry_preserves_encoding_and_exact_wav_frames(monkeypatch):
    import httpx
    import wave as _wave
    from utils.stt import pre_recorded as pr

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    pcm = b'\x00\x01' * 1600
    posted = []
    response = httpx.Response(
        200, request=httpx.Request('POST', 'http://parakeet.invalid'), json={'text': 'Hello world', 'segments': []}
    )
    client = MagicMock()
    client.__enter__.return_value = client

    def post(url, **kwargs):
        wav = kwargs['files']['file'][1].getvalue()
        posted.append(wav)
        with _wave.open(BytesIO(wav)) as audio:
            assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
            assert audio.readframes(audio.getnframes()) == pcm
        if len(posted) == 1:
            raise httpx.ConnectError('transient')
        return response

    client.post.side_effect = post
    monkeypatch.setattr(pr.httpx, 'Client', lambda **k: client)
    words = pr.parakeet_prerecorded_from_bytes(pcm, encoding='linear16', diarize=False)
    assert isinstance(words, list) and words[0]['text'] == 'Hello world'
    assert len(posted) == 2 and posted[0] == posted[1]


@pytest.mark.asyncio
async def test_album_late_during_media_preparation_attaches_before_generation(adapter, monkeypatch):
    if adapter.channel != 'telegram':
        return
    first = replace(parsed(adapter, 'photo')[0], media_group_id='late-album')
    second = replace(first, provider_message_id='later', text='late caption')
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(first)
    store.jobs[path]['album_ready_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    from utils.messaging.contracts import Artifact

    async def prepare(message, uid, session, guard):
        if not message.media:
            assert store.enqueue(second) == path
        return replace(message, media=(*message.media, Artifact('owned', 'image/jpeg', 1, 'p.jpg')), attachments=())

    monkeypatch.setattr(adapter, 'prepare', prepare)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    turns = []

    async def turn(uid, session, message, *a, **k):
        turns.append(message)
        assert store.jobs[path]['generation_started_at']
        third = replace(first, provider_message_id='last')
        followup = store.enqueue(third)
        assert followup != path
        assert store.enqueue(replace(first, provider_message_id='out-of-order')) == followup
        assert store.enqueue(third) is None
        assert len(store.jobs[followup]['payload']['attachments']) == 2

    monkeypatch.setattr(gateway, '_turn', turn)
    assert await gateway.process(path) is True
    assert len(turns) == 1 and len(turns[0].media) == 2 and 'late caption' in turns[0].text


@pytest.mark.asyncio
async def test_failed_first_batch_preserves_late_readable_photo(adapter, monkeypatch):
    if adapter.channel != 'telegram':
        return
    from utils.messaging.contracts import Artifact

    first = replace(parsed(adapter, 'photo')[0], media_group_id='partial-late')
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(first)
    store.jobs[path]['album_ready_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    calls = []

    async def prepare(message, uid, session, guard):
        calls.append(message)
        if len(calls) == 1:
            store.enqueue(replace(first, provider_message_id='readable-late'))
            raise MediaPreparationError('media_download', 'Synthetic download refusal')
        return replace(message, media=(Artifact('file', 'image/jpeg', 1, 'p.jpg'),), attachments=())

    monkeypatch.setattr(adapter, 'prepare', prepare)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    turns = []

    async def turn(uid, session, message, *a, **k):
        turns.append(message)

    monkeypatch.setattr(gateway, '_turn', turn)
    assert await gateway.process(path) is True
    assert len(turns) == 1 and len(turns[0].media) == 1
    assert 'Synthetic download refusal' in turns[0].text


@pytest.mark.asyncio
async def test_worker_failure_logs_only_bounded_reason(adapter, monkeypatch, caplog):
    first = parsed(adapter, 'text')[0]
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u', active=True, generation='g'
    )
    path = store.enqueue(first)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)

    class PrivateFailure(Exception):
        reason = 'private_exception_data'

    async def fail(*a, **k):
        raise PrivateFailure('private_exception_data')

    monkeypatch.setattr(gateway, '_turn', fail)
    await gateway.process(path)
    assert 'reason=worker_error' in caplog.text
    assert 'private_exception_data' not in caplog.text


@pytest.mark.asyncio
async def test_album_reload_never_reintroduces_disabled_voice(adapter, monkeypatch):
    if adapter.channel != 'telegram':
        return
    from utils.messaging.contracts import Artifact

    photo = parsed(adapter, 'photo')[0]
    voice = InboundAttachment('disabled-audio', 'voice.ogg', 'audio/ogg', voice=True)
    first = replace(photo, media_group_id='voice-preference', attachments=(*photo.attachments, voice))
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u',
        active=True,
        generation='g',
        voice_notes=False,
    )
    path = store.enqueue(first)
    store.jobs[path]['album_ready_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    batches = []

    async def prepare(message, uid, session, guard):
        batches.append(message.attachments)
        assert not any(a.voice for a in message.attachments)
        if len(batches) == 1:
            store.enqueue(replace(first, provider_message_id='late-audio', attachments=(voice,)))
        return replace(message, media=message.media or (Artifact('photo', 'image/jpeg', 1, 'p.jpg'),), attachments=())

    monkeypatch.setattr(adapter, 'prepare', prepare)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    turns = []

    async def turn(uid, session, message, *a, **k):
        turns.append(message)

    monkeypatch.setattr(gateway, '_turn', turn)
    assert await gateway.process(path) is True
    assert len(turns) == 1 and len(turns[0].media) == 1
    assert len(batches) == 2 and len(batches[0]) == 1 and batches[1] == ()


@pytest.mark.asyncio
@pytest.mark.parametrize('late_photo', [False, True])
async def test_voice_disabled_album_seals_notice_or_consumes_late_photo(adapter, monkeypatch, late_photo):
    if adapter.channel != 'telegram':
        return
    from utils.messaging.contracts import Artifact

    photo = parsed(adapter, 'photo')[0]
    voice = InboundAttachment('disabled-audio', 'v.ogg', 'audio/ogg', voice=True)
    first = replace(photo, text='', media_group_id='all-voice-off', attachments=(voice,))
    store = MemoryStore()
    store.identities[(first.channel, first.provider, first.external_user_id)] = dict(
        uid='u',
        active=True,
        generation='g',
        voice_notes=False,
    )
    path = store.enqueue(first)
    store.jobs[path]['album_ready_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    seal = store.seal_album
    seals = []

    def race(path, count):
        seals.append(count)
        if late_photo and len(seals) == 1:
            store.enqueue(
                replace(photo, text='', provider_message_id='late-readable', media_group_id=first.media_group_id)
            )
        return seal(path, count)

    monkeypatch.setattr(store, 'seal_album', race)
    batches, turns = [], []

    async def prepare(message, uid, session, guard):
        assert message.attachments and not any(a.voice for a in message.attachments)
        batches.append(message)
        return replace(message, media=(Artifact('photo', 'image/jpeg', 1, 'p.jpg'),), attachments=())

    async def turn(uid, session, message, *a, **k):
        turns.append(message)

    monkeypatch.setattr(adapter, 'prepare', prepare)
    gateway = Gateway(adapter, store=store, admission=lambda *a: None, rate_limit=lambda *a: None)
    monkeypatch.setattr(gateway, '_turn', turn)
    assert await gateway.process(path) is True
    assert len(turns) == len(batches) == int(late_photo)
    assert store.jobs[path]['generation_started_at'] and store.jobs[path]['status'] == 'done'
