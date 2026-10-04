"""Replay the vendor's documented nullable/interleaved terminal protocol.

UUID-less previews retain the legacy single-preview behavior; the nullable
timing fix and UUID correlation are enabled only behind the rollback flag.
"""

import asyncio
import json

import pytest

from utils.stt import streaming
from utils.stt.modulate_protocol import ModulatePendingUtterances


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
@pytest.mark.parametrize('start', [None, 100, 3000])
@pytest.mark.parametrize('text', ['Another utterance', 'Hello, how are', '  HELLO, how\nare! '])
async def test_any_nonempty_final_clears_uuidless_preview_like_legacy(monkeypatch, enabled, terminal, start, text):
    emitted = []
    socket = await receive(
        [documented_partial(text=text, start_ms=start), documented_final(), terminal],
        emitted.extend,
        monkeypatch,
        enabled=enabled,
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
    assert not socket._has_pending_partial()
    socket._flush_partial()
    assert len(emitted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
@pytest.mark.parametrize('identifier', [None, '', 123])
async def test_anonymous_revisions_empty_updates_and_speaker_follow_legacy(monkeypatch, enabled, terminal, identifier):
    emitted = []
    socket = await receive(
        [
            documented_partial(text='Original preview', start_ms=100, speaker=2),
            documented_partial(utterance_uuid=identifier, text='  Latest  preview  ', start_ms=3000, speaker=3),
            documented_partial(text='  ', start_ms=4000),
            documented_final(text=''),
            terminal,
        ],
        emitted.extend,
        monkeypatch,
        enabled=enabled,
    )
    assert emitted == [
        {
            'speaker': 'SPEAKER_00',
            'start': 3.0,
            'end': 3.001,
            'text': 'Latest  preview',
            'is_user': False,
            'person_id': None,
        }
    ]
    assert not socket._has_pending_partial()
    socket._flush_partial()
    assert len(emitted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
@pytest.mark.parametrize('identified', [False, True])
async def test_nullable_terminal_timing_uses_zero_only_with_guard(monkeypatch, enabled, terminal, identified):
    emitted = []
    message = partial('a', 'Bonjour') if identified else documented_partial(text='Bonjour', start_ms=None)
    socket = await receive([message, terminal], emitted.extend, monkeypatch, enabled=enabled)
    if enabled:
        assert emitted == [
            {
                'speaker': 'SPEAKER_00',
                'start': 0.0,
                'end': 0.001,
                'text': 'Bonjour',
                'is_user': False,
                'person_id': None,
            }
        ]
        assert socket.is_connection_dead is (terminal['type'] == 'error')
        assert socket.typed_death_reason == ('modulate_serve_error' if terminal['type'] == 'error' else None)
        assert socket._done_event.is_set()
    else:
        # Rollback preserves even the original nullable-timing failure.
        assert emitted == []
        assert socket.is_connection_dead
        assert socket.typed_death_reason is None
        assert not socket._done_event.is_set()
    assert not socket._has_pending_partial()


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_uuidless_null_update_keeps_legacy_default_without_inheriting_prior_time(monkeypatch, terminal):
    emitted = []
    socket = await receive(
        [documented_partial(start_ms=3000), documented_partial(text='Tail', start_ms=None, speaker=2), terminal],
        emitted.extend,
        monkeypatch,
    )
    assert [(s['text'], s['speaker'], s['start'], s['end']) for s in emitted] == [('Tail', 'SPEAKER_00', 0.0, 0.001)]
    assert socket._done_event.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_matching_uuid_final_only_retires_its_identified_preview(monkeypatch, terminal):
    emitted = []
    socket = await receive(
        [
            partial('a', 'Bonjour', 100, 1),
            partial('b', 'Guten', 200, 2),
            partial('b', 'Guten Tag', None, None),
            documented_partial(text='Anonymous tail', start_ms=3000),
            documented_final(utterance_uuid='a', text='Bonjour.', start_ms=100, duration_ms=80, language='fr'),
            terminal,
        ],
        emitted.extend,
        monkeypatch,
    )
    assert [(s['text'], s['speaker'], s['start']) for s in emitted] == [
        ('Bonjour.', 'SPEAKER_00', 0.1),
        ('Guten Tag', 'SPEAKER_01', 0.2),
    ]
    assert not socket._has_pending_partial()
    socket._flush_partial()
    assert len(emitted) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_uuidless_final_does_not_retire_identified_previews(monkeypatch, terminal):
    emitted = []
    await receive(
        [partial('a', 'Same text', 100, 2), documented_final(utterance_uuid=None, text='Same text'), terminal],
        emitted.extend,
        monkeypatch,
    )
    assert [(s['text'], s['speaker'], s['start']) for s in emitted] == [
        ('Same text', 'SPEAKER_00', 0.0),
        ('Same text', 'SPEAKER_01', 0.1),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', TERMINALS, ids=['done', 'error'])
async def test_anonymous_tail_is_not_evicted_by_identified_previews(monkeypatch, terminal):
    emitted = []
    await receive(
        [documented_partial(text='Anonymous tail', start_ms=3000, speaker=3)]
        + [partial(str(i), f'Tail {i}', 100 + i, 2) for i in range(65)]
        + [terminal],
        emitted.extend,
        monkeypatch,
    )
    assert len(emitted) == 66
    assert [s['text'] for s in emitted] == [f'Tail {i}' for i in range(65)] + ['Anonymous tail']
    assert emitted[-1]['speaker'] == 'SPEAKER_00'


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_flag_off_interleaving_preserves_single_legacy_preview(monkeypatch, enabled):
    emitted = []
    await receive(
        [
            partial('a', 'Bonjour', 100, 1),
            partial('b', 'Guten Tag', 200, 2),
            documented_final(utterance_uuid='a', text='Bonjour.', start_ms=100),
            TERMINALS[0],
        ],
        emitted.extend,
        monkeypatch,
        enabled=enabled,
    )
    assert [s['text'] for s in emitted] == (['Bonjour.', 'Guten Tag'] if enabled else ['Bonjour.'])


def test_helper_ignores_anonymous_previews_and_finals():
    pending = ModulatePendingUtterances()
    pending.observe(documented_partial()['partial_utterance'])
    assert not pending
    pending.observe(partial('a', 'Hola', 100)['partial_utterance'])
    pending.finalized(documented_final(utterance_uuid=None, text='Hola')['utterance'])
    assert [s['text'] for s in pending.flush()] == ['Hola']


def test_empty_identified_preview_retracts_only_its_uuid():
    pending = ModulatePendingUtterances()
    pending.observe(partial('a', 'Hola', 100)['partial_utterance'])
    pending.observe(partial('b', 'Bonjour', 200)['partial_utterance'])
    pending.observe(partial('a', '', None)['partial_utterance'])
    assert [s['text'] for s in pending.flush()] == ['Bonjour']
    assert not pending


def test_preroll_is_filtered_per_utterance_and_tails_keep_capture_order():
    pending = ModulatePendingUtterances()
    for name, start in [('new', 2100), ('preroll', 500), ('untimed', None), ('old', 2000)]:
        pending.observe(partial(name, name, start)['partial_utterance'])
    assert [s['text'] for s in pending.flush(preseconds=1)] == ['old', 'new']
