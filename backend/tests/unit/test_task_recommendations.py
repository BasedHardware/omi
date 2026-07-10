import ast
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import AlreadyExists
from pydantic import ValidationError

import database.task_recommendations as recommendation_db
from models.task_intelligence import TaskIntelligenceFeedbackAction, TaskIntelligenceFeedbackReason
from models.task_recommendation import (
    DeterministicFacts,
    EvaluationRequest,
    FeedbackCreate,
    FeedbackRecord,
    FeedbackSubjectKind,
    InterventionCreate,
    InterventionSurface,
    NormalizedContextMatch,
    NormalizedContextSnapshot,
    OpenLoopDescriptor,
    OpenLoopKind,
    OpenLoopSnapshot,
    OpenLoopStatus,
    OutcomeCreate,
    Recommendation,
    RecommendationSubjectKind,
    ShortlistEligibility,
    WhatMattersNowProjection,
)
from models.task_intelligence import TaskIntelligenceOutcomeCode
from utils.task_intelligence import recommendations

NOW = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
RANKING_FIXTURE = Path(__file__).parent / 'fixtures' / 'task_intelligence' / 'ranking_v1.json'


class FakeSnapshot:
    def __init__(self, database, path, payload=None):
        self.database = database
        self.path = path
        self._payload = deepcopy(payload)
        self.exists = payload is not None
        self.id = path[-1]
        self.reference = FakeDocument(database, path)

    def to_dict(self):
        return deepcopy(self._payload)


class FakeDocument:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        if transaction is not None:
            transaction.read()
        return FakeSnapshot(self.database, self.path, self.database.rows.get(self.path))

    def set(self, payload):
        self.database.rows[self.path] = deepcopy(payload)

    def create(self, payload):
        if self.path in self.database.rows:
            raise AlreadyExists('already exists')
        self.set(payload)

    def update(self, patch):
        self.database.rows[self.path].update(deepcopy(patch))

    def delete(self):
        self.database.rows.pop(self.path, None)


class FakeCollection:
    def __init__(self, database, path, filters=(), query_limit=None):
        self.database = database
        self.path = path
        self.filters = filters
        self.query_limit = query_limit

    def document(self, name):
        return FakeDocument(self.database, (*self.path, name))

    def where(self, *args, filter=None):
        if filter is not None:
            condition = (filter.field_path, filter.op_string, filter.value)
        else:
            condition = (args[0], args[1], args[2])
        return FakeCollection(self.database, self.path, (*self.filters, condition), self.query_limit)

    def limit(self, value):
        return FakeCollection(self.database, self.path, self.filters, value)

    def stream(self):
        rows = []
        expected_length = len(self.path) + 1
        for path, payload in self.database.rows.items():
            if path[: len(self.path)] != self.path or len(path) != expected_length:
                continue
            if all(self._matches(payload.get(field), operator, value) for field, operator, value in self.filters):
                rows.append(FakeSnapshot(self.database, path, payload))
        rows.sort(key=lambda snapshot: snapshot.id)
        return rows[: self.query_limit] if self.query_limit is not None else rows

    @staticmethod
    def _matches(actual, operator, expected):
        if operator == '==':
            return actual == expected
        if operator == '>':
            return actual is not None and actual > expected
        raise AssertionError(f'unsupported fake query operator: {operator}')


class FakeBatch:
    def __init__(self):
        self.operations = []

    def set(self, ref, payload):
        self.operations.append((ref, payload))

    def delete(self, ref):
        self.operations.append((ref, None))

    def commit(self):
        for ref, payload in self.operations:
            ref.delete() if payload is None else ref.set(payload)


class FakeFirestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return FakeCollection(self, (name,))

    def batch(self):
        return FakeBatch()

    def transaction(self):
        return FakeTransaction()


class FakeTransaction:
    def __init__(self):
        self.has_written = False

    def read(self):
        if self.has_written:
            raise AssertionError('Firestore transactions require all reads before writes')

    def set(self, ref, payload):
        self.has_written = True
        ref.set(payload)


@pytest.fixture
def fake_firestore(monkeypatch):
    monkeypatch.setattr(
        recommendation_db.firestore,
        'transactional',
        lambda function: lambda transaction: function(transaction),
    )
    return FakeFirestore()


