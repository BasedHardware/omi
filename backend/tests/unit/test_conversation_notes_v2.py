from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# firebase_admin reaches google.auth.credentials lazily. When an earlier test module has already
# imported google.auth without that submodule, the attribute lookup fails during our imports below.
import google.auth.credentials  # noqa: F401

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.structured import ActionItem, Structured
from testing.import_isolation import stub_modules


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        # Keep production-module import cost out of individual fast-unit timing.
        import utils.conversations.meeting_context  # noqa: F401
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401
        import utils.llm.working_observations  # noqa: F401

        yield


def _meeting_context() -> CalendarMeetingContext:
    return CalendarMeetingContext(
        calendar_event_id='screen-activity',
        title='Fulcrum Dynamics',
        participants=[
            MeetingParticipant(name='David'),
            MeetingParticipant(name='Ash Kalb', email='ash@fulcradynamics.com'),
        ],
        platform='Zoom',
        start_time=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        duration_minutes=30,
        calendar_source='screen_activity',
    )


def _long_transcript() -> str:
    detail = 'Mem0 HSM GPT store catalog revoke Greg Leaf Discord September 8 '
    return '\n\n'.join(
        [f'[segment:s{i} {i:.3f}-{i + 1:.3f}] {"David" if i % 2 == 0 else "Speaker 1"}: {detail}' for i in range(100)]
    )


def test_structured_additions_are_backward_compatible():
    old = Structured.model_validate(
        {
            'title': 'Legacy note',
            'overview': 'Old overview',
            'emoji': '🧠',
            'category': 'work',
            'action_items': [{'description': 'Send invite'}],
            'events': [],
        }
    )

    assert old.sections == []
    assert old.action_items[0].owner_name is None
    assert old.action_items[0].context is None
    assert old.action_items[0].due_certainty is None


def test_merged_note_call_projects_sections_and_preserves_action_detail(monkeypatch):
    from utils.llm import conversation_processing
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-123',
        transcript=_long_transcript(),
        started_at=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        timezone_name='America/New_York',
        language_code='en',
        calendar_context=_meeting_context(),
    )
    captured = {}

    class Model:
        def invoke(self, messages):
            captured['messages'] = messages
            return SimpleNamespace(content='''{
                  "title":"Ash and David Discuss Agent Infrastructure",
                  "overview":"compatibility",
                  "emoji":"🔐",
                  "category":"technology",
                  "sections":[{"heading":"Agent operations","body_markdown":"Ash runs ~12 long-running agents.","source_segment_ids":["s1"]}],
                  "action_items":[{"description":"Send Fulcrum dinner invite","owner_name":"David","context":"Tentative NYC lunch or dinner with Ash.","due_at":"2026-09-08T12:00:00","due_certainty":"tentative","capture_owner":"user","source_segment_ids":["s9"]}],
                  "events":[]
                }''')

    def fake_get_llm(_feature, **kwargs):
        captured['kwargs'] = kwargs
        return Model()

    monkeypatch.setattr(conversation_processing, 'get_llm', fake_get_llm)
    monkeypatch.setattr(conversation_processing, 'shared_conversation_cache_supported', lambda: True)
    result = conversation_processing.get_conversation_notes(
        prefix,
        started_at=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        language_code='en',
        output_language_code='en',
        tz='America/New_York',
        task_intelligence_capture=True,
    )

    assert result.overview == '## Agent operations\n\nAsh runs ~12 long-running agents.'
    assert result.events == []
    assert result.action_items[0].owner_name == 'David'
    assert result.action_items[0].due_certainty == 'tentative'
    assert captured['kwargs']['cache_key'] == 'omi-conv-conv-123'
    assert captured['messages'][1]['content'][0]['prompt_cache_breakpoint'] == {'mode': 'explicit'}
    instructions = captured['messages'][-1].content
    assert 'Never normalize or "correct" an uncertain name from general knowledge' in instructions
    assert 'participant email domain corroborates' in instructions
    assert 'fulcradynamics.com corroborates "Fulcra Dynamics" over ASR "Vulcra"' in instructions
    assert 'Ash Kalb <ash@fulcradynamics.com>' in prefix.context


def test_note_and_memory_use_byte_identical_shared_prefix(monkeypatch):
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix
    from utils.llm.working_observations import extract_l1_memory_archive_items_from_text

    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-shared',
        transcript=_long_transcript(),
        started_at=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        timezone_name='America/New_York',
        language_code='en',
        calendar_context=_meeting_context(),
    )
    expected = prefix.messages(cache_enabled=True)
    rebuilt_for_memory = build_conversation_prompt_prefix(
        conversation_id='conv-shared',
        transcript=_long_transcript(),
        started_at=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        timezone_name='America/New_York',
        language_code='en',
        calendar_context=_meeting_context(),
    )
    assert rebuilt_for_memory.messages(cache_enabled=True) == expected
    assert 'Speaker 1:' not in prefix.context
    assert 'Ash Kalb:' in prefix.context

    class MemoryModel:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content='{"items": []}')

    model = MemoryModel()
    result = extract_l1_memory_archive_items_from_text(
        uid='u1',
        source_id='conv-shared',
        source_type='voice_transcript',
        text=_long_transcript(),
        prompt_prefix=prefix,
        prompt_cache_enabled=True,
        llm=model,
    )

    assert result == []
    assert model.messages[:2] == expected


def test_screen_activity_context_is_bounded_to_conferencing_rows_and_names():
    from utils.conversations.meeting_context import context_from_screen_activity

    # Names come only from a source that asserts participation (here the Meet
    # roster sentence). A bare capitalised line is NOT enough — see
    # tests/unit/test_screen_activity_identity.py for why.
    context = context_from_screen_activity(
        [
            {'appName': 'Cursor', 'windowTitle': 'notes.py', 'ocrText': 'Not A Participant'},
            {
                'appName': 'zoom.us',
                'windowTitle': 'Fulcrum Dynamics',
                'ocrText': 'Ash Kalb and David Zhang are in this call\nMute\nStop Video',
            },
        ],
        started_at=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 18, 14, 30, tzinfo=timezone.utc),
    )

    assert context is not None
    assert context.title == 'Fulcrum Dynamics'
    assert [participant.name for participant in context.participants] == ['Ash Kalb', 'David Zhang']
    assert context.calendar_source == 'screen_activity'


def test_action_item_new_fields_round_trip():
    item = ActionItem(
        description='Send invite',
        owner_name='David',
        context='Tentative dinner with Ash.',
        due_certainty='tentative',
    )
    assert ActionItem.model_validate_json(item.model_dump_json()) == item
