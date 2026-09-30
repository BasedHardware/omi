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
from utils.conversations import finalizer  # imported at collection: the finalizer's import graph is not per-test cost
from utils.conversations import meeting_evidence_admission as admission
from utils.conversations.processing_trigger import ProcessingTrigger

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
    monkeypatch.setattr(admission, 'get_meeting_note_screenshots_enabled', lambda uid: True)

    async def inline(_pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(admission, 'run_blocking', inline)


def _marker(monkeypatch, stamps):
    """Adjudication marker reads return successive values (None = not yet)."""
    reads = []

    def read(uid, conversation_id, *, bucket):
        reads.append(bucket)
        return stamps[min(len(reads) - 1, len(stamps) - 1)]

    monkeypatch.setattr(admission, 'get_conversation_screen_frames_adjudicated_at', read)
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


def test_no_evidence_proceeds_at_the_bound(monkeypatch, clock):
    _marker(monkeypatch, [None])
    assert _run(clock) == 'timed_out'
    assert clock.now == pytest.approx(25.0)


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
    monkeypatch.setattr(admission, 'get_meeting_note_screenshots_enabled', lambda uid: False)
    reads = _marker(monkeypatch, [None])
    assert _run(clock) == 'not_applicable'
    assert reads == []


def test_a_read_failure_proceeds_instead_of_failing_finalization(monkeypatch, clock):
    def boom(*_args, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(admission, 'get_conversation_screen_frames_adjudicated_at', boom)
    assert _run(clock) == 'error'


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
