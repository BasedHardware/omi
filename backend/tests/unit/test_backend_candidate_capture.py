import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault('TYPESENSE_API_KEY', 'test-key-not-real')

from models.candidate import CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
from utils.conversations import process_conversation
from utils.task_intelligence.backend_capture import BackendCaptureSignals, adapt_backend_capture
from utils.task_intelligence import conversation_capture
from models.action_item import EvidenceRef, TaskCreatePayload
from models.structured_extraction import ActionItemsExtraction
from utils.llm import conversation_processing
from utils.memory.memory_system import MemorySystem
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort


def _enable_canonical(monkeypatch):
    """Patch conversation_capture so user-1 resolves to the canonical cohort."""
    set_canonical_cohort(monkeypatch, 'user-1')
    monkeypatch.setattr(
        conversation_capture,
        'resolve_memory_system',
        lambda uid, db_client=None: MemorySystem.CANONICAL,
    )


def _action(
    description,
    *,
    capture_kind=None,
    capture_owner=None,
    candidate_action=None,
    target_task_id=None,
    concrete_deliverable=None,
    capture_confidence=None,
):
    default_confidence = 0.95 if capture_kind else None
    return SimpleNamespace(
        description=description,
        completed=False,
        created_at=None,
        updated_at=None,
        due_at=None,
        completed_at=None,
        capture_kind=capture_kind,
        capture_owner=capture_owner,
        capture_confidence=default_confidence if capture_confidence is None else capture_confidence,
        ownership_confidence=1 if capture_owner == 'user' else None,
        candidate_action=candidate_action,
        target_task_id=target_task_id,
        concrete_deliverable=concrete_deliverable,
    )


def _conversation(*actions):
    return SimpleNamespace(
        id='conversation-1',
        is_locked=False,
        structured=SimpleNamespace(action_items=list(actions)),
    )


def _record(proposal, index):
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id=f'candidate-{index}',
        account_generation=3,
        idempotency_key=f'idem-{index}',
        created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
    )


def test_backend_adapter_maps_frozen_policy_outcomes_to_typed_candidates():
    task = TaskCreatePayload(description='Send the budget')
    evidence = EvidenceRef(kind='conversation', id='conversation-1', scope='canonical')
    pending = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            direct_request=True,
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.9,
            ownership_confidence=0.9,
        ),
    )
    accepted = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            clear_commitment=True,
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.95,
            ownership_confidence=1,
        ),
    )
    low_confidence = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            clear_commitment=True,
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.5,
            ownership_confidence=1,
        ),
    )
    without_deliverable = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            clear_commitment=True,
            concrete_deliverable=False,
            owner='user',
            capture_confidence=0.95,
            ownership_confidence=1,
        ),
    )
    ignored = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(public_broadcast=True),
    )
    weak_request = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            direct_request=True,
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.79,
            ownership_confidence=1,
        ),
    )
    strong_inference = adapt_backend_capture(
        task,
        evidence_ref=evidence,
        source_surface='conversation',
        signals=BackendCaptureSignals(
            inferred_next_step=True,
            concrete_deliverable=True,
            owner='user',
            capture_confidence=0.9,
            ownership_confidence=0.9,
        ),
    )

    assert pending.policy.outcome == 'pending_candidate'
    assert pending.candidate is not None
    assert accepted.policy.outcome == 'auto_accept_silent'
    assert accepted.policy.interruption == 'none'
    assert accepted.candidate.capture_confidence == 0.95
    assert low_confidence.policy.outcome == 'pending_candidate'
    assert low_confidence.policy.interruption == 'none'
    assert without_deliverable.policy.outcome == 'ignore'
    assert without_deliverable.policy.interruption == 'none'
    assert ignored.policy.outcome == 'ignore'
    assert ignored.candidate is None
    assert weak_request.policy.outcome == 'ignore'
    assert weak_request.candidate is None
    assert strong_inference.policy.outcome == 'pending_candidate'
    assert strong_inference.candidate is not None


