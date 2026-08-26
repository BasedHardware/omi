"""Regression: a multi-channel listen session must not accumulate ``channel_mix_buffers`` when
there is no audio-bytes consumer.

``decide_multi_channel_mix`` and the teardown flush both return should_mix/flush=False when
``audio_bytes_send`` is None, so appending every inbound frame unconditionally (the old behavior)
left the per-channel buffers growing for the whole session (~64 KB/s for stereo) until the worker
ran out of memory, taking every co-located live session down with it. The append must obey the same
condition the drain and flush already use.

Exercises the real ``ListenReceiver._handle_multi_channel_audio`` with the real
``decide_multi_channel_mix``/``mix_n_channel_buffers``/``resample_pcm``; the receiver is a minimal
stand-in supplying only the attributes the method reads (``use_custom_stt=True`` skips the STT
branch, which is the realistic custom-STT multi-channel desktop case, and captured audio still
flows to the mix path).
"""

import asyncio
from types import MethodType, SimpleNamespace

import routers.listen.receiver as receiver

TARGET_SAMPLE_RATE = receiver.TARGET_SAMPLE_RATE


def _make_receiver(audio_bytes_send):
    recv = SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(codec='pcm', sample_rate=TARGET_SAMPLE_RATE, websocket=None),
            use_custom_stt=True,
            audio_bytes_send=audio_bytes_send,
            state=SimpleNamespace(last_audio_received_time=0.0),
        ),
        channel_id_to_index={0: 0, 1: 1},
        multi_opus_decoders=[None, None],
        stt_sockets_multi=[None, None],
        channel_mix_buffers=[bytearray(), bytearray()],
    )
    # Bind the real _capture so the mock exercises actual capture delegation.
    recv._capture = MethodType(receiver.ListenReceiver._capture, recv)
    return recv


def _frame(channel_id, payload):
    return bytes([channel_id]) + payload


async def _feed(recv, frames):
    for channel_id, payload in frames:
        await receiver.ListenReceiver._handle_multi_channel_audio(recv, _frame(channel_id, payload))


def test_multichannel_buffers_do_not_leak_without_audio_bytes_consumer():
    recv = _make_receiver(audio_bytes_send=None)
    pcm = b'\x01\x02' * 160  # 320 bytes
    asyncio.run(_feed(recv, [(0, pcm)] * 50))
    buffered = sum(len(b) for b in recv.channel_mix_buffers)
    # With no consumer nothing ever drains these buffers, so nothing may accumulate. The old code
    # held all 50 frames (~16000 bytes) and would keep growing for the whole session.
    assert buffered == 0


def test_multichannel_mix_still_drains_with_audio_bytes_consumer():
    sent = []
    recv = _make_receiver(audio_bytes_send=lambda mixed, ts: sent.append(mixed))
    pcm = b'\x01\x02' * 160
    # Feed both channels so decide_multi_channel_mix sees all buffers non-empty and mixes.
    asyncio.run(_feed(recv, [(0, pcm), (1, pcm)]))
    assert sent, "expected a mixed frame delivered to the audio-bytes consumer"
    assert sum(len(b) for b in recv.channel_mix_buffers) == 0


def test_multichannel_client_pcm_reaches_optional_parity_capture():
    captured = []
    recv = _make_receiver(audio_bytes_send=None)
    recv.host.capture_client_audio = captured.append
    pcm = b'\x01\x02' * 160

    asyncio.run(_feed(recv, [(0, pcm)]))

    assert captured == [pcm]


def _make_photo_receiver(*, use_custom_stt: bool):
    async def _noop_event(_event):
        return None

    recv = SimpleNamespace(
        host=SimpleNamespace(
            use_custom_stt=use_custom_stt,
            request=SimpleNamespace(uid='test-uid'),
            asend_event=_noop_event,
            transcripts=SimpleNamespace(photo_buffer=[]),
        ),
        image_chunks={},
    )
    return recv


async def _process_photo(recv, image_b64: str = 'ZmFrZS1pbWFnZQ=='):
    await receiver.ListenReceiver._process_photo(recv, image_b64, 'temp-1')