class RecordedJudgment:
    model_version = 'recorded:ranking.v1'

    def __init__(self, selected_ids: list[str]):
        self.selected_ids = selected_ids
        self.calls = 0

    def judge(self, subjects):
        self.calls += 1
        subjects_by_id = {subject.subject_id: subject for subject in subjects}
        return [
            recommendations.JudgmentSelection(
                subject_kind=subjects_by_id[subject_id].kind,
                subject_id=subject_id,
                why_now='Recorded fixture selected this item.',
                recommended_action='Continue',
            )
            for subject_id in self.selected_ids
            if subject_id in subjects_by_id
        ]


class ProjectionHarness:
    def __init__(self, monkeypatch, *, subjects, suppressed=None, context=None, open_loops=None):
        self.projection = None
        self.decisions = []
        self.subjects = subjects
        self.suppressed = set(suppressed or ())
        self.context = context
        self.open_loops = list(open_loops or ())
        monkeypatch.setattr(recommendations.recommendation_db, 'load_canonical_product_state', lambda *_a, **_k: {})
        monkeypatch.setattr(
            recommendations,
            '_build_subjects',
            lambda *_a, **_k: list(self.subjects),
        )
        monkeypatch.setattr(
            recommendations.recommendation_db,
            'get_context_snapshot',
            lambda *_a, **_k: self.context,
        )
        monkeypatch.setattr(
            recommendations.recommendation_db,
            'list_open_loop_snapshots',
            lambda *_a, **_k: list(self.open_loops),
        )
        monkeypatch.setattr(
            recommendations.recommendation_db,
            'list_active_override_dedupe_keys',
            lambda *_a, **_k: set(self.suppressed),
        )
        monkeypatch.setattr(
            recommendations.recommendation_db,
            'get_projection',
            lambda *_a, **_k: (
                self.projection
                if self.projection and (_k.get('include_expired') or self.projection.expires_at > _k['now'])
                else None
            ),
        )
        monkeypatch.setattr(
            recommendations.recommendation_db,
            'get_decisions',
            lambda *_a, **_k: list(self.decisions),
        )

        def save(*_args, projection, decisions, **_kwargs):
            self.projection = projection
            self.decisions = decisions
            return projection

        monkeypatch.setattr(recommendations.recommendation_db, 'save_projection', save)


def fixture_subject(subject_id: str, facts_payload: dict) -> recommendations.EvaluationSubject:
    facts = DeterministicFacts.model_validate(
        {key: value for key, value in facts_payload.items() if key in DeterministicFacts.model_fields}
    )
    open_value = bool(facts_payload.get('open', True))
    unexpired = bool(facts_payload.get('unexpired', True))
    eligibility = recommendations._eligibility(
        is_open=open_value,
        unexpired=unexpired,
        facts=facts,
        recent_material_activity=True,
    )
    return recommendations.EvaluationSubject(
        kind=RecommendationSubjectKind.task,
        subject_id=subject_id,
        feedback_subject_kind=FeedbackSubjectKind.task,
        feedback_subject_id=subject_id,
        headline=f'Fixture {subject_id}',
        label=None,
        evidence_preview='Fixture evidence.',
        evidence_refs=(),
        facts=facts,
        eligibility=eligibility,
        material_token='v1',
    )


@pytest.mark.parametrize('case', json.loads(RANKING_FIXTURE.read_text())['cases'], ids=lambda case: case['id'])
def test_golden_ranking_uses_filters_then_one_recorded_judgment(monkeypatch, case):
    subjects = [fixture_subject(item['subject_id'], item['facts']) for item in case['subjects']]
    harness = ProjectionHarness(monkeypatch, subjects=subjects)
    judgment = RecordedJudgment(case['recorded_judgment'])

    projection = recommendations.evaluate(
        'u1',
        EvaluationRequest(device_id=case['current_context']['device_id']),
        judgment=judgment,
        now=NOW,
    )

    selected = [item.subject_id for item in projection.recommendations]
    assert selected == case['recorded_judgment']
    assert not set(selected).intersection(case['must_not_select'])
    assert judgment.calls == (1 if any(subject.eligibility.passes_recommendation_gates for subject in subjects) else 1)
    assert len(projection.recommendations) <= 3
    assert harness.decisions


def test_shortlist_filters_without_reordering_or_scores():
    eligible = fixture_subject('z-last-looking', {'capture_confidence': 1, 'has_concrete_next_action': True})
    ineligible = fixture_subject('middle', {'capture_confidence': 0.2, 'has_concrete_next_action': True})
    also_eligible = fixture_subject('a-first-looking', {'capture_confidence': 1, 'has_concrete_next_action': True})

    shortlist = recommendations.filter_shortlist([eligible, ineligible, also_eligible], set())

    assert [subject.subject_id for subject in shortlist] == ['z-last-looking', 'a-first-looking']
    assert 'score' not in ShortlistEligibility.model_fields
    assert 'attention_score' not in recommendations.Recommendation.model_fields


