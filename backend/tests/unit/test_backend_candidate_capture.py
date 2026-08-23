import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault('TYPESENSE_API_KEY', 'test-key-not-real')

from models.candidate import CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
from utils.conversations import process_conversation
from utils.task_intelligence.backend_capture import BackendCaptureSignals, adapt_backend_capture
from utils.task_intelligence.capture_policy import run_capture_policy
from utils.task_intelligence import conversation_capture
from utils.task_intelligence import conversation_capture_policy
from models.action_item import EvidenceRef, TaskCreatePayload
from models.structured_extraction import ActionItemsExtraction
from utils.llm import conversation_processing
from utils.llm.wake_word_adjudication import WakeWordAdjudication, WakeWordInvocationVerdict


def _enable_canonical(monkeypatch):
    """Retained test helper name; universal capture needs no cohort setup."""
    return None


def _action(
    description,
    *,
    capture_kind=None,
    capture_owner=None,
    candidate_action=None,
    target_task_id=None,
    concrete_deliverable=None,
    capture_confidence=None,
    source_segment_ids=None,
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
        source_segment_ids=source_segment_ids or [],
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
    # I1: even a high-confidence first-person commitment only proposes.
    assert accepted.policy.outcome == 'pending_candidate'
    assert accepted.policy.interruption == 'none'
    assert accepted.candidate.capture_confidence == 0.95
    # Below the floor the Suggested surface would hide it, so it is not admitted.
    assert low_confidence.policy.outcome == 'ignore'
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
    unknown = conversation_capture_policy.capture_signals_for_action_item(
        _action('Send the budget', capture_kind='clear_commitment')
    )
    explicit = conversation_capture_policy.capture_signals_for_action_item(
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
        == 'pending_candidate'
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
        == 'ignore'
    )
    assert (
        conversation_capture._capture_decision(
            _action('Send the budget', capture_kind='clear_commitment', capture_owner='user'),
            'conversation-1',
        ).policy.outcome
        == 'ignore'
    )


def _wake_word_gate(*verdicts):
    return conversation_capture_policy.WakeWordCaptureGate(
        matched_segment_ids=frozenset({'wake-segment'}),
        adjudication=WakeWordAdjudication(
            invocations=[
                WakeWordInvocationVerdict(
                    segment_ids=['wake-segment'],
                    verdict=verdict,
                    evidence_quote='Hey Omi',
                    payload_segment_ids=['payload-segment'],
                )
                for verdict in verdicts
            ]
        ),
    )


@pytest.mark.parametrize('verdict', ['task_command', 'memory_command'])
def test_wake_word_explicit_command_requires_an_independent_accepting_verdict(verdict):
    action = _action(
        'Send the budget',
        capture_kind='explicit_command',
        capture_owner='user',
        concrete_deliverable=True,
        source_segment_ids=['wake-segment', 'payload-segment'],
    )

    signals = conversation_capture_policy.capture_signals_for_action_item(action, _wake_word_gate(verdict))

    assert signals.explicit_command is True
    assert signals.direct_request is False
    assert signals.direct_mention is False


@pytest.mark.parametrize(
    'verdict',
    ['question', 'quoted_or_meta', 'not_addressed_to_omi', 'abandoned', 'unclear'],
)
def test_wake_word_rejection_demotes_extractor_explicit_command_to_review_path(verdict):
    action = _action(
        'Send the budget',
        capture_kind='explicit_command',
        capture_owner='user',
        concrete_deliverable=True,
        source_segment_ids=['wake-segment'],
    )

    signals = conversation_capture_policy.capture_signals_for_action_item(action, _wake_word_gate(verdict))

    assert signals.explicit_command is False
    assert signals.direct_request is True
    assert signals.capture_confidence == 0.95
    assert run_capture_policy(signals.policy_signals()).outcome == 'pending_candidate'


def test_wake_word_task_verdict_promotes_non_explicit_extraction_without_changing_confidence():
    action = _action(
        'Send the budget',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
        capture_confidence=0.42,
        source_segment_ids=['wake-segment'],
    )

    signals = conversation_capture_policy.capture_signals_for_action_item(action, _wake_word_gate('task_command'))

    assert signals.explicit_command is True
    assert signals.direct_request is False
    assert signals.capture_confidence == 0.42
    # Wake-word promotion still only proposes, and every kind clears the 0.8
    # visibility floor — 0.42 is below it, so the policy ignores rather than
    # writing a task (#11980's create_direct outcome is gone).
    assert run_capture_policy(signals.policy_signals()).outcome == 'ignore'


@pytest.mark.parametrize(
    'verdicts',
    [('memory_command',), ('task_command', 'quoted_or_meta')],
)
def test_wake_word_non_explicit_extraction_promotes_only_on_unambiguous_task_verdicts(verdicts):
    action = _action(
        'Send the budget',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
        source_segment_ids=['wake-segment'],
    )

    signals = conversation_capture_policy.capture_signals_for_action_item(action, _wake_word_gate(*verdicts))

    assert signals.explicit_command is False
    assert signals.direct_request is True


def test_wake_word_gate_leaves_non_intersecting_item_completely_untouched():
    action = _action(
        'Call the dentist',
        capture_kind='clear_commitment',
        capture_owner='user',
        concrete_deliverable=True,
        source_segment_ids=['ambient-segment'],
    )

    gated = conversation_capture_policy.capture_signals_for_action_item(action, _wake_word_gate('quoted_or_meta'))
    ordinary = conversation_capture_policy.capture_signals_for_action_item(action)

    assert gated == ordinary


def test_wake_word_no_longer_overloads_direct_mention_for_future_broadcast_policy():
    action = _action(
        'Send the budget',
        capture_kind='explicit_command',
        source_segment_ids=['wake-segment'],
    )
    signals = conversation_capture_policy.capture_signals_for_action_item(
        action, _wake_word_gate('task_command')
    ).model_copy(update={'public_broadcast': True})

    decision = adapt_backend_capture(
        TaskCreatePayload(description=action.description),
        evidence_ref=EvidenceRef(kind='conversation', id='conversation-1', scope='canonical'),
        source_surface='conversation',
        signals=signals,
    )

    assert signals.direct_mention is False
    assert decision.policy.outcome == 'ignore'


def test_wake_word_adjudication_is_strictly_match_triggered():
    calls = []
    conversation = SimpleNamespace(
        id='conversation-1',
        transcript_segments=[
            SimpleNamespace(
                id='ordinary-1',
                text='We should review the budget.',
                start=0,
                end=2,
                is_user=True,
            )
        ],
        structured=SimpleNamespace(action_items=[]),
    )

    result = conversation_capture.prepare_wake_word_capture_gate(
        'user-1',
        conversation,
        adjudicator=lambda **kwargs: calls.append(kwargs) or WakeWordAdjudication(),
    )

    assert result is None
    assert calls == []


def test_wake_word_adjudication_logs_question_descope_and_task_omission_without_synthesis(monkeypatch):
    metric_codes = []

    class FakeCounter:
        def labels(self, **labels):
            metric_codes.append(labels['code'])
            return self

        def inc(self):
            return None

    segments = [
        SimpleNamespace(
            id='wake-task',
            text='Hey Omi, remind me to send the budget.',
            start=0,
            end=2,
            is_user=True,
            person_id=None,
            speaker_id=0,
        ),
        SimpleNamespace(
            id='wake-question',
            text='Hey Omi, what time is the review?',
            start=3,
            end=5,
            is_user=True,
            person_id=None,
            speaker_id=0,
        ),
    ]
    conversation = SimpleNamespace(
        id='conversation-1',
        transcript_segments=segments,
        structured=SimpleNamespace(action_items=[]),
    )
    adjudication = WakeWordAdjudication(
        invocations=[
            WakeWordInvocationVerdict(
                segment_ids=['wake-task'],
                verdict='task_command',
                evidence_quote='Hey Omi',
                payload_segment_ids=['wake-task'],
            ),
            WakeWordInvocationVerdict(
                segment_ids=['wake-question'],
                verdict='question',
                evidence_quote='Hey Omi',
                payload_segment_ids=['wake-question'],
            ),
        ]
    )
    calls = []
    monkeypatch.setattr(conversation_capture, 'TASK_INTELLIGENCE_ATTRIBUTION_TOTAL', FakeCounter())
    monkeypatch.setattr(conversation_capture, 'conversation_transcript_for_action_items', lambda *_a, **_k: 'marked')
    monkeypatch.setattr(conversation_capture, 'conversation_action_item_speaker_labels', lambda *_a, **_k: [])

    gate = conversation_capture.prepare_wake_word_capture_gate(
        'user-1',
        conversation,
        adjudicator=lambda **kwargs: calls.append(kwargs) or adjudication,
    )

    assert gate is not None
    assert len(calls) == 1
    assert calls[0]['matched_segment_ids'] == {'wake-task', 'wake-question'}
    assert calls[0]['action_items'] == ()
    assert sorted(metric_codes) == ['question_descope', 'task_command_without_extraction']


def test_save_action_items_runs_wake_adjudication_even_when_extractor_returned_no_items(monkeypatch):
    conversation = SimpleNamespace(
        id='conversation-1',
        structured=SimpleNamespace(action_items=[]),
    )
    prepare = SimpleNamespace(calls=0)

    def fake_prepare(*_args, **_kwargs):
        prepare.calls += 1
        return None

    monkeypatch.setattr(process_conversation.conversation_capture, 'prepare_wake_word_capture_gate', fake_prepare)

    process_conversation._save_action_items('user-1', conversation)

    assert prepare.calls == 1


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

    signals = conversation_capture_policy.capture_signals_for_action_item(action)

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


def test_rejected_item_is_dropped_alone_and_never_falls_back_to_a_writer(monkeypatch):
    """I1: an ignored item must not drag its siblings onto the legacy writer."""
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='shadow', account_generation=3),
    )
    seen = []
    created = []

    class _NoCandidateDecision:
        candidate = None

    class _CandidateDecision:
        candidate = object()

    def decide(action_item, conversation_id, *args, **kwargs):
        seen.append((action_item.description, conversation_id))
        return _NoCandidateDecision() if action_item.description == 'Ignore me' else _CandidateDecision()

    monkeypatch.setattr(conversation_capture, '_capture_decision', decide)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'create_candidate',
        lambda uid, proposal, **kw: created.append(proposal) or SimpleNamespace(candidate_id='candidate-1'),
    )

    assert conversation_capture.capture_enabled('user-1') is True
    handled = conversation_capture.process_before_legacy(
        'user-1',
        'conversation-1',
        [_action('Ignore me'), _action('Send budget')],
    )

    # Always handled: there is no path back to a writer that bypasses the user.
    assert handled is True
    assert seen == [('Ignore me', 'conversation-1'), ('Send budget', 'conversation-1')]
    # Only the admitted item was proposed; the ignored one was dropped alone.
    assert len(created) == 1


