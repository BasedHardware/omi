"""Replay the vendor's documented nullable/interleaved terminal protocol.

Guards both vendor cause preservation and exactly-once pending tail emission;
the flag-off oracle pins the original adapter behavior for rollback.
"""

import asyncio
import json
from unittest.mock import patch

import pytest

from utils.stt import streaming
from utils.stt.modulate_protocol import MAX_PENDING_UTTERANCES, ModulatePendingUtterances, modulate_death_reason
from utils.stt.stream_close import bounded_stream_close_reason


class Frames:
    def __init__(self, messages):
        self.messages = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return json.dumps(next(self.messages))
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, data):
        pass

    async def close(self):
        pass


def partial(identifier, text, start=None, speaker=None):
    return {
        'type': 'partial_utterance',
        'partial_utterance': {'utterance_uuid': identifier, 'text': text, 'start_ms': start, 'speaker': speaker},
    }


async def receive(messages, callback, monkeypatch, *, enabled=True):
    monkeypatch.setenv('MODULATE_STREAM_PROTOCOL_GUARD_ENABLED', str(enabled).lower())
    socket = streaming.SafeModulateSocket(Frames(messages), callback, asyncio.get_running_loop())
    try:
        await socket._recv_task
    finally:
        socket._send_task.cancel()
        await asyncio.gather(socket._send_task, return_exceptions=True)
    return socket


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_nullable_preview_cannot_erase_a_terminal_vendor_fault(monkeypatch, enabled):
    emitted = []
    socket = await receive(
        [partial('a', 'Bonjour'), {'type': 'error', 'error': 'Internal server error'}],
        emitted.extend,
        monkeypatch,
        enabled=enabled,
    )
    assert socket.is_connection_dead
    assert socket.typed_death_reason == ('modulate_serve_error' if enabled else None)
    assert socket._done_event.is_set() is enabled
    assert emitted == []


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_normal_done_after_nullable_preview_is_not_a_provider_death(monkeypatch, enabled):
    socket = await receive(
        [partial('a', 'Bonjour'), {'type': 'done', 'duration_ms': 1000}],
        lambda segments: None,
        monkeypatch,
        enabled=enabled,
    )
    assert socket.is_connection_dead is (not enabled)
    assert socket._done_event.is_set() is enabled


@pytest.mark.asyncio
async def test_interleaved_final_only_retires_its_own_preview(monkeypatch):
    emitted = []
    socket = await receive(
        [
            partial('a', 'Bonjour', 100, 1),
            partial('b', 'Guten', 200, 2),
            partial('b', 'Guten Tag', None, None),
            {
                'type': 'utterance',
                'utterance': {
                    'utterance_uuid': 'a',
                    'text': 'Bonjour.',
                    'start_ms': 100,
                    'duration_ms': 80,
                    'speaker': 1,
                },
            },
            {'type': 'done', 'duration_ms': 1000},
        ],
        emitted.extend,
        monkeypatch,
    )
    assert [(segment['text'], segment['speaker'], segment['start']) for segment in emitted] == [
        ('Bonjour.', 'SPEAKER_00', 0.1),
        ('Guten Tag', 'SPEAKER_01', 0.2),
    ]
    assert not socket.is_connection_dead
    socket._flush_partial()
    assert len(emitted) == 2


@pytest.mark.asyncio
async def test_tail_callback_exception_preserves_terminal_error_and_completion(monkeypatch):
    def failed_callback(segments):
        raise RuntimeError('local consumer failed')

    socket = await receive(
        [partial('a', 'Bonjour', 100, 1), {'type': 'error', 'error': 'Internal server error'}],
        failed_callback,
        monkeypatch,
    )
    assert socket.typed_death_reason == 'modulate_serve_error'
    assert socket._done_event.is_set()


@pytest.mark.parametrize(
    ('message', 'reason'),
    [
        ('Insufficient credits.', 'provider_budget_exhausted'),
        (
            'Concurrent request limit reached. Please retry after your in-flight requests complete.',
            'provider_rate_limited',
        ),
        ('Invalid API key.', 'provider_auth_rejected'),
        ('The request is not permitted.', 'provider_auth_rejected'),
        ('API key does not have access to this model.', 'provider_auth_rejected'),
    ],
)
@pytest.mark.asyncio
async def test_documented_account_and_concurrency_refusals_keep_their_class(monkeypatch, message, reason):
    socket = await receive([{'type': 'error', 'error': message}], lambda segments: None, monkeypatch)
    assert socket.typed_death_reason == reason
    assert modulate_death_reason(message) is None  # flag-off rollback


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_invalid_audio_is_not_counted_as_a_vendor_connection_loss(monkeypatch, enabled):
    with patch.object(streaming, 'record_stt_stream_close') as record:
        socket = await receive(
            [{'type': 'error', 'error': 'Invalid input audio'}], lambda segments: None, monkeypatch, enabled=enabled
        )
    assert socket.typed_death_reason == 'other'
    recorded = record.call_args.kwargs['reason']
    assert bounded_stream_close_reason(recorded) == ('provider_invalid_request' if enabled else 'connection_lost')


def test_empty_preview_retracts_pending_text_and_invalid_timing_never_invents_an_anchor():
    pending = ModulatePendingUtterances()
    pending.observe({'utterance_uuid': 'a', 'text': 'Hola', 'start_ms': 100})
    pending.observe({'utterance_uuid': 'a', 'text': '', 'start_ms': None})
    pending.observe({'utterance_uuid': 'b', 'text': 'Bonjour', 'start_ms': -1})
    pending.observe({'text': 'Guten Tag', 'start_ms': None})
    assert pending.flush() == []
    assert not pending


def test_preview_cache_is_bounded_and_finals_do_not_need_a_cached_preview():
    pending = ModulatePendingUtterances()
    for index in range(MAX_PENDING_UTTERANCES + 1):
        pending.observe({'utterance_uuid': str(index), 'text': str(index), 'start_ms': index, 'speaker': 2})
    pending.finalized({'utterance_uuid': '0'})
    segments = pending.flush()
    assert len(segments) == MAX_PENDING_UTTERANCES
    assert segments[0]['text'] == '1'
    assert all(segment['speaker'] == 'SPEAKER_01' for segment in segments)


def test_preroll_is_filtered_per_utterance_and_tails_keep_capture_order():
    pending = ModulatePendingUtterances()
    for name, start in [('new', 2100), ('preroll', 500), ('old', 2000)]:
        pending.observe({'utterance_uuid': name, 'text': name, 'start_ms': start})
    assert [segment['text'] for segment in pending.flush(preseconds=1)] == ['old', 'new']
