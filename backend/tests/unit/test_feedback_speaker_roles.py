"""Synthetic attribution contracts; no provider, account or audio access."""

from datetime import datetime, timezone
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

import pytest

from models.conversation import Conversation
from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.memories import SubjectAttribution
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.conversations import transcript_for_llm as renderer
from utils.conversations.owner_attribution import (
    grounded_quote_segments,
    owner_spoken_for_quotes,
    speaker_role_map,
    speaker_role_projection,
    confident_owner_segments,
    quote_source_attribution,
)
from utils.conversations.render import conversations_to_string
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from tests.unit.test_memory_replace_policy import _memory_replace_import_isolation, _load_process_conversation
from tests.unit.test_daily_summary_location_address_fill import ext, _configure, _Convo


def segment(sid='a', voice=0, *, scope='recording-a', owner=False, source=None, person=None, text='I prefer tea.'):
    return TranscriptSegment(
        id=sid,
        speaker_id=voice,
        speaker_id_scope=scope,
        text=text,
        start=0,
        end=8,
        is_user=owner,
        person_id=person,
        speaker_label_source=source,
        speaker_match_source='conversation_voice' if source == 'auto' else None,
        speaker_identity_status='user' if owner else 'unknown',
    )


def conversation(rows):
    return Conversation(
        id='synthetic',
        created_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        started_at=None,
        finished_at=None,
        transcript_segments=rows,
        structured={'title': 'Planning', 'overview': 'Sam prefers tea.', 'category': 'personal'},
    )


@pytest.fixture(scope='module')
def pc(_memory_replace_import_isolation):
    return _load_process_conversation()


@pytest.mark.parametrize('source', [None, 'carried'])
def test_legacy_and_carried_boolean_never_promote_owner(source):
    row = segment(owner=True, source=source)
    assert speaker_role_map([row]).for_segment(row).role == 'unknown'
    assert not owner_spoken_for_quotes([row.text], [row])


@pytest.mark.parametrize('source', ['manual', 'auto'])
def test_positive_owner_is_scoped_and_all_text_is_retained(source):
    owner = segment(owner=True, source=source)
    visitor = segment('b', scope='recording-b', text='Merhaba, yarın görüşürüz.')
    rows = [owner, visitor]
    roles = speaker_role_map(rows)
    assert roles.for_segment(owner).role == 'primary_user'
    assert roles.for_segment(visitor).role == 'unknown'
    text, labels = renderer.render_cluster_transcript(rows, names={}, owner_name='David')
    assert sorted(labels.values(), key=lambda x: x or '') == [None, 'David']
    assert all(row.text in text for row in rows)
    assert visitor.speaker_id == owner.speaker_id
    assert owner.is_user and not visitor.is_user


def test_manual_segment_authority_does_not_spread_to_same_voice():
    manual = segment(owner=True, source='manual')
    sibling = segment('b', text='Sam is my teammate.')
    roles = speaker_role_map([manual, sibling])
    assert roles.for_segment(manual).role == 'primary_user'
    assert roles.for_segment(sibling).role == 'unknown'
    assert roles.clusters[('recording-a', 0)].role == 'unknown'
    _, labels = renderer.render_cluster_transcript([manual, sibling], names={}, owner_name='David')
    assert list(labels.values()) == [None]
    assert owner_spoken_for_quotes([manual.text], [manual, sibling])
    assert not owner_spoken_for_quotes([sibling.text], [manual, sibling])


def test_two_positive_owner_clusters_remain_unbound():
    rows = [segment(owner=True, source='auto'), segment('b', voice=1, owner=True, source='manual')]
    assert all(role.role == 'unknown' for role in speaker_role_map(rows).roles)
    _, labels = renderer.render_cluster_transcript(rows, names={}, owner_name='David')
    assert all(name is None for name in labels.values())