def test_extraction_only_proposes_and_never_accepts_or_writes_a_task(monkeypatch):
    """I1: conversation extraction creates pending Candidates and nothing else."""
    _enable_canonical(monkeypatch)
    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    records = []

    def create(uid, proposal, **kwargs):
        record = _record(proposal, len(records) + 1)
        records.append(record)
        return record

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda *a, **kw: pytest.fail('extraction must never accept a candidate'),
    )
    monkeypatch.setattr(
        process_conversation,
        'send_action_item_data_message',
        lambda **kwargs: pytest.fail('Candidate capture cannot notify'),
    )
    monkeypatch.setattr(
        process_conversation.action_items_db,
        'create_action_items_batch',
        lambda *args, **kwargs: pytest.fail('extraction must never write an action item'),
    )
    monkeypatch.setattr(
        process_conversation.action_items_db,
        'create_action_item',
        lambda *args, **kwargs: pytest.fail('extraction must never write an action item'),
    )
    emitted = []
    monkeypatch.setattr(process_conversation, 'emit_product_event', lambda **event: emitted.append(event))

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
    assert [record.status for record in records] == ['pending', 'pending']
    assert emitted == [
        {
            'uid': 'user-1',
            'event': 'Task Extracted',
            'properties': {
                'task_count': 2,
                'conversation_id': 'conversation-1',
                'task_source': 'transcript',
                'persistence_path': 'canonical_candidate',
            },
        }
    ]


