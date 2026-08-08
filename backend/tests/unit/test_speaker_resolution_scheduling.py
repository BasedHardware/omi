"""How the finalization-time speaker naming pass is scheduled by process_conversation.

Five guarantees are asserted here, each one a review finding:

1. The pass never occupies a ``postprocess_executor`` worker for its whole run — it is
   driven by a shared event loop thread, so a burst of finalized conversations cannot
   starve memory extraction, action items or vector indexing.
2. It is handed a deep copy, so the segment mutations it makes cannot be observed by
   ``_extract_memories`` running concurrently on ``postprocess_executor``.
3. It is scheduled after the private-cloud audio files are written, because enrolment
   reads them back and silently gives up when there are none.
4. What it persists carries no transcript text. The suggestions land as plain Firestore
   fields and only ``transcript_segments`` is encrypted, so a verbatim evidence quote
   in that payload would publish transcript content an enhanced-protection conversation
   exists to keep opaque. Segment ids address the same evidence inside the encrypted
   transcript the client already holds.
5. Every pass is a tracked task the process-exit drain waits on, so a shutdown cannot
   abandon one midway through creating a Person or writing segment assignments, and
   nothing it raises is lost with the discarded ``Future``.

Plus the delivery guarantee: the suggestions it returns are persisted on the
conversation document instead of being dropped with the discarded return value.
"""

import asyncio
import re
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.conversation import Conversation, SpeakerLabelSuggestion
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import process_conversation as pc

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE = (BACKEND_DIR / "utils" / "conversations" / "process_conversation.py").read_text(encoding="utf-8")


def _conversation() -> Conversation:
    return Conversation(
        id="conv-1",
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        structured=Structured(title="t", overview="o"),
        transcript_segments=[
            TranscriptSegment(id="seg-1", text="hi Ana", speaker="SPEAKER_00", is_user=False, start=0.0, end=1.0),
        ],
    )


def _suggestion(speaker_id: int = 0):
    return SimpleNamespace(
        speaker_id=speaker_id,
        person_name="Ana",
        evidence_quote="hi Ana",
        confidence=0.8,
        segment_ids=("seg-1",),
    )


def _run_submitted(coro, *, name, cancel_on_shutdown=True):
    future = Future()
    try:
        future.set_result(asyncio.run(coro))
    except BaseException as exc:
        future.set_exception(exc)
    return future


@pytest.fixture(autouse=True)
def application_background_task_registry(monkeypatch):
    monkeypatch.setattr(pc, 'submit_background_task', _run_submitted)


class TestSchedulingIsolation:
    def test_pass_is_not_submitted_to_the_postprocess_pool(self):
        """No postprocess worker is borrowed for the duration of the async coordinator."""
        submissions = re.findall(r'submit_with_context\(\s*postprocess_executor,\s*(\w+)', SOURCE)
        assert 'resolve_conversation_speakers' not in submissions
        assert 'resolve_conversation_speakers_sync' not in submissions
        assert 'schedule_speaker_resolution' not in submissions
        assert 'resolve_conversation_speakers_sync' not in SOURCE

    def test_pass_uses_the_application_background_task_registry(self):
        assert 'submit_background_task' in SOURCE
        assert '_get_speaker_resolution_loop' not in SOURCE
        assert 'atexit.register(drain_speaker_resolution)' not in SOURCE

    def test_scheduled_after_audio_files_are_durable(self):
        """Enrolment reads audio_files back, so the write must already have happened."""
        conversation = _conversation()
        conversation.folder_id = 'folder-1'
        conversation.private_cloud_sync_enabled = True
        finalized = []
        events = []

        class AudioFile:
            def dict(self):
                return {'id': 'audio-1'}

        def create_audio_files(*args):
            events.append('audio_create')
            return [AudioFile()]

        def update_conversation(*args, **kwargs):
            if 'audio_files' in args[2]:
                events.append('audio_write')

        def schedule(*args, **kwargs):
            events.append('schedule')

        with patch.object(pc, '_get_structured', return_value=(conversation.structured, False)), patch.object(
            pc, '_get_conversation_obj', return_value=conversation
        ), patch.object(pc.redis_db, 'get_conversation_meeting_id', return_value=None), patch.object(
            pc.lifecycle_service, 'persist_processed_conversation', return_value=True
        ), patch.object(
            pc, 'submit_with_context'
        ), patch.object(
            pc, '_trigger_apps'
        ), patch.object(
            pc.conversations_db, 'create_audio_files_from_chunks', side_effect=create_audio_files
        ), patch.object(
            pc.conversations_db, 'update_conversation', side_effect=update_conversation
        ), patch.object(
            pc, 'precache_conversation_audio'
        ), patch.object(
            pc, 'is_audio_merge_dispatch_enabled', return_value=False
        ), patch.object(
            pc, 'schedule_speaker_resolution', side_effect=schedule
        ):
            pc.process_conversation(
                'uid',
                'en',
                conversation,
                defer_memory_extraction=True,
                defer_derived_effects=True,
                derived_effects_observer=finalized.append,
            )
            assert len(finalized) == 1
            finalized[0]()

        assert events == ['audio_create', 'audio_write', 'schedule']


