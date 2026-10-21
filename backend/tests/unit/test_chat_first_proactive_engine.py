"""Meeting treatment remains independent of automatic Chat cards."""

from datetime import datetime, timedelta, timezone
from utils.conversations import meeting_receipt
from utils.conversations.meeting_treatment import (
    MIN_MEETING_DURATION_SECONDS,
    deduplicated_transcribed_speech_seconds,
    is_meeting_treatment_eligible,
)

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def test_meeting_treatment_requires_five_minutes_and_deduplicated_speech():
    eligible = {
        'source': 'desktop',
        'discarded': False,
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=MIN_MEETING_DURATION_SECONDS),
        'external_data': {'conversation_role': 'meeting'},
        'transcript_segments': [
            {'text': 'first exchange', 'start': 0, 'end': 35},
            # Duration is the transcript span (#19391); the two intervals also
            # provide exactly the required sixty seconds of distinct speech.
            {
                'text': 'second exchange',
                'start': MIN_MEETING_DURATION_SECONDS - 25,
                'end': MIN_MEETING_DURATION_SECONDS,
            },
        ],
    }
    assert is_meeting_treatment_eligible(eligible) is True

    short_call = {
        **eligible,
        'transcript_segments': [
            *eligible['transcript_segments'][:-1],
            {**eligible['transcript_segments'][-1], 'end': MIN_MEETING_DURATION_SECONDS - 1},
        ],
    }
    assert is_meeting_treatment_eligible(short_call) is False

    duplicate_streams = {
        **eligible,
        'finished_at': NOW + timedelta(minutes=20),
        'transcript_segments': [
            {'text': 'remote stream from mic', 'start': 0, 'end': 45},
            {'text': 'same remote stream from system audio', 'start': 0, 'end': 45},
        ],
    }
    assert deduplicated_transcribed_speech_seconds(duplicate_streams['transcript_segments']) == 45
    assert is_meeting_treatment_eligible(duplicate_streams) is False


def test_finalized_meeting_records_audit_receipt_without_a_chat_intent(monkeypatch):
    calls = []
    monkeypatch.setattr(
        meeting_receipt.jobs_db,
        'record_meeting_receipt',
        lambda *args, **kwargs: calls.append(kwargs) or {'status': 'recorded'},
    )
    monkeypatch.setattr(
        meeting_receipt.jobs_db,
        'mark_meeting_receipt_intent_persisted',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not post to Chat')),
    )
    conversation = {
        'id': 'meeting',
        'status': 'completed',
        'source': 'desktop',
        'external_data': {'conversation_role': 'meeting'},
        'transcript_segments': [],
    }
    assert meeting_receipt.record_finalized_meeting_receipt('user', conversation) == {'status': 'recorded'}
    assert len(calls) == 1