def test_off_mode_still_only_proposes_and_never_reaches_a_writer(monkeypatch):
    # Workflow mode is diagnostic; every authenticated UID uses Candidate. `off`
    # is what the control endpoint reports on its own read failure, and it must
    # not become a route into the task list (I1).
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
    monkeypatch.setattr(process_conversation, 'submit_with_context', lambda *args, **kwargs: None)

    conversation = _conversation(
        _action(
            'Send the budget',
            capture_kind='direct_request',
            capture_owner='user',
            concrete_deliverable=True,
        )
    )

    assert conversation_capture.capture_enabled('user-1') is True
    candidates = {}

    def create(uid, proposal, **kwargs):
        key = kwargs['idempotency_key']
        candidates.setdefault(key, _record(proposal, len(candidates) + 1))
        return candidates[key]

    monkeypatch.setattr(conversation_capture.candidate_service, 'create_candidate', create)
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda *a, **kw: pytest.fail('extraction must never accept a candidate'),
    )
    assert conversation_capture.capture_enabled('user-1') is True
    result = conversation_capture.process_before_legacy(
        'user-1', 'conversation-1', conversation.structured.action_items
    )
    assert result is True
    assert len(candidates) == 1
    assert writes == []
    # reconcile_after_legacy is a no-op for universal Candidate captures.
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
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda uid, candidate_id, **kwargs: None,
    )

    conversation_capture.process_before_legacy('user-1', 'conversation-1', [morning, evening])
    first_keys = list(keys)
    keys.clear()
    conversation_capture.process_before_legacy('user-1', 'conversation-1', [evening, morning])

    assert first_keys[0] != first_keys[1]
    assert keys == [first_keys[1], first_keys[0]]