def test_judgment_identity_is_compound_across_subject_kinds(monkeypatch):
    task = fixture_subject('shared-id', {'capture_confidence': 1, 'has_concrete_next_action': True})
    artifact = recommendations.EvaluationSubject(
        **{
            **task.__dict__,
            'kind': RecommendationSubjectKind.artifact,
            'feedback_subject_kind': FeedbackSubjectKind.artifact,
        }
    )
    harness = ProjectionHarness(monkeypatch, subjects=[task, artifact])

    class ArtifactOnlyJudgment:
        model_version = 'recorded:compound-id'

        def judge(self, _subjects):
            return [
                recommendations.JudgmentSelection(
                    subject_kind=RecommendationSubjectKind.artifact,
                    subject_id='shared-id',
                    why_now='Artifact needs review.',
                    recommended_action='Review',
                )
            ]

    projection = recommendations.evaluate('u1', EvaluationRequest(), judgment=ArtifactOnlyJudgment(), now=NOW)

    assert [(item.subject_kind, item.subject_id) for item in projection.recommendations] == [
        (RecommendationSubjectKind.artifact, 'shared-id')
    ]
    assert {(decision.subject_kind, decision.subject_id) for decision in harness.decisions} == {
        (RecommendationSubjectKind.task, 'shared-id'),
        (RecommendationSubjectKind.artifact, 'shared-id'),
    }
    assert len(set(harness.decisions[0].shortlist_ids)) == 2
    assert all(len(subject_ref) <= 128 for subject_ref in harness.decisions[0].shortlist_ids)


def test_projection_is_stable_until_material_state_changes(monkeypatch):
    subject = fixture_subject('task-1', {'capture_confidence': 1, 'has_concrete_next_action': True})
    harness = ProjectionHarness(monkeypatch, subjects=[subject])
    judgment = RecordedJudgment(['task-1'])

    first = recommendations.evaluate('u1', EvaluationRequest(device_id='device-1'), judgment=judgment, now=NOW)
    second = recommendations.evaluate(
        'u1', EvaluationRequest(device_id='device-1'), judgment=judgment, now=NOW + timedelta(minutes=5)
    )
    changed = recommendations.evaluate(
        'u1',
        EvaluationRequest(device_id='device-1', material_hint='new-context'),
        judgment=judgment,
        now=NOW + timedelta(minutes=6),
    )
    refreshed = recommendations.evaluate(
        'u1',
        EvaluationRequest(device_id='device-1', material_hint='new-context'),
        judgment=judgment,
        now=NOW + timedelta(minutes=37),
    )

    assert second == first
    assert judgment.calls == 2
    assert changed.output_version != first.output_version
    assert changed.material_version != first.material_version
    assert refreshed.output_version == changed.output_version
    assert refreshed.expires_at > changed.expires_at
    assert len(harness.decisions) == 1


