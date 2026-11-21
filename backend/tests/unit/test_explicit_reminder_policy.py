"""Synthetic reminder contracts; these tests do not measure model recall."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from models.action_item import TaskCreatePayload
from models.structured import ActionItem
from models.structured_extraction import ActionItemsExtraction
from models.task_due import TaskDue
from utils.task_intelligence import reminder_policy as policy
from utils.task_intelligence.conversation_capture_policy import evaluate_action_item_capture_policy

SOURCE = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)


def conversation(text='Remind me to renew the library card on January fifteenth.', *, owner='user', **overrides):
    row = SimpleNamespace(
        id='synthetic-turn-1',
        text=text,
        start=10.0,
        end=13.0,
        speaker_id=7,
        is_user=owner == 'user',
        speaker_label_source='manual' if owner != 'unknown' else None,
        person_id='synthetic-contact' if owner == 'other' else None,
    )
    values = dict(
        id='synthetic-conversation', started_at=SOURCE, capture_timezone='Asia/Ho_Chi_Minh', transcript_segments=[row]
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def extraction(kind='explicit_reminder', expression='January fifteenth', **overrides):
    values = dict(
        description='Renew the library card',
        capture_kind='explicit_command',
        capture_confidence=0.98,
        capture_owner='user',
        ownership_confidence=0.99,
        concrete_deliverable=True,
        source_segment_ids=['synthetic-turn-1'],
        reminder_intent=dict(kind=kind, due_expression=expression),
    )
    values.update(overrides)
    # Exercises the actual notes-output -> SDK contract.
    return ActionItemsExtraction.model_validate({'action_items': [values]}).to_action_items()[0]


def prepare(item=None, conv=None):
    return policy.prepare_reminder(item or extraction(), conversation=conv or conversation(), extracted_at=SOURCE)


def test_extractor_date_only_round_trip_and_capture_policy():
    item = prepare()
    assert item.due.kind == 'date'
    assert item.due.date == '2027-01-15'
    assert item.due.year_basis == 'next_future_occurrence'
    assert item.due_at is None
    assert '2027-01-15' in item.context
    payload = TaskCreatePayload(description=item.description, due=item.due.model_dump(), due_at=item.due_at)
    assert payload.model_dump(mode='json')['due']['date'] == '2027-01-15'
    assert evaluate_action_item_capture_policy(item).policy.outcome == 'pending_candidate'


@pytest.mark.parametrize('owner', ['user', 'other', 'unknown'])
def test_owner_other_waiting_on_and_pending_review(owner):
    item = prepare(conv=conversation(owner=owner))
    if owner == 'other':
        assert item is None  # broad waiting-on path is deliberately off
    else:
        assert item.capture_owner == owner
        assert evaluate_action_item_capture_policy(item).policy.outcome == 'pending_candidate'
        assert item.reminder_origin.review_reason == ('owner_unresolved' if owner == 'unknown' else None)
        if owner == 'unknown':
            assert item.ownership_confidence == 0
            assert item.context.startswith('Review speaker:')


@pytest.mark.parametrize('kind', ['quoted', 'hypothetical', 'current_session', 'status', 'waiting_on'])
def test_non_commitments_never_enter_reminder_path(kind):
    assert prepare(extraction(kind)) is None


@pytest.mark.parametrize(
    'text',
    [
        'Morgan said "remind me to renew the library card on January fifteenth".',
        'If I said remind me to renew the library card on January fifteenth, that would be hypothetical.',
        'Investigate the library card policy now.',
        'I am renewing the library card now.',
    ],
)
def test_deterministic_admission_vetoes_misclassified_extraction(text):
    assert prepare(conv=conversation(text)) is None


def test_explicit_errand_survives_without_a_wake_word():
    item = prepare(extraction(expression=None, description='Get fuel'), conversation('Remind me to get fuel.'))
    assert item is not None
    assert item.due.kind == 'none'


def test_missing_or_fabricated_source_cannot_admit():
    assert prepare(extraction(source_segment_ids=[])) is None
    assert prepare(extraction(source_segment_ids=['invented'])) is None
    assert prepare(extraction(expression='March first')) is None


def test_legacy_boolean_does_not_resolve_owner():
    conv = conversation(owner='unknown')
    conv.transcript_segments[0].is_user = True
    item = prepare(conv=conv)
    assert item.capture_owner == 'unknown'


def test_identity_integration_seam_is_bounded():
    item = policy.prepare_reminder(
        extraction(),
        conversation=conversation(),
        extracted_at=SOURCE,
        evidence=lambda rows: policy.SpeakerEvidence('user', 'synthetic-identity-v2'),
    )
    assert item.reminder_origin.speaker_evidence_revision == 'synthetic-identity-v2'


@pytest.mark.parametrize(
    'expression,expected',
    [
        ('January fifteenth', '2027-01-15'),
        ('January 15', '2027-01-15'),
        ('January 15, 2028', '2028-01-15'),
        ('2026-10-01', '2026-10-01'),
        ('tomorrow', '2026-11-02'),
        ('today', '2026-11-01'),
        ('February twenty ninth', '2028-02-29'),
    ],
)
def test_source_clock_date_resolution(expression, expected):
    due = policy.resolve_due(expression, source_at=SOURCE, capture_timezone='Asia/Ho_Chi_Minh')
    assert due.kind == 'date'
    assert due.date == expected
    assert due.instant is None


@pytest.mark.parametrize(
    'expression', ['01/02', 'yesterday', 'last January fifteenth', 'February 30', 'later', 'at midnight']
)
def test_ambiguous_dates_are_retained_without_an_hour(expression):
    due = policy.resolve_due(expression, source_at=SOURCE, capture_timezone='Asia/Ho_Chi_Minh')
    assert due.kind == 'unresolved'
    assert due.expression == expression
    assert due.instant is None


@pytest.mark.parametrize(
    'expression,kind',
    [
        ('2026-03-08T02:30', 'unresolved'),
        ('2026-11-01T01:30', 'unresolved'),
        ('2026-11-01T01:30-04:00', 'instant'),
        ('2026-11-01T01:30-05:00', 'instant'),
        ('2026-11-01T00:00', 'instant'),
    ],
)
def test_dst_and_explicit_midnight(expression, kind):
    due = policy.resolve_due(expression, source_at=SOURCE, capture_timezone='America/New_York')
    assert due.kind == kind
    assert (due.instant is not None) == (kind == 'instant')


def test_timezone_change_missing_clock_and_delayed_extraction():
    conv = conversation('Remind me tomorrow to review the draft.')
    conv.started_at = datetime(2026, 11, 1, 20, tzinfo=timezone.utc)
    first = policy.prepare_reminder(extraction(expression='tomorrow'), conversation=conv, extracted_at=SOURCE)
    second = policy.prepare_reminder(
        extraction(expression='tomorrow'), conversation=conv, extracted_at=datetime(2027, 5, 1, tzinfo=timezone.utc)
    )
    assert first.due == second.due
    assert first.due.date == '2026-11-03'
    assert first.reminder_origin.source_at == second.reminder_origin.source_at
    conv.capture_timezone = None
    assert prepare(extraction(expression='tomorrow'), conv).due.reason == 'missing_capture_timezone'
    conv.started_at = None
    assert prepare(extraction(expression='tomorrow'), conv).due.reason == 'missing_source_clock'


def test_kill_switch_inert_and_read_contract_survives(monkeypatch):
    item = prepare()
    monkeypatch.setenv(policy.FLAG, 'false')
    assert prepare() is None
    assert policy.instructions('baseline') == 'baseline'
    assert ActionItem.model_validate(item.model_dump()).due.date == '2027-01-15'


def test_date_only_cannot_become_invented_due_at():
    due = TaskDue(kind='date', date='2027-01-15', timezone='Asia/Ho_Chi_Minh')
    with pytest.raises(ValidationError):
        TaskCreatePayload(description='Renew the card', due=due, due_at=SOURCE)


def test_sdk_and_fallback_due_models_have_one_contract():
    root = Path(__file__).resolve().parents[3]
    assert (root / 'backend/models/task_due.py').read_text() == (
        root / 'plugins/omi-plugin-sdk/src/omi_plugin_sdk/task_due.py'
    ).read_text()


def test_owner_ambiguity_elsewhere_in_source_keeps_review_pending():
    conv = conversation()
    other_cluster = SimpleNamespace(**{**vars(conv.transcript_segments[0]), 'id': 'synthetic-turn-2', 'speaker_id': 8})
    conv.transcript_segments.append(other_cluster)
    assert prepare(conv=conv).capture_owner == 'unknown'


def test_new_reminder_path_never_mutates_an_existing_task():
    assert prepare(extraction(candidate_action='complete', target_task_id='synthetic-existing-task')) is None


def test_ingress_revalidation_preserves_extraction_time_until_evidence_changes():
    item = prepare()
    later = datetime(2027, 5, 1, tzinfo=timezone.utc)
    replay = policy.prepare_reminder(item, conversation=conversation(), extracted_at=later)
    assert replay.reminder_origin == item.reminder_origin
    assert replay.due == item.due
    changed = conversation()
    changed.transcript_segments[0].end += 1
    revised = policy.prepare_reminder(item, conversation=changed, extracted_at=later)
    assert revised.reminder_origin.input_revision != item.reminder_origin.input_revision
    assert revised.reminder_origin.extracted_at == later
