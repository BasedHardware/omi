"""How the finalization-time speaker naming pass is scheduled by process_conversation.

Three guarantees are asserted here, each one a review finding:

1. The pass never occupies a ``postprocess_executor`` worker for its whole run — it is
   driven by a shared event loop thread, so a burst of finalized conversations cannot
   starve memory extraction, action items or vector indexing.
2. It is handed a deep copy, so the segment mutations it makes cannot be observed by
   ``_extract_memories`` running concurrently on ``postprocess_executor``.
3. It is scheduled after the private-cloud audio files are written, because enrolment
   reads them back and silently gives up when there are none.

Plus the delivery guarantee: the suggestions it returns are persisted on the
conversation document instead of being dropped with the discarded return value.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.conversation import Conversation
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


class TestSchedulingIsolation:
    def test_pass_is_not_submitted_to_the_postprocess_pool(self):
        """No postprocess worker is borrowed for the duration of the async coordinator."""
        submissions = re.findall(r'submit_with_context\(\s*postprocess_executor,\s*(\w+)', SOURCE)
        assert 'resolve_conversation_speakers' not in submissions
        assert 'resolve_conversation_speakers_sync' not in submissions
        assert 'schedule_speaker_resolution' not in submissions
        assert 'resolve_conversation_speakers_sync' not in SOURCE

    def test_pass_runs_on_a_dedicated_loop_thread(self):
        loop = pc._get_speaker_resolution_loop()
        assert loop is pc._get_speaker_resolution_loop()
        assert loop.is_running()

    def test_scheduled_after_audio_files_are_durable(self):
        """Enrolment reads audio_files back, so the write must already have happened."""
        audio_write = SOURCE.index("conversations_db.create_audio_files_from_chunks")
        schedule = SOURCE.index("schedule_speaker_resolution(uid, cast(Conversation, conversation))")
        assert audio_write < schedule


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
        ), patch.object(pc.conversations_db, 'update_conversation') as update:
            future = pc.schedule_speaker_resolution("uid", conversation)
            assert future is not None
            future.result(timeout=10)

        update.assert_called_once()
        uid, conversation_id, payload = update.call_args[0]
        assert (uid, conversation_id) == ("uid", "conv-1")
        assert payload == {
            pc.SPEAKER_RESOLUTION_SUGGESTIONS_FIELD: [
                {
                    'speaker_id': 0,
                    'person_name': "Ana",
                    'evidence_quote': "hi Ana",
                    'confidence': 0.8,
                    'segment_ids': ["seg-1"],
                }
            ]
        }

    def test_no_suggestions_writes_nothing(self):
        async def _fake(uid, conv):
            return SimpleNamespace(suggested=[])

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ), patch.object(pc.conversations_db, 'update_conversation') as update:
            future = pc.schedule_speaker_resolution("uid", _conversation())
            assert future is not None
            future.result(timeout=10)

        update.assert_not_called()

    def test_a_failing_pass_is_swallowed(self):
        async def _fake(uid, conv):
            raise RuntimeError("boom")

        with patch('utils.conversations.speaker_resolution.SPEAKER_RESOLUTION_ENABLED', True), patch(
            'utils.conversations.speaker_resolution.resolve_conversation_speakers', _fake
        ), patch.object(pc.conversations_db, 'update_conversation') as update:
            future = pc.schedule_speaker_resolution("uid", _conversation())
            assert future is not None
            future.result(timeout=10)

        update.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
