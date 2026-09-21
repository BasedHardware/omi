from __future__ import annotations
import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'pusher_semantic_probe.py'


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location('pusher_semantic_probe_test_target', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_terminal_readback_requires_completed_successful_fanout(monkeypatch, probe):
    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (200, {'id': 'conversation-1', 'status': 'completed', 'transcript_segments': [{'text': 'hello'}]}),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))

    await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('terminal_outcome', 'fanout_status'),
    [('stale', 'fenced'), ('failure', 'fenced'), ('success', 'leased'), ('unknown', 'unknown')],
)
async def test_terminal_readback_rejects_completed_without_successful_fanout(
    monkeypatch, probe, terminal_outcome: str, fanout_status: str
):
    monkeypatch.setattr(
        probe,
        '_http_json',
        lambda *_args: (
            200,
            {
                'status': 'completed',
                'terminal': True,
                'terminal_outcome': terminal_outcome,
                'fanout_status': fanout_status,
            },
        ),
    )
    with pytest.raises(probe.ProbeError, match='terminal_failure'):
        await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)


class _FailoverListenSocket:
    """A /v4/listen socket whose final segment lands late, after one failover.

    Early segments are available immediately; the final segment becomes
    available only once the (fake) clock passes stream_end + late_after,
    mimicking the successor provider's end-of-speech flush timer that fired
    seconds after the probe's old 5s tail closed (dev runs 35513163118,
    35517257170, and the 14:41 cancelled-run probe: transcript_mismatch 3/3).
    """

    def __init__(self, conversation_id: str, late_after: float, clock: list[float]) -> None:
        self._clock = clock
        self._late_after = late_after
        self._stream_ended_at: float | None = None
        self._early = [
            {'type': 'conversation_session', 'conversation_id': conversation_id},
            {'type': 'service_status', 'status': 'ready'},
            {'segments': [{'text': 'He began a confused'}]},
        ]
        self._late = {'segments': [{'text': 'complaint against the wizard'}]}
        self.closed = False

    async def recv(self) -> str:
        if self._early:
            return json.dumps(self._early.pop(0))
        if (
            self._late is not None
            and self._stream_ended_at is not None
            and self._clock[0] >= self._stream_ended_at + self._late_after
        ):
            payload, self._late = self._late, None
            return json.dumps(payload)
        # Yield so the timeline (and cancellation) can advance while idle.
        await asyncio.sleep(0)
        raise asyncio.TimeoutError

    async def send(self, _chunk: bytes) -> None:
        self._stream_ended_at = self._clock[0]

    async def close(self, code: int = 1000, reason: str = '') -> None:
        self.closed = True


class _FakeConnect:
    def __init__(self, socket: _FailoverListenSocket) -> None:
        self._socket = socket

    async def __aenter__(self) -> _FailoverListenSocket:
        return self._socket

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _install_fake_timeline(monkeypatch: pytest.MonkeyPatch, probe, clock: list[float]) -> None:
    real_sleep = probe.asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        clock[0] += delay
        await real_sleep(0)

    async def fake_wait_for(awaitable, timeout: float | None = None):
        return await awaitable

    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(probe.asyncio, 'sleep', fake_sleep)
    monkeypatch.setattr(probe.asyncio, 'wait_for', fake_wait_for)


@pytest.mark.asyncio
@pytest.mark.parametrize('late_after', [12.0])
async def test_listen_sample_collects_a_final_segment_that_lands_after_one_failover(
    monkeypatch, probe, late_after: float
):
    """The final segment of a failover-recovered session lands seconds past the
    old 5s tail (12s here) but inside the failover-tolerant collection window;
    the probe must still accept it."""
    clock = [0.0]
    socket = _FailoverListenSocket('conversation-1', late_after, clock)
    _install_fake_timeline(monkeypatch, probe, clock)
    monkeypatch.setattr(probe.websockets, 'connect', lambda *_a, **_k: _FakeConnect(socket))
    fixture = probe.Fixture(
        pcm=b'\x00' * (16000 * 2 * 3),  # three full 100ms chunks
        sample_rate=16000,
        expected_phrase='he began a confused complaint against the wizard',
    )

    await probe._listen_sample('https://api.example.invalid', 'token', fixture, 'conversation-1')

    assert socket.closed


@pytest.mark.asyncio
async def test_listen_sample_still_fails_closed_when_the_phrase_never_lands(monkeypatch, probe):
    """A provider that never delivers the phrase must keep failing the probe:
    the live window reports no match, and the durable readback rejects a
    completed conversation whose transcript lacks the fixture phrase."""
    clock = [0.0]
    socket = _FailoverListenSocket('conversation-1', 90.0, clock)
    _install_fake_timeline(monkeypatch, probe, clock)
    monkeypatch.setattr(probe.websockets, 'connect', lambda *_a, **_k: _FakeConnect(socket))
    fixture = probe.Fixture(
        pcm=b'\x00' * (16000 * 2 * 3),
        sample_rate=16000,
        expected_phrase='he began a confused complaint against the wizard',
    )

    matched, transcript = await probe._listen_sample('https://api.example.invalid', 'token', fixture, 'conversation-1')

    assert matched is False
    # The failover socket delivered a partial early segment only; the phrase
    # as a whole never landed inside the live window.
    assert 'complaint against the wizard' not in transcript
    # The socket closes gracefully; acceptance is decided by the durable
    # readback below, not by the live window.
    assert socket.closed

    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (
                200,
                {'id': 'conversation-1', 'status': 'completed', 'transcript_segments': [{'text': 'unrelated words'}]},
            ),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))
    with pytest.raises(probe.ProbeError, match='transcript_mismatch'):
        await probe._terminal_readback(
            'https://api.example.invalid', 'token', 'conversation-1', 1, expected_phrase=fixture.expected_phrase
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('durable_segments', 'should_pass'),
    [
        ([{'text': 'He began a confused complaint against the wizard who had vanished.'}], True),
        ([{'text': 'partial audio only'}], False),
    ],
)
async def test_terminal_readback_enforces_the_fixture_phrase_in_the_durable_transcript(
    monkeypatch, probe, durable_segments, should_pass
):
    """The durable completed conversation is the release contract: the fixture
    phrase must appear in its transcript segments regardless of whether the
    live streaming window or the batch finalization path produced it."""
    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (
                200,
                {
                    'id': 'conversation-1',
                    'status': 'completed',
                    'transcript_segments': durable_segments,
                },
            ),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))

    if should_pass:
        await probe._terminal_readback(
            'https://api.example.invalid',
            'token',
            'conversation-1',
            1,
            expected_phrase='he began a confused complaint against the wizard',
        )
    else:
        with pytest.raises(probe.ProbeError, match='transcript_mismatch'):
            await probe._terminal_readback(
                'https://api.example.invalid',
                'token',
                'conversation-1',
                1,
                expected_phrase='he began a confused complaint against the wizard',
            )