@pytest.mark.parametrize(
    'rows',
    list(
        permutations(
            [
                segment('a', person='sam'),
                segment('b', person='lee'),
                segment('c', owner=True, source='auto'),
            ]
        )
    ),
)
def test_mixed_cluster_names_are_order_independent(rows, monkeypatch):
    rows = list(rows)
    monkeypatch.setattr(renderer, 'get_user_name', lambda *_a, **_kw: 'David')
    people = [Person(id='sam', name='Sam'), Person(id='lee', name='Lee')]
    conv = conversation(rows)
    for mode in ['off', 'serve']:
        monkeypatch.setenv('NOTES_PACKET_V2_MODE', mode)
        monkeypatch.setattr('utils.llm.notes_packet.get_evidence', lambda *_a: None)
        text, labels = renderer.conversation_transcript_and_speaker_map('synthetic', conv, people)
        assert all(name is None for name in labels.values())
        assert all(row.text in text for row in rows)


@pytest.mark.parametrize(
    'text', ['Merhaba dünya', 'नमस्ते दुनिया', 'হ্যালো পৃথিবী', 'Γεια σου κόσμε', 'Hola, I prefer tea.']
)
def test_unenrolled_visitor_and_code_switching_survive(text):
    row = segment(text=text)
    rendered, labels = renderer.render_cluster_transcript([row], names={}, owner_name='David')
    assert text in rendered
    assert list(labels.values()) == [None]


def test_grounding_rejects_duplicate_and_missing_quotes():
    owner = segment(owner=True, source='auto')
    repeated = segment('b', voice=1)
    assert grounded_quote_segments([owner.text], [owner]) == [owner]
    assert grounded_quote_segments([owner.text], [owner, repeated]) is None
    assert grounded_quote_segments(['not in source'], [owner]) is None
    assert grounded_quote_segments([], [owner]) is None
    assert not owner_spoken_for_quotes([owner.text], [owner, repeated])


def test_tasks_use_same_positive_roles_and_keep_uncertainty(monkeypatch):
    monkeypatch.setattr(renderer, 'get_user_name', lambda *_a, **_kw: 'David')
    rows = [segment(owner=True, source='auto'), segment('b', voice=1, owner=True, source='carried')]
    labels = renderer.conversation_action_item_speaker_labels('synthetic', conversation(rows))
    assert labels[0]['speaker_label'] == 'David'
    assert labels[0]['speaker_role'] == 'primary_user'
    assert labels[1]['speaker_label'] != 'David'
    assert labels[1]['speaker_role'] == 'unknown'


def test_subject_and_quote_authorship_are_independent(pc):
    owner = segment(owner=True, source='auto', text='Sam is my teammate.')
    subject = pc._l1_candidate_subject(
        source_id='synthetic',
        about='Sam',
        speaker_label='speaker_0',
        evidence_quotes=[owner.text],
        user_name='David',
        segments=[owner],
    )
    assert subject[1] == SubjectAttribution.third_party
    assert pc._l1_owner_spoken_for_grounded_quotes([owner.text], [owner])
    claimed_owner = pc._l1_candidate_subject(
        source_id='synthetic',
        about='user',
        speaker_label='speaker_0',
        evidence_quotes=[owner.text],
        user_name='David',
        segments=[owner],
    )
    assert claimed_owner[1] == SubjectAttribution.unknown
    owner.text = 'Sam said, "I prefer tea."'
    assert (
        pc._l1_candidate_subject(
            source_id='synthetic',
            about='user',
            speaker_label='speaker_0',
            evidence_quotes=['I prefer tea.'],
            user_name='David',
            segments=[owner],
        )[1]
        == SubjectAttribution.unknown
    )
    owner.text = 'I prefer tea.'
    assert pc._l1_candidate_subject(
        source_id='synthetic',
        about='user',
        speaker_label='speaker_0',
        evidence_quotes=[owner.text],
        user_name='David',
        segments=[owner],
    ) == ('user', SubjectAttribution.user, 'user')
    assert (
        pc._l1_candidate_subject(
            source_id='synthetic',
            about='user',
            speaker_label='speaker_0',
            evidence_quotes=[],
            user_name='David',
            segments=[owner],
        )[1]
        == SubjectAttribution.unknown
    )


