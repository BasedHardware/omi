"""Synthetic notes acceptance: packet parity, attribution, spelling and output-language policy."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from database import users as users_db

from config.refactor_modes import serving_for, uid_digest
from models.speaker_evidence import SpeakerEvidence, VoiceCluster, SpeakerCandidate, ClusterSimilarity
from models.structured import Structured
from utils.conversations.transcript_for_llm import render_cluster_transcript
from utils.episodes import incremental, moment_render
from utils.llm import notes_packet as packet
from utils.llm import output_language, conversation_topic, notes_output_contract as contract
from utils.llm import notes_short_clip
from utils.llm.conversation_prompt_context import ConversationPromptPrefix
from utils.llm.notes_output import NotesOutput
from utils.llm.notes_language_inputs import in_profile_segments

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/notes_packet_v2/synthetic.json').read_text())
START = datetime(2026, 1, 12, 1, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_flags(monkeypatch):
    for flag in ('NOTES_PACKET_V2_MODE', 'STT_LANGUAGE_HINTS_MODE'):
        monkeypatch.delenv(flag, raising=False)
        monkeypatch.delenv(flag + '_SERVE_PERCENT', raising=False)
        monkeypatch.delenv(flag + '_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setattr(packet, 'get_evidence', lambda *_args: None)
    from utils.llm import known_spellings

    monkeypatch.setattr(
        known_spellings, 'conversation_people_names', lambda *_args: FIXTURES['contact_spelling']['people']
    )
    monkeypatch.setattr(users_db, 'get_user_language_preference', lambda *_args: 'en')


def prefix(**kwargs):
    return ConversationPromptPrefix(conversation_id='synthetic-conversation', context='FULL TRANSCRIPT\ntext', **kwargs)


def inputs(**overrides):
    values = dict(
        started_at=START,
        tz='Asia/Ho_Chi_Minh',
        language_code='zh',
        output_language_code='en',
        task_intelligence_capture=False,
        people=FIXTURES['contact_spelling']['people'],
    )
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    'tz,expected',
    [
        ('Asia/Ho_Chi_Minh', '2026-01-12T08:30:00'),
        ('America/Los_Angeles', '2026-01-11T17:30:00'),
        ('invalid', '2026-01-12T01:30:00'),
        (None, '2026-01-12T01:30:00'),
    ],
)
def test_local_capture_time_is_converted_in_code(tz, expected):
    assert packet._local_started_at_iso(START, tz) == expected
    assert packet._local_started_at_iso(START.replace(tzinfo=None), tz) == expected


@pytest.mark.parametrize('preference,conversation,expected', [('en', 'zh', 'en'), ('', 'fr', 'fr'), (None, None, 'en')])
def test_language_preference_precedes_noisy_conversation_language(monkeypatch, preference, conversation, expected):
    monkeypatch.setattr(users_db, 'get_user_language_preference', lambda *_args: preference)
    assert output_language.resolve_output_language('synthetic-account', conversation) == expected


@pytest.mark.parametrize('mode', ['off', 'shadow', 'typo'])
def test_nonserving_packet_is_identical_and_shadow_logs_only_counts(monkeypatch, caplog, mode):
    monkeypatch.setenv(packet.FLAG, mode)
    original = {'capture_evidence': 'private synthetic source', 'started_at': 'old bytes'}
    with caplog.at_level('INFO'):
        selected = packet.select_notes_packet(
            original,
            prefix=prefix(),
            uid='synthetic-account',
            capture_evidence=original['capture_evidence'],
            words=30,
            inputs=inputs(),
        )
    assert selected == original
    assert 'private synthetic source' not in caplog.text
    assert 'synthetic-account' not in caplog.text
    if mode != 'off':
        assert 'event=refactor_shadow lane=L3 check=packet outcome=disagree' in caplog.text
        assert 'packet_bytes:' in caplog.text and 'changed_fields:' in caplog.text


def test_shadow_digest_cohort_selects_same_packet_builder(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'shadow')
    monkeypatch.setenv(packet.FLAG + '_SERVE_UID_SHA256S', uid_digest('synthetic-account'))
    assert serving_for(packet.FLAG, 'synthetic-account')
    chosen = packet.select_notes_packet(
        {}, prefix=prefix(), uid='synthetic-account', capture_evidence='source', words=30, inputs=inputs()
    )
    assert chosen['version'] == 2 and chosen['output_language'] == 'en'
    assert not serving_for(packet.FLAG, 'other-synthetic-account')


def test_one_builder_supplies_agent_and_oneshot_language_local_time_density_spelling_and_wakeword(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    fixture = FIXTURES['contact_spelling']
    common = dict(
        prefix=prefix(), uid='synthetic-account', capture_evidence=fixture['transcript'], words=18, inputs=inputs()
    )
    oneshot = packet.select_notes_packet({'capture_evidence': fixture['transcript']}, **common)
    agent = packet.select_notes_packet({'calendar_overlap': []}, **common)
    fields = (
        'version',
        'output_language',
        'started_local_iso',
        'density',
        'LENGTH',
        'wake_word_rules',
        'contact_name_spellings',
        'speaker_evidence',
        'capture_evidence',
    )
    assert {key: oneshot[key] for key in fields} == {key: agent[key] for key in fields}
    assert 'Nik Shevchenko' in agent['contact_name_spellings']
    assert 'Nick' in agent['capture_evidence']
    assert 'close sound-alikes' in agent['speaker_evidence']
    assert agent['started_local_iso'] == '2026-01-12T08:30:00'
    assert agent['wake_word_rules'] and agent['density'] and agent['LENGTH']


def candidate(name, probability, band, person_id='synthetic-contact'):
    return SpeakerCandidate(person_id=person_id, name=name, probability=probability, band=band, source='voice')


def test_speaker_evidence_lists_best_probability_bands_and_similarity():
    evidence = SpeakerEvidence(
        status='partial',
        policy_version='synthetic-v1',
        clusters=[
            VoiceCluster(
                id='v0',
                segment_ids=['synthetic-a'],
                candidates=[candidate('Other', 0.35, 'unknown'), candidate('Nik', 0.8, 'likely')],
            )
        ],
        similarities=[ClusterSimilarity(a='v0', b='v1', similarity=0.82)],
    )
    rendered = packet.render_speaker_evidence(evidence, [])
    assert rendered.index('"name": "Nik"') < rendered.index('"name": "Other"')
    assert '0.8' in rendered and 'likely' in rendered and '0.82' in rendered
    assert 'Never attribute personal stories to a named person without evidence' in rendered


@pytest.mark.parametrize('evidence', [None, SpeakerEvidence(status='unavailable', policy_version='synthetic-v1')])
def test_two_speakers_with_unknown_owner_never_get_named_attribution(evidence):
    fixture = FIXTURES['two_speakers_unknown_owner']
    rendered, mapping = render_cluster_transcript(fixture['segments'], names={}, owner_name='Morgan', evidence=evidence)
    assert set(mapping.values()) == {None}
    assert 'Morgan' not in rendered and 'Owner:' not in rendered and 'Speaker ' not in rendered
    assert 'first-person statements as unattributed' in rendered
    assert 'spk c0 ?' in rendered and 'spk c1 ?' in rendered
    assert fixture['segments'][0]['is_user'] is True  # Source labels are never rewritten.


@pytest.mark.parametrize('band,expected', [('confident', 'Nik'), ('likely', 'likely Nik'), ('unknown', None)])
def test_renderer_uses_the_policy_band_and_higher_probability(band, expected):
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='synthetic-v1',
        clusters=[
            VoiceCluster(
                id='v0',
                segment_ids=['synthetic-a'],
                candidates=[candidate('Wrong', 0.1, 'confident'), candidate('Nik', 0.8, band)],
            )
        ],
    )
    text, mapping = render_cluster_transcript(
        [{'id': 'synthetic-a', 'text': 'A synthetic remark', 'speaker_id': 0}], names={}, evidence=evidence
    )
    assert mapping['v0'] == expected
    assert 'Wrong' not in text
    assert '[synthetic-a v0]' in text


def test_scopes_do_not_collapse_reused_numeric_speaker_keys():
    rows = [
        {'id': 'synthetic-a', 'text': 'First capture', 'speaker_id': 0, 'speaker_id_scope': 'one'},
        {'id': 'synthetic-b', 'text': 'Second capture', 'speaker_id': 0, 'speaker_id_scope': 'two'},
    ]
    text, mapping = render_cluster_transcript(rows, names={})
    assert len(mapping) == 2 and '[synthetic-a c0]' in text and '[synthetic-b c1]' in text


def test_episode_moments_drop_classified_noise_and_use_the_notes_owner_gate(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    fixture = FIXTURES['two_speakers_unknown_owner']
    named = moment_render.name_segments(fixture['segments'], {})
    assert not any(row['is_user'] for row in named)
    rendered = incremental.render_moment(named, uid='synthetic-account')
    assert 'Owner:' not in rendered.text and 'Speaker ' not in rendered.text
    assert 'spk c0 ?' in rendered.text
    language = FIXTURES['english_with_noise']
    moment = incremental.render_moment(language['segments'], uid='synthetic-account')
    assert language['segments'][1]['text'] not in moment.text
    messages = incremental.build_messages('{}', moment.text, now=START, tz_name='UTC', output_language='en')
    assert 'including title and moment_heading, in en' in messages[0][1]
    assert 'language the people speak' not in messages[0][1]


def test_topic_title_has_resolved_english_instruction_and_no_chinese_noise(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    fixture = FIXTURES['english_with_noise']
    prompts = []
    monkeypatch.setattr(
        conversation_topic,
        'get_llm',
        lambda *_args: SimpleNamespace(
            invoke=lambda prompt: prompts.append(prompt)
            or SimpleNamespace(content='{"title":"Workshop volunteer schedule","emoji":""}')
        ),
    )
    from contextlib import nullcontext

    monkeypatch.setattr(conversation_topic, 'track_usage', lambda *_args: nullcontext())
    result = conversation_topic.generate_conversation_topic(
        'synthetic-account',
        'ignored',
        conversation_language=fixture['conversation_language'],
        segments=fixture['segments'],
    )
    assert result.title == 'Workshop volunteer schedule'
    assert prompts[0].startswith('Write the title in en.')
    assert fixture['segments'][1]['text'] not in prompts[0]


@pytest.mark.parametrize('mode', ['off', 'shadow', 'typo'])
def test_episode_shadow_has_exact_legacy_text(monkeypatch, mode):
    monkeypatch.setenv(packet.FLAG, mode)
    moment = incremental.render_moment([{'text': 'A synthetic remark', 'is_user': True}], uid='synthetic-account')
    assert moment.text == 'Owner: A synthetic remark'
    messages = incremental.build_messages('{}', moment.text, now=START, tz_name='UTC')
    assert messages[0] == ('system', incremental.PROMPT_PREFIX)


@pytest.mark.parametrize('words,minimum', [(1, True), (11, True), (12, False), (13, False)])
def test_word_floor_never_uses_duration_or_discards(monkeypatch, words, minimum):
    monkeypatch.setenv(packet.FLAG, 'serve')
    conversation = SimpleNamespace(
        transcript_segments=[SimpleNamespace(text='word ' * words)], started_at=START, finished_at=START, photos=[]
    )
    result = notes_short_clip.quiet_minimum('synthetic-account', conversation, tz='UTC')
    assert (result is not None) is minimum
    if minimum:
        assert result.title and result.emoji == '' and result.sections == [] and result.action_items == []
        assert result.title_provenance == 'server_minimum'


def test_short_clip_shadow_does_not_serve_minimum(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'shadow')
    conversation = SimpleNamespace(transcript_segments=[SimpleNamespace(text='A brief synthetic remark')], photos=[])
    assert notes_short_clip.quiet_minimum('synthetic-account', conversation) is None


def test_one_contract_checks_floor_ceiling_title_and_participants():
    check = contract.check_notes(
        {
            'title': 'word ' * 50,
            'sections': [{'heading': 'Topic', 'body_markdown': '- Brief'}],
            'participants': [{'name': 'a speaker'}],
        },
        transcript_words=2000,
        contract_v2=True,
    )
    assert {'format', 'content'} == {problem.kind for problem in check.findings}
    assert any('at least 480' in problem.message for problem in check.findings)
    assert any('70 characters' in problem.message for problem in check.findings)


def test_shared_static_repairs_bound_output_and_repair_citations_without_a_model():
    output = NotesOutput.model_validate(
        {
            'title': 'word ' * 40,
            'participants': [{'name': 'a speaker', 'evidence': 'unknown'}],
            'sections': [
                {
                    'heading': 'Topic',
                    'body_markdown': 'An ordinary synthetic sentence.',
                    'source_segment_ids': ['synthetic-a', 'invented'],
                }
            ],
            'action_items': [{'description': 'Check the workshop schedule'}],
        }
    ).to_structured()
    check = contract.enforce_output_contract(output, transcript_words=40, transcript_segment_ids=['synthetic-a'])
    assert len(output.title) <= 70 and len(output.title.split()) <= 10
    assert output.participants == []
    assert output.sections[0].body_markdown.startswith('- ')
    assert output.sections[0].source_segment_ids == ['synthetic-a']
    assert 'body_bulleted' in check.repairs


def test_shadow_output_validation_cannot_mutate_the_served_artifact(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'shadow')
    output = Structured(title='word ' * 40, sections=[])
    before = output.model_dump()
    contract.finish_notes_contract(
        output, prefix=prefix(), uid='synthetic-account', words=100, rich_mode=False, inputs={}
    )
    assert output.model_dump() == before


@pytest.fixture(scope='module')
def processing():
    from utils.conversations import process_conversation

    return process_conversation


@pytest.mark.parametrize(
    'trigger_name',
    [
        'CAPTURE_END',
        'CLIENT_FINALIZE',
        'SYNC_UPDATE',
        'SERVER_RECOVERY',
        'USER_REPROCESS',
        'FIRST_OPEN',
        'BACKLOG_CHOICE',
        'MERGE',
        'SMART_MERGE',
        'SILENT_BACKFILL',
    ],
)
def test_every_trigger_skips_paid_notes_for_fragments(monkeypatch, processing, trigger_name):
    from utils.conversations.processing_trigger import ProcessingTrigger

    monkeypatch.setenv(packet.FLAG, 'serve')
    monkeypatch.setattr(processing.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(processing, 'get_conversation_notes', lambda *_args, **_kwargs: pytest.fail('paid notes'))
    monkeypatch.setattr(
        processing, 'should_discard_conversation', lambda *_args, **_kwargs: pytest.fail('paid discard')
    )
    conversation = SimpleNamespace(
        transcript_segments=[SimpleNamespace(text='A brief synthetic remark')],
        started_at=START,
        photos=[],
        source='omi',
    )
    trigger = getattr(ProcessingTrigger, trigger_name)
    decisions, minimum = [], []
    structured, discarded = processing._get_structured(
        'synthetic-account',
        'en',
        conversation,
        trigger=trigger,
        relevance_observer=decisions.append,
        recovery_minimum_fallback_observer=lambda: minimum.append(True),
    )
    assert structured.title and structured.emoji == '' and not discarded
    assert decisions[0].trigger == trigger and minimum == [True]


def test_no_names_when_whole_conversation_speaker_resolution_is_unavailable():
    rows = [
        {'id': 'synthetic-a', 'text': 'A synthetic story', 'speaker_id': 0, 'is_user': False, 'person_id': 'person'}
    ]
    text, mapping = render_cluster_transcript(rows, names={'person': 'Nik'}, resolution_available=False)
    assert mapping['c0'] is None and 'Nik' not in text


def test_agent_and_one_shot_have_the_same_schema():
    from utils.llm.notes_output import submit_tool

    assert submit_tool()['function']['parameters'] == NotesOutput.model_json_schema()


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_real_one_shot_path_uses_one_model_call_and_only_cohort_gets_v2_repairs(monkeypatch, mode, processing):
    from utils.llm import conversation_processing as notes
    from contextlib import asynccontextmanager

    monkeypatch.setenv(packet.FLAG, mode)
    requests = []

    class Model:
        async def ainvoke(self, messages):
            requests.append(messages)
            return SimpleNamespace(
                content=json.dumps(
                    {
                        'title': 'word ' * 20,
                        'sections': [{'heading': 'Topic', 'body_markdown': 'A grounded synthetic statement.'}],
                    }
                )
            )

    @asynccontextmanager
    async def isolated(model):
        yield model

    monkeypatch.setattr(notes, 'get_llm', lambda *_args, **_kwargs: Model())
    monkeypatch.setattr(notes, 'agentic_notes_payload', lambda **_kwargs: None)
    monkeypatch.setattr(notes, 'isolated_notes_model', isolated)
    source = prefix(shaped_context='FULL TRANSCRIPT\n' + FIXTURES['contact_spelling']['transcript'])
    output = notes._get_shaped_conversation_notes(source, uid='synthetic-account', **inputs())
    assert len(requests) == 1
    packets = [
        json.loads(message['content'])
        for message in requests[0]
        if isinstance(message, dict) and message.get('role') == 'user' and isinstance(message.get('content'), str)
    ]
    if mode == 'serve':
        assert packets[0]['version'] == 2 and packets[0]['output_language'] == 'en'
        assert 'Nik Shevchenko' in packets[0]['contact_name_spellings']
        assert len(output.title) <= 70 and output.sections[0].body_markdown.startswith('- ')
    else:
        assert 'version' not in packets[0]
        assert len(output.title) > 70
        assert output.sections[0].body_markdown == 'A grounded synthetic statement.'


def test_shadow_packet_build_failure_returns_exact_legacy_packet(monkeypatch, caplog):
    monkeypatch.setattr(packet, 'build_notes_packet', lambda **_kwargs: (_ for _ in ()).throw(ValueError('synthetic')))
    original = {'response_language': 'en', 'capture_evidence': 'synthetic content'}
    with caplog.at_level('INFO'):
        assert (
            packet.select_notes_packet(
                original,
                prefix=prefix(),
                uid='synthetic-account',
                capture_evidence='synthetic content',
                words=18,
                inputs=inputs(),
            )
            == original
        )
    assert 'check=packet outcome=error' in caplog.text and 'synthetic content' not in caplog.text


def test_shadow_moment_name_projection_is_the_exact_existing_labels(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'shadow')
    rows = FIXTURES['two_speakers_unknown_owner']['segments']
    named = moment_render.name_segments(rows, {})
    assert named == rows


def test_external_audio_fragments_also_get_the_model_free_minimum(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    audio = SimpleNamespace(text_source='audio', text='A short synthetic utterance', started_at=START, photos=[])
    minimum = notes_short_clip.quiet_minimum('synthetic-account', audio)
    assert minimum.title == 'A short synthetic utterance' and minimum.emoji == ''


def test_photo_content_is_not_judged_by_a_speech_word_floor(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    capture = SimpleNamespace(transcript_segments=[SimpleNamespace(text='A short remark')], photos=[object()])
    assert notes_short_clip.quiet_minimum('synthetic-account', capture) is None


@pytest.mark.parametrize('mode,expected', [('shadow', 'zh'), ('serve', 'en')])
def test_app_result_receives_the_resolved_output_language_only_in_cohort(monkeypatch, processing, mode, expected):
    from contextlib import nullcontext
    from concurrent.futures import Future

    monkeypatch.setenv(packet.FLAG, mode)
    app = SimpleNamespace(id='synthetic-app', name='Synthetic summary', enabled=True, works_with_memories=lambda: True)
    conversation = SimpleNamespace(
        id='synthetic-conversation', language='zh', started_at=None, photos=[], apps_results=[]
    )
    seen = []
    monkeypatch.setattr(processing, 'get_available_apps', lambda *_args: [app])
    monkeypatch.setattr(processing, 'conversation_transcript_for_llm', lambda *_args: 'Synthetic workshop discussion')
    monkeypatch.setattr(processing, 'track_usage', lambda *_args: nullcontext())
    monkeypatch.setattr(
        processing, 'get_app_result', lambda *_args, **kwargs: seen.append(kwargs['language_code']) or 'Summary'
    )

    def inline(_executor, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as error:
            future.set_exception(error)
        return future

    monkeypatch.setattr(processing, 'submit_with_context', inline)
    assert processing.trigger_conversation_apps(
        'synthetic-account', conversation, is_reprocess=True, app_id=app.id, explicit_app=app, language_code='zh'
    )
    assert seen == [expected]


def test_empty_segments_do_not_create_a_visible_minimum(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    capture = SimpleNamespace(transcript_segments=[{'text': ''}], photos=[])
    assert notes_short_clip.quiet_minimum('synthetic-account', capture) is None


def test_ceiling_repair_preserves_grounded_content_of_one_long_bullet():
    repaired, repairs = contract.repair_contract(
        {'title': 'Workshop', 'sections': [{'heading': 'Topic', 'body_markdown': '- ' + 'synthetic ' * 220}]},
        transcript_words=100,
    )
    assert repaired['sections'] and repaired['sections'][0]['body_markdown'].startswith('- synthetic')
    assert contract.body_words(repaired['sections']) == 170
    assert 'length_bounded' in repairs


def test_citations_cannot_reference_segments_removed_from_language_inputs():
    from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix

    rows = in_profile_segments(FIXTURES['english_with_noise']['segments'])
    text, mapping = render_cluster_transcript(rows, names={})
    context = build_conversation_prompt_prefix(
        conversation_id='synthetic-conversation',
        transcript=text,
        started_at=START,
        timezone_name='UTC',
        language_code='en',
        speaker_map=mapping,
        transcript_segment_ids=['synthetic-en', 'synthetic-noise'],
    )
    assert context.transcript_segment_ids == frozenset({'synthetic-en'})


def test_ambiguous_contact_names_keep_both_spellings_without_choosing(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    fixture = FIXTURES['ambiguous_contact_spelling']
    contacts = fixture['people']
    ambiguous = SpeakerEvidence(
        status='partial',
        policy_version='synthetic-v1',
        clusters=[
            VoiceCluster(
                id='v0',
                segment_ids=['s'],
                candidates=[
                    SpeakerCandidate(
                        person_id=p['id'], name=p['name'], probability=0.1, band='unknown', source='roster'
                    )
                    for p in contacts
                ],
            )
        ],
    )
    monkeypatch.setattr(packet, 'get_evidence', lambda *args: ambiguous)
    selected = packet.select_notes_packet(
        {}, prefix=prefix(), uid='synthetic-account', capture_evidence='John', words=1, inputs=inputs(people=contacts)
    )
    rules = selected['speaker_evidence']
    assert 'keep the transcript spelling and do not pick one' in rules
    assert 'Never merge two people because they share a first name' in rules
    assert selected['capture_evidence'] == 'John'
    for person in contacts:
        assert person['name'] in selected['contact_name_spellings']
    for person in contacts:
        assert person['name'] in rules
    from utils.speakers.evidence import project_labels

    assert project_labels(ambiguous, {}) == {}
