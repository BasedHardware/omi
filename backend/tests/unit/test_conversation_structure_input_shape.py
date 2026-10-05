"""Source provenance must not determine the input model used for summarization."""

import importlib
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from testing.import_isolation import stub_modules


@pytest.fixture(scope='module')
def stack():
    # Load names within the isolated fixture: other suites stub these modules.
    # Imports run during setup, outside the fast-unit call-phase CPU budget.
    with stub_modules({}):
        yield SimpleNamespace(
            process=importlib.import_module('utils.conversations.process_conversation'),
            models=importlib.import_module('models.conversation'),
            enums=importlib.import_module('models.conversation_enums'),
            structured=importlib.import_module('models.structured'),
            segments=importlib.import_module('models.transcript_segment'),
        )


@pytest.fixture
def processing(stack, monkeypatch):
    pc = stack.process
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_: 'en')
    monkeypatch.setattr(pc, '_proposes_task_candidates', lambda *_: False)
    monkeypatch.setattr(pc, 'track_usage', lambda *_, **__: nullcontext())
    monkeypatch.setattr(pc, '_meeting_notes_rich_context_enabled', lambda: False)
    monkeypatch.setattr(pc, '_fetch_dedup_candidates', lambda *_, **__: [])
    monkeypatch.setattr(pc, '_fetch_dedup_candidates_for_query', lambda *_, **__: [])
    monkeypatch.setattr(pc, '_primary_user_name', lambda *_: None)
    monkeypatch.setattr(pc, 'submit_relevance_shadow', lambda **_: None)
    monkeypatch.setattr(pc, 'decide_relevance', lambda **_: SimpleNamespace(discard=False, reason='kept'))
    return pc


@pytest.mark.parametrize('source', ['workflow', 'external_integration'])
@pytest.mark.parametrize('model_name', ['Conversation', 'CreateConversation'])
@pytest.mark.parametrize('notes_v2', [False, True])
def test_segment_models_use_transcript_even_with_integration_provenance(
    stack, processing, monkeypatch, source, model_name, notes_v2
):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    segment = stack.segments.TranscriptSegment(
        id='segment-1', text='Synthetic transcript', speaker='SPEAKER_00', is_user=False, start=0, end=10
    )
    fields = dict(started_at=now, finished_at=now, source=source, transcript_segments=[segment])
    if model_name == 'Conversation':
        fields.update(id='segment-conversation', created_at=now, structured=stack.structured.Structured())
    conversation = getattr(stack.models, model_name)(**fields)
    assert not hasattr(conversation, 'text_source')
    transcript = Mock(return_value=('Synthetic transcript', '[segment-1] Synthetic transcript', {}))
    monkeypatch.setattr(processing, 'conversation_transcripts_for_llm', transcript)
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: notes_v2)
    structured = stack.structured.Structured(title='Segment summary')
    legacy = Mock(return_value=structured)
    notes = Mock(return_value=structured)
    actions = Mock(return_value=[])
    prefix = Mock(return_value='Synthetic prefix')
    monkeypatch.setattr(processing, 'get_transcript_structure', legacy)
    monkeypatch.setattr(processing, 'get_conversation_notes', notes)
    monkeypatch.setattr(processing, 'build_conversation_prompt_prefix', prefix)
    monkeypatch.setattr(processing, 'extract_action_items', actions)
    message = Mock(side_effect=AssertionError('Segment input reached message summarization'))
    monkeypatch.setattr(processing, 'get_message_structure', message)

    result, discarded = processing._get_structured('synthetic-uid', 'en', conversation)

    assert result is structured
    assert discarded is False
    transcript.assert_called_once_with('synthetic-uid', conversation, None)
    message.assert_not_called()
    if notes_v2:
        notes.assert_called_once()
        assert prefix.call_args.kwargs['transcript_segment_ids'] == ['segment-1']
        legacy.assert_not_called()
        actions.assert_not_called()
    else:
        legacy.assert_called_once()
        assert legacy.call_args.kwargs['transcript_segment_ids'] == ['segment-1']
        actions.assert_called_once()
        notes.assert_not_called()