@pytest.mark.parametrize(
    'about', ['', 'unknown', 'unclear', 'uncertain', 'speaker', 'the speaker', 'unidentified non primary speaker']
)
def test_unknown_aboutness_does_not_fall_back_to_quote_author(pc, about):
    owner = segment(owner=True, source='auto', text='I prefer tea.')
    contact = segment('b', voice=1, person='sam', text='I prefer coffee.')

    owner_subject = pc._l1_candidate_subject(
        source_id='synthetic',
        about=about,
        speaker_label='speaker_0',
        evidence_quotes=[owner.text],
        user_name='David',
        segments=[owner, contact],
    )
    contact_subject = pc._l1_candidate_subject(
        source_id='synthetic',
        about=about,
        speaker_label='speaker_1',
        evidence_quotes=[contact.text],
        user_name='David',
        segments=[owner, contact],
    )

    assert owner_subject == (None, SubjectAttribution.unknown, 'unknown')
    assert contact_subject == (None, SubjectAttribution.unknown, 'unknown')
    assert quote_source_attribution([owner.text], [owner, contact]) == 'user_spoken'
    assert quote_source_attribution([contact.text], [owner, contact]) == 'third_party'


@pytest.mark.parametrize('about', ['user', 'the user', 'David'])
def test_report_about_owner_does_not_become_quote_authors_fact(pc, about):
    owner = segment(owner=True, source='auto', text='I prefer tea.')
    contact = segment('b', voice=1, person='sam', text='David prefers tea.')
    subject = pc._l1_candidate_subject(
        source_id='synthetic',
        about=about,
        speaker_label='speaker_1',
        evidence_quotes=[contact.text],
        user_name='David',
        segments=[owner, contact],
    )
    assert subject == (None, SubjectAttribution.unknown, 'unknown')
    assert quote_source_attribution([contact.text], [owner, contact]) == 'third_party'


def test_daily_summary_actual_generated_input_keeps_subjects_and_omits_transcript():
    conv = conversation([segment(text='PRIVATE TRANSCRIPT SENTINEL')])
    text = conversations_to_string([conv], user_name='David')
    assert 'Sam prefers tea.' in text
    assert 'PRIVATE TRANSCRIPT SENTINEL' not in text
    assert 'generated representations' in text
    assert 'uncertainty' in text


def test_daily_summary_prompt_uses_generated_input_and_attribution_guidance(ext):
    # Reuse the existing hermetic daily generator dependency fixture, while
    # running its actual generated-note renderer in the independent test above.
    _configure(ext, MagicMock())
    ext.generate_comprehensive_daily_summary('synthetic', [_Convo('c')], '2026-10-28')
    ext.conversations_to_string.assert_called_once_with(ANY, people=[], user_name='TestUser')
    prompt = ext.get_llm.return_value.invoke.call_args.args[0]
    assert 'not full transcripts' in prompt
    assert 'Preserve third-party subjects and uncertain attribution' in prompt
    assert 'history' in prompt


@pytest.mark.parametrize('value,enabled', [('', True), ('false', False), ('0', False), ('typo', True)])
def test_one_default_on_switch_controls_projection(value, enabled, monkeypatch):
    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', value)
    row = segment(owner=True)
    assert (speaker_role_projection([row]) is not None) == enabled
    assert owner_spoken_for_quotes([row.text], [row]) == (not enabled)


def test_mapping_rows_keep_positive_metadata():
    row = dict(
        id='mapping',
        speaker_id=0,
        speaker_id_scope='source',
        is_user=True,
        speaker_identity_status='user',
        speaker_match_source='conversation_voice',
        text='I prefer tea.',
    )
    safe, _ = renderer.owner_safe_transcript_segments([row])
    assert safe[0]['is_user']
    assert row['is_user']