def test_custom_stt_photo_skips_omi_description_without_llm_byok_key(monkeypatch):
    """#7690: a custom-STT session without an LLM BYOK key must not pay for
    describe_image; the photo is still stored with a placeholder description."""
    recv = _make_photo_receiver(use_custom_stt=True)
    described = []

    async def _describe(_uid, _img):
        described.append(1)
        return 'a description'

    monkeypatch.setattr(receiver, 'describe_image', _describe)
    monkeypatch.setattr(receiver, 'request_has_llm_byok_key', lambda: False)
    monkeypatch.setattr(receiver.users_db, 'is_byok_active', lambda _uid: False)

    asyncio.run(_process_photo(recv))

    assert described == [], 'describe_image ran for a custom-STT session without an LLM BYOK key'
    assert len(recv.host.transcripts.photo_buffer) == 1
    photo = recv.host.transcripts.photo_buffer[0]
    assert photo.discarded is False
    assert 'Custom STT' in photo.description


def test_custom_stt_photo_uses_placeholder_when_byok_enrollment_lookup_fails(monkeypatch):
    """A failed enrollment read must fail closed without dropping the photo."""
    recv = _make_photo_receiver(use_custom_stt=True)
    described = []

    async def _describe(_uid, _img):
        described.append(1)
        return 'a description'

    monkeypatch.setattr(receiver, 'describe_image', _describe)
    monkeypatch.setattr(receiver, 'request_has_llm_byok_key', lambda: True)

    def _enrollment_failure(_uid):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(receiver.users_db, 'is_byok_active', _enrollment_failure)

    asyncio.run(_process_photo(recv))

    assert described == []
    assert len(recv.host.transcripts.photo_buffer) == 1
    assert 'Custom STT' in recv.host.transcripts.photo_buffer[0].description


def test_custom_stt_photo_runs_description_with_llm_byok_key(monkeypatch):
    """A custom-STT user with active BYOK enrollment and an OpenAI/Anthropic
    request key pays their own bill, so photo descriptions must still run."""
    recv = _make_photo_receiver(use_custom_stt=True)
    described = []

    async def _describe(_uid, _img):
        described.append(1)
        return 'a description'

    monkeypatch.setattr(receiver, 'describe_image', _describe)
    monkeypatch.setattr(receiver, 'request_has_llm_byok_key', lambda: True)
    monkeypatch.setattr(receiver.users_db, 'is_byok_active', lambda _uid: True)

    asyncio.run(_process_photo(recv))

    assert described, 'describe_image was skipped despite an LLM BYOK key'
    assert recv.host.transcripts.photo_buffer[0].description == 'a description'


def test_custom_stt_photo_skips_description_when_byok_header_present_but_inactive(monkeypatch):
    """WebSocket X-BYOK-* headers are copied into context without enrollment
    validation. A raw LLM header with inactive BYOK must not escape the gate."""
    recv = _make_photo_receiver(use_custom_stt=True)
    described = []
    active_checks = []

    async def _describe(_uid, _img):
        described.append(1)
        return 'a description'

    monkeypatch.setattr(receiver, 'describe_image', _describe)
    monkeypatch.setattr(receiver, 'request_has_llm_byok_key', lambda: True)
    monkeypatch.setattr(
        receiver.users_db,
        'is_byok_active',
        lambda uid: active_checks.append(uid) or False,
    )

    asyncio.run(_process_photo(recv))

    assert active_checks == ['test-uid']
    assert described == [], 'describe_image ran for inactive BYOK despite a raw LLM header'
    assert 'Custom STT' in recv.host.transcripts.photo_buffer[0].description


def test_omi_stt_photo_always_runs_description(monkeypatch):
    """Omi-STT sessions are unaffected: descriptions always run, and the BYOK
    enrollment/key lookups are deferred so the hot path never pays for them."""
    recv = _make_photo_receiver(use_custom_stt=False)
    described = []
    byok_calls = []
    active_calls = []

    async def _describe(_uid, _img):
        described.append(1)
        return 'a description'

    monkeypatch.setattr(receiver, 'describe_image', _describe)
    monkeypatch.setattr(receiver, 'request_has_llm_byok_key', lambda: byok_calls.append('llm') or True)
    monkeypatch.setattr(
        receiver.users_db,
        'is_byok_active',
        lambda uid: active_calls.append(uid) or True,
    )

    asyncio.run(_process_photo(recv))

    assert described, 'describe_image was skipped for an Omi-STT session'
    assert byok_calls == [], f'BYOK key lookup fired on the Omi-STT photo path: {byok_calls}'
    assert active_calls == [], f'is_byok_active fired on the Omi-STT photo path: {active_calls}'
