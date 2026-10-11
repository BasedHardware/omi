import json
import os
import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.structured import NoteClaim, Structured
from models.episode_extraction import EpisodeStructuredExtraction
from models.structured_extraction import RichStructuredExtraction, StructuredExtraction
from utils.conversations.episode_evidence import (
    EvidenceItem,
    context_pack_evidence,
    meeting_evidence,
    open_task_evidence,
    render_episode_evidence,
)
from utils.llm.conversation_notes_prompts import (
    conversation_notes_static_instructions as _conversation_notes_static_instructions,
    conversation_notes_volatile_instructions as _conversation_notes_volatile_instructions,
)
from utils.llm.episode_notes_prompts import EPISODE_CONTRACT, episode_static_instructions
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage, rich_static_instructions, screen_frames_message

START = datetime(2026, 1, 12, 10, tzinfo=timezone.utc)


def claim(target, text, id='screen_ocr:1', provenance='written'):
    return NoteClaim(target=target, text=text, evidence_ids=[id], provenance=provenance)


def valid_note(title='Written approval', overview='The message shows approval.'):
    return Structured(
        title=title, overview=overview, note_claims=[claim('/title', title), claim('/overview', overview)]
    )


@pytest.fixture(autouse=True)
def claim_generation_mode(monkeypatch):
    # These regression fixtures exercise the existing annotated path explicitly.
    monkeypatch.setenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'true')
    # Isolate annotation/repair regressions from the separately tested selector.
    from dataclasses import replace
    from config import episode_writer

    configured = episode_writer.episode_writer_settings
    monkeypatch.setenv('MEETING_NOTES_EPISODE_SELECTION', 'compact')
    monkeypatch.setattr(
        episode_writer,
        'episode_writer_settings',
        lambda: (
            replace(configured(), selection='compact')
            if os.getenv('MEETING_NOTES_EPISODE_SELECTION') == 'compact'
            else configured()
        ),
    )
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'default')


@pytest.fixture(scope='module', autouse=True)
def processing():
    from testing.import_isolation import stub_modules

    with stub_modules({}):
        from utils.llm import conversation_processing
        import utils.conversations.meeting_notes_wiring

        # Optional retrieval is now lazy; exclude its cold import from per-test call timing.
        import utils.conversations.meeting_context_pack

        yield conversation_processing


