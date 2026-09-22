"""Opt-in reprocessing sends corrected identity through real prompt formatting."""

from contextlib import nullcontext
from datetime import datetime, timezone

from models.conversation import Conversation
from models.other import Person
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import process_conversation as pc
from utils.conversations import transcript_for_llm


def test_corrected_person_reaches_summary_provider(monkeypatch):
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    conversation = Conversation(
        id='c',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(),
        transcript_segments=[
            TranscriptSegment(
                id='s', text='Synthetic meeting text', speaker_id=4, is_user=False, person_id='correct', start=0, end=5
            )
        ],
    )
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *a, **k: 'Owner')
    monkeypatch.setattr(pc, '_primary_user_name', lambda uid: 'Owner')
    monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: False)
    monkeypatch.setattr(pc, 'track_usage', lambda *a, **k: nullcontext())
    monkeypatch.setattr(pc, '_fetch_dedup_candidates', lambda *a: [])
    monkeypatch.setattr(pc, 'extract_action_items', lambda *a, **k: [])
    prompts = []

    def summarize(transcript, *a, **k):
        prompts.append(transcript)
        return Structured(overview='Updated summary')

    monkeypatch.setattr(pc, 'get_reprocess_transcript_structure', summarize)
    result, discarded = pc._get_structured(
        'synthetic', 'en', conversation, force_process=True, people=[Person(id='correct', name='Correct Name')]
    )
    assert not discarded and result.overview == 'Updated summary'
    assert len(prompts) == 1 and 'Correct Name: Synthetic meeting text' in prompts[0]
