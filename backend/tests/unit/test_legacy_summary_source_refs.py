"""Source-reference validation at the legacy summary composition boundary."""

from contextlib import nullcontext
from datetime import datetime, timezone

from models.conversation import CreateConversation
from models.conversation_enums import ConversationSource
from models.structured import ActionItem, Section, Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations import process_conversation as process_module


def _conversation() -> CreateConversation:
    return CreateConversation(
        started_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 17, 12, 5, tzinfo=timezone.utc),
        source=ConversationSource.phone,
        transcript_segments=[
            TranscriptSegment(
                id='s1',
                text='The first source point',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                start=0,
                end=2,
            ),
            TranscriptSegment(
                id='s2',
                text='The second source point',
                speaker='SPEAKER_01',
                speaker_id=1,
                is_user=False,
                start=2,
                end=4,
            ),
        ],
    )


def test_flag_off_legacy_composition_validates_all_summary_evidence(monkeypatch):
    """The legacy path uses typed segment IDs after both structure and actions run."""
    monkeypatch.delenv('CONVERSATION_NOTES_V2_ENABLED', raising=False)
    conversation = _conversation()
    legacy_structure = Structured(
        title='Legacy note',
        overview='Legacy overview',
        sections=[
            Section(
                heading='Grounded',
                body_markdown='- Source point',
                source_segment_ids=['s2', 'invented', 's2', 's1'],
            )
        ],
    )
    extracted_actions = [ActionItem(description='Follow up', source_segment_ids=['invented', 's1', 's1'])]

    monkeypatch.setattr(process_module.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(process_module.users_db, 'get_user_language_preference', lambda *_args: None)
    monkeypatch.setattr(process_module, '_proposes_task_candidates', lambda *_args: False)
    monkeypatch.setattr(process_module, '_detect_duplicate_capture', lambda *_args: None)
    monkeypatch.setattr(process_module, 'track_usage', lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(process_module, 'should_discard_conversation', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        process_module,
        'conversation_transcripts_for_llm',
        lambda *_args, **_kwargs: (
            'User: The first source point\nSpeaker 1: The second source point',
            '[s1 0] The first source point\n[s2 1] The second source point',
            {0: 'User', 1: None},
        ),
    )

    captured_kwargs = {}

    def fake_legacy_structure(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        return legacy_structure

    monkeypatch.setattr(process_module, 'get_transcript_structure', fake_legacy_structure)
    monkeypatch.setattr(process_module, 'extract_action_items', lambda *_args, **_kwargs: extracted_actions)
    monkeypatch.setattr(process_module, '_fetch_dedup_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(process_module, '_primary_user_name', lambda *_args: None)

    result, discarded = process_module._get_structured('uid-legacy', 'en', conversation)

    assert discarded is False
    assert captured_kwargs['transcript_segment_ids'] == ['s1', 's2']
    assert result.sections[0].source_segment_ids == ['s2', 's1']
    assert result.action_items[0].source_segment_ids == ['s1']


def test_flag_off_reprocess_composition_validates_source_evidence(monkeypatch):
    monkeypatch.delenv('CONVERSATION_NOTES_V2_ENABLED', raising=False)
    conversation = _conversation()
    reprocessed_structure = Structured(
        title='Reprocessed note',
        sections=[Section(heading='Topic', body_markdown='- Detail', source_segment_ids=['s1', 'unknown'])],
    )
    extracted_actions = [ActionItem(description='Follow up', source_segment_ids=['s2', 's2', 'unknown'])]
    captured_kwargs = {}

    monkeypatch.setattr(process_module.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(process_module.users_db, 'get_user_language_preference', lambda *_args: None)
    monkeypatch.setattr(process_module, '_proposes_task_candidates', lambda *_args: False)
    monkeypatch.setattr(process_module, 'track_usage', lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(
        process_module,
        'conversation_transcripts_for_llm',
        lambda *_args, **_kwargs: ('normal transcript', '[s1 0] one\n[s2 1] two', {0: 'User', 1: None}),
    )

    def fake_reprocess(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        return reprocessed_structure

    monkeypatch.setattr(process_module, 'get_reprocess_transcript_structure', fake_reprocess)
    monkeypatch.setattr(process_module, 'extract_action_items', lambda *_args, **_kwargs: extracted_actions)
    monkeypatch.setattr(process_module, '_fetch_dedup_candidates', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(process_module, '_primary_user_name', lambda *_args: None)

    result, discarded = process_module._get_structured('uid-legacy', 'en', conversation, force_process=True)

    assert discarded is False
    assert captured_kwargs['transcript_segment_ids'] == ['s1', 's2']
    assert result.sections[0].source_segment_ids == ['s1']
    assert result.action_items[0].source_segment_ids == ['s2']