def test_conversation_adapter_defaults_concrete_deliverable_false_and_honors_explicit_true():
    unknown = conversation_capture._capture_signals(_action('Send the budget', capture_kind='clear_commitment'))
    explicit = conversation_capture._capture_signals(
        _action('Send the budget', capture_kind='clear_commitment', concrete_deliverable=True)
    )

    assert unknown.concrete_deliverable is False
    assert explicit.concrete_deliverable is True
    assert (
        conversation_capture._capture_decision(
            _action(
                'Send the budget',
                capture_kind='clear_commitment',
                capture_owner='user',
                concrete_deliverable=True,
            ),
            'conversation-1',
        ).policy.outcome
        == 'auto_accept_silent'
    )
    assert (
        conversation_capture._capture_decision(
            _action(
                'Send the budget',
                capture_kind='clear_commitment',
                capture_owner='user',
                capture_confidence=0.4,
                concrete_deliverable=True,
            ),
            'conversation-1',
        ).policy.outcome
        == 'pending_candidate'
    )
    assert (
        conversation_capture._capture_decision(
            _action('Send the budget', capture_kind='clear_commitment', capture_owner='user'),
            'conversation-1',
        ).policy.outcome
        == 'ignore'
    )


@pytest.mark.parametrize(
    ('capture_kind', 'capture_owner', 'concrete_deliverable', 'capture_confidence', 'expected'),
    [
        ('direct_request', 'user', True, 0.8, 'pending_candidate'),
        ('direct_request', 'unknown', True, 0.95, 'ignore'),
        ('direct_request', 'user', False, 0.95, 'ignore'),
        ('direct_request', 'user', True, 0.79, 'ignore'),
        ('inferred_next_step', 'user', True, 0.8, 'pending_candidate'),
        ('inferred_next_step', 'unknown', True, 0.95, 'ignore'),
    ],
)
def test_conversation_adapter_requires_owned_concrete_high_confidence_requests_and_inferences(
    capture_kind,
    capture_owner,
    concrete_deliverable,
    capture_confidence,
    expected,
):
    decision = conversation_capture._capture_decision(
        _action(
            'Send the budget',
            capture_kind=capture_kind,
            capture_owner=capture_owner,
            concrete_deliverable=concrete_deliverable,
            capture_confidence=capture_confidence,
        ),
        'conversation-1',
    )

    assert decision.policy.outcome == expected
    assert (decision.candidate is not None) is (expected != 'ignore')


def test_conversation_adapter_uses_supplied_targets_for_update_and_completion():
    update = conversation_capture._capture_decision(
        _action('Send the revised budget', candidate_action='update', target_task_id='task-budget'),
        'conversation-1',
    )
    complete = conversation_capture._capture_decision(
        _action('Send the budget', candidate_action='complete', target_task_id='task-budget'),
        'conversation-1',
    )
    invented_target = conversation_capture._capture_decision(
        _action(
            'Send the revised budget',
            capture_kind='direct_request',
            capture_owner='user',
            candidate_action='update',
            concrete_deliverable=True,
        ),
        'conversation-1',
    )

    assert update.candidate.proposed_action == 'update'
    assert update.candidate.task_id == 'task-budget'
    assert complete.candidate.proposed_action == 'complete'
    assert complete.candidate.task_id == 'task-budget'
    assert invented_target.candidate.proposed_action == 'create'


def test_zero_confidence_values_are_not_replaced_by_defaults():
    action = _action('Review the forecast', capture_kind='direct_request')
    action.capture_confidence = 0.0
    action.ownership_confidence = 0.0

    signals = conversation_capture._capture_signals(action)

    assert signals.capture_confidence == 0.0
    assert signals.ownership_confidence == 0.0


def test_canonical_prompt_and_parser_preserve_no_deadline_requests_and_completion_targets(monkeypatch):
    captured = {}
    response = ActionItemsExtraction.model_validate(
        {
            'action_items': [
                {
                    'description': 'Review the forecast',
                    'capture_kind': 'direct_request',
                    'capture_owner': 'user',
                    'capture_confidence': 0.8,
                    'ownership_confidence': 1,
                    'candidate_action': 'create',
                },
                {
                    'description': 'Send the budget',
                    'capture_kind': 'direct_request',
                    'capture_owner': 'user',
                    'capture_confidence': 0.95,
                    'ownership_confidence': 1,
                    'candidate_action': 'complete',
                    'target_task_id': 'task-budget',
                },
            ]
        }
    )

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            captured['values'] = values
            return response

    def from_messages(messages):
        captured['instructions'] = messages[0][1]
        return FakePrompt()

    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', from_messages)
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *args, **kwargs: object())

    items = conversation_processing.extract_action_items(
        transcript='Please review the forecast. The budget task is done.',
        started_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        language_code='en',
        tz='UTC',
        existing_action_items=[{'id': 'task-budget', 'description': 'Send the budget', 'completed': False}],
        task_intelligence_capture=True,
    )
    rendered = captured['instructions'].format(**captured['values'])

    assert 'do not require a deadline for a concrete explicit' in rendered
    assert 'emit candidate_action=complete' in rendered
    assert 'A concrete request addressed directly to the primary user' in rendered
    assert 'capture_owner=user' in rendered
    assert 'do not modify the existing one' not in rendered
    assert items[0].due_at is None
    assert items[0].capture_kind == 'direct_request'
    assert items[1].candidate_action == 'complete'
    assert items[1].target_task_id == 'task-budget'