class TestScheduleSpeakerResolution:
    def test_disabled_flag_schedules_nothing(self):
        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', False):
            assert pc.schedule_speaker_resolution("uid", _conversation()) is None

    def test_pass_cannot_mutate_the_conversation_other_jobs_read(self):
        conversation = _conversation()
        seen = {}

        async def _fake(uid, conv):
            seen['is_copy'] = conv is not conversation
            seen['segment_is_copy'] = conv.transcript_segments[0] is not conversation.transcript_segments[0]
            conv.transcript_segments[0].person_id = "person-1"
            return SimpleNamespace(suggested=[])

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ):
            future = pc.schedule_speaker_resolution("uid", conversation)
            assert future is not None
            future.result(timeout=10)

        assert seen == {'is_copy': True, 'segment_is_copy': True}
        assert conversation.transcript_segments[0].person_id is None

    def test_suggestions_are_persisted_on_the_conversation(self):
        conversation = _conversation()

        async def _fake(uid, conv):
            return SimpleNamespace(suggested=[_suggestion()])

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ), patch.object(pc.conversations_db, 'persist_speaker_resolution_suggestions') as persist:
            future = pc.schedule_speaker_resolution("uid", conversation)
            assert future is not None
            future.result(timeout=10)

        persist.assert_called_once()
        uid, conversation_id, payload = persist.call_args[0]
        assert (uid, conversation_id) == ("uid", "conv-1")
        assert payload == [
            {
                'speaker_id': 0,
                'person_name': "Ana",
                'confidence': 0.8,
                'segment_ids': ["seg-1"],
            }
        ]

    def test_no_suggestions_writes_nothing(self):
        async def _fake(uid, conv):
            return SimpleNamespace(suggested=[])

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ), patch.object(pc.conversations_db, 'persist_speaker_resolution_suggestions') as persist:
            future = pc.schedule_speaker_resolution("uid", _conversation())
            assert future is not None
            future.result(timeout=10)

        persist.assert_not_called()

    def test_a_failing_pass_is_swallowed(self):
        async def _fake(uid, conv):
            raise RuntimeError("boom")

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ), patch.object(pc.conversations_db, 'persist_speaker_resolution_suggestions') as persist:
            future = pc.schedule_speaker_resolution("uid", _conversation())
            assert future is not None
            future.result(timeout=10)

        persist.assert_not_called()


class TestSuggestionsStayInsideTheEncryptionBoundary:
    """A suggestion is stored as plain Firestore fields; only segments are encrypted.

    Whatever the pass writes here is readable by anyone who can read the document,
    which for an enhanced-protection conversation is exactly the audience the
    protection level exists to exclude from transcript content.
    """

    def test_no_transcript_text_is_written(self):
        payload = pc._speaker_suggestion_payload([_suggestion()])
        assert payload == [{'speaker_id': 0, 'person_name': "Ana", 'confidence': 0.8, 'segment_ids': ["seg-1"]}]

    def test_the_stored_model_cannot_carry_a_quote(self):
        """`extra` is ignored by default, so the field's absence is the guarantee."""
        assert 'evidence_quote' not in SpeakerLabelSuggestion.model_fields
        stored = SpeakerLabelSuggestion(speaker_id=0, person_name="Ana", confidence=0.8, segment_ids=["seg-1"])
        assert 'evidence_quote' not in stored.model_dump()

    def test_the_evidence_stays_addressable_by_segment_id(self):
        """Dropping the quote must not drop the client's ability to render the evidence."""
        conversation = _conversation()
        payload = pc._speaker_suggestion_payload([_suggestion()])
        known = {segment.id for segment in conversation.transcript_segments}
        assert payload[0]['segment_ids']
        assert set(payload[0]['segment_ids']) <= known


class TestTheDrainOwnsInFlightPasses:
    """A shutdown must not abandon a pass that has already created a Person."""

    def test_the_pass_is_submitted_with_a_stable_tracking_name(self):
        with patch.object(pc, 'submit_background_task', wraps=_run_submitted) as submit:
            with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True):
                assert pc.schedule_speaker_resolution("uid", _conversation()) is not None

        submit.assert_called_once()
        assert submit.call_args.kwargs['name'] == 'speaker_resolution:conv-1'
        assert submit.call_args.kwargs['cancel_on_shutdown'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