def _segment(segment_id, start, end):
    return SimpleNamespace(id=segment_id, start=start, end=end)


def test_capture_survives_negative_segment_offsets():
    """Merged sync audio yields segment offsets below zero; evidence clamps to zero.

    Before this, EvidenceRef(ge=0) raised inside the adapter and the raising call
    sat first in _save_action_items, so the conversation produced no task at all.
    """

    action = _action(
        'Comprar o presente da sogra',
        capture_kind='explicit_command',
        capture_owner='user',
        concrete_deliverable=True,
    )
    action.source_segment_ids = ['segment-1', 'segment-2']
    segments = [_segment('segment-1', -17.329691410064697, 5.790308589935304), _segment('segment-2', -1.8e-07, 2.15)]

    decision = conversation_capture._capture_decision(action, 'conversation-1', segments)

    assert decision.candidate is not None
    evidence = decision.candidate.evidence_refs[0]
    assert evidence.start_seconds == 0.0
    assert evidence.end_seconds == 5.790308589935304
    assert evidence.transcript_segment_ids == ['segment-1', 'segment-2']


def test_pending_tier_create_stays_pending_for_the_user(monkeypatch):
    """I1: a create from conversation extraction is a suggestion, never a task.

    #12014 auto-accepted conversation creates because only macOS read the
    Candidate surface. This branch makes that surface the product: the user
    adds the suggestion, extraction does not.
    """

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
    action = _action(
        'Review the forecast',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
    )

    assert conversation_capture._capture_decision(action, 'conversation-1').policy.outcome == 'pending_candidate'
    assert conversation_capture.process_before_legacy('user-1', 'conversation-1', [action]) is True
    assert [record.status for record in records] == ['pending']
    assert accepted == []


def test_task_mutation_still_waits_for_review(monkeypatch):
    """Only creates resolve on capture; editing an existing task keeps its review gate."""

    monkeypatch.setattr(
        conversation_capture.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    records = []
    accepted = []
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'create_candidate',
        lambda uid, proposal, **kwargs: records.append(_record(proposal, len(records) + 1)) or records[-1],
    )
    monkeypatch.setattr(
        conversation_capture.candidate_service,
        'accept_candidate',
        lambda uid, candidate_id, **kwargs: accepted.append(candidate_id),
    )
    action = _action(
        'Send the revised budget',
        capture_kind='direct_request',
        capture_owner='user',
        concrete_deliverable=True,
        candidate_action='update',
        target_task_id='task-budget',
    )

    assert conversation_capture.process_before_legacy('user-1', 'conversation-1', [action]) is True
    assert len(records) == 1
    assert accepted == []


def test_capture_exception_does_not_fall_back_to_a_writer(monkeypatch):
    """INV-TASK-2: a raising capture adapter must not write tasks behind the user."""

    def boom(uid, conversation, *args, **kwargs):
        raise ValueError('capture adapter exploded')

    monkeypatch.setattr(process_conversation.conversation_capture, 'process_conversation_before_legacy', boom)
    monkeypatch.setattr(
        process_conversation.conversation_capture, 'prepare_wake_word_capture_gate', lambda *args, **kwargs: None
    )
    fallbacks = []
    monkeypatch.setattr(process_conversation, 'record_fallback', lambda **event: fallbacks.append(event))
    writes = []

    def write(uid, rows, **kwargs):
        writes.append(rows)
        return [f'task-{index + 1}' for index in range(len(rows))]

    monkeypatch.setattr(process_conversation.action_items_db, 'create_action_items_batch', write)
    monkeypatch.setattr(
        process_conversation.action_items_db,
        'create_action_item',
        lambda *args, **kwargs: pytest.fail('extraction must never write an action item'),
    )

    conversation = _conversation(
        _action('Send the budget', capture_kind='explicit_command', capture_owner='user', concrete_deliverable=True)
    )
    conversation.transcript_segments = []

    process_conversation._save_action_items('user-1', conversation)

    assert writes == []
    assert fallbacks == [
        {
            'component': 'other',
            'from_mode': 'canonical_task_capture',
            'to_mode': 'defer_retry',
            'reason': 'other',
            'outcome': 'degraded',
        }
    ]