def test_material_version_ignores_snapshot_lease_refreshes():
    subject = fixture_subject('task-1', {'capture_confidence': 1, 'has_concrete_next_action': True})
    first_context = NormalizedContextSnapshot(
        device_id='device-1',
        snapshot_id='context-1',
        matches=[
            NormalizedContextMatch(
                subject_kind=RecommendationSubjectKind.task,
                subject_id='task-1',
                signals=['document'],
            )
        ],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    refreshed_context = first_context.model_copy(
        update={
            'snapshot_id': 'context-2',
            'generated_at': NOW + timedelta(minutes=1),
            'expires_at': NOW + timedelta(minutes=6),
        }
    )

    first = recommendations._material_version(
        [subject], suppressed_dedupe_keys=set(), context=first_context, open_loops=[], material_hint=None
    )
    refreshed = recommendations._material_version(
        [subject], suppressed_dedupe_keys=set(), context=refreshed_context, open_loops=[], material_hint=None
    )

    assert refreshed == first

    open_loop = OpenLoopSnapshot(
        device_id='device-1',
        owner='u1',
        runtime_id='runtime-1',
        workstream_id='workstream-1',
        conversation_id='conversation-1',
        context_packet_version='packet-v1',
        open_loop_snapshot=[
            OpenLoopDescriptor(
                loop_id='loop-1',
                kind=OpenLoopKind.task,
                subject_id='task-1',
                status=OpenLoopStatus.open,
                next_action_code='continue',
                updated_at=NOW,
            )
        ],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    refreshed_open_loop = open_loop.model_copy(
        update={'generated_at': NOW + timedelta(minutes=1), 'expires_at': NOW + timedelta(minutes=6)}
    )
    first_loop_version = recommendations._material_version(
        [subject], suppressed_dedupe_keys=set(), context=None, open_loops=[open_loop], material_hint=None
    )
    refreshed_loop_version = recommendations._material_version(
        [subject],
        suppressed_dedupe_keys=set(),
        context=None,
        open_loops=[refreshed_open_loop],
        material_hint=None,
    )
    assert refreshed_loop_version == first_loop_version


def test_active_exact_suppression_removes_only_matching_material_version(monkeypatch):
    first_subject = fixture_subject('task-1', {'capture_confidence': 1, 'has_concrete_next_action': True})
    suppressed_key = recommendations._stable_id('recommendation', 'task', 'task-1', 'v1')
    harness = ProjectionHarness(monkeypatch, subjects=[first_subject], suppressed={suppressed_key})

    hidden = recommendations.evaluate('u1', EvaluationRequest(), judgment=RecordedJudgment(['task-1']), now=NOW)
    harness.subjects = [recommendations.EvaluationSubject(**{**first_subject.__dict__, 'material_token': 'v2'})]
    visible = recommendations.evaluate(
        'u1',
        EvaluationRequest(material_hint='material-v2'),
        judgment=RecordedJudgment(['task-1']),
        now=NOW + timedelta(minutes=1),
    )

    assert hidden.recommendations == []
    assert [item.subject_id for item in visible.recommendations] == ['task-1']


def test_decision_records_are_bounded_and_do_not_store_private_headline_or_reasoning(monkeypatch):
    private_text = 'Email Sarah about the secret acquisition number 12345'
    subject = fixture_subject('task-private', {'capture_confidence': 1, 'has_concrete_next_action': True})
    subject = recommendations.EvaluationSubject(**{**subject.__dict__, 'headline': private_text})
    harness = ProjectionHarness(monkeypatch, subjects=[subject])

    recommendations.evaluate('u1', EvaluationRequest(), judgment=RecordedJudgment(['task-private']), now=NOW)

    serialized = json.dumps([record.model_dump(mode='json') for record in harness.decisions])
    assert private_text not in serialized
    assert 'raw_prompt' not in serialized.casefold()
    assert 'model_reasoning' not in serialized.casefold()
    assert 'chain-of-thought' not in serialized.casefold()
    assert all(len(record.decision_summary) <= 1024 for record in harness.decisions)


def test_no_production_branch_consumes_debug_summary_or_reason_codes():
    forbidden = {'decision_summary', 'reason_codes'}
    violations = []
    for path in (ROOT / 'routers').rglob('*.py'):
        if path.name == 'task_recommendations.py':
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.IfExp, ast.Match, ast.While)):
                continue
            names = {
                child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute) and child.attr in forbidden
            }
            if names:
                violations.append((path, node.lineno, names))
    assert violations == []


def test_context_contract_rejects_raw_local_payload_and_ttl_over_one_hour(monkeypatch):
    with pytest.raises(ValidationError):
        NormalizedContextSnapshot.model_validate(
            {
                'device_id': 'device-1',
                'snapshot_id': 'context-1',
                'matches': [],
                'generated_at': NOW.isoformat(),
                'expires_at': (NOW + timedelta(minutes=5)).isoformat(),
                'window_text': 'private browser contents',
            }
        )
    snapshot = NormalizedContextSnapshot(
        device_id='device-1',
        snapshot_id='context-1',
        matches=[],
        generated_at=NOW,
        expires_at=NOW + timedelta(hours=2),
    )
    monkeypatch.setattr(recommendations.recommendation_db, 'replace_context_snapshot', lambda *_a, **_k: None)
    with pytest.raises(recommendations.SnapshotValidationError, match='one hour'):
        recommendations.ingest_context_snapshot('u1', snapshot, now=NOW)
    with pytest.raises(recommendations.SnapshotValidationError, match='must precede'):
        recommendations.ingest_context_snapshot(
            'u1',
            snapshot.model_copy(update={'expires_at': NOW}),
            now=NOW,
        )


