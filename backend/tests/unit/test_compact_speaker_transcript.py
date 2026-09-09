"""Compact cluster-key transcript contract (SCA-454).

The summarizer prefix must never carry `Speaker N:` dialogue labels — the model
copies them into titles and overviews. Speaker identity is paid for once as
`spk` map metadata lines; turns key on `[segment-id cluster]` headers with
run-length keys. These tests pin the renderer, the prefix map (including the
one-name calendar guard), the screenshot-equivalent sanitize path, and
`get_app_result` stripping.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# firebase_admin reaches google.auth.credentials lazily. Same guard as test_conversation_notes_v2.
import google.auth.credentials  # noqa: F401

from models.app import App
from models.other import Person
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import stub_modules


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        import utils.conversations.transcript_for_llm  # noqa: F401
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401

        yield


def _seg(segment_id: str, text: str, *, speaker: str = 'SPEAKER_00', is_user: bool = True, person_id=None):
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker=speaker,
        is_user=is_user,
        person_id=person_id,
        start=0.0,
        end=2.0,
    )

    return int(speaker.split('_', 1)[1])


def test_renderer_uses_cluster_keys_and_run_length_form(monkeypatch):
    from utils.conversations import transcript_for_llm

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('seg-1', 'the flush is about 9mm'),
            _seg('seg-2', 'it can sit flush with the wall'),
            _seg('seg-3', 'can it sit flush', speaker='SPEAKER_01', is_user=False),
            _seg('seg-4', 'yes, barely visible', speaker='SPEAKER_01', is_user=False),
            _seg('seg-5', 'ultra-thin then'),
        ]
    )

    rendered, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map('uid-1', conversation)

    assert rendered == (
        '[seg-1 0] the flush is about 9mm\n\n'
        '[seg-2] it can sit flush with the wall\n\n'
        '[seg-3 1] can it sit flush\n\n'
        '[seg-4] yes, barely visible\n\n'
        '[seg-5 0] ultra-thin then'
    )
    assert 'Speaker' not in rendered
    assert 'segment:' not in rendered
    assert '0.000' not in rendered
    assert speaker_map == {0: 'David', 1: None}


def test_speaker_map_binds_only_evidence_backed_names(monkeypatch):
    from utils.conversations import transcript_for_llm

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    people = [Person(id='p1', name='Alice')]
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('seg-1', 'hi', speaker='SPEAKER_02'),
            _seg('seg-2', 'hello', speaker='SPEAKER_05', is_user=False, person_id='p1'),
            _seg('seg-3', 'hey', speaker='SPEAKER_00', is_user=False),
        ]
    )

    _, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map('uid-1', conversation, people)

    assert speaker_map == {2: 'David', 5: 'Alice', 0: None}


def test_prefix_renders_spk_map_and_never_speaker_labels(monkeypatch):
    from utils.conversations import transcript_for_llm
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('seg-1', 'the flush is about 9mm'),
            _seg('seg-2', 'can it sit flush', speaker='SPEAKER_01', is_user=False),
        ]
    )
    transcript, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map('uid-1', conversation)

    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-1',
        transcript=transcript,
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        speaker_map=speaker_map,
    )

    assert 'spk 0 David\nspk 1 ?' in prefix.context
    assert 'Speaker 0' not in prefix.context
    assert 'Speaker 1:' not in prefix.context
    assert '[seg-1 0] the flush is about 9mm' in prefix.context


def test_calendar_guard_resolves_single_unresolved_cluster_from_map():
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-1',
        transcript='[seg-1 0] hi',
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        calendar_context=None,
        speaker_map={0: 'David', 1: None},
    )

    assert 'spk 1 ?' in prefix.context


def test_calendar_guard_requires_exactly_one_unresolved_and_one_remaining_name():
    from models.calendar_context import CalendarMeetingContext, MeetingParticipant
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    context = CalendarMeetingContext(
        calendar_event_id='evt-1',
        title='1:1',
        participants=[MeetingParticipant(name='David'), MeetingParticipant(name='Ash')],
        platform='Zoom',
        start_time=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        duration_minutes=30,
    )
    # Two unresolved clusters, one remaining name: ambiguous, so nothing is bound.
    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-1',
        transcript='[seg-1 0] hi',
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        calendar_context=context,
        speaker_map={0: None, 1: None},
    )
    assert 'spk 0 ?' in prefix.context
    assert 'spk 1 ?' in prefix.context
    assert 'spk 0 David' not in prefix.context

    # One unresolved cluster, one remaining participant: bound through the map, not a transcript rewrite.
    resolved = build_conversation_prompt_prefix(
        conversation_id='conv-2',
        transcript='[seg-1 0] hi',
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        calendar_context=context,
        speaker_map={0: 'David', 1: None},
    )
    assert 'spk 1 Ash' in resolved.context
    assert 'Speaker' not in resolved.context


def _poisoned_notes_model(captured):
    class Model:
        def invoke(self, messages):
            captured['messages'] = messages
            return SimpleNamespace(content='''{
                  "title":"Speaker 0 Examines Ultra-Thin Flush Design",
                  "overview":"Speaker 0 said the flush is about 9mm.",
                  "emoji":"🔧",
                  "category":"work",
                  "sections":[{"heading":"Flush design","body_markdown":"- The flush is about 9mm deep, so it can sit flush with the wall.","source_segment_ids":["seg-1"]}],
                  "action_items":[],
                  "events":[]
                }''')

    return Model()


def test_screenshot_equivalent_scrap_yields_no_speaker_placeholder_title(monkeypatch):
    """11s hardware scrap, unresolved cluster, model that copies Speaker 0 anyway."""
    from utils.conversations import transcript_for_llm
    from utils.llm import conversation_processing
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('seg-1', 'the flush is about 9mm, ultra-thin', speaker='SPEAKER_00', is_user=False),
            _seg('seg-2', 'so it can sit flush with the wall', speaker='SPEAKER_00', is_user=False),
        ]
    )
    transcript, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map('uid-1', conversation)
    prefix = build_conversation_prompt_prefix(
        conversation_id='conv-scrap',
        transcript=transcript,
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        speaker_map=speaker_map,
    )
    assert 'spk 0 ?' in prefix.context
    assert 'Speaker 0' not in prefix.context

    captured: dict = {}
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *_a, **_k: _poisoned_notes_model(captured))
    monkeypatch.setattr(conversation_processing, 'shared_conversation_cache_supported', lambda: False)
    structured = conversation_processing.get_conversation_notes(
        prefix,
        started_at=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
    )

    assert structured.title == 'Examines Ultra-Thin Flush Design'
    assert 'Speaker 0' not in structured.title
    assert 'Speaker 0' not in structured.overview
    assert 'flush is about 9mm' in structured.overview
    instructions = captured['messages'][-1].content
    assert 'Speaker keys are diarization clusters, not names' in instructions


def _summary_app() -> App:
    return App(
        id='app-1',
        name='Summary',
        category='productivity',
        author='Omi',
        description='Summarizes the conversation.',
        image='/app.png',
        capabilities={'memories'},
    )


def test_get_app_result_strips_speaker_and_spk_placeholders(monkeypatch):
    from utils.llm import conversation_processing
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

    monkeypatch.setattr(
        conversation_processing,
        'get_llm',
        lambda *_a, **_k: SimpleNamespace(
            invoke=lambda _messages: SimpleNamespace(
                content='```json\nSpeaker 0 said the flush is 9mm. spk 1 confirmed it. SPEAKER_02 agreed.```'
            )
        ),
    )

    legacy = conversation_processing.get_app_result('raw transcript', [], _summary_app())
    assert legacy == 'said the flush is 9mm. confirmed it. agreed.'

    prefix = ConversationPromptPrefix(conversation_id='conv-1', context='FULL TRANSCRIPT\n[seg-1 0] hi')
    prefixed = conversation_processing.get_app_result('raw transcript', [], _summary_app(), prompt_prefix=prefix)
    assert prefixed == 'said the flush is 9mm. confirmed it. agreed.'
