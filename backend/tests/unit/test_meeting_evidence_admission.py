"""Bounded evidence admission before a desktop meeting's notes.

The Mac closes the listen socket before its evidence pass (screenshot
adjudication, identity upload, OCR flush) lands, and teardown admits
finalization immediately. The finalizer waits, bounded, for this environment's
adjudication marker; everything else never waits.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from models.conversation_enums import ConversationStatus
from utils.metrics import MEETING_NOTES_EVIDENCE_WAIT_TOTAL
from utils.conversations import finalizer  # imported at collection: the finalizer's import graph is not per-test cost
from utils.conversations import meeting_evidence_admission as admission
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.screen_content_window import selection_fingerprint, trusted_content_window

BUCKET = 'based-hardware-dev-screen-frames'
MEETING = {'source': 'desktop', 'external_data': {'conversation_role': 'meeting', 'screen_evidence_pass': True}}
STAMP = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture(autouse=True)
def _environment(monkeypatch):
    monkeypatch.setenv('MEETING_NOTES_EVIDENCE_WAIT_SECONDS', '25')
    monkeypatch.setenv('BUCKET_SCREEN_FRAMES', BUCKET)
    monkeypatch.setattr(admission, 'get_meeting_note_screenshots_enabled', lambda uid, **kw: True)

    async def inline(_pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(admission, 'run_blocking', inline)


@pytest.fixture(autouse=True)
def fallbacks(monkeypatch):
    recorded = []
    monkeypatch.setattr(admission, 'record_fallback', lambda **kw: recorded.append(kw))
    return recorded


def _window(end_seconds: float) -> dict:
    """The content-window fields of a v2-timeline meeting whose speech ends at ``end_seconds``."""
    return {
        'started_at': STAMP,
        'audio_timeline': {'version': 2},
        'transcript_segments': [{'text': 'hello', 'start': 5.0, 'end': end_seconds}],
    }


CURRENT = _window(300.0)
CURRENT_FINGERPRINT = selection_fingerprint(*trusted_content_window(CURRENT))
EARLIER_FINGERPRINT = selection_fingerprint(*trusted_content_window(_window(120.0)))


def _marker(monkeypatch, stamps, window=CURRENT):
    """Marker reads return successive values: None (not yet), STAMP (a pass over the
    current window), or an explicit (stamp, fingerprint) pair."""
    reads = []

    def read(uid, conversation_id, *, bucket, rpc_timeout):
        assert 0 < rpc_timeout <= 25.0  # every RPC is bounded by what is left of the wait
        reads.append(bucket)
        value = stamps[min(len(reads) - 1, len(stamps) - 1)]
        if value is None:
            return None, None
        return value if isinstance(value, tuple) else (value, CURRENT_FINGERPRINT)

    def window_fields(uid, conversation_id, *, rpc_timeout):
        assert 0 < rpc_timeout <= 25.0
        return window

    monkeypatch.setattr(admission, 'get_conversation_screen_frames_marker', read)
    monkeypatch.setattr(admission, 'get_conversation_content_window_fields', window_fields)
    return reads


def _run(clock, data=MEETING, trigger=ProcessingTrigger.CAPTURE_END):
    return asyncio.run(
        admission.await_meeting_evidence('u', 'c', data, trigger=trigger, sleep=clock.sleep, monotonic=clock.monotonic)
    )


def test_evidence_already_present_proceeds_without_waiting(monkeypatch, clock):
    reads = _marker(monkeypatch, [STAMP])
    assert _run(clock) == 'present'
    assert clock.sleeps == [] and reads == [BUCKET]


def test_evidence_arriving_mid_wait_proceeds_as_soon_as_it_lands(monkeypatch, clock):
    _marker(monkeypatch, [None, None, STAMP])
    assert _run(clock) == 'arrived'
    assert clock.now == pytest.approx(2 * admission.EVIDENCE_POLL_SECONDS)


def test_no_evidence_proceeds_at_the_bound_degraded(monkeypatch, clock, fallbacks):
    _marker(monkeypatch, [None])
    assert _run(clock) == 'timed_out'
    assert clock.now == pytest.approx(25.0)
    assert [(f['reason'], f['outcome']) for f in fallbacks] == [('timeout', 'degraded')]


def test_evidence_in_time_records_no_fallback(monkeypatch, clock, fallbacks):
    _marker(monkeypatch, [None, STAMP])
    assert _run(clock) == 'arrived'
    assert fallbacks == []


@pytest.mark.parametrize(
    'data',
    [
        {'source': 'desktop', 'external_data': {'conversation_role': 'dictation'}},
        {'source': 'omi', 'external_data': {'conversation_role': 'meeting'}},
        {'source': 'desktop'},
        # A released desktop build: a meeting, but it never runs the pass.
        {'source': 'desktop', 'external_data': {'conversation_role': 'meeting'}},
    ],
)
def test_non_meeting_conversations_never_wait(monkeypatch, clock, data):
    reads = _marker(monkeypatch, [None])
    assert _run(clock, data=data) == 'not_applicable'
    assert clock.sleeps == [] and reads == []


@pytest.mark.parametrize(
    'trigger', [ProcessingTrigger.USER_REPROCESS, ProcessingTrigger.FIRST_OPEN, ProcessingTrigger.SERVER_RECOVERY]
)
def test_later_triggers_never_wait(monkeypatch, clock, trigger):
    _marker(monkeypatch, [None])
    assert _run(clock, trigger=trigger) == 'not_applicable'
    assert clock.sleeps == []


def test_client_finalize_waits_like_capture_end(monkeypatch, clock):
    _marker(monkeypatch, [None])
    assert _run(clock, trigger=ProcessingTrigger.CLIENT_FINALIZE) == 'timed_out'


def test_disabled_by_default(monkeypatch, clock):
    monkeypatch.delenv('MEETING_NOTES_EVIDENCE_WAIT_SECONDS')
    _marker(monkeypatch, [None])
    assert _run(clock) == 'not_applicable'


def test_no_screen_frame_bucket_means_no_evidence_to_wait_for(monkeypatch, clock):
    monkeypatch.delenv('BUCKET_SCREEN_FRAMES')
    monkeypatch.setattr('utils.other.storage.screen_frames_bucket', None)
    _marker(monkeypatch, [None])
    assert _run(clock) == 'not_applicable'


def test_screenshot_setting_off_never_waits(monkeypatch, clock):
    monkeypatch.setattr(admission, 'get_meeting_note_screenshots_enabled', lambda uid, **kw: False)
    reads = _marker(monkeypatch, [None])
    assert _run(clock) == 'not_applicable'
    assert reads == []


def test_a_read_failure_proceeds_degraded_instead_of_failing_finalization(monkeypatch, clock, fallbacks):
    def boom(*_args, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(admission, 'get_conversation_screen_frames_marker', boom)
    assert _run(clock) == 'error'
    assert fallbacks and fallbacks[0]['outcome'] == 'degraded'
    assert fallbacks[0]['component'] == 'conversation_finalization'


def test_a_hung_read_cannot_outlive_the_bound(monkeypatch, fallbacks):
    """The await is cut at the remaining budget even when the RPC never returns."""
    monkeypatch.setenv('MEETING_NOTES_EVIDENCE_WAIT_SECONDS', '0.2')
    seen_timeouts = []

    async def hung(_pool, fn, *args, rpc_timeout=None, **kwargs):
        seen_timeouts.append(rpc_timeout)
        if fn is admission.get_meeting_note_screenshots_enabled:
            return True
        await asyncio.Event().wait()

    monkeypatch.setattr(admission, 'run_blocking', hung)
    started = asyncio.get_event_loop_policy().new_event_loop()
    try:
        import time as _time

        began = _time.monotonic()
        outcome = started.run_until_complete(
            admission.await_meeting_evidence('u', 'c', MEETING, trigger=ProcessingTrigger.CAPTURE_END)
        )
        elapsed = _time.monotonic() - began
    finally:
        started.close()
    assert outcome == 'timed_out'
    assert [(f['reason'], f['outcome']) for f in fallbacks] == [('timeout', 'degraded')]
    assert elapsed < 1.0
    assert all(timeout is not None and timeout <= 0.2 for timeout in seen_timeouts)


def test_the_bound_is_capped(monkeypatch):
    monkeypatch.setenv('MEETING_NOTES_EVIDENCE_WAIT_SECONDS', '3600')
    assert admission.evidence_wait_seconds() == admission.MAX_EVIDENCE_WAIT_SECONDS
    monkeypatch.setenv('MEETING_NOTES_EVIDENCE_WAIT_SECONDS', 'soon')
    assert admission.evidence_wait_seconds() == 0.0


class _Stop(Exception):
    pass


def _finalize_until_geolocation(monkeypatch, status):
    """Drive the shared finalizer (pusher, Cloud Tasks, and POST /finalize all use it) to its first step."""
    calls: list[str] = []
    data = dict(MEETING, id='c')

    async def fake_run_blocking(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            return data
        if function is finalizer.get_cached_user_geolocation:
            calls.append('geolocation')
            raise _Stop()
        raise AssertionError(f'unexpected blocking call: {function!r}')

    async def fake_admission(uid, conversation_id, conversation_data, *, trigger):
        calls.append(f'admission:{trigger.value}')
        return 'timed_out'

    class _Conversation:
        id = 'c'
        source = 'desktop'
        geolocation = None

    conversation = _Conversation()
    conversation.status = getattr(ConversationStatus, status)
    monkeypatch.setattr(finalizer, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', fake_admission)
    with pytest.raises(Exception):
        asyncio.run(
            finalizer.finalize_persisted_conversation(
                'u',
                'c',
                finalization_job_id='job',
                dispatch_generation=1,
                lease_epoch=1,
                trigger=ProcessingTrigger.CLIENT_FINALIZE,
            )
        )
    return calls


def test_the_finalizer_admits_evidence_before_any_processing_step(monkeypatch):
    assert _finalize_until_geolocation(monkeypatch, 'processing') == ['admission:client_finalize', 'geolocation']


def test_a_completed_replay_does_not_wait(monkeypatch):
    assert _finalize_until_geolocation(monkeypatch, 'completed') == ['geolocation']


class TestTheMarkerMustCoverTheCurrentWindow:
    """A marker stamped mid-meeting for an earlier content window is stale once the
    transcript extends; the Mac runs a fresh pass for the new fingerprint."""

    def test_a_stale_marker_keeps_waiting_until_the_bound(self, monkeypatch, clock, fallbacks):
        _marker(monkeypatch, [(STAMP, EARLIER_FINGERPRINT)])
        assert _run(clock) == 'timed_out'
        assert clock.now == pytest.approx(25.0)
        assert [f['reason'] for f in fallbacks] == ['timeout']

    def test_a_stale_marker_releases_when_the_current_pass_lands(self, monkeypatch, clock):
        _marker(monkeypatch, [(STAMP, EARLIER_FINGERPRINT), (STAMP, EARLIER_FINGERPRINT), (STAMP, CURRENT_FINGERPRINT)])
        assert _run(clock) == 'arrived'
        assert clock.now == pytest.approx(2 * admission.EVIDENCE_POLL_SECONDS)

    def test_the_window_is_re_read_each_poll(self, monkeypatch, clock):
        windows = iter([_window(120.0), _window(300.0)])
        _marker(monkeypatch, [(STAMP, CURRENT_FINGERPRINT)])
        monkeypatch.setattr(
            admission, 'get_conversation_content_window_fields', lambda uid, cid, *, rpc_timeout: next(windows)
        )
        # First poll: the transcript still ended at 120 s, so the current-window marker does
        # not match yet; the next read sees the extended transcript and it does.
        assert _run(clock) == 'arrived'

    def test_a_window_that_vanishes_mid_wait_keeps_waiting(self, monkeypatch, clock):
        windows = iter([CURRENT] + [None] * 100)
        _marker(monkeypatch, [None])
        monkeypatch.setattr(
            admission, 'get_conversation_content_window_fields', lambda uid, cid, *, rpc_timeout: next(windows)
        )
        assert _run(clock) == 'timed_out'


def _process_after_wait(monkeypatch, *, reloaded_status, outcome='arrived'):
    """Run the finalizer to process_conversation with a transcript that grows during the wait."""
    before = dict(MEETING, id='c', status='processing', segments=['hello'])
    after = dict(MEETING, id='c', status=reloaded_status, segments=['hello', 'tail said during the wait'])
    reads = iter([before, after])
    processed: list = []

    class _Conversation:
        def __init__(self, data):
            self.id = 'c'
            self.source = 'desktop'
            self.geolocation = None
            self.status = getattr(ConversationStatus, data['status'])
            self.segments = list(data['segments'])

    async def fake_run_blocking(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            return next(reads)
        if function is finalizer.get_cached_user_geolocation:
            return None
        if function is finalizer.process_conversation:
            processed.append(args[2])
            raise _Stop()
        raise AssertionError(f'unexpected blocking call: {function!r}')

    async def fake_admission(uid, conversation_id, conversation_data, *, trigger):
        return outcome

    monkeypatch.setattr(finalizer, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(finalizer, 'deserialize_conversation', _Conversation)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', fake_admission)
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *a: None)
    try:
        asyncio.run(
            finalizer.finalize_persisted_conversation(
                'u', 'c', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
            )
        )
    except Exception:
        pass
    return processed


@pytest.mark.parametrize('outcome', ['present', 'arrived', 'timed_out', 'error'])
def test_processing_uses_the_row_as_it_is_after_the_wait(monkeypatch, outcome):
    """Tail segments that land during the wait are summarized, and the pre-wait snapshot
    never reaches process_conversation (whose persist would overwrite the newer transcript)."""
    processed = _process_after_wait(monkeypatch, reloaded_status='processing', outcome=outcome)
    assert len(processed) == 1
    assert processed[0].segments == ['hello', 'tail said during the wait']


def test_a_row_completed_by_another_owner_during_the_wait_is_not_reprocessed(monkeypatch):
    processed = _process_after_wait(monkeypatch, reloaded_status='completed')
    assert processed == []


class TestNoTrustedWindowProceedsAtOnce:
    """Without a trusted content window nothing can be selected or stamped (the
    adjudication route refuses an open conversation without one), so waiting
    could only ever time out."""

    @pytest.mark.parametrize(
        'window',
        [
            None,  # the row is gone
            {'started_at': STAMP, 'audio_timeline': {'version': 2}, 'transcript_segments': []},  # no speech
            # A legacy (untrusted) origin whose projection disagrees with finished_at.
            {'started_at': STAMP, 'finished_at': STAMP, 'transcript_segments': [{'text': 'x', 'start': 0, 'end': 600}]},
        ],
    )
    def test_no_window_proceeds_immediately_without_a_fallback(self, monkeypatch, clock, fallbacks, window):
        reads = _marker(monkeypatch, [STAMP], window=window)
        before = MEETING_NOTES_EVIDENCE_WAIT_TOTAL.labels(outcome='no_window')._value.get()

        assert _run(clock) == 'no_window'

        assert clock.sleeps == [] and reads == []  # no marker read, no wait
        assert fallbacks == []
        assert MEETING_NOTES_EVIDENCE_WAIT_TOTAL.labels(outcome='no_window')._value.get() == before + 1

    def test_a_trusted_window_keeps_the_marker_rule(self, monkeypatch, clock):
        _marker(monkeypatch, [None, STAMP])
        assert _run(clock) == 'arrived'