def test_shadow_mode_uses_canonical_extraction_without_writing(monkeypatch):
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='shadow', account_generation=3),
    )
    decisions = []

    class _NoCandidateDecision:
        candidate = None

    monkeypatch.setattr(
        conversation_capture,
        '_capture_decision',
        lambda action_item, conversation_id: decisions.append((action_item.description, conversation_id))
        or _NoCandidateDecision(),
    )
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'create_candidate',
        lambda *a, **kw: pytest.fail('should not create candidate when decision.candidate is None'),
    )

    assert conversation_capture.capture_enabled('user-1') is True
    # Canonical users route through process_before_legacy (returns True).
    assert conversation_capture.process_before_legacy('user-1', 'conversation-1', [_action('Send budget')]) is True
    assert decisions == [('Send budget', 'conversation-1')]


def test_read_mode_creates_pending_and_silently_accepts_commitment_without_notifications(monkeypatch):
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    records = []
    accepted = []

    def create(uid, proposal, **kwargs):
        record = _record(proposal, len(records) + 1)
        records.append(record)
        return record

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda uid, candidate_id, **kwargs: accepted.append(candidate_id),
    )
    monkeypatch.setattr(
        process_conversation,
        'send_action_item_data_message',
        lambda **kwargs: pytest.fail('Candidate capture cannot notify'),
    )
    monkeypatch.setattr(
        process_conversation.action_items_db,
        'create_action_items_batch',
        lambda *args: pytest.fail('read mode cannot use legacy batch writer'),
    )

    process_conversation._save_action_items(
        'user-1',
        _conversation(
            _action(
                'Send the budget',
                capture_kind='clear_commitment',
                capture_owner='user',
                concrete_deliverable=True,
            ),
            _action(
                'Review the forecast',
                capture_kind='direct_request',
                capture_owner='user',
                concrete_deliverable=True,
            ),
        ),
    )

    assert len(records) == 2
    assert accepted == ['candidate-1']
    assert records[1].status == 'pending'


def test_off_mode_is_behaviorally_legacy_and_canonical_route_bypasses_legacy_writer(monkeypatch):
    # Legacy (non-canonical) users keep the legacy writer untouched.
    set_canonical_cohort(monkeypatch)  # empty cohort = everyone is legacy
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='off', account_generation=3),
    )
    monkeypatch.setattr(process_conversation.action_items_db, 'get_action_items_by_conversation', lambda *args: [])
    monkeypatch.setattr(process_conversation.action_items_db, 'delete_action_items_for_conversation', lambda *args: 0)
    monkeypatch.setattr(
        process_conversation.action_items_db, 'retire_action_items_for_conversation', lambda *args, **kwargs: 0
    )
    writes = []

    def write(uid, rows, **kwargs):
        writes.append((rows, kwargs))
        return kwargs.get('document_ids') or [f'task-{len(writes)}']

    monkeypatch.setattr(
        process_conversation.action_items_db,
        'create_action_items_batch',
        write,
    )
    monkeypatch.setattr(process_conversation, 'upsert_action_item_vectors_batch', lambda *args, **kwargs: None)
    monkeypatch.setattr(process_conversation, 'delete_action_item_vectors_batch', lambda *args, **kwargs: None)
    monkeypatch.setattr(process_conversation, 'submit_with_context', lambda *args, **kwargs: None)

    conversation = _conversation(
        _action(
            'Send the budget',
            capture_kind='direct_request',
            capture_owner='user',
            concrete_deliverable=True,
        )
    )

    # Legacy user: capture_enabled is False, so legacy writer runs.
    assert conversation_capture.capture_enabled('user-1') is False
    process_conversation._save_action_items('user-1', conversation)
    assert len(writes) == 1

    # Canonical user: capture_enabled is True, process_before_legacy returns True.
    _enable_canonical(monkeypatch)
    candidates = {}

    def create(uid, proposal, **kwargs):
        key = kwargs['idempotency_key']
        candidates.setdefault(key, _record(proposal, len(candidates) + 1))
        return candidates[key]

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda uid, candidate_id, **kwargs: None,
    )
    assert conversation_capture.capture_enabled('user-1') is True
    result = conversation_capture.process_before_legacy(
        'user-1', 'conversation-1', conversation.structured.action_items
    )
    assert result is True
    assert len(candidates) == 1
    # reconcile_after_legacy is a no-op for canonical users.
    assert conversation_capture.reconcile_after_legacy('user-1', 'conversation-1', [], []) is None


