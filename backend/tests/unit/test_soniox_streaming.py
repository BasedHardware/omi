"""Soniox streams token deltas, not utterances, so the socket must assemble segments.

Every message carries a ``tokens`` list whose entries flip ``is_final`` once committed;
non-final tokens are revised in place and forwarding them would emit text that the model
later retracts. Consecutive final tokens from one speaker must coalesce into a single
segment, because the listen pipeline expects provider-shaped segments rather than words.

Soniox is opt-in: it is absent from the policy defaults, so a deployment that does not
name it in STT_SERVICE_MODELS must never select it.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.stt_provider_policy import (
    SONIOX_PROVIDER,
    STTServingSurface,
    default_models_for_surface,
    provider_is_enabled,
)
from utils.stt.streaming import SafeSonioxSocket, process_audio_soniox


class FakeWebSocket:
    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)

        return gen()


def _drive(inbound, preseconds=0):
    captured = []

    async def main():
        ws = FakeWebSocket(inbound)
        sock = SafeSonioxSocket(ws, captured.append, asyncio.get_running_loop(), preseconds=preseconds)
        await asyncio.sleep(0.05)
        return sock

    sock = asyncio.run(main())
    return captured, sock


def test_only_final_tokens_reach_the_transcript():
    captured, _ = _drive(
        [
            {'tokens': [{'text': 'He', 'is_final': False, 'speaker': 1, 'start_ms': 0, 'duration_ms': 100}]},
            {'tokens': [{'text': 'Hello ', 'is_final': True, 'speaker': 1, 'start_ms': 0, 'duration_ms': 500}]},
        ]
    )
    texts = [segment['text'] for batch in captured for segment in batch]
    assert texts == ['Hello']


def test_consecutive_tokens_from_one_speaker_coalesce():
    captured, _ = _drive(
        [
            {
                'tokens': [
                    {'text': 'Hello ', 'is_final': True, 'speaker': 1, 'start_ms': 0, 'duration_ms': 400},
                    {'text': 'there', 'is_final': True, 'speaker': 1, 'start_ms': 400, 'duration_ms': 400},
                ]
            }
        ]
    )
    batch = captured[0]
    assert len(batch) == 1
    assert batch[0]['text'] == 'Hello there'
    assert batch[0]['speaker'] == 'SPEAKER_00'
    assert batch[0]['end'] == pytest.approx(0.8)


def test_a_speaker_change_starts_a_new_segment():
    captured, _ = _drive(
        [
            {
                'tokens': [
                    {'text': 'Hi ', 'is_final': True, 'speaker': 1, 'start_ms': 0, 'duration_ms': 300},
                    {'text': 'Bye', 'is_final': True, 'speaker': 2, 'start_ms': 300, 'duration_ms': 300},
                ]
            }
        ]
    )
    batch = captured[0]
    assert [segment['speaker'] for segment in batch] == ['SPEAKER_00', 'SPEAKER_01']


def test_a_missing_speaker_field_does_not_crash_the_socket():
    captured, sock = _drive([{'tokens': [{'text': 'Hello', 'is_final': True, 'start_ms': 0, 'duration_ms': 200}]}])
    assert captured[0][0]['speaker'] == 'SPEAKER_00'
    assert not sock.is_connection_dead


def test_an_error_message_marks_the_socket_dead_with_its_reason():
    _, sock = _drive(
        [
            {
                'tokens': [],
                'error_code': 402,
                'error_type': 'organization_balance_exhausted',
                'error_message': 'Organization balance exhausted.',
            }
        ]
    )
    assert sock.is_connection_dead
    assert '402' in (sock.death_reason or '')
    assert 'organization_balance_exhausted' in (sock.death_reason or '')


def test_preseconds_audio_is_not_emitted_as_transcript():
    captured, _ = _drive(
        [
            {
                'tokens': [
                    {'text': 'profile ', 'is_final': True, 'speaker': 1, 'start_ms': 0, 'duration_ms': 500},
                    {'text': 'real', 'is_final': True, 'speaker': 1, 'start_ms': 3000, 'duration_ms': 500},
                ]
            }
        ],
        preseconds=2,
    )
    texts = [segment['text'] for batch in captured for segment in batch]
    assert texts == ['real']


@pytest.mark.asyncio
async def test_auto_detect_sessions_send_no_language_hint():
    ws = AsyncMock()
    with patch.object(
        __import__('utils.stt.streaming', fromlist=['websockets']).websockets, 'connect', new=AsyncMock(return_value=ws)
    ), patch('utils.stt.streaming.SafeSonioxSocket', MagicMock()), patch.dict(
        'os.environ', {'SONIOX_API_KEY': 'test-key'}
    ):
        await process_audio_soniox(lambda _s: None, 16000, 'multi')
    config = json.loads(ws.send.await_args.args[0])
    assert 'language_hints' not in config
    assert config['enable_language_identification'] is True
    assert config['enable_speaker_diarization'] is True


@pytest.mark.asyncio
async def test_a_declared_language_is_sent_as_a_hint():
    ws = AsyncMock()
    with patch.object(
        __import__('utils.stt.streaming', fromlist=['websockets']).websockets, 'connect', new=AsyncMock(return_value=ws)
    ), patch('utils.stt.streaming.SafeSonioxSocket', MagicMock()), patch.dict(
        'os.environ', {'SONIOX_API_KEY': 'test-key'}
    ):
        await process_audio_soniox(lambda _s: None, 16000, 'ja')
    config = json.loads(ws.send.await_args.args[0])
    assert config['language_hints'] == ['ja']


def test_soniox_is_streaming_only_and_off_by_default():
    assert provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.PTT)
    for surface in STTServingSurface:
        assert 'soniox' not in default_models_for_surface(surface)
