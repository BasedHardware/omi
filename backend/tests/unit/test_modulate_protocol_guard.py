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
    # Full UUID-bearing Partial Utterance Result shape in the same docs.
    return documented_partial(utterance_uuid=identifier, text=text, start_ms=start, speaker=speaker)


def documented_partial(**updates):
    # Exact UUID-less example in the vendor's Server messages section:
    # https://docs.modulate.ai/api-reference/stt/streaming
    message = {
        'text': 'Hello, how are',
        'start_ms': 0,
        'speaker': 1,
        'emotion': None,
        'accent': None,
        'deepfake_score': None,
    }
    message.update(updates)
    return {'type': 'partial_utterance', 'partial_utterance': message}


def documented_final(**updates):
    message = {
        'utterance_uuid': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        'text': 'Hello, how are you today?',
        'start_ms': 0,
        'duration_ms': 2500,
        'speaker': 1,
        'language': 'en',
        'emotion': 'Neutral',
        'accent': 'American',
        'deepfake_score': None,
    }
    message.update(updates)
    return {'type': 'utterance', 'utterance': message}


TERMINALS = [
    {'type': 'done', 'duration_ms': 45000},
    {'type': 'error', 'error': 'Internal server error'},
]


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
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_documented_uuidless_preview_is_not_reemitted_after_final(monkeypatch, enabled, terminal):
    emitted = []
    socket = await receive(
        [documented_partial(), documented_final(), terminal], emitted.extend, monkeypatch, enabled=enabled
    )
    assert emitted == [
        {
            'speaker': 'SPEAKER_00',
            'start': 0.0,
            'end': 2.5,
            'text': 'Hello, how are you today?',
            'is_user': False,
            'person_id': None,
            '_provider_language': 'en',
        }
    ]
    assert socket.typed_death_reason == ('modulate_serve_error' if terminal['type'] == 'error' else None)
    assert socket._done_event.is_set()
    socket._flush_partial()
    assert len(emitted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
@pytest.mark.parametrize('start', [100, 3000])
async def test_interleaved_uuidless_preview_survives_an_unrelated_final(monkeypatch, terminal, start):
    emitted = []
    socket = await receive(
        [
            documented_partial(),
            documented_partial(text='Another utterance', start_ms=start, speaker=2),
            documented_final(),
            terminal,
        ],
        emitted.extend,
        monkeypatch,
    )
    # Even a start inside the final's span cannot prove coverage: the
    # documented preview has no duration and may extend beyond that final.
    assert [(segment['text'], segment['start']) for segment in emitted] == [
        ('Hello, how are you today?', 0.0),
        ('Another utterance', start / 1000.0),
    ]
    assert not socket._has_pending_partial()
    socket._flush_partial()
    assert len(emitted) == 2


@pytest.mark.parametrize('start', [None, 100, 3000])
@pytest.mark.parametrize('identifier', [None, 'final-a'])
@pytest.mark.parametrize('preview_text', ['Another utterance', 'Hello, how were you?', 'he', '!!!'])
def test_uncovered_anonymous_preview_remains_pending(start, identifier, preview_text):
    pending = ModulatePendingUtterances()
    preview = documented_partial(text=preview_text, start_ms=start)['partial_utterance']
    pending.observe(preview)
    pending.finalized(documented_final(utterance_uuid=identifier)['utterance'])
    assert pending
    # Supplying a known timestamp later lets terminal flush demonstrate that
    # even the null-timed pending text was retained by the unrelated final.
    pending.observe({**preview, 'start_ms': 3000})
    assert [segment['text'] for segment in pending.flush()] == [preview_text]


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
@pytest.mark.parametrize('start', [None, 0])
@pytest.mark.parametrize(
    ('preview_text', 'final_text'),
    [
        ('Hello, how are', 'Hello, how are you today?'),
        ('  HELLO,  how\nare! ', 'Hello how are'),
        ('how are', 'Hello, how are you today?'),
    ],
)
async def test_anonymous_preview_retires_only_when_final_contains_normalized_text(
    monkeypatch, terminal, start, preview_text, final_text
):
    emitted = []
    socket = await receive(
        [documented_partial(text=preview_text, start_ms=start), documented_final(text=final_text), terminal],
        emitted.extend,
        monkeypatch,
    )
    assert [segment['text'] for segment in emitted] == [final_text]
    assert not socket._has_pending_partial()
    socket._flush_partial()
    assert len(emitted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_uuidless_final_retirement_preserves_identified_and_later_previews(monkeypatch, terminal):
    emitted = []
    socket = await receive(
        [
            documented_partial(),
            partial('b', 'Identified tail', 3000, 2),
            documented_final(),
            documented_partial(text='Later anonymous tail', start_ms=4000, speaker=3),
            terminal,
        ],
        emitted.extend,
        monkeypatch,
    )
    assert [(segment['text'], segment['speaker'], segment['start']) for segment in emitted] == [
        ('Hello, how are you today?', 'SPEAKER_00', 0.0),
        ('Identified tail', 'SPEAKER_01', 3.0),
        ('Later anonymous tail', 'SPEAKER_02', 4.0),
    ]
    socket._flush_partial()
    assert len(emitted) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_documented_uuidless_null_timing_does_not_inherit_an_unproven_anchor(monkeypatch, terminal):
    emitted = []
    socket = await receive(
        [documented_partial(), documented_partial(text='Hello, how are you', start_ms=None, speaker=None), terminal],
        emitted.extend,
        monkeypatch,
    )
    assert emitted == []
    assert socket._done_event.is_set()
    assert socket.typed_death_reason == ('modulate_serve_error' if terminal['type'] == 'error' else None)


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
            documented_final(utterance_uuid='a', text='Bonjour.', start_ms=100, duration_ms=80, language='fr'),
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
    pending.observe(partial('a', 'Hola', 100)['partial_utterance'])
    pending.observe(partial('a', '', None)['partial_utterance'])
    pending.observe(partial('b', 'Bonjour', -1)['partial_utterance'])
    pending.observe(documented_partial(text='Guten Tag', start_ms=None)['partial_utterance'])
    assert pending.flush() == []
    assert not pending


def test_preview_cache_is_bounded_and_finals_do_not_need_a_cached_preview():
    pending = ModulatePendingUtterances()
    for index in range(MAX_PENDING_UTTERANCES + 1):
        pending.observe(partial(str(index), str(index), index, 2)['partial_utterance'])
    pending.finalized(documented_final(utterance_uuid='0')['utterance'])
    segments = pending.flush()
    assert len(segments) == MAX_PENDING_UTTERANCES
    assert segments[0]['text'] == '1'
    assert all(segment['speaker'] == 'SPEAKER_01' for segment in segments)


def test_preroll_is_filtered_per_utterance_and_tails_keep_capture_order():
    pending = ModulatePendingUtterances()
    for name, start in [('new', 2100), ('preroll', 500), ('old', 2000)]:
        pending.observe(partial(name, name, start)['partial_utterance'])
    assert [segment['text'] for segment in pending.flush(preseconds=1)] == ['old', 'new']
