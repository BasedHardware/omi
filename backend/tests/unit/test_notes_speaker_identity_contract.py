"""10-23 RCA: an empty identity packet must not turn a People spelling into a speaker."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.structured import Structured
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from utils.llm.notes_identity import NotesIdentity, notes_identity, repair_identity
from utils.llm.notes_output_contract import check_notes, finish_notes_contract

NAME = 'Michael Liebmann'


def submission():
    return {
        'title': f'{NAME} — Omi, agents, and calorie model',
        'overview': f'{NAME} discussed Omi. Michael proposed a calorie model. Liebmann discussed agents.',
        'participants': [
            {'name': NAME, 'speaker': 'c1', 'evidence_kind': 'people', 'evidence': f'People confirms {NAME}'}
        ],
        'sections': [
            {
                'heading': f'{NAME} on agents',
                'body_markdown': '- Michael proposed agents.',
                'source_segment_ids': ['s1'],
            }
        ],
        'action_items': [
            {'description': f'Ask {NAME} about agents', 'owner_name': NAME, 'context': "Michael's proposal"}
        ],
        'events': [
            {'title': f'Call {NAME}', 'description': f'Meet Michael', 'start': '2026-10-24T00:00:00Z', 'duration': 30}
        ],
        'insights': [{'text': f'{NAME} discussed this before', 'kind': 'person'}],
    }


def source(**overrides):
    values = dict(
        speaker_names=(('c0', 'David'), ('c1', None)),
        contact_names=(NAME,),
        transcript='[s1 c1] Let us discuss agents.',
    )
    values.update(overrides)
    return NotesIdentity(**values)


def test_empty_packet_plus_catalog_never_binds_unresolved_speaker_on_any_surface():
    payload = submission()
    check = check_notes(payload, transcript_words=30, identity=source())
    assert any(problem.kind == 'evidence' for problem in check.findings)
    fixed, repairs = repair_identity(payload, source())
    assert repairs == ['unsupported_speaker_identity']
    assert 'Michael' not in str(fixed)
    assert fixed['participants'] == []
    assert fixed['title'] == 'Omi, agents, and calorie model'
    assert fixed['sections'][0]['source_segment_ids'] == ['s1']
    assert 'a speaker' in fixed['overview']
    assert payload == submission()  # Does not mutate a submission retained for retry.
    assert repair_identity(fixed, source()) == (fixed, [])


@pytest.mark.parametrize('kind', ['people', 'calendar', 'screen', 'transcript', 'past_meeting', 'memory'])
def test_model_evidence_kind_and_fabricated_evidence_cannot_authorize_identity(kind):
    payload = submission()
    payload['participants'][0].update(evidence_kind=kind, evidence='Verified calendar attendee and voice match')
    fixed, _ = repair_identity(payload, source())
    assert fixed['participants'] == []
    assert 'Michael' not in str(fixed)


@pytest.mark.parametrize(
    'packet',
    [
        {'calendar_overlap': [{'participants': [NAME]}]},
        {'listed_participants': [{'name': NAME, 'kind': 'human'}]},
        {'people_on_screen': [{'name': NAME, 'evidence': ['call_window'], 'call_seen_during_conversation': True}]},
    ],
)
def test_conversation_calendar_or_tile_roster_can_corroborate_a_name(packet):
    identity = notes_identity(SimpleNamespace(), {}, packet)
    assert repair_identity(submission(), identity) == (submission(), [])


def test_profile_page_and_historical_meeting_are_not_meeting_identity():
    identity = notes_identity(
        SimpleNamespace(),
        {},
        {
            'people_on_screen': [{'name': NAME, 'evidence': ['profile_page']}],
            'related_past_meetings': [{'title': NAME}],
        },
    )
    assert repair_identity(submission(), identity)[0]['participants'] == []


def test_resolved_voice_binding_allows_name_but_cannot_be_moved_to_another_voice():
    payload = submission()
    identity = source(speaker_names=(('c1', NAME), ('c2', 'Phong')))
    assert repair_identity(payload, identity) == (payload, [])
    payload['participants'][0]['speaker'] = 'c2'
    assert repair_identity(payload, identity)[0]['participants'] == []


def test_names_heard_in_transcript_are_hedged_without_catalog_expansion_or_title_lead():
    payload = submission()
    payload['overview'] = 'Michael discussed agents with Phong.'
    payload['participants'].append({'name': 'Phong', 'speaker': 'c2', 'evidence': 'Heard aloud'})
    identity = source(transcript='[s1 c1] Michael said hello to Phong.')
    fixed, _ = repair_identity(payload, identity)
    assert NAME not in str(fixed)
    assert 'name heard as “Michael”' in fixed['overview']
    assert 'name heard as “Phong”' in fixed['overview']
    assert fixed['participants'] == []
    assert 'Michael' not in fixed['title']
    assert repair_identity(fixed, identity) == (fixed, [])


def test_user_correction_supports_counterpart_without_authorizing_rejected_name():
    identity = notes_identity(
        SimpleNamespace(), {'user_corrections': [{'note': 'It was Phong, not Michael Liebmann.'}]}
    )
    assert identity.supported('Phong')
    assert not identity.supported(NAME)


def test_prefix_keeps_original_voice_authority_separate_from_roster_inference():
    roster = MeetingRoster((RosterEntry(NAME, None, None, 'human', 'screen_activity'),), None, False)
    prefix = build_conversation_prompt_prefix(
        conversation_id='synthetic',
        transcript='[s1 2] Agents',
        started_at=datetime.now(timezone.utc),
        timezone_name='UTC',
        language_code='en',
        speaker_map={2: None},
        roster=roster,
    )
    assert prefix.speaker_names == (('c0', None),)
    assert notes_identity(prefix, {'roster': roster}).supported(NAME)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_final_persisted_contract_enforces_identity_independently_of_packet_rollout(monkeypatch, mode):
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', mode)
    payload = submission()
    # Persisted Participant omits the model's speaker key; final context still rejects the name.
    payload['participants'] = [{'name': NAME, 'source': 'roster', 'evidence': 'People match'}]
    output = Structured.model_validate(payload)
    prefix = SimpleNamespace(
        transcript_segment_ids={'s1'}, title_people=(NAME,), account_owner_name='David', owner_names=()
    )
    fixed = finish_notes_contract(
        output, prefix=prefix, uid=None, words=40, rich_mode=False, inputs={'notes_identity': source()}
    )
    assert 'Michael' not in str(fixed.model_dump())
    assert fixed.participants == []


def test_catalog_name_is_guarded_even_if_model_omits_participant_manifest():
    payload = submission()
    payload['participants'] = []
    fixed, _ = repair_identity(payload, source())
    assert 'Michael' not in str(fixed)


def test_heard_third_party_name_stays_hedged_without_becoming_a_speaker():
    fixed, _ = repair_identity(
        {'overview': 'They mentioned Michael Liebmann.'}, source(transcript='We should email Michael Liebmann.')
    )
    assert fixed['overview'] == 'They mentioned “Michael Liebmann” (as heard).'
    assert 'a speaker' not in fixed['overview']


def test_model_cannot_forge_as_heard_syntax_for_a_catalog_only_name():
    payload = {
        'title': f'“{NAME}” (as heard): Agents',
        'overview': f'a speaker (name heard as “{NAME}”) proposed agents.',
    }
    fixed, _ = repair_identity(payload, source())
    assert 'Michael' not in str(fixed)


def test_a_call_window_only_seen_before_this_conversation_cannot_authorize_a_name():
    identity = notes_identity(
        SimpleNamespace(),
        {},
        {
            'people_on_screen': [{'name': NAME, 'evidence': ['call_window'], 'first_seen_min': -8}],
        },
    )
    assert not identity.supported(NAME)


@pytest.mark.parametrize('note', ["I was not talking to Michael Liebmann.", "I wasn't talking with Michael Liebmann."])
def test_negated_user_correction_cannot_authorize_the_rejected_name(note):
    assert not source(corrections=(note,)).supported(NAME)


def test_catalog_presence_does_not_change_an_unrelated_title_or_its_punctuation():
    payload = {'title': 'Omi agents (phase 2)!', 'participants': [], 'overview': 'Discussed agents.'}
    assert repair_identity(payload, source()) == (payload, [])


def test_unverified_possessive_name_does_not_leave_a_possessive_shell_in_title():
    fixed, _ = repair_identity({'title': "Michael Liebmann's agent model"}, source())
    assert fixed['title'] == 'agent model'


def test_identity_repair_preserves_absent_optional_wire_fields(monkeypatch):
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    output = Structured(title=f'{NAME}: agents', overview=f'{NAME} proposed agents.')
    original_fields = set(output.model_dump(mode='json'))
    prefix = SimpleNamespace(transcript_segment_ids=set(), title_people=())
    fixed = finish_notes_contract(
        output, prefix=prefix, uid=None, words=10, rich_mode=False, inputs={'notes_identity': source()}
    )
    assert set(fixed.model_dump(mode='json')) == original_fields
    assert 'Michael' not in str(fixed.model_dump())