def test_canonical_route_produces_single_pending_candidate(monkeypatch):
    """Canonical users get one candidate per action item; no legacy projection."""
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    records = {}

    def create(uid, proposal, **kwargs):
        records.setdefault(kwargs['idempotency_key'], _record(proposal, len(records) + 1))
        return records[kwargs['idempotency_key']]

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda uid, candidate_id, **kwargs: None,
    )
    action = _action(
        'Send the revised budget',
        capture_kind='direct_request',
        candidate_action='update',
        target_task_id='task-budget',
    )

    result = conversation_capture.process_before_legacy('user-1', 'conversation-1', [action])
    assert result is True
    # One candidate for the mutation, no separate legacy projection.
    assert len(records) == 1


def test_legacy_document_ids_returns_none_for_all_users(monkeypatch):
    """legacy_document_ids is retired; canonical users bypass the legacy writer."""
    _enable_canonical(monkeypatch)
    assert (
        conversation_capture.legacy_document_ids(
            'user-1', 'conversation-1', [_action('Send budget'), _action('Review forecast')]
        )
        is None
    )


def test_legacy_replacement_map_links_only_explicit_refinement_targets():
    """legacy_replacement_map still links extraction-provided update targets."""
    first_id = 'task-budget'
    second_id = 'task-forecast'
    explicit_refinement = _action(
        'Send revised budget',
        candidate_action='update',
        target_task_id=first_id,
    )
    # Explicit refinement of a retired task links to the new ID.
    assert conversation_capture.legacy_replacement_map(
        [
            {'id': first_id, 'description': 'Send budget'},
            {'id': second_id, 'description': 'Review forecast'},
        ],
        [explicit_refinement, _action('Review forecast')],
        ['task-new-budget', second_id],
    ) == {first_id: 'task-new-budget'}
    # No update action → no replacement.
    assert (
        conversation_capture.legacy_replacement_map(
            [
                {'id': first_id, 'description': 'Send budget'},
                {'id': second_id, 'description': 'Review forecast'},
            ],
            [_action('Send budget')],
            [first_id],
        )
        == {}
    )
    # Unrelated item → no replacement.
    assert (
        conversation_capture.legacy_replacement_map(
            [{'id': first_id, 'description': 'Send budget'}],
            [_action('Book dentist')],
            ['task-dentist'],
        )
        == {}
    )
    # Different entity with same action → no replacement.
    assert (
        conversation_capture.legacy_replacement_map(
            [{'id': first_id, 'description': 'Email Alice'}],
            [_action('Email Bob')],
            ['task-bob'],
        )
        == {}
    )


def test_repeated_descriptions_use_semantic_occurrences_without_order_dependent_candidate_keys(monkeypatch):
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    morning = _action(
        'Email the update',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
    )
    morning.due_at = datetime(2026, 7, 10, 9, tzinfo=timezone.utc)
    evening = _action(
        'Email the update',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
    )
    evening.due_at = datetime(2026, 7, 10, 17, tzinfo=timezone.utc)
    keys = []

    def create(uid, proposal, **kwargs):
        keys.append(kwargs['idempotency_key'])
        return _record(proposal, len(keys))

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)

    conversation_capture.process_before_legacy('user-1', 'conversation-1', [morning, evening])
    first_keys = list(keys)
    keys.clear()
    conversation_capture.process_before_legacy('user-1', 'conversation-1', [evening, morning])

    assert first_keys[0] != first_keys[1]
    assert keys == [first_keys[1], first_keys[0]]