@pytest.mark.parametrize('source', ['workflow', 'external_integration'])
@pytest.mark.parametrize('text_source', ['audio', 'message', 'other'])
@pytest.mark.parametrize('notes_v2', [False, True])
def test_external_create_models_keep_text_summarization(stack, processing, monkeypatch, source, text_source, notes_v2):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conversation = stack.models.ExternalIntegrationCreateConversation(
        started_at=now,
        source=source,
        text='Synthetic integration input',
        text_source=getattr(stack.enums.ExternalIntegrationConversationSource, text_source),
        text_source_spec='synthetic',
    )
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: notes_v2)
    transcript = Mock(side_effect=AssertionError('External create input reached segment summarization'))
    monkeypatch.setattr(processing, 'conversation_transcripts_for_llm', transcript)
    structured = stack.structured.Structured(title='External summary')
    providers = {}
    for name in (
        'get_transcript_structure',
        'get_conversation_notes',
        'get_message_structure',
        'summarize_experience_text',
    ):
        providers[name] = Mock(return_value=structured)
        monkeypatch.setattr(processing, name, providers[name])
    prefix = Mock(return_value='Synthetic prefix')
    monkeypatch.setattr(processing, 'build_conversation_prompt_prefix', prefix)
    monkeypatch.setattr(processing, 'extract_action_items', Mock(return_value=[]))

    result, discarded = processing._get_structured('synthetic-uid', 'en', conversation)

    assert result is structured
    assert discarded is False
    transcript.assert_not_called()
    expected = {
        'audio': 'get_conversation_notes' if notes_v2 else 'get_transcript_structure',
        'message': 'get_message_structure',
        'other': 'summarize_experience_text',
    }[text_source]
    providers[expected].assert_called_once()
    for name, provider in providers.items():
        if name != expected:
            provider.assert_not_called()
    if text_source == 'audio' and notes_v2:
        assert prefix.call_args.kwargs['transcript'] == conversation.text
    else:
        assert providers[expected].call_args.args[0] == conversation.text
        if text_source == 'message':
            assert providers[expected].call_args.args[4] == conversation.text_source_spec
        elif text_source == 'other':
            assert providers[expected].call_args.args[1] == conversation.text_source_spec


def _blank_capture(stack):
    now = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
    return stack.models.Conversation(
        id='blank-capture',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=stack.structured.Structured(),
        transcript_segments=[
            stack.segments.TranscriptSegment(
                id='seg-blank', text='   ', speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0, end=3
            )
        ],
        source='omi',
        status='processing',
    )


def test_empty_capture_is_rule_discarded_before_the_notes_model(stack, processing, monkeypatch):
    from unittest.mock import Mock

    from utils.conversations import transcript_for_llm
    from utils.conversations.relevance import decide_relevance

    conversation = stack.models.Conversation(
        id='empty-capture',
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        structured=stack.structured.Structured(),
        transcript_segments=[],
        source='omi',
        status='processing',
    )
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_args, **_kwargs: 'User')
    monkeypatch.setattr(processing, 'decide_relevance', decide_relevance)
    monkeypatch.setattr(processing, '_calendar_overlap_retains_conversation', lambda *_args: False)
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: True)
    notes = Mock(side_effect=AssertionError('empty capture reached the notes model'))
    monkeypatch.setattr(processing, 'get_conversation_notes', notes)
    decisions = []
    _structured, discarded = processing._get_structured(
        'synthetic-uid', 'en', conversation, relevance_observer=decisions.append
    )

    assert discarded is True
    notes.assert_not_called()
    assert [(d.verdict, d.decided_by, d.reason) for d in decisions] == [('discard', 'rule', 'empty_transcript')]


def test_restored_blank_capture_keeps_deterministic_title_without_a_model_call(stack, processing, monkeypatch):
    """A user-restored capture whose transcript renders only structural headers
    keeps through the real relevance path, never reaches the model, and lands on
    the deterministic minimum title instead of a provider error."""
    from unittest.mock import Mock

    from utils.conversations import transcript_for_llm
    from utils.conversations.relevance import decide_relevance
    from utils.llm import conversation_processing as notes_module

    conversation = _blank_capture(stack)
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_args, **_kwargs: 'User')
    monkeypatch.setattr(processing, 'decide_relevance', decide_relevance)
    monkeypatch.setattr(processing, 'relevance_arm', lambda *_args: 'nano')
    monkeypatch.setattr(processing, '_calendar_overlap_retains_conversation', lambda *_args: False)
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: True)
    get_llm = Mock(side_effect=AssertionError('content-free capture reached the notes model'))
    monkeypatch.setattr(notes_module, 'get_llm', get_llm)

    decisions = []
    structured, discarded = processing._get_structured(
        'synthetic-uid',
        'en',
        conversation,
        user_kept=True,
        relevance_observer=decisions.append,
    )

    assert discarded is False
    assert structured.title == ''
    assert [(d.verdict, d.decided_by, d.reason) for d in decisions] == [('keep', 'user', 'restored')]
    get_llm.assert_not_called()

    restored = processing._get_conversation_obj(
        'synthetic-uid', structured, conversation, relevance_discarded=discarded
    )
    assert restored.discarded is False
    assert restored.structured.title.startswith('Recording · ')


