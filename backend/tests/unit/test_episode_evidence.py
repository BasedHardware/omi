import json
import os
import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.structured import ActionItem, NoteClaim, Participant, Section, Structured
from models.episode_extraction import EpisodeStructuredExtraction
from models.structured_extraction import RichStructuredExtraction, StructuredExtraction
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


def test_flag_defaults_off_and_reads_env_at_call_boundary(monkeypatch):
    from utils.conversations import meeting_notes_wiring as wiring

    monkeypatch.delenv('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED', raising=False)
    assert not wiring.meeting_notes_episode_evidence_enabled()
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_PERCENT', '100')
    for raw in ('true', '1', 'on', 'YES'):
        monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_ENABLED', raw)
        assert wiring.meeting_notes_episode_evidence_enabled('synthetic-owner')
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


def test_adapters_keep_source_time_actor_and_screen_rows():
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
    assert ocr.time == '10:01' and ocr.actor is None
    assert 'Ari: agreed' in ocr.content
    assert render_episode_evidence(items).startswith('EPISODE EVIDENCE')
    frame = SimpleNamespace(frame_id='f1', summary='Empty call screen', names=(), role='strip', captured_at=START)
    assert meeting_evidence(None, None, [frame])[0].source_ref == 'f1'
    assert (
        open_task_evidence([{'id': 't1', 'description': 'Review'}, {'id': 'done', 'completed': True}])[0].source_ref
        == 't1'
    )