def test_open_loop_subjects_are_device_scoped_actionable_and_expiring():
    loop = OpenLoopDescriptor(
        loop_id='loop-1',
        kind=OpenLoopKind.approval,
        subject_id='artifact-1',
        status=OpenLoopStatus.awaiting_user,
        next_action_code='approve-draft',
        updated_at=NOW,
    )
    device_one = OpenLoopSnapshot(
        device_id='device-1',
        owner='u1',
        runtime_id='runtime-1',
        workstream_id='workstream-1',
        conversation_id='conversation-1',
        context_packet_version='context-v1',
        open_loop_snapshot=[loop],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    state = {
        'tasks': [],
        'candidates': [],
        'goals': [],
        'workstreams': [
            {
                'workstream_id': 'workstream-1',
                'status': 'open',
                'title': 'Investor thread',
                'objective': 'Finish draft',
                'current_state_summary': 'Waiting',
                'updated_at': NOW,
            }
        ],
        'artifacts': [],
    }

    subjects = recommendations._build_subjects(state, context=None, open_loop_snapshots=[device_one], now=NOW)
    expired = recommendations._build_subjects(
        state, context=None, open_loop_snapshots=[device_one], now=NOW + timedelta(minutes=11)
    )

    loop_subject = next(subject for subject in subjects if subject.kind == RecommendationSubjectKind.agent_open_loop)
    expired_subject = next(subject for subject in expired if subject.kind == RecommendationSubjectKind.agent_open_loop)
    assert loop_subject.eligibility.passes_recommendation_gates
    assert loop_subject.feedback_subject_kind == FeedbackSubjectKind.artifact
    assert loop_subject.feedback_subject_id == 'artifact-1'
    assert loop_subject.evidence_refs[0].device_id == 'device-1'
    assert not expired_subject.eligibility.passes_recommendation_gates

    decision_snapshot = device_one.model_copy(
        update={
            'open_loop_snapshot': [loop.model_copy(update={'kind': OpenLoopKind.decision, 'subject_id': 'decision-1'})]
        }
    )
    decision_subject = next(
        subject
        for subject in recommendations._build_subjects(
            state, context=None, open_loop_snapshots=[decision_snapshot], now=NOW
        )
        if subject.kind == RecommendationSubjectKind.decision
    )
    assert decision_subject.subject_id == 'decision-1'
    assert decision_subject.feedback_subject_kind == FeedbackSubjectKind.decision

    closed_state = deepcopy(state)
    closed_state['workstreams'][0]['status'] = 'completed'
    closed_subjects = recommendations._build_subjects(
        closed_state, context=None, open_loop_snapshots=[device_one], now=NOW
    )
    assert not any(subject.kind == RecommendationSubjectKind.agent_open_loop for subject in closed_subjects)


def test_feedback_later_and_already_handled_semantics(monkeypatch):
    captured = {}

    def create_feedback(_uid, request, *, override_expires_at, now, **_kwargs):
        captured['override_expires_at'] = override_expires_at
        return (
            FeedbackRecord(
                **request.model_dump(mode='python'),
                feedback_id='feedback-1',
                attribution_chain_id='attr-1',
                created_at=now,
                dedupe_key='recommendation-1',
                proposed_completion=request.reason == TaskIntelligenceFeedbackReason.already_handled,
            ),
            True,
        )

    monkeypatch.setattr(recommendations.recommendation_db, 'create_feedback', create_feedback)
    later = FeedbackCreate(
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        intervention_id='intervention-1',
        action=TaskIntelligenceFeedbackAction.later,
    )
    record = recommendations.record_feedback('u1', later, idempotency_key='later-1', now=NOW)
    assert record.subject_id == 'task-1'
    assert captured['override_expires_at'] == NOW + recommendations.DEFAULT_LATER_TTL

    candidate = SimpleNamespace(status=recommendations.CandidateStatus.pending, account_generation=7)
    resolved = []
    monkeypatch.setattr(recommendations.candidates_db, 'get_candidate', lambda *_a, **_k: candidate)
    monkeypatch.setattr(
        recommendations.candidates_db,
        'resolve_candidate_without_mutation',
        lambda *args, **kwargs: resolved.append((args, kwargs)),
    )
    already_handled = FeedbackCreate(
        subject_kind=FeedbackSubjectKind.candidate,
        subject_id='candidate-1',
        intervention_id='intervention-2',
        action=TaskIntelligenceFeedbackAction.dismiss,
        reason=TaskIntelligenceFeedbackReason.already_handled,
    )
    result = recommendations.record_feedback('u1', already_handled, idempotency_key='handled-1', now=NOW)
    assert result.proposed_completion
    assert resolved[0][1]['status'] == recommendations.CandidateStatus.rejected
    assert resolved[0][1]['reason'] == 'already_handled'

    not_mine = FeedbackCreate(
        subject_kind=FeedbackSubjectKind.candidate,
        subject_id='candidate-1',
        intervention_id='intervention-2',
        action=TaskIntelligenceFeedbackAction.dismiss,
        reason=TaskIntelligenceFeedbackReason.not_mine,
    )
    recommendations.record_feedback('u1', not_mine, idempotency_key='not-mine-1', now=NOW)
    assert resolved[1][1]['reason'] == 'not_mine'

    monkeypatch.setattr(
        recommendations.task_control_db,
        'get_task_workflow_control',
        lambda _uid: SimpleNamespace(account_generation=7),
    )
    monkeypatch.setattr(
        recommendations.candidates_db,
        'create_candidate',
        lambda *_a, **_k: SimpleNamespace(candidate_id='completion-candidate-1'),
    )
    links = []
    monkeypatch.setattr(
        recommendations.recommendation_db,
        'link_feedback_completion_candidate',
        lambda *args, **_kwargs: links.append(args),
    )
    task_handled = FeedbackCreate(
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        intervention_id='intervention-3',
        action=TaskIntelligenceFeedbackAction.dismiss,
        reason=TaskIntelligenceFeedbackReason.already_handled,
    )
    task_result = recommendations.record_feedback('u1', task_handled, idempotency_key='task-handled-1', now=NOW)
    assert task_result.proposed_completion_candidate_id == 'completion-candidate-1'
    assert links == [('u1', 'feedback-1', 'completion-candidate-1')]


def test_snapshot_owner_and_replacement_contract(monkeypatch):
    snapshot = OpenLoopSnapshot(
        device_id='device-1',
        owner='another-user',
        runtime_id='runtime-1',
        workstream_id='workstream-1',
        conversation_id='conversation-1',
        context_packet_version='v1',
        open_loop_snapshot=[],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    with pytest.raises(recommendations.SnapshotValidationError, match='owner'):
        recommendations.ingest_open_loop_snapshot('u1', snapshot, now=NOW)

    valid = snapshot.model_copy(update={'owner': 'u1'})
    monkeypatch.setattr(recommendations.workstreams_db, 'get_workstream', lambda *_a, **_k: None)
    with pytest.raises(recommendations.SnapshotValidationError, match='canonical'):
        recommendations.ingest_open_loop_snapshot('u1', valid, now=NOW)

    monkeypatch.setattr(
        recommendations.workstreams_db,
        'get_workstream',
        lambda *_a, **_k: SimpleNamespace(status='paused'),
    )
    with pytest.raises(recommendations.SnapshotValidationError, match='canonical'):
        recommendations.ingest_open_loop_snapshot('u1', valid, now=NOW)

    calls = []
    monkeypatch.setattr(
        recommendations.workstreams_db,
        'get_workstream',
        lambda *_a, **_k: SimpleNamespace(status='open'),
    )
    monkeypatch.setattr(
        recommendations.recommendation_db,
        'replace_open_loop_snapshot',
        lambda uid, item, **_kwargs: calls.append((uid, item.runtime_id, item.workstream_id)),
    )
    recommendations.ingest_open_loop_snapshot('u1', valid, now=NOW)
    recommendations.ingest_open_loop_snapshot('u1', valid.model_copy(update={'context_packet_version': 'v2'}), now=NOW)
    assert calls == [
        ('u1', 'runtime-1', 'workstream-1'),
        ('u1', 'runtime-1', 'workstream-1'),
    ]


def test_feedback_validation_keeps_three_choice_reason_taxonomy_small():
    assert {reason.value for reason in TaskIntelligenceFeedbackReason} == {
        'already_handled',
        'not_mine',
        'not_useful',
    }
    with pytest.raises(ValidationError):
        FeedbackCreate(
            subject_kind=FeedbackSubjectKind.task,
            subject_id='task-1',
            action=TaskIntelligenceFeedbackAction.dismiss,
            reason=TaskIntelligenceFeedbackReason.not_mine,
        )


def test_database_module_has_attribution_join_and_no_raw_content_fields():
    assert {'attribution_chain_id', 'subject_id', 'outcome_code'} <= set(recommendation_db.OutcomeCreate.model_fields)
    assert not {'task_text', 'prompt', 'reasoning', 'screenshot', 'window_text'}.intersection(
        FeedbackRecord.model_fields
    )


def test_firestore_feedback_replay_heals_override_and_outcomes_require_known_chain(fake_firestore):
    fake_db = fake_firestore
    intervention, created = recommendation_db.create_intervention(
        'u1',
        InterventionCreate(
            surface=InterventionSurface.suggested,
            subject_kind=FeedbackSubjectKind.task,
            subject_id='task-1',
            dedupe_key='task-1:v1',
            expires_at=NOW + timedelta(hours=1),
        ),
        idempotency_key='shown-1',
        now=NOW,
        firestore_client=fake_db,
    )
    assert created
    feedback_request = FeedbackCreate(
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        intervention_id=intervention.intervention_id,
        action=TaskIntelligenceFeedbackAction.later,
    )
    first, first_created = recommendation_db.create_feedback(
        'u1',
        feedback_request,
        idempotency_key='feedback-click-1',
        now=NOW,
        override_expires_at=NOW + timedelta(days=1),
        firestore_client=fake_db,
    )
    override_paths = [path for path in fake_db.rows if path[-2] == recommendation_db.ATTENTION_OVERRIDES_COLLECTION]
    assert first_created and len(override_paths) == 1
    del fake_db.rows[override_paths[0]]

    replay, replay_created = recommendation_db.create_feedback(
        'u1',
        feedback_request,
        idempotency_key='feedback-click-1',
        now=NOW + timedelta(minutes=1),
        override_expires_at=NOW + timedelta(days=1),
        firestore_client=fake_db,
    )
    assert replay.feedback_id == first.feedback_id
    assert not replay_created
    assert len([path for path in fake_db.rows if path[-2] == recommendation_db.ATTENTION_OVERRIDES_COLLECTION]) == 1

    outcome_request = OutcomeCreate(
        attribution_chain_id=first.attribution_chain_id,
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        outcome_code=TaskIntelligenceOutcomeCode.task_completed,
    )
    outcome, outcome_created = recommendation_db.create_outcome(
        'u1',
        outcome_request,
        idempotency_key='outcome-1',
        now=NOW,
        firestore_client=fake_db,
    )
    outcome_replay, outcome_replay_created = recommendation_db.create_outcome(
        'u1',
        outcome_request,
        idempotency_key='outcome-1',
        now=NOW + timedelta(minutes=1),
        firestore_client=fake_db,
    )
    assert outcome_created and not outcome_replay_created
    assert outcome_replay.outcome_id == outcome.outcome_id
    with pytest.raises(recommendation_db.AttributionChainNotFoundError):
        recommendation_db.create_outcome(
            'u1',
            outcome_request.model_copy(update={'attribution_chain_id': 'attr-unknown'}),
            idempotency_key='outcome-unknown',
            now=NOW,
            firestore_client=fake_db,
        )
    with pytest.raises(recommendation_db.IdempotencyConflictError, match='does not match'):
        recommendation_db.create_outcome(
            'u1',
            outcome_request.model_copy(update={'subject_id': 'another-task'}),
            idempotency_key='outcome-wrong-subject',
            now=NOW,
            firestore_client=fake_db,
        )


def test_firestore_snapshot_replacement_expiry_and_cross_device_isolation(fake_firestore):
    fake_db = fake_firestore
    first = NormalizedContextSnapshot(
        device_id='device-1',
        snapshot_id='context-v1',
        matches=[
            NormalizedContextMatch(
                subject_kind=RecommendationSubjectKind.task,
                subject_id='task-1',
                signals=['document'],
            )
        ],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    second = first.model_copy(
        update={
            'snapshot_id': 'context-v2',
            'generated_at': NOW + timedelta(minutes=1),
            'expires_at': NOW + timedelta(minutes=6),
        }
    )
    other_device = first.model_copy(update={'device_id': 'device-2', 'snapshot_id': 'context-other'})

    receipt_one = recommendation_db.replace_context_snapshot('u1', first, firestore_client=fake_db)
    receipt_two = recommendation_db.replace_context_snapshot('u1', second, firestore_client=fake_db)
    recommendation_db.replace_context_snapshot('u1', other_device, firestore_client=fake_db)

    assert not receipt_one.replaced and receipt_two.replaced
    with pytest.raises(recommendation_db.StaleSnapshotError):
        recommendation_db.replace_context_snapshot('u1', first, firestore_client=fake_db)
    assert (
        recommendation_db.get_context_snapshot('u1', 'device-1', now=NOW, firestore_client=fake_db).snapshot_id
        == 'context-v2'
    )
    assert (
        recommendation_db.get_context_snapshot('u1', 'device-2', now=NOW, firestore_client=fake_db).snapshot_id
        == 'context-other'
    )
    assert (
        recommendation_db.get_context_snapshot(
            'u1', 'device-1', now=NOW + timedelta(minutes=7), firestore_client=fake_db
        )
        is None
    )


def test_firestore_projection_persists_stable_intervention_and_debug_trace(fake_firestore):
    fake_db = fake_firestore
    subject = fixture_subject('task-1', {'capture_confidence': 1, 'has_concrete_next_action': True})
    projection = WhatMattersNowProjection(
        evaluation_id='evaluation-1',
        output_version='output-1',
        material_version='material-1',
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        recommendations=[
            Recommendation(
                intervention_id='intervention-1',
                output_version='output-1',
                subject_kind=RecommendationSubjectKind.task,
                subject_id='task-1',
                feedback_subject_kind=FeedbackSubjectKind.task,
                feedback_subject_id='task-1',
                headline='Do the thing',
                why_now='It is ready.',
                recommended_action='Continue',
                evidence_preview='Due soon.',
                dedupe_key='task-1:v1',
                expires_at=NOW + timedelta(minutes=30),
            )
        ],
    )
    decision = recommendations.DecisionRecord(
        evaluation_id='evaluation-1',
        subject_kind=RecommendationSubjectKind.task,
        subject_id='task-1',
        shortlist_ids=['task-1'],
        facts_snapshot=subject.facts,
        eligibility=subject.eligibility,
        prompt_version='prompt-v1',
        policy_version='policy-v1',
        fact_definition_version='facts-v1',
        model_version='recorded-v1',
        decision_summary='Selected.',
        reason_codes=['selected'],
        evidence_refs=[],
        final_output_ref='output-1',
        evaluated_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    recommendation_db.save_projection(
        'u1',
        device_scope='device-1',
        projection=projection,
        decisions=[decision],
        firestore_client=fake_db,
    )
    cached = recommendation_db.get_projection('u1', device_scope='device-1', now=NOW, firestore_client=fake_db)
    intervention = recommendation_db.get_intervention('u1', 'intervention-1', firestore_client=fake_db)
    assert cached == projection
    assert intervention['subject_id'] == 'task-1'
    assert intervention['attribution_chain_id'].startswith('attr_')
    first_created_at = recommendation_db.get_intervention('u1', 'intervention-1', firestore_client=fake_db)[
        'created_at'
    ]
    refreshed = projection.model_copy(
        update={'generated_at': NOW + timedelta(minutes=31), 'expires_at': NOW + timedelta(minutes=61)}
    )
    recommendation_db.save_projection(
        'u1',
        device_scope='device-1',
        projection=refreshed,
        decisions=[decision.model_copy(update={'expires_at': refreshed.expires_at})],
        firestore_client=fake_db,
    )
    assert (
        recommendation_db.get_intervention('u1', 'intervention-1', firestore_client=fake_db)['created_at']
        == first_created_at
    )
    assert (
        recommendation_db.get_evaluation_projection(
            'u1', 'evaluation-1', device_scope='device-1', now=NOW, firestore_client=fake_db
        )
        == refreshed
    )
    second_projection = projection.model_copy(
        update={
            'evaluation_id': 'evaluation-2',
            'output_version': 'output-2',
            'material_version': 'material-2',
            'generated_at': NOW + timedelta(minutes=32),
            'expires_at': NOW + timedelta(minutes=62),
            'recommendations': [],
        }
    )
    recommendation_db.save_projection(
        'u1',
        device_scope='device-1',
        projection=second_projection,
        decisions=[],
        firestore_client=fake_db,
    )
    assert recommendation_db.get_decisions('u1', 'evaluation-1', device_scope='device-1', firestore_client=fake_db) == [
        decision.model_copy(update={'expires_at': refreshed.expires_at})
    ]
    decision_paths = [path for path in fake_db.rows if path[-2] == recommendation_db.DECISIONS_COLLECTION]
    assert len(decision_paths) == 2


def test_firestore_same_material_publication_returns_one_winner(fake_firestore):
    first = WhatMattersNowProjection(
        evaluation_id='evaluation-same',
        output_version='output-first',
        material_version='material-same',
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        recommendations=[],
    )
    competing = first.model_copy(update={'output_version': 'output-competing'})

    first_result = recommendation_db.save_projection(
        'u1', device_scope='device-1', projection=first, decisions=[], firestore_client=fake_firestore
    )
    competing_result = recommendation_db.save_projection(
        'u1', device_scope='device-1', projection=competing, decisions=[], firestore_client=fake_firestore
    )

    assert first_result == first
    assert competing_result == first
    assert (
        recommendation_db.get_projection('u1', device_scope='device-1', now=NOW, firestore_client=fake_firestore)
        == first
    )