@pytest.mark.parametrize('episode_enabled', [False, True])
@pytest.mark.parametrize('recovery', [False, True])
def test_discard_unchanged_and_episode_inputs_not_gathered(stack, processing, monkeypatch, episode_enabled, recovery):
    from utils.conversations.episode_evidence import EvidenceItem

    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conversation = stack.models.CreateConversation(
        started_at=now, finished_at=now, source='desktop', transcript_segments=[], photos=[]
    )
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: True)
    monkeypatch.setattr(processing, '_meeting_notes_episode_evidence_enabled', lambda uid: episode_enabled)
    monkeypatch.setattr(processing, '_meeting_notes_screen_text_context_enabled', lambda: True)
    monkeypatch.setattr(processing, 'conversation_transcripts_for_llm', lambda *a: ('', '', {}))
    monkeypatch.setattr(processing, 'recovery_minimum_terminal_enabled', lambda: True)
    relevance = Mock(return_value=SimpleNamespace(discard=True, reason='empty', decided_by='rule'))
    monkeypatch.setattr(processing, 'decide_relevance', relevance)
    gathered = []

    def inputs(*args, **kwargs):
        gathered.append(kwargs)
        kwargs['evidence_items'].append(
            EvidenceItem(id='screen_frame:f1', source_kind='screen_frame', content='Empty call screen')
        )
        return None, None, True, ()

    monkeypatch.setattr(processing, 'rich_notes_inputs', inputs)
    notes = Mock(return_value=stack.structured.Structured(title='Observed empty call'))
    monkeypatch.setattr(processing, 'get_conversation_notes', notes)
    result, discarded = processing._get_structured(
        'synthetic-uid',
        'en',
        conversation,
        trigger=processing.ProcessingTrigger.SERVER_RECOVERY if recovery else processing.ProcessingTrigger.CAPTURE_END,
    )
    relevance.assert_called_once()
    assert relevance.call_args.kwargs['texts'] == []
    assert relevance.call_args.kwargs['has_photos'] is False
    assert relevance.call_args.kwargs['trusted_wake_word'] is False
    assert discarded is True
    assert not gathered
    notes.assert_not_called()


def test_episode_inputs_gathered_once_after_keep_decision(stack, processing, monkeypatch):
    from utils.conversations.episode_evidence import EvidenceItem

    conversation = _blank_capture(stack)
    events = []
    monkeypatch.setattr(processing, '_conversation_notes_v2_enabled', lambda: True)
    monkeypatch.setattr(processing, '_meeting_notes_episode_evidence_enabled', lambda uid: True)
    monkeypatch.setattr(processing, '_meeting_notes_screen_text_context_enabled', lambda: True)
    monkeypatch.setattr(processing, 'conversation_transcripts_for_llm', lambda *a: ('', '', {}))

    def keep(**kwargs):
        events.append('keep')
        return SimpleNamespace(discard=False, reason='kept')

    def inputs(*args, **kwargs):
        events.append('gather')
        kwargs['evidence_items'].append(
            EvidenceItem(id='screen_frame:f1', source_kind='screen_frame', content='Synthetic screen')
        )
        return None, None, True, ()

    def notes(*args, **kwargs):
        events.append('notes')
        assert {'speech', 'device_state', 'screen_frame'} == {item.source_kind for item in kwargs['episode_evidence']}
        return stack.structured.Structured(title='Observed screen')

    monkeypatch.setattr(processing, 'decide_relevance', keep)
    monkeypatch.setattr(processing, 'rich_notes_inputs', inputs)
    monkeypatch.setattr(processing, 'get_conversation_notes', notes)
    _, discarded = processing._get_structured('synthetic-uid', 'en', conversation)
    assert not discarded and events == ['keep', 'gather', 'notes']
