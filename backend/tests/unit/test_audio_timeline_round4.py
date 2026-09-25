"""Round-4 re-review regressions for the audio-timeline branch.

Locks the wiring the round-3 re-review flagged:

- N1: ownership fail-open no longer adopts a sample older than the oldest
  retained run (retention may have evicted the run and every boundary that
  would contradict the surviving single conversation); the fail-open applies
  only between retained runs, inside the retention horizon, when the retained
  runs are one conversation.
- N5: a provider callback deferred onto the listen loop runs on its own copy
  of the segment list, an exception inside it increments the rejected
  counter with a bounded log, and a closed loop still drops quietly.
"""

import asyncio
import logging
import threading
from collections import deque
from types import SimpleNamespace

import pytest

from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from utils.metrics import OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL

RATE = 16000
UID = 'uid-r4'
T0 = 1_700_000_000.0


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _receiver(monkeypatch, *, v2: bool, conversation='conv-a') -> ListenReceiver:
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
    state = ListenSessionState()
    state.current_conversation_id = conversation
    collected = []
    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID, websocket=None, codec='pcm16', sample_rate=RATE, channels=1, source='desktop'),
        state=state,
        is_multi_channel=False,
        use_custom_stt=False,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=collected.extend),
        client_device_context=SimpleNamespace(platform='test'),
        stt_service='soniox',
        spawn=lambda coro, *, name: asyncio.create_task(coro),
    )
    receiver = ListenReceiver(host, [], {})
    receiver.collected = collected
    return receiver


def _feed_contiguous(receiver: ListenReceiver, seconds: float, *, first_wall: float = T0, frame=0.5):
    """Feed real accepted frames through the capture clock and ownership map."""
    per_frame = int(frame * RATE)
    pcm = b'\x01\x00' * per_frame
    count = int(seconds / frame)
    first_start = None
    last_end = None
    for i in range(count):
        wall = first_wall + i * frame
        start, end, _ = receiver.capture_timeline.accept(pcm, wall + frame, wall + frame)
        receiver._note_accepted_frame(start, end)
        if first_start is None:
            first_start = start
        last_end = end
    return first_start, last_end


# ---------------------------------------------------------------------------
# N1: the owner fail-open cannot reach below the oldest retained run
# ---------------------------------------------------------------------------
async def test_final_older_than_the_retained_runs_stays_dropped(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 30.0, frame=0.5)  # conversation A: [0, 30s)
    receiver.host.state.current_conversation_id = 'conv-b'
    # 125 s of B: more than the 120 s retention past A's end, so A's run is
    # evicted and the retained window shows only B.
    _feed_contiguous(receiver, 125.0, first_wall=T0 + 30.0, frame=1.0)

    ranges = receiver.host.state.conversation_sample_ranges
    assert len(ranges) == 1 and ranges[0][2] == 'conv-b', "retention must have trimmed conversation A's run"

    dropped = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='late_owner_dropped')
    before = dropped._value.get()
    receiver._enqueue_translated_segments(
        [
            {
                'id': 'ancient',
                'speaker_id': 0,
                'start': receiver.capture_timeline.wall(RATE),
                'end': receiver.capture_timeline.wall(2 * RATE),
                'text': 'late final for conversation A',
                'is_user': False,
                '_capture_start_sample': RATE,
                '_capture_end_sample': 2 * RATE,
            }
        ]
    )
    assert receiver.collected == [], 'a final older than every retained run must not be re-owned by conv B'
    assert dropped._value.get() == before + 1


async def test_single_conversation_gap_inside_horizon_fails_open(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    receiver.host.state.current_conversation_id = 'conv-now'
    state = receiver.host.state

    # A wall gap the session never accepted audio for, bracketed by one
    # conversation's runs, inside the retention horizon: fail open.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 25, RATE * 30, 'conv-a')])
    assert receiver._owner_for_sample(RATE * 22) == 'conv-a'

    # The same single-conversation gap outside the retention horizon is
    # ambiguous: runs covering the sample were eligible for eviction.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 200, RATE * 210, 'conv-a')])
    assert receiver._owner_for_sample(RATE * 50) is None

    # A boundary inside the retained window never fails open.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 25, RATE * 30, 'conv-b')])
    assert receiver._owner_for_sample(RATE * 22) is None


# ---------------------------------------------------------------------------
# N5: the loop hop copies the segment list and counts deferred failures
# ---------------------------------------------------------------------------
class _CaptureLoop:
    """Stand-in for the listen loop: records deferred callbacks for manual run."""

    def __init__(self):
        self.callbacks = []

    def call_soon_threadsafe(self, callback, *args):
        self.callbacks.append((callback, args))


class _ClosedLoop:
    def call_soon_threadsafe(self, callback, *args):
        raise RuntimeError('Event loop is closed')


def test_deferred_callback_runs_on_its_own_segment_list(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    loop = _CaptureLoop()
    receiver._listen_loop = loop
    seen = []
    segments = [{'id': 's1'}, {'id': 's2'}]

    receiver._run_on_listen_loop(seen.extend, segments)
    segments.clear()  # a provider may reuse its buffer once the callback returns
    assert seen == [], 'nothing runs until the listen loop does'
    callback, args = loop.callbacks[0]
    callback(*args)
    assert seen == [{'id': 's1'}, {'id': 's2'}], 'the hop must carry its own copy of the list'


@pytest.mark.parametrize('v2,mode', [(True, 'v2'), (False, 'legacy')])
def test_deferred_callback_exception_counts_rejected(monkeypatch, caplog, v2, mode):
    receiver = _receiver(monkeypatch, v2=v2)
    loop = _CaptureLoop()
    receiver._listen_loop = loop

    def boom(segments):
        raise ValueError('provider callback exploded')

    rejected = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='rejected')
    before = rejected._value.get()
    with caplog.at_level(logging.WARNING, logger='routers.listen.receiver'):
        receiver._run_on_listen_loop(boom, [{'id': 's1'}])
        callback, args = loop.callbacks[0]
        callback(*args)  # must not raise out of the deferred action
    assert rejected._value.get() == before + 1
    assert any('Listen STT callback failed' in record.message for record in caplog.records)
    # The bounded log never carries segment content or identity.
    assert 's1' not in caplog.text


def test_closed_loop_still_drops_quietly(monkeypatch, caplog):
    receiver = _receiver(monkeypatch, v2=True)
    receiver._listen_loop = _ClosedLoop()
    ran = []

    with caplog.at_level(logging.WARNING, logger='routers.listen.receiver'):
        receiver._run_on_listen_loop(ran.append, [{'id': 's1'}])  # must not raise

    assert ran == []
    assert any('loop shutdown' in record.message for record in caplog.records)
