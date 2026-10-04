import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.structured import NoteClaim, Section, Structured
from models.structured_extraction import EpisodeStructuredExtraction, RichStructuredExtraction, StructuredExtraction
from utils.conversations.episode_evidence import (
    EvidenceItem,
    capture_evidence,
    claim_violations,
    context_pack_evidence,
    meeting_evidence,
    open_task_evidence,
    render_episode_evidence,
)
from utils.llm.conversation_notes_prompts import (
    conversation_notes_static_instructions as _conversation_notes_static_instructions,
)
from utils.llm.episode_notes_prompts import EPISODE_CONTRACT, episode_static_instructions
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage, rich_static_instructions, screen_frames_message

START = datetime(2026, 1, 12, 10, tzinfo=timezone.utc)


def claim(target, text, id='screen_ocr:1', provenance='written', private=False):
    return NoteClaim(target=target, text=text, evidence_ids=[id], provenance=provenance, private=private)


def valid_note(title='Written approval', overview='The message shows approval.'):
    return Structured(
        title=title, overview=overview, note_claims=[claim('/title', title), claim('/overview', overview)]
    )


@pytest.fixture(scope='module', autouse=True)
def processing():
    from testing.import_isolation import stub_modules

    with stub_modules({}):
        from utils.llm import conversation_processing
        import utils.conversations.meeting_notes_wiring

        yield conversation_processing


def test_flag_defaults_off_and_reads_env_at_call_boundary(monkeypatch):
    from utils.conversations import meeting_notes_wiring as wiring

    monkeypatch.delenv('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED', raising=False)
    assert not wiring.meeting_notes_episode_evidence_enabled()
    for raw in ('true', '1', 'on', 'YES'):
        monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED', raw)
        assert wiring.meeting_notes_episode_evidence_enabled()
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED', 'off')
    assert not wiring.meeting_notes_episode_evidence_enabled()


def test_flag_off_prompt_bytes_pinned_to_base(processing):
    from utils.llm.meeting_notes_rich_prompts import rich_volatile_instructions

    fixture = json.loads((Path(__file__).parent / 'fixtures/episode_notes/flag_off_prompts.json').read_text())
    static, volatile = (
        processing._conversation_notes_static_instructions,
        processing._conversation_notes_volatile_instructions,
    )
    assert static('FORMAT') == fixture['legacy_static']
    assert volatile(**fixture['kwargs']) == fixture['legacy_volatile']
    assert rich_static_instructions('FORMAT', static) == fixture['rich_static']
    assert (
        rich_volatile_instructions(legacy_volatile=volatile, meeting_context='BACKGROUND SENTINEL', **fixture['kwargs'])
        == fixture['rich_volatile']
    )
    for model in (StructuredExtraction, RichStructuredExtraction):
        assert 'note_claims' not in model.model_json_schema()['properties']
    assert 'note_claims' not in Structured().model_dump()
    assert 'note_claims' in EpisodeStructuredExtraction.model_json_schema()['properties']


def test_adapters_keep_source_time_actor_and_private_rows():
    segment = SimpleNamespace(id='s1', start=1.0, end=3.0, is_user=True, speaker='SPEAKER_00', text='Hello')
    conv = SimpleNamespace(transcript_segments=[segment], source='desktop', started_at=START, finished_at=None)
    speech, state = capture_evidence(conv)
    assert speech.id == 'speech:s1' and speech.source_ref == 's1' and speech.actor == 'account owner'
    assert speech.time == '+1.0s..+3.0s'
    assert state.source_kind == 'device_state'
    pack = SimpleNamespace(
        prior_meetings=[
            SimpleNamespace(title='Earlier', gist='Budget pending', date_label='2026-01-09', open_items=['Check quote'])
        ],
        people_facts=[],
        goals=['Save time'],
        memories=[],
        screen_rows=[{'id': 'row1', 'timestamp': '10:01', 'appName': 'WhatsApp', 'ocrText': 'Ari: agreed'}],
    )
    items = context_pack_evidence(pack)
    assert {item.source_kind for item in items} == {'prior_conversation', 'open_task', 'goal', 'screen_ocr'}
    ocr = items[-1]
    assert ocr.time == '10:01' and ocr.actor is None and ocr.sensitivity == 'private'
    assert 'Ari: agreed' in ocr.content
    assert all(item.sensitivity == 'private' for item in items)
    assert render_episode_evidence(items).startswith('EPISODE EVIDENCE')
    frame = SimpleNamespace(frame_id='f1', summary='Empty call screen', names=(), role='strip', captured_at=START)
    assert meeting_evidence(None, None, [frame])[0].source_ref == 'f1'
    assert (
        open_task_evidence([{'id': 't1', 'description': 'Review'}, {'id': 'done', 'completed': True}])[0].source_ref
        == 't1'
    )


