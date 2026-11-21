"""Synthetic calendar instructions survive compute thinning, not event adjudication."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.speaker_evidence import SpeakerCandidate, SpeakerEvidence, VoiceCluster
from models.structured import Structured
from utils.conversations.relevance_content import classify_content
from utils.conversations.relevance_rules import deterministic_relevance, has_explicit_keep_instruction
from utils.conversations.relevance_salience import minimum_is_background
from utils.llm.notes_short_clip import quiet_minimum

REQUESTS = (
    'Put my bike service on the calendar.',
    'Add the annual inspection to my calendar.',
    'Please put the tire change on my calendar.',
    'Could you add the safety check to the calendar?',
    'Can you please put the bike service on the calendar tomorrow?',
    'Please add the Notion workshop to my calendar.',
    'Could you please put notebook shopping on the calendar?',
    'Can you add the notifications review to my calendar?',
    'Ｐｕｔ my bike service on the calendar.',
)


@pytest.fixture(autouse=True)
def isolated_flags(monkeypatch):
    monkeypatch.delenv('EXPLICIT_CALENDAR_REQUEST_KEEP', raising=False)
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'on')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)


def capture(text):
    return SimpleNamespace(
        transcript_segments=[SimpleNamespace(text=text, start=0.0, end=2.0)],
        language='en',
        photos=[],
    )


@pytest.mark.parametrize('text', REQUESTS)
def test_calendar_instruction_bypasses_both_short_clip_floors(text):
    # No event/action is asserted here: None admits normal downstream processing.
    assert quiet_minimum('synthetic-account', capture(text), tz='UTC') is None


@pytest.mark.parametrize('text', REQUESTS)
def test_later_relevance_cannot_discard_the_preserved_instruction(text):
    assert deterministic_relevance([text], speech_seconds=2.0) == ('keep', 'explicit_reminder')


@pytest.mark.parametrize(
    'text',
    [
        'I will add the inspection to my calendar.',
        'I put bike service on the calendar yesterday.',
        'Do not put bike service on the calendar.',
        'Did you add the inspection to my calendar?',
        'The calendar shows a bike service.',
        'Add the annual inspection.',
        'Put the bike on the stand.',
        'Tomorrow I will service my bike.',
        'The manual says put bike service on the calendar.',
        'Put ' + 'x' * 161 + ' on the calendar.',
    ],
)
def test_non_instruction_and_below_floor_controls_still_take_minimum(text):
    assert not has_explicit_keep_instruction(text)
    minimum = quiet_minimum('synthetic-account', capture(text), tz='UTC')
    assert minimum is not None
    assert minimum.overview == '' and minimum.action_items == [] and minimum.events == []


@pytest.mark.parametrize('switch', ['false', 'off', '0', 'no'])
@pytest.mark.parametrize('text', REQUESTS)
def test_explicit_false_restores_previous_floor_and_relevance(monkeypatch, switch, text):
    monkeypatch.setenv('EXPLICIT_CALENDAR_REQUEST_KEEP', switch)
    assert not has_explicit_keep_instruction(text)
    assert quiet_minimum('synthetic-account', capture(text), tz='UTC') is not None
    assert deterministic_relevance([text], 2.0)[0] is None


@pytest.mark.parametrize('switch', ['false', 'true'])
@pytest.mark.parametrize(
    'text',
    [
        'Remind me to call tomorrow.',
        'Add this to my calendar.',
        'Remind me not to call tomorrow.',
        'Do not forget to call tomorrow.',
        'Do not add this to my calendar.',
        'Never add this to my calendar.',
    ],
)
def test_existing_reminders_keep_their_authority(monkeypatch, switch, text):
    monkeypatch.setenv('EXPLICIT_CALENDAR_REQUEST_KEEP', switch)
    assert quiet_minimum('synthetic-account', capture(text), tz='UTC') is None
    assert deterministic_relevance([text], 2.0) == ('keep', 'explicit_reminder')


def test_new_calendar_guard_does_not_fuse_speakers_or_turns():
    rows = [
        SimpleNamespace(text='Put my bike service', start=0.0, end=1.0, speaker='first'),
        SimpleNamespace(text='on the calendar.', start=1.0, end=2.0, speaker='second'),
    ]
    conversation = SimpleNamespace(transcript_segments=rows, language='en', photos=[])
    assert quiet_minimum('synthetic-account', conversation, tz='UTC') is not None
    assert deterministic_relevance([s.text for s in rows], 2.0)[0] is None


def unowned_media_minimum(text):
    start = datetime(2026, 11, 11, tzinfo=timezone.utc)
    rows = [SimpleNamespace(id='synthetic-segment', text=text, start=0.0, end=2.0, is_user=False)]
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='synthetic',
        clusters=[
            VoiceCluster(
                id='synthetic-voice',
                segment_ids=['synthetic-segment'],
                speech_seconds=2,
                candidates=[SpeakerCandidate(person_id='other', probability=1, band='confident', source='voice')],
            )
        ],
    )
    conversation = SimpleNamespace(transcript_segments=rows, content_kind='media')
    minimum = Structured(title='Synthetic minimum', title_provenance='server_minimum')
    return start, rows, evidence, conversation, minimum


@pytest.mark.parametrize('text', REQUESTS)
def test_same_instruction_contract_precedes_content_and_minimum_salience(monkeypatch, text):
    start, rows, evidence, conversation, minimum = unowned_media_minimum(text)
    decision = classify_content(rows, started_at=start, finished_at=start + timedelta(seconds=2), evidence=evidence)
    assert decision.content_kind == 'conversation' and decision.reason == 'protected'
    assert not minimum_is_background(conversation, minimum, evidence)
    monkeypatch.setenv('EXPLICIT_CALENDAR_REQUEST_KEEP', 'false')
    assert minimum_is_background(conversation, minimum, evidence)
    assert (
        classify_content(rows, started_at=start, finished_at=start + timedelta(seconds=2), evidence=evidence).reason
        != 'protected'
    )


@pytest.mark.parametrize('switch', ['true', 'false'])
@pytest.mark.parametrize(
    'text',
    [
        'Put my bike service not on the calendar.',
        'Add the annual inspection not to my calendar.',
        'Please put my bike service not on the calendar.',
        'Can you please add the inspection not to my calendar?',
        'Could you please put my bike service never on the calendar?',
        'Can you please not put my bike service on the calendar?',
        'Could you please never add the inspection to my calendar?',
        'Put no bike service on the calendar.',
        'Add the cancelled inspection to my calendar.',
        'Add the canceled inspection to my calendar.',
        'Please add the cancellation to my calendar.',
        'Put my bike service on the calendar never mind.',
        'Could you add the inspection I can’t attend to my calendar?',
        'Put my bike service ｎｏｔ on the calendar.',
        'Put the inspection I cannot attend on the calendar.',
        'Add the inspection without adding it to my calendar.',
        'Can you please add the inspection without adding it to my calendar?',
        'Could you please put the inspection without booking it on the calendar?',
        'Add the list except the inspection to my calendar.',
        'Put the visits excluding inspection on the calendar.',
        'Add the visits avoiding inspection to my calendar.',
        'Put the plan to avoid inspection on the calendar.',
        'Add the request to omit inspection to my calendar.',
        'Add the plan omitting inspection to my calendar.',
        'Add the inspection instead of another entry to my calendar.',
        'Put the inspection rather than the visit on the calendar.',
        'Add the inspection instead-of another entry to my calendar.',
        'Put the inspection rather-than the visit on the calendar.',
    ],
)
def test_negated_calendar_forms_preserve_floor_and_later_unprotected_policy(monkeypatch, switch, text):
    monkeypatch.setenv('EXPLICIT_CALENDAR_REQUEST_KEEP', switch)
    floor = quiet_minimum('synthetic-account', capture(text), tz='UTC')
    assert floor is not None
    assert not has_explicit_keep_instruction(text)
    assert floor.overview == '' and floor.action_items == [] and floor.events == []
    assert deterministic_relevance([text], speech_seconds=2.0)[0] is None
    start, rows, evidence, conversation, minimum = unowned_media_minimum(text)
    assert (
        classify_content(rows, started_at=start, finished_at=start + timedelta(seconds=2), evidence=evidence).reason
        != 'protected'
    )
    assert minimum_is_background(conversation, minimum, evidence)
