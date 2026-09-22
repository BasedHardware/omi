"""Provider frames are transport chunks, never word or timestamp boundaries."""

import asyncio
import json

import pytest

from models.transcript_segment import TranscriptSegment
from utils.stt.soniox import SafeSonioxSocket


def token(text, start=0, end=100, **extra):
    return {'text': text, 'start_ms': start, 'end_ms': end, 'speaker': '1', 'is_final': True, **extra}


class Socket:
    def __init__(self, frames):
        self.frames = frames
        self.sent = []
        self.closed = False

    def __aiter__(self):
        async def receive():
            for frame in self.frames:
                yield json.dumps(frame)

        return receive()

    async def send(self, value):
        self.sent.append(value)

    async def close(self):
        self.closed = True


def drive(frames, preseconds=0):
    captured = []

    async def run():
        socket = SafeSonioxSocket(Socket(frames), captured.extend, asyncio.get_running_loop(), preseconds)
        await socket._recv_task
        socket._send_task.cancel()
        await asyncio.gather(socket._send_task, return_exceptions=True)

    asyncio.run(run())
    return captured


def test_subwords_and_standalone_spaces_survive_real_downstream_merge():
    frames = [
        {'tokens': [token('It', 100, 200)]},
        {'tokens': [token(' ', 200, 200)]},
        {'tokens': [token('res', 300, 400)]},
        {'tokens': [token('umed', 400, 600)]},
        {'tokens': [token('.', 600, 620), token('<fin>')]},
    ]
    merged = []
    for segment in drive(frames):
        result = TranscriptSegment.combine_segments(merged, [TranscriptSegment(**segment, stt_provider='soniox')])
        merged = result.segments
    assert [segment.text for segment in merged] == ['It resumed.']
    assert merged[0].start == pytest.approx(0.1)
    assert merged[0].end == pytest.approx(0.62)


def test_subword_buffer_preserves_contractions_and_non_latin_text():
    segments = drive(
        [
            {'tokens': [token('I'), token("'", 100, 150)]},
            {'tokens': [token('m', 150, 200), token(' 好', 300, 400)]},
            {'tokens': [token('的', 400, 500), token('。', 500, 550)]},
            {'finished': True},
        ]
    )
    assert [segment['text'] for segment in segments] == ["I'm", '好的。']


def test_actual_end_does_not_extend_to_next_speaker_or_silence():
    segments = drive(
        [{'tokens': [token('First', 100, 450, duration_ms=99999), token('Next', 5000, 5300, speaker='2')]}]
    )
    assert [(s['start'], s['end']) for s in segments] == [(0.1, 0.45), (5.0, 5.3)]
    assert [s['speaker'] for s in segments] == ['SPEAKER_00', 'SPEAKER_01']


def test_long_silence_cannot_join_disconnected_word_pieces():
    segments = drive([{'tokens': [token('part', 0, 200)]}, {'tokens': [token('ial', 16000, 16200)]}])
    assert [s['text'] for s in segments] == ['part', 'ial']
    assert [s['end'] for s in segments] == [0.2, 16.2]


@pytest.mark.parametrize('marker', ['<end>', '<fin>'])
def test_control_markers_flush_committed_words_without_becoming_speech(marker):
    segments = drive([{'tokens': [token('Done'), {'text': marker, 'is_final': True}]}])
    assert [s['text'] for s in segments] == ['Done']


def test_translation_and_nonfinal_tokens_do_not_change_original_text():
    segments = drive(
        [
            {'tokens': [token('res'), token('incorrect', is_final=False)]},
            {'tokens': [token('traduit', translation_status='translation'), token('umed', 100, 200)]},
        ]
    )
    assert [s['text'] for s in segments] == ['resumed']


def test_preroll_and_invalid_spans_do_not_create_negative_durations():
    segments = drive([{'tokens': [token('profile', 0, 200), token('real', 3000, 2999)]}], preseconds=2)
    assert [(s['text'], s['start'], s['end']) for s in segments] == [('real', 1.0, 1.0)]


def test_finalization_is_text_control_ordered_after_queued_audio():
    async def run():
        ws = Socket([])
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        assert sock.send(b'\x01\x00')
        sock.finalize()
        sock._send_queue.put_nowait(b'')
        await sock._send_task
        await sock._recv_task
        assert ws.sent == [b'\x01\x00', '{"type": "finalize"}', '']

    asyncio.run(run())


def test_drain_delivers_last_committed_word_before_closing():
    async def run():
        ws = Socket([{'tokens': [token('last')]}, {'finished': True}])
        captured = []
        sock = SafeSonioxSocket(ws, captured.extend, asyncio.get_running_loop())
        await sock.drain_and_close()
        await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
        assert [s['text'] for s in captured] == ['last']
        assert ws.closed

    asyncio.run(run())


def test_drain_timeout_waits_for_pending_word_callback(monkeypatch):
    class HangingSocket(Socket):
        def __aiter__(self):
            async def receive():
                yield json.dumps({'tokens': [token('tail')]})
                await asyncio.Event().wait()

            return receive()

    async def run():
        ws = HangingSocket([])
        captured = []
        sock = SafeSonioxSocket(ws, captured.extend, asyncio.get_running_loop())
        await asyncio.sleep(0)
        assert captured == []

        async def timed_out():
            raise asyncio.TimeoutError

        monkeypatch.setattr(sock._done_event, 'wait', timed_out)
        await sock.drain_and_close()
        assert [s['text'] for s in captured] == ['tail']
        assert sock._recv_task.done()
        assert sock._send_task.done()
        assert ws.closed

    asyncio.run(run())


def test_finalize_from_worker_thread_uses_provider_loop():
    async def run():
        ws = Socket([])
        sock = SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
        await asyncio.to_thread(sock.finalize)
        sock._send_queue.put_nowait(b'')
        await asyncio.gather(sock._send_task, sock._recv_task)
        assert ws.sent == ['{"type": "finalize"}', '']

    asyncio.run(run())


@pytest.mark.parametrize('worker_thread', [False, True])
def test_finish_delivers_pending_word_exactly_once(worker_thread):
    class HangingSocket(Socket):
        def __aiter__(self):
            async def receive():
                yield json.dumps({'tokens': [token('tail.')]})
                await asyncio.Event().wait()

            return receive()

    async def run():
        captured = []
        sock = SafeSonioxSocket(HangingSocket([]), captured.extend, asyncio.get_running_loop())
        await asyncio.sleep(0)
        assert captured == []
        if worker_thread:
            await asyncio.to_thread(sock.finish)
        else:
            sock.finish()
        assert [s['text'] for s in captured] == ['tail.']
        sock.finish()
        sock._recv_task.cancel()
        sock._send_task.cancel()
        await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
        assert [s['text'] for s in captured] == ['tail.']

    asyncio.run(run())