def test_wrong_provenance_invalid_ids_coverage_and_sensitivity():
    evidence = [EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed', sensitivity='private')]
    note = valid_note()
    assert not claim_violations(note, evidence)
    assert all(c.private for c in note.note_claims)
    assert note.note_claims[0].evidence_sources[0].source_kind == 'screen_ocr'
    assert 'content' not in note.note_claims[0].evidence_sources[0].model_dump()
    note.note_claims[0].provenance = 'said'
    assert 'wrong_provenance' in claim_violations(note, evidence)
    note.note_claims[0].evidence_ids = ['invented']
    assert 'invalid_evidence_reference' in claim_violations(note, evidence)
    note.note_claims[0].text = 'not in title'
    assert 'invalid_claim_span' in claim_violations(note, evidence)
    note.sections = [Section(heading='Uncovered', body_markdown='- A detail')]
    assert 'missing_claim_coverage' in claim_violations(note, evidence)


def test_episode_prompt_replaces_speech_only_rules_and_binds_images():
    text = episode_static_instructions('FORMAT', _conversation_notes_static_instructions)
    assert EPISODE_CONTRACT in text
    assert 'sole source of truth' not in text
    assert 'Do not summarize screen text that was not discussed' not in text
    assert 'not part of this conversation' not in text
    frame = NotesFrameImage(frame_id='f1', offset_label='+00:10', data_url='data:image/jpeg;base64,eA==')
    message = screen_frames_message([frame], episode_mode=True)
    assert message['content'][1]['text'] == 'Evidence screen_frame:f1 at +00:10'
    assert message['content'][2]['type'] == 'image_url'
    assert len(screen_frames_message([frame])['content']) == 2


def invoke_notes(processing, monkeypatch, responses, *, episode=True, sections=False):
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps(responses[min(len(calls) - 1, len(responses) - 1)]))

    monkeypatch.setattr(processing, 'get_llm', lambda *a, **k: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)
    prefix = ConversationPromptPrefix(
        conversation_id='synthetic', context='FULL TRANSCRIPT\n', has_usable_content=False
    )
    evidence = [EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed', sensitivity='private')]
    result = processing.get_conversation_notes(
        prefix,
        started_at=START,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=False,
        **({'episode_evidence': evidence} if episode else {}),
    )
    return result, calls


def test_empty_audio_with_screen_evidence_and_one_vacuity_retry(processing, monkeypatch):
    bad = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    good = valid_note().model_dump(mode='json')
    result, calls = invoke_notes(processing, monkeypatch, [bad, good])
    assert len(calls) == 2
    assert 'coverage is missing' in calls[-1][-1].content
    assert result.title == 'Written approval'
    assert all(c.private for c in result.note_claims)
    assert 'EPISODE EVIDENCE' in calls[0][1].content
    assert 'FULL TRANSCRIPT' not in calls[0][1].content


def test_retry_is_bounded_and_remaining_vacuity_rejected(processing, monkeypatch):
    bad = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps(bad))

    monkeypatch.setattr(processing, 'get_llm', lambda *a, **k: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

    with pytest.raises(ValueError, match='vacuity'):
        processing.get_conversation_notes(
            ConversationPromptPrefix('synthetic', 'text'),
            started_at=START,
            language_code='en',
            output_language_code=None,
            tz='UTC',
            task_intelligence_capture=False,
            episode_evidence=[EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed')],
        )
    assert len(calls) == 2


def test_flag_off_still_returns_empty_without_audio(processing, monkeypatch):
    result, calls = invoke_notes(processing, monkeypatch, [], episode=False)
    assert not calls and result.title == '' and 'note_claims' not in result.model_dump()


def test_section_projection_remaps_claims(processing, monkeypatch):
    note = valid_note()
    note.sections = [Section(heading='Written decision', body_markdown='- The message shows approval.')]
    note.note_claims += [
        claim('/sections/0/heading', 'Written decision'),
        claim('/sections/0/body_markdown', 'The message shows approval.'),
    ]
    result, calls = invoke_notes(processing, monkeypatch, [note.model_dump(mode='json')])
    assert len(calls) == 1
    assert result.overview.startswith('## Written decision')
    overview_claims = [c for c in result.note_claims if c.target == '/overview']
    assert len(overview_claims) == 2 and all(c.text in result.overview and c.private for c in overview_claims)


def test_sdk_and_backend_fallback_keep_claims_optional():
    import ast
    from pydantic import BaseModel, Field, field_validator, model_serializer
    from typing import List, Literal, Optional

    source = Path('models/structured.py').read_text()
    fallback = next(node for node in ast.parse(source).body if isinstance(node, ast.Try)).handlers[0].body
    namespace = dict(
        BaseModel=BaseModel,
        Field=Field,
        field_validator=field_validator,
        model_serializer=model_serializer,
        datetime=datetime,
        List=List,
        Literal=Literal,
        Optional=Optional,
    )
    exec(compile(ast.Module(body=fallback, type_ignores=[]), 'structured_fallback', 'exec'), namespace)
    for model in (Structured, namespace['Structured']):
        assert 'note_claims' not in model().model_dump()
        value = model.model_validate(valid_note().model_dump(mode='json'))
        assert value.model_dump()['note_claims'][0]['provenance'] == 'written'


def test_mixed_remote_channel_does_not_gain_an_actor_from_roster():
    from utils.conversations.meeting_participants import MeetingRoster, RosterEntry

    entries = tuple(
        RosterEntry(display_name=name, email=None, organization=None, kind=kind, source='calendar')
        for name, kind in (('Owner', 'owner'), ('Ari', 'human'), ('Noor', 'human'))
    )
    roster = MeetingRoster(entries=entries, display_title=None, title_is_window_title=False)
    segment = SimpleNamespace(
        id='s1', start=0, end=1, text='Approved', speaker='SPEAKER_01', speaker_id=1, is_user=False
    )
    conv = SimpleNamespace(transcript_segments=[segment], photos=[])
    items = capture_evidence(conv, speaker_map={1: 'Ari'}, roster=roster, desktop_capture=True)
    assert items[0].actor is None
    assert json.loads(items[-1].content)['speaker_map'] == {'1': None}


def test_claim_error_receives_one_retry(processing, monkeypatch):
    bad = valid_note().model_dump(mode='json')
    bad['note_claims'][0]['provenance'] = 'said'
    result, calls = invoke_notes(processing, monkeypatch, [bad, valid_note().model_dump(mode='json')])
    assert len(calls) == 2 and 'wrong_provenance' in calls[-1][-1].content
    assert result.note_claims[0].provenance == 'written'


def test_actual_flag_off_request_uses_pinned_prompts(processing, monkeypatch):
    from langchain_core.output_parsers import PydanticOutputParser
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix
    from utils.llm.meeting_notes_rich_prompts import rich_volatile_instructions

    calls = []
    monkeypatch.setattr(
        processing,
        'get_llm',
        lambda *a, **k: SimpleNamespace(
            invoke=lambda messages: (
                calls.append(messages)
                or SimpleNamespace(content='{"title":"Budget","overview":"Approved five percent cut"}')
            )
        ),
    )
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)

    class FrozenTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 12, 10, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(processing, 'datetime', FrozenTime)
    fixture = json.loads((Path(__file__).parent / 'fixtures/episode_notes/flag_off_prompts.json').read_text())
    for rich in (False, True):
        result = processing.get_conversation_notes(
            ConversationPromptPrefix('synthetic', 'FULL TRANSCRIPT\nHello.'),
            started_at=START,
            language_code='en',
            output_language_code=None,
            tz='UTC',
            task_intelligence_capture=False,
            rich_context_enabled=rich,
            meeting_context='BACKGROUND SENTINEL' if rich else None,
        )
        schema = PydanticOutputParser(
            pydantic_object=RichStructuredExtraction if rich else StructuredExtraction
        ).get_format_instructions()
        assert calls[-1][0].content == [
            {'type': 'text', 'text': fixture['rich_static' if rich else 'legacy_static'].replace('FORMAT', schema)}
        ]
        kwargs = {
            **fixture['kwargs'],
            'density': f'Use 1-2 sections; target ~{95 if rich else 80} words across the entire note.',
        }
        expected = (
            rich_volatile_instructions(
                legacy_volatile=processing._conversation_notes_volatile_instructions,
                meeting_context='BACKGROUND SENTINEL',
                **kwargs,
            )
            if rich
            else processing._conversation_notes_volatile_instructions(**kwargs)
        )
        assert calls[-1][1].content == expected
        assert 'note_claims' not in result.model_dump()


def test_same_bounded_ocr_read_retains_messages_only_for_episode_pack(monkeypatch):
    from utils.conversations import meeting_context_pack as pack_module
    from utils.conversations.meeting_participants import MeetingRoster

    calls = []

    def screen_rows(*args, **kwargs):
        calls.append(kwargs)
        return [
            {
                'id': 'row1',
                'timestamp': START,
                'appName': 'WhatsApp',
                'windowTitle': 'Ari',
                'ocrText': 'Ari: postpone our call; sensitive reason',
            }
        ]

    monkeypatch.setattr(pack_module.screen_activity_db, 'get_screen_activity', screen_rows)
    monkeypatch.setattr(pack_module, '_gather_prior_meetings', lambda *a: ())
    monkeypatch.setattr(pack_module, '_gather_people_facts', lambda *a: ())
    monkeypatch.setattr(pack_module, '_gather_goals', lambda *a: ())
    monkeypatch.setattr(pack_module, '_gather_memories', lambda *a: ())
    conv = SimpleNamespace(started_at=START, finished_at=START)
    roster = MeetingRoster(entries=(), display_title=None, title_is_window_title=False)
    legacy = pack_module.gather_meeting_context_pack('synthetic', conv, roster, people=[], include_screen_text=True)
    typed = pack_module.gather_meeting_context_pack(
        'synthetic', conv, roster, people=[], include_screen_text=True, preserve_screen_rows=True
    )
    assert calls == [{'start_date': START, 'end_date': START, 'limit': 80}] * 2
    assert 'sensitive reason' not in legacy.screen_text and not legacy.screen_rows
    assert not typed.screen_text
    items = context_pack_evidence(typed)
    assert 'sensitive reason' in items[0].content and items[0].sensitivity == 'private'
