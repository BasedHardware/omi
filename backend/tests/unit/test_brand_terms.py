import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers.listen.receiver import ListenReceiver, STTService
from utils.stt import soniox as soniox_module
from utils.stt.brand_terms import normalize_brand_segments, normalize_brand_terms
from utils.stt.pre_recorded import _segments_as_objects


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('omi', 'Omi'),
        ('OMI', 'Omi'),
        ('oMi', 'Omi'),
        ("OMI's device", "Omi's device"),
        ('omis', 'Omis'),
        ('OMIs', 'Omis'),
        ('Omie', 'Omi'),
        ('omies', 'Omis'),
        ("omie's", "Omi's"),
        ('O M I', 'Omi'),
        ('O. M. I.', 'Omi.'),
        ('It is called O m I.', 'It is called Omi.'),
        ('o m i', 'Omi'),
        ('I love omi.', 'I love Omi.'),
        ('Did you ask omi? What is OMI?', 'Did you ask Omi? What is Omi?'),
        ('omi & me, omi+ai', 'Omi & me, omi+ai'),
        ('omi.me app.omi.me omi.dmg', 'omi.me app.omi.me omi.dmg'),
        ('https://omi.me @omi user@omi.me', 'https://omi.me @omi user@omi.me'),
        ('https://example.com/search?q=omi&omi=1', 'https://example.com/search?q=omi&omi=1'),
        ('example.com?Omi=1', 'example.com?Omi=1'),
        ('/omi _omi omi_ai omi-app #omi', '/omi _omi omi_ai omi-app #omi'),
        ('omi\u0301', 'omi\u0301'),
        ('omibeta OmiPie OmiWalkets', 'omibeta OmiPie OmiWalkets'),
        ('Omni omni Omni hotels omni voice', 'Omni omni Omni hotels omni voice'),
        (
            'Omnia homie Oh me Naomi Amy Ami Umi omy Omic omit omitted omission',
            'Omnia homie Oh me Naomi Amy Ami Umi omy Omic omit omitted omission',
        ),
        ('o mi casa; Om i', 'o mi casa; Om i'),
        ('mon ami', 'mon ami'),
    ],
)
def test_normalize_brand_terms_table(source, expected):
    assert normalize_brand_terms(source) == expected


def test_normalize_brand_terms_leaves_empty_text():
    assert normalize_brand_terms('') == ''


def test_normalize_brand_terms_is_idempotent():
    text = "O M I and omie, OMIs, and OMI's."
    normalized = normalize_brand_terms(text)
    assert normalize_brand_terms(normalized) == normalized


def test_live_segments_normalize_text_in_place_and_skip_non_strings():
    segments = [{'text': 'omies use OMI', 'other': 1}, {'text': None}]
    assert normalize_brand_segments(segments) is segments
    assert segments == [{'text': 'Omis use Omi', 'other': 1}, {'text': None}]


def test_enqueue_normalizes_before_failover_capture_stamp_and_queue(monkeypatch):
    receiver = object.__new__(ListenReceiver)
    receiver.host = MagicMock()
    receiver.host.use_custom_stt = True
    receiver._pending_live_failover = MagicMock(to_mode='soniox', settled=False)
    receiver.speaker_provider_epoch = MagicMock()
    receiver.host.transcripts = MagicMock()
    captured = []
    receiver._capture = lambda _kind, segments: captured.append(segments[0]['text'])
    segments = [{'text': 'OMI is here'}]

    receiver._enqueue_stt_segments(segments, provider='soniox')

    assert receiver._pending_live_failover.note_transcript.call_args.args[0][0]['text'] == 'Omi is here'
    assert captured == ['Omi is here']
    assert receiver.speaker_provider_epoch.stamp.call_args.args[0][0]['text'] == 'Omi is here'
    assert receiver.host.transcripts.enqueue.call_args.args[0][0]['text'] == 'Omi is here'


def test_prerecorded_segments_normalize_after_capitalize():
    result = _segments_as_objects(
        [{'text': 'we use omie daily', 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 4.0, 'end': 5.0}]
    )
    assert result[0].text == 'We use Omi daily'


@pytest.mark.parametrize(('flag', 'expected'), [(None, None), ('false', None), ('true', ['Omi', 'omi.me'])])
async def test_soniox_context_terms_are_gated_and_sanitized(monkeypatch, flag, expected):
    ws = AsyncMock()
    connect = AsyncMock(return_value=ws)
    socket_ctor = MagicMock()
    monkeypatch.setattr(soniox_module.websockets, 'connect', connect)
    monkeypatch.setattr(soniox_module, 'SafeSonioxSocket', socket_ctor)
    monkeypatch.setenv('SONIOX_API_KEY', 'test-key')
    if flag is None:
        monkeypatch.delenv('SONIOX_CONTEXT_TERMS', raising=False)
    else:
        monkeypatch.setenv('SONIOX_CONTEXT_TERMS', flag)

    await soniox_module.process_audio_soniox(
        lambda _segments: None,
        16000,
        'en',
        keywords=[' Omi ', 'Omi', '', 'omi.me', 'x' * 51],
    )

    config = json.loads(ws.send.await_args.args[0])
    assert config.get('context', {}).get('terms') == expected


@pytest.mark.parametrize('same_provider', [False, True])
async def test_legacy_receiver_passes_vocabulary_to_soniox(monkeypatch, same_provider):
    receiver = object.__new__(ListenReceiver)
    receiver.host = MagicMock()
    receiver.host.vocabulary = ['Omi', 'omi.me']
    receiver.host.stt_service = STTService.soniox
    receiver.host.stt_language = 'en'
    receiver.host.language_profile = None
    monkeypatch.setattr('routers.listen.receiver.managed_chain_enabled', lambda _host: False)
    process_audio = AsyncMock(return_value=object())
    monkeypatch.setattr('routers.listen.receiver.process_audio_soniox', process_audio)
    if not same_provider:

        async def connect_primary(**kwargs):
            return await kwargs['connect_primary'](), kwargs['primary_service']

        monkeypatch.setattr('routers.listen.receiver.connect_stt_socket_with_fallback', connect_primary)

    await receiver._create_stt_socket(lambda _segments: None, 16000, same_provider=same_provider)

    assert process_audio.await_args.kwargs['keywords'] == ['Omi', 'omi.me']