def test_flag_off_prompt_bytes_pinned_to_base(processing):
    from utils.llm.meeting_notes_rich_prompts import rich_volatile_instructions

    fixture = json.loads((Path(__file__).parent / 'fixtures/episode_notes/flag_off_prompts.json').read_text())
    static, volatile = (
        processing._conversation_notes_static_instructions,
        _conversation_notes_volatile_instructions,
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


def test_context_adapters_keep_source_time_actor_and_screen_rows():
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
    assert ocr.time == '10:01' and ocr.actor is None
    assert 'Ari: agreed' in ocr.content
    assert render_episode_evidence(items).startswith('EPISODE EVIDENCE')
    frame = SimpleNamespace(frame_id='f1', summary='Empty call screen', names=(), role='strip', captured_at=START)
    assert meeting_evidence(None, None, [frame])[0].source_ref == 'f1'
    assert (
        open_task_evidence([{'id': 't1', 'description': 'Review'}, {'id': 'done', 'completed': True}])[0].source_ref
        == 't1'
    )


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
        claim_schema = model.model_json_schema()['$defs']['NoteClaim']['properties']
        assert 'private' not in claim_schema
        assert 'sensitivity' not in model.model_json_schema()['$defs']['NoteEvidenceRef']['properties']
        legacy = valid_note().model_dump(mode='json')
        legacy['note_claims'][0]['private'] = True
        legacy['note_claims'][0]['evidence_sources'] = [
            {'id': 'screen_ocr:1', 'source_kind': 'screen_ocr', 'sensitivity': 'private'}
        ]
        serialized = model.model_validate(legacy).model_dump()['note_claims'][0]
        assert 'private' not in serialized and 'sensitivity' not in serialized['evidence_sources'][0]


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
    assert 'sensitive reason' in items[0].content


def test_frame_images_keep_screen_roster_identity(processing, monkeypatch):
    wiring = importlib.import_module('utils.conversations.meeting_notes_wiring')
    frame_module = importlib.import_module('utils.conversations.screen_frame_evidence')
    frame = frame_module.ScreenFrameEvidence('frame', START, 'strip', 0.5, ('Screen identity',), 'Private screen text')
    monkeypatch.setattr(wiring, '_screen_frame_evidence', lambda *a: (frame,))
    sources = SimpleNamespace(load_people_documents=lambda *a: [], resolve_owner_identity=lambda *a: (None, ()))
    monkeypatch.setattr(wiring, 'meeting_context_sources', lambda: sources)
    monkeypatch.setattr(wiring, '_rich_meeting_context_block', lambda *a, **k: None)
    monkeypatch.setattr(wiring, 'meeting_notes_screen_frames_context_enabled', lambda: True)
    observed = []
    image = NotesFrameImage('frame', '+00:00', 'data:image/jpeg;base64,eA==')
    monkeypatch.setattr(
        wiring, 'load_notes_frame_images', lambda uid, cid, frames, start: observed.extend(frames) or (image,)
    )
    conv = SimpleNamespace(
        id='synthetic', source='desktop', external_data={'conversation_role': 'meeting'}, started_at=START
    )
    roster, _, _, images = wiring.rich_notes_inputs(
        'synthetic',
        conv,
        None,
        'UTC',
        include_background=True,
        include_screen_text=False,
    )
    assert images == (image,)
    assert observed[0].frame_id == frame.frame_id
    assert observed[0].summary == frame.summary
    assert roster.entries[0].display_name == 'Screen identity'


def test_frame_added_identity_in_calendar_roster_keeps_screen_source():
    from utils.conversations.meeting_participants import MeetingRoster, RosterEntry

    roster = MeetingRoster(
        entries=(
            RosterEntry('Ari', None, None, 'human', 'google'),
            RosterEntry('Bo', None, None, 'human', 'google'),
        ),
        display_title=None,
        title_is_window_title=False,
    )
    calendar = SimpleNamespace(
        calendar_source='google',
        participants=[SimpleNamespace(name='Ari')],
        start_time=START,
        calendar_event_id='synthetic',
        model_dump=lambda **k: {},
    )
    frame = SimpleNamespace(frame_id='f1', names=('Bo',), summary='Synthetic screen', role='strip', captured_at=START)
    items = meeting_evidence(roster, calendar, [frame])
    assert json.loads(items[1].content)['source'] == 'google'
    assert json.loads(items[2].content)['source'] == 'screen_activity'


def test_compact_evidence_preserves_provenance_and_trusted_metadata():
    items = [
        EvidenceItem(
            id='speech:1',
            source_kind='speech',
            time='2026-01-01T10:00:00Z',
            actor='Ari',
            content='Invented message',
            source_ref='s1',
            wake_word_invocation=True,
            diarization_key='cluster:0',
        ),
        EvidenceItem(id='screen:1', source_kind='screen_ocr', content='Invented screen'),
    ]
    rendered = render_episode_evidence(items)
    encoded = json.loads(rendered.split('\n', 1)[1])
    assert encoded['observed_participation'][0] == {
        'id': 'evidence:0',
        'k': 'speech',
        'at': items[0].time,
        'a': 'Ari',
        'c': items[0].content,
        'r': 's1',
        'w': True,
        'd': 'cluster:0',
    }
    assert encoded['expected_context'] == []
    assert 'a' not in encoded['observed_participation'][1] and 'sensitivity' not in encoded['observed_participation'][1]
    assert len(rendered) < len(json.dumps([item.model_dump() for item in items], indent=2))


def test_episode_person_provenance_and_relevance_rules_are_shared():
    from testing.episode_notes.runner import JUDGE_PROMPT, REFERENCE_PROMPT
    from utils.llm.episode_policy import EPISODE_PROVENANCE_RULE, EPISODE_RELEVANCE_RULE
    from utils.llm.meeting_notes_rich_prompts import RICH_PERSON_RULES

    for rule in [EPISODE_PROVENANCE_RULE, EPISODE_RELEVANCE_RULE]:
        assert all(rule in prompt for prompt in [EPISODE_CONTRACT, REFERENCE_PROMPT, JUDGE_PROMPT])
    for line in RICH_PERSON_RULES.splitlines():
        if 'Fill participants from the roster and transcript evidence' in line:
            assert line not in EPISODE_CONTRACT
        else:
            assert line in EPISODE_CONTRACT
    assert 'Fill participants from the roster and transcript evidence' not in EPISODE_CONTRACT
    assert 'List a person in participants only when observed participation shows they took part' in EPISODE_CONTRACT
    assert 'expected_context' in EPISODE_CONTRACT and 'observed_participation' in EPISODE_CONTRACT
    assert "Never infer anyone's gender" in EPISODE_CONTRACT
    assert 'Treat an AI agent as a separate speaker' in EPISODE_CONTRACT
    assert 'Set meeting_type only' not in EPISODE_CONTRACT
    assert 'Section headings need no claims' in EPISODE_CONTRACT
    schema = EpisodeStructuredExtraction.model_json_schema()
    assert 'evidence_sources' not in schema['$defs']['ExtractedNoteClaim']['properties']
    assert 'private' not in schema['$defs']['ExtractedNoteClaim']['properties']
    assert 'private' not in EPISODE_CONTRACT and 'sensitivity' not in EPISODE_CONTRACT
    output = EpisodeStructuredExtraction.model_validate(
        {'note_claims': [claim('/title', 'Budget').model_dump()]}
    ).to_structured()
    assert isinstance(output.note_claims[0], NoteClaim)