def test_wrong_provenance_invalid_ids_coverage():
    evidence = [EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed')]
    note = valid_note()
    assert not claim_violations(note, evidence)
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


def invoke_notes(processing, monkeypatch, responses, *, episode=True, sections=False, cache=False):
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix

    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps(responses[min(len(calls) - 1, len(responses) - 1)]))

    monkeypatch.setattr(processing, 'get_llm', lambda *a, **k: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: cache)
    prefix = ConversationPromptPrefix(
        conversation_id='synthetic', context='FULL TRANSCRIPT\n', has_usable_content=False
    )
    evidence = [EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed')]
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
    assert 'EPISODE EVIDENCE' in calls[0][1].content
    assert 'FULL TRANSCRIPT' not in calls[0][1].content


def test_retry_is_bounded_and_remaining_vacuity_accepted(processing, monkeypatch, caplog):
    bad = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    bad['note_claims'][0]['evidence_ids'] = ['missing']
    result, calls = invoke_notes(
        processing, monkeypatch, [valid_note().model_dump(mode='json') | {'overview': 'A brief exchange'}, bad]
    )
    assert len(calls) == 2
    assert result.title == 'Quick chat'  # Structurally valid retry wins.
    assert len(result.note_claims) == 1
    assert 'to=vacuity' in caplog.text
    assert 'to=invalid_evidence_reference' in caplog.text
    assert 'to=missing_claim_coverage' in caplog.text


def test_malformed_retry_retains_initial_note(processing, monkeypatch, caplog):
    bad = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    result, calls = invoke_notes(processing, monkeypatch, [bad, {'title': {'invalid': 'shape'}}])
    assert len(calls) == 2 and result.title == 'Quick chat'
    assert 'to=retry_unavailable' in caplog.text


def test_episode_ids_removed_from_initial_and_retry_without_transcript_citations(processing, monkeypatch, caplog):
    first = valid_note(overview='The message shows approval. [screen_ocr:1]')
    retry = valid_note(overview='The message shows approval. `screen_frame:invented`')
    result, calls = invoke_notes(
        processing, monkeypatch, [first.model_dump(mode='json'), retry.model_dump(mode='json')]
    )
    assert len(calls) == 2
    assert 'screen_' not in result.overview
    assert all(not section.source_segment_ids for section in result.sections)
    assert 'to=evidence_id_in_prose' in caplog.text


def test_claim_coverage_includes_each_factual_span():
    note = valid_note(overview='The message shows approval. Ari wrote about medical treatment.')
    note.note_claims[1].text = 'The message shows approval.'
    evidence = [EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Synthetic thread')]
    assert 'missing_claim_coverage' in claim_violations(note, evidence)
    note.note_claims.append(claim('/overview', 'Ari wrote about medical treatment.'))
    assert not claim_violations(note, evidence)


def test_wake_word_metadata_is_server_authored_and_prompted(processing, monkeypatch):
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix
    from utils.conversations.wake_word import WAKE_WORD_MARKER

    segments = [
        SimpleNamespace(id='s1', text='Hey Omi, remind me to send the invoice.', start=0, end=3, is_user=True),
        SimpleNamespace(id='s2', text=WAKE_WORD_MARKER, start=4, end=5, is_user=True),
    ]
    items = capture_evidence(SimpleNamespace(transcript_segments=segments))
    assert items[0].wake_word_invocation and not items[1].wake_word_invocation
    assert WAKE_WORD_MARKER not in items[1].content
    calls = []
    monkeypatch.setattr(
        processing,
        'get_llm',
        lambda *a, **k: SimpleNamespace(
            invoke=lambda m: calls.append(m)
            or SimpleNamespace(content=json.dumps(valid_note().model_dump(mode='json')))
        ),
    )
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)
    processing.get_conversation_notes(
        ConversationPromptPrefix('synthetic', 'FULL TRANSCRIPT'),
        started_at=START,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=True,
        episode_evidence=items,
    )
    assert 'wake_word_invocation=true' in calls[0][1].content
    assert 'capture_kind=explicit_command' in calls[0][1].content
    assert 'bracketed turn header' not in calls[0][1].content


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
    assert overview_claims == []
    assert any(c.target == '/sections/0/body_markdown' for c in result.note_claims)


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
    monkeypatch.setattr(processing, 'import_module', lambda name: pytest.fail('flag-off loaded episode runtime'))
    from langchain_core.output_parsers import PydanticOutputParser
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix
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
    assert 'sensitive reason' in items[0].content


def test_invalid_claim_schema_never_invalidates_usable_note(processing, monkeypatch, caplog):
    bad = valid_note().model_dump(mode='json')
    bad['note_claims'].append({'provenance': 'invented'})
    result, calls = invoke_notes(processing, monkeypatch, [bad, bad])
    assert len(calls) == 2 and result.title == 'Written approval'
    assert len(result.note_claims) == 2
    assert 'to=invalid_claim_schema' in caplog.text


def test_retry_provider_error_never_invalidates_usable_note(processing, monkeypatch, caplog):
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix

    bad = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    calls = []

    def invoke(messages):
        calls.append(messages)
        if len(calls) == 2:
            raise TimeoutError('synthetic')
        return SimpleNamespace(content=json.dumps(bad))

    monkeypatch.setattr(processing, 'get_llm', lambda *a, **k: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)
    result = processing.get_conversation_notes(
        ConversationPromptPrefix('synthetic', 'FULL TRANSCRIPT'),
        started_at=START,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=False,
        episode_evidence=[EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Synthetic')],
    )
    assert len(calls) == 2 and result.title == 'Quick chat'
    assert 'to=retry_unavailable' in caplog.text


def test_unknown_speech_clusters_remain_distinguishable_without_names():
    segments = [
        SimpleNamespace(
            id=f's{index}', text='Synthetic commitment', start=index, end=index + 1, speaker_id=cluster, is_user=False
        )
        for index, cluster in enumerate((0, 1, 0))
    ]
    items = capture_evidence(SimpleNamespace(transcript_segments=segments))[:3]
    assert [item.actor for item in items] == [None, None, None]
    assert [item.diarization_key for item in items] == ['0', '1', '0']
    note = valid_note()
    note.note_claims[0].evidence_ids = ['speech:s0']
    note.note_claims[0].provenance = 'said'
    claim_violations(note, items)
    assert note.note_claims[0].evidence_sources[0].diarization_key == '0'


def test_empty_retry_keeps_initial_note(processing, monkeypatch, caplog):
    initial = valid_note('Quick chat', 'A brief exchange').model_dump(mode='json')
    result, calls = invoke_notes(processing, monkeypatch, [initial, {}])
    assert len(calls) == 2
    assert result.title == 'Quick chat' and result.overview == 'A brief exchange'
    assert 'to=empty_retry' in caplog.text


@pytest.mark.parametrize('source', ['screen_activity', 'google'])
def test_roster_claim_retains_underlying_source(source):
    from utils.conversations.meeting_participants import MeetingRoster, RosterEntry

    roster = MeetingRoster(
        entries=(RosterEntry('Ari', None, None, 'human', source),),
        display_title=None,
        title_is_window_title=False,
    )
    item = meeting_evidence(roster, None, [])[0]
    note = Structured(title='Ari', note_claims=[claim('/title', 'Ari', item.id, 'shown')])
    assert not claim_violations(note, [item])
    assert json.loads(item.content)['source'] == source
    assert note.note_claims[0].evidence_sources[0].source_ref == source


@pytest.mark.parametrize('field', ['owner_name', 'name', 'email', 'organization', 'role'])
def test_claim_coverage_includes_owner_and_participant_fields(field):
    item = EvidenceItem(id='roster:0', source_kind='roster', content='Synthetic identity')
    note = Structured(title='Synthetic', note_claims=[claim('/title', 'Synthetic', item.id, 'shown')])
    if field == 'owner_name':
        note.action_items = [ActionItem(description='Send report', owner_name='Ari')]
        note.note_claims.append(claim('/action_items/0/description', 'Send report', item.id, 'shown'))
        target, text = '/action_items/0/owner_name', 'Ari'
    else:
        values = {'name': None, 'email': None, 'organization': None, 'role': None, 'source': 'roster'}
        values[field] = 'Synthetic value'
        note.participants = [Participant(**values)]
        target, text = f'/participants/0/{field}', 'Synthetic value'
    assert 'missing_claim_coverage' in claim_violations(note, [item], drop_invalid=True)
    note.note_claims.append(claim(target, text, item.id, 'shown'))
    assert not claim_violations(note, [item])


@pytest.mark.parametrize('episode_mode', [True, False])
def test_frame_text_respects_episode_screen_text_opt_out(processing, monkeypatch, episode_mode):
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
    items = [] if episode_mode else None
    roster, _, _, images = wiring.rich_notes_inputs(
        'synthetic',
        conv,
        None,
        'UTC',
        include_background=True,
        include_screen_text=False,
        evidence_items=items,
    )
    assert images == (image,)
    assert observed[0].frame_id == frame.frame_id
    if episode_mode:
        assert observed[0].summary == '' and observed[0].names == ()
        assert 'Private screen text' not in render_episode_evidence(items)
        assert 'Screen identity' not in render_episode_evidence(items)
        assert not roster.entries
    else:
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


def test_short_unique_anchor_covers_its_unit_and_headings_need_no_claim():
    item = EvidenceItem(id='speech:1', source_kind='speech', content='Ari approved a synthetic budget.')
    note = Structured(
        title='Budget approval',
        overview='Ari approved the synthetic budget. They requested an agenda.',
        sections=[Section(heading='Outcome', body_markdown='- Ari approved the synthetic budget.')],
        note_claims=[
            claim('/title', 'Budget approval', item.id, 'said'),
            claim('/overview', 'synthetic budget', item.id, 'said'),
            claim('/sections/0/body_markdown', 'synthetic budget', item.id, 'said'),
        ],
    )
    assert 'missing_claim_coverage' in claim_violations(note, [item])
    note.note_claims.append(claim('/overview', 'requested an agenda', item.id, 'said'))
    assert not claim_violations(note, [item])
    note.overview = 'Ari approved the synthetic budget. A private message mentioned the synthetic budget.'
    assert 'ambiguous_claim_span' in claim_violations(note, [item], drop_invalid=True)


def test_expected_counterpart_without_observed_participation_is_not_attendance(processing, monkeypatch):
    """An expected counterpart with no observed participation is not an attendee.

    The fixture is generic: no real conversation, app, or person. The note is
    written from the packet and instructions the writer actually receives.
    """
    from langchain_core.output_parsers import PydanticOutputParser
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix
    from models.calendar_context import CalendarMeetingContext, MeetingParticipant
    from models.structured_extraction import RichStructuredExtraction
    from utils.conversations.meeting_participants import MeetingRoster, RosterEntry

    expected_name = 'Synthetic Counterpart'
    speech = 'I am still sitting here and have not started anything.'
    segment = SimpleNamespace(id='s1', start=1.0, end=4.0, is_user=True, speaker_id=0, text=speech)
    conversation = SimpleNamespace(
        transcript_segments=[segment], source='desktop', started_at=START, finished_at=START, photos=[]
    )
    roster = MeetingRoster(
        entries=(RosterEntry(expected_name, None, None, 'human', 'screen_activity'),),
        display_title=None,
        title_is_window_title=False,
    )
    calendar = CalendarMeetingContext(
        calendar_event_id='synthetic-event',
        title='Scheduled time',
        participants=[MeetingParticipant(name=expected_name)],
        start_time=START,
        duration_minutes=30,
    )
    frame = SimpleNamespace(
        frame_id='f1',
        summary='A tile is visible and silent.',
        names=(expected_name,),
        role='view',
        captured_at=START,
    )
    evidence = [
        *capture_evidence(conversation, roster=roster, desktop_capture=True),
        *meeting_evidence(roster, calendar, [frame]),
    ]
    rendered = render_episode_evidence(evidence)
    packet = json.loads(rendered.split('\n', 1)[1])
    observed = packet['observed_participation']
    expected = packet['expected_context']
    observed_text = json.dumps(observed, ensure_ascii=False)
    assert expected_name in json.dumps(expected, ensure_ascii=False)
    assert expected_name not in observed_text
    assert [row.get('c') for row in observed if row.get('k') == 'speech'] == [speech]
    assert all(row.get('a') != expected_name for row in observed)
    assert 'visible_names' not in observed_text

    instructions = episode_static_instructions(
        PydanticOutputParser(pydantic_object=RichStructuredExtraction).get_format_instructions(),
        _conversation_notes_static_instructions,
        include_claims=False,
    )
    assert 'Fill participants from the roster and transcript evidence' not in instructions
    assert 'whose participation was observed' in instructions
    assert 'not participation' in instructions
    assert 'Do not describe a meeting, attendance' in instructions
    assert 'People and AI agents evidenced by the meeting roster or the transcript' not in instructions

    calls = []
    grounded = valid_note(title='Still sitting here', overview=speech)
    for entry in grounded.note_claims:
        entry.evidence_ids = ['evidence:0']
        entry.provenance = 'said'

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps(grounded.model_dump(mode='json')))

    monkeypatch.setattr(processing, 'get_llm', lambda *a, **k: SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: False)
    result = processing.get_conversation_notes(
        ConversationPromptPrefix('synthetic', 'FULL TRANSCRIPT\n', has_usable_content=False),
        started_at=START,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=False,
        episode_evidence=evidence,
    )
    system = calls[0][0].content
    system_text = system[0]['text'] if isinstance(system, list) else system
    user_text = calls[0][1].content
    writer_packet = json.loads(user_text.split('EPISODE EVIDENCE', 1)[1].split('\n', 1)[1].split('\n', 1)[0])
    writer_observed = json.dumps(writer_packet['observed_participation'], ensure_ascii=False)
    assert expected_name in json.dumps(writer_packet['expected_context'], ensure_ascii=False)
    assert expected_name not in writer_observed
    assert speech in writer_observed
    assert 'FULL TRANSCRIPT' not in user_text
    assert 'PARTICIPANTS' not in user_text
    assert 'Do not describe a meeting, attendance' in system_text
    assert 'Fill participants from the roster and transcript evidence' not in system_text
    assert not result.participants
    assert not result.events
    assert expected_name not in f'{result.title}\n{result.overview}'
    assert 'agreed' not in result.overview.casefold() and 'decided' not in result.overview.casefold()


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


def test_short_aliases_expand_before_validation_and_never_become_speech_citations(processing, monkeypatch):
    data = valid_note().model_dump(mode='json')
    for entry in data['note_claims']:
        entry['evidence_ids'] = ['evidence:0']
    result, calls = invoke_notes(processing, monkeypatch, [data])
    assert len(calls) == 1
    assert all(c.evidence_ids == ['screen_ocr:1'] for c in result.note_claims)
    assert all(c.evidence_sources[0].id == 'screen_ocr:1' for c in result.note_claims)
    assert not result.sections
    assert '"id":"evidence:0"' in calls[0][1].content


@pytest.mark.parametrize('ending', ['', '\n', '\r\n'])
def test_coverage_checks_each_unpunctuated_bullet(ending):
    item = EvidenceItem(id='speech:1', source_kind='speech', content='Alice agreed; Bob declined.')
    note = Structured(
        title='Two responses',
        sections=[Section(heading='Responses', body_markdown='- Alice agreed\n- Bob declined' + ending)],
        note_claims=[
            claim('/title', 'Two responses', item.id, 'inferred'),
            claim('/sections/0/body_markdown', 'Alice agreed', item.id, 'said'),
        ],
    )
    assert 'missing_claim_coverage' in claim_violations(note, [item])
    note.note_claims.append(claim('/sections/0/body_markdown', 'Bob declined', item.id, 'said'))
    assert not claim_violations(note, [item])


def test_written_roster_provenance_is_valid():
    item = EvidenceItem(id='roster:0', source_kind='roster', content='Synthetic roster name')
    note = Structured(
        title='Synthetic roster name',
        note_claims=[claim('/title', 'Synthetic roster name', item.id, 'written')],
    )
    assert not claim_violations(note, [item], drop_invalid=True)
    assert note.note_claims[0].evidence_sources[0].source_kind == 'roster'


def test_episode_and_presentation_repairs_share_two_call_budget(processing, monkeypatch, caplog):
    bad = valid_note().model_dump(mode='json')
    bad['note_claims'] = []
    bad['overview'] += ' screen_ocr:1'
    good = valid_note().model_dump(mode='json')
    with caplog.at_level('INFO'):
        result, calls = invoke_notes(processing, monkeypatch, [bad, good])
    assert len(calls) == 2
    assert result.title == 'Written approval'
    assert 'retry_count=1' in caplog.text and 'evidence_id_in_prose' in caplog.text
    assert 'Prior JSON' not in calls[-1][-1].content


def test_large_episode_has_no_full_context_repair(processing, monkeypatch, caplog):
    from langchain_core.output_parsers import PydanticOutputParser
    from utils.llm.episode_notes_validation import repair_episode_note
    from utils.llm.notes_observability import NotesRun
    from langchain_core.messages import HumanMessage

    note = valid_note()
    note.note_claims = []
    run = NotesRun('episode')
    result = repair_episode_note(
        note,
        evidence=[EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Invented')],
        model=SimpleNamespace(invoke=lambda _: pytest.fail('long evidence must not retry')),
        messages=[HumanMessage(content='x' * 120001)],
        parser=PydanticOutputParser(pydantic_object=EpisodeStructuredExtraction),
        raw_response='{}',
        content_str=lambda response: response.content,
        transcript_segment_ids=(),
        initial_violations=set(),
        run=run,
    )
    assert result.title == note.title and run.calls == 0
    assert 'repair_budget_exhausted' in run.violations and run.fallback_to_best_note


def test_long_speech_uses_baseline_prompt_with_no_episode_overhead(processing, monkeypatch, caplog):
    from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix

    calls, configs = [], []

    def model(*args, **kwargs):
        configs.append(kwargs)
        return SimpleNamespace(
            invoke=lambda messages: calls.append(messages)
            or SimpleNamespace(
                content=json.dumps(
                    {
                        'title': 'Pricing decision',
                        'overview': 'Ari approved pricing.',
                    }
                )
            )
        )

    monkeypatch.setattr(processing, 'get_llm', model)
    prefix = build_conversation_prompt_prefix(
        conversation_id='invented',
        transcript='Ari approved pricing. ' * 15000,
        started_at=START,
        timezone_name='UTC',
        language_code='en',
    )
    with caplog.at_level('INFO'):
        result = processing.get_conversation_notes(
            prefix,
            started_at=START,
            language_code='en',
            output_language_code=None,
            tz='UTC',
            task_intelligence_capture=False,
            rich_context_enabled=True,
            episode_evidence=[EvidenceItem(id='speech:1', source_kind='speech', content=prefix.context)],
        )
    assert result.title == 'Pricing decision' and len(calls) == 1
    assert 'EPISODE NOTES CONTRACT' not in str(calls[0][0].content)
    assert 'FULL TRANSCRIPT' in calls[0][1].content
    assert 'baseline_long' in caplog.text and 'retry_count=0' in caplog.text
    assert configs[0]['request_timeout'] == processing.CONVERSATION_STRUCTURE_TIMEOUT_SECONDS


def test_episode_static_prefix_keeps_explicit_cache_breakpoint(processing, monkeypatch):
    monkeypatch.setattr(processing, 'shared_conversation_cache_supported', lambda: True)
    monkeypatch.setattr(processing, 'explicit_cache_switch_enabled', lambda: True)
    _, calls = invoke_notes(processing, monkeypatch, [valid_note().model_dump(mode='json')], cache=True)
    static = calls[0][0].content[0]
    assert static['prompt_cache_breakpoint'] == {'mode': 'explicit'}
    assert 'EPISODE NOTES CONTRACT' in static['text']
    assert 'screen_ocr:1' not in static['text']


def test_metadata_off_has_no_coverage_repair_and_optional_claims(processing, monkeypatch, caplog):
    monkeypatch.setenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'false')
    result, calls = invoke_notes(
        processing, monkeypatch, [{'title': 'Written approval', 'overview': 'The message shows approval.'}]
    )
    assert len(calls) == 1
    assert result.note_claims is None
    assert 'Do not generate note_claims' in str(calls[0][0].content)
    assert 'missing_claim' not in caplog.text


def test_selected_effort_applies_to_writer_and_repair(processing, monkeypatch):
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix

    bindings, calls = [], []

    class Model:
        def bind(self, **options):
            bindings.append(options)
            return self

        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(
                content=json.dumps(valid_note('Quick chat', 'A brief exchange').model_dump(mode='json'))
            )

    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'high')
    monkeypatch.setattr(processing, 'get_llm', lambda *a, **kw: Model())
    processing.get_conversation_notes(
        ConversationPromptPrefix('synthetic', 'FULL TRANSCRIPT'),
        started_at=START,
        language_code='en',
        output_language_code=None,
        tz='UTC',
        task_intelligence_capture=False,
        episode_evidence=[EvidenceItem(id='screen_ocr:1', source_kind='screen_ocr', content='Ari: agreed')],
    )
    assert bindings == [{'reasoning_effort': 'high'}, {'reasoning_effort': 'high'}]
    assert len(calls) == 2