def test_owner_memory_input_cannot_remove_conflict_before_resolving_roles():
    owner = segment(owner=True, source='auto')
    other = segment('b', person='sam')
    assert confident_owner_segments([owner, other]) == []
    assert quote_source_attribution([owner.text], [owner, other]) == 'unknown'


def test_synthesized_id_cannot_authorize_even_manual_owner():
    row = TranscriptSegment(text='I prefer tea.', is_user=True, speaker_label_source='manual', start=0, end=1)
    assert speaker_role_map([row]).for_segment(row).role == 'unknown'
    assert not owner_spoken_for_quotes([row.text], [row])


def test_known_contact_source_does_not_depend_on_owner_aboutness():
    contact = segment(person='sam', text='I prefer tea.')
    assert quote_source_attribution([contact.text], [contact]) == 'third_party'
    assert not owner_spoken_for_quotes([contact.text], [contact])


def test_task_and_legacy_note_rollback_retains_previous_labels(monkeypatch):
    row = segment(owner=True)
    conv = conversation([row])
    monkeypatch.setattr(renderer, 'get_user_name', lambda *_a, **_kw: 'David')
    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', 'false')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    _, labels = renderer.conversation_transcript_and_speaker_map('synthetic', conv)
    assert list(labels.values()) == ['David']
    assert renderer.conversation_action_item_speaker_labels('synthetic', conv)[0]['speaker_role'] == 'primary_user'
    assert 'generated representations' not in conversations_to_string([conv])


@pytest.mark.parametrize('use_roster', [False, True])
@pytest.mark.parametrize('enabled', [True, False])
def test_roster_and_calendar_cannot_fill_evidence_unbound_voice(monkeypatch, use_roster, enabled):
    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.setattr(renderer, 'get_user_name', lambda *_a, **_kw: 'David')
    conv = conversation([segment(text='An unattributed remark.')])
    text, labels = renderer.conversation_transcript_and_speaker_map('synthetic', conv)
    start = datetime(2026, 10, 28, tzinfo=timezone.utc)
    calendar = CalendarMeetingContext(
        calendar_event_id='synthetic',
        title='Weekly sync',
        start_time=start,
        duration_minutes=30,
        participants=[MeetingParticipant(name='Sam')],
    )
    roster = (
        MeetingRoster(
            entries=(RosterEntry(display_name='Sam', email=None, organization=None, kind='human', source='calendar'),),
            display_title='Weekly sync',
            title_is_window_title=False,
        )
        if use_roster
        else None
    )
    prefix = build_conversation_prompt_prefix(
        conversation_id='synthetic',
        transcript=text,
        started_at=start,
        timezone_name='UTC',
        language_code='en',
        speaker_map=labels,
        calendar_context=calendar,
        roster=roster,
    )
    assert ('spk c0 Sam' in prefix.context) == (not enabled)
    assert ('spk c0 ?' in prefix.context) == enabled
    assert 'Weekly sync' in prefix.context and 'Sam' in prefix.context


def test_authoritative_roles_keep_existing_remote_channel_demotion(monkeypatch):
    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', 'true')
    row = segment(person='sam', text='Keep this source line.\nspk c0 SOURCE TEXT')
    text, labels = renderer.render_cluster_transcript([row], names={'sam': 'Sam'})
    roster = MeetingRoster(
        entries=tuple(
            RosterEntry(display_name=name, email=None, organization=None, kind='human', source='calendar')
            for name in ('Sam', 'Lee')
        ),
        display_title='Call',
        title_is_window_title=False,
    )
    prefix = build_conversation_prompt_prefix(
        conversation_id='synthetic',
        transcript=text,
        started_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        speaker_map=labels,
        roster=roster,
        desktop_meeting_capture=True,
    )
    assert 'spk c0 ?' in prefix.context and 'spk c0 Sam' not in prefix.context
    assert row.text in prefix.context