def test_high_effort_budget_falls_back_before_writer_and_preserves_original_frames(processing, monkeypatch, caplog):
    from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix

    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'xhigh')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'false')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_SELECTION', 'deterministic')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES', '24000')
    messages, configs = [], []

    def model(*args, **kwargs):
        configs.append(kwargs)
        return SimpleNamespace(
            invoke=lambda value: messages.append(value)
            or SimpleNamespace(
                content=json.dumps({'title': 'Pricing approval', 'overview': 'Ari approved the pricing proposal.'})
            )
        )

    monkeypatch.setattr(processing, 'get_llm', model)
    speech = 'Ari approved the pricing proposal. ' * 1500
    prefix = build_conversation_prompt_prefix(
        conversation_id='invented', transcript=speech, started_at=START, timezone_name='UTC', language_code='en'
    )
    frame = NotesFrameImage('original-frame', '+00:10', 'data:image/jpeg;base64,eA==')
    with caplog.at_level('INFO'):
        note = processing.get_conversation_notes(
            prefix,
            started_at=START,
            language_code='en',
            output_language_code=None,
            tz='UTC',
            task_intelligence_capture=False,
            rich_context_enabled=True,
            screen_frames=[frame],
            episode_evidence=[EvidenceItem(id='s', source_kind='speech', content=speech)],
        )
    assert note.title == 'Pricing approval'
    assert len(configs) == len(messages) == 1
    assert 'max_retries' not in configs[0]  # Only the ordinary baseline model is acquired.
    assert 'EPISODE NOTES CONTRACT' not in str(messages[0][0].content)
    assert 'data:image/jpeg;base64,eA==' in str(messages[0][2])
    receipts = [record.message for record in caplog.records if 'conversation_notes_receipt' in record.message]
    assert len(receipts) == 1
    assert 'arm=baseline_budget' in receipts[0]
    assert 'requested_effort=xhigh' in receipts[0] and 'effort=default' in receipts[0]
    assert 'thinking_input_baseline' in receipts[0]
