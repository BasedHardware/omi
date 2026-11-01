"""Unit tests for naive and ISO-8601 datetime coercion in task_recommendations."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sys
import types

import pytest

if 'redis' in sys.modules and 'redis.exceptions' not in sys.modules:
    exc_mod = getattr(sys.modules['redis'], 'exceptions', types.SimpleNamespace())
    if not hasattr(exc_mod, 'WatchError'):
        exc_mod.WatchError = Exception
    sys.modules['redis.exceptions'] = exc_mod

import database.task_recommendations as recommendation_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.task_intelligence import (
    TaskIntelligenceFeedbackAction,
    TaskIntelligenceFeedbackReason,
    TaskWorkflowControl,
    TaskWorkflowMode,
)
from models.task_recommendation import (
    DeterministicFacts,
    EvaluationRequest,
    FeedbackCreate,
    FeedbackSubjectKind,
    InterventionSurface,
    NormalizedContextSnapshot,
    OpenLoopDescriptor,
    OpenLoopKind,
    OpenLoopSnapshot,
    OpenLoopStatus,
    Recommendation,
    RecommendationSubjectKind,
    ShortlistEligibility,
    WhatMattersNowProjection,
)
from utils.task_intelligence import recommendations

NOW = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)


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

    @property
    def id(self):
        return self.path[-1]

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        if transaction is not None:
            transaction.read()
        return FakeSnapshot(self.database, self.path, self.database.rows.get(self.path))

    def set(self, payload):
        self.database.rows[self.path] = deepcopy(payload)

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
        if operator == '<=':
            return actual is not None and actual <= expected
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


class FakeTransaction:
    def __init__(self):
        self.has_written = False

    def read(self):
        if self.has_written:
            raise AssertionError('Firestore transactions require all reads before writes')

    def set(self, ref, payload):
        self.has_written = True
        ref.set(payload)

    def delete(self, ref):
        self.has_written = True
        ref.delete()


class FakeFirestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return FakeCollection(self, (name,))

    def batch(self):
        return FakeBatch()

    def transaction(self):
        return FakeTransaction()


@pytest.fixture
def fake_firestore(monkeypatch):
    monkeypatch.setattr(
        recommendation_db.firestore,
        'transactional',
        lambda function: lambda transaction: function(transaction),
    )
    fake = FakeFirestore()
    fake.rows[
        (
            'users',
            'u1',
            recommendation_db.TASK_INTELLIGENCE_CONTROL_COLLECTION,
            recommendation_db.TASK_INTELLIGENCE_CONTROL_DOCUMENT,
        )
    ] = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0).model_dump(mode='python')
    return fake


def test_save_projection_prunes_decision_history_with_mixed_naive_aware_and_iso_timestamps(fake_firestore):
    decisions_col = ('users', 'u1', recommendation_db.DECISIONS_COLLECTION)
    fake_firestore.rows[(*decisions_col, 'dec_naive_expired')] = {
        'device_scope': 'macbook',
        'account_generation': 0,
        'evaluation_id': 'eval_old_naive',
        'evaluated_at': datetime(2026, 7, 9, 10, 0, 0),  # naive
        'expires_at': datetime(2026, 7, 9, 11, 0, 0),  # naive, <= projection.generated_at
    }
    fake_firestore.rows[(*decisions_col, 'dec_iso_active')] = {
        'device_scope': 'macbook',
        'account_generation': 0,
        'evaluation_id': 'eval_iso_active',
        'evaluated_at': '2026-07-09T11:30:00Z',
        'expires_at': '2026-07-09T15:00:00Z',
    }
    fake_firestore.rows[(*decisions_col, 'dec_aware_active')] = {
        'device_scope': 'macbook',
        'account_generation': 0,
        'evaluation_id': 'eval_aware_active',
        'evaluated_at': NOW - timedelta(minutes=15),
        'expires_at': NOW + timedelta(hours=2),
    }

    projection = WhatMattersNowProjection(
        evaluation_id='eval_current',
        output_version='out_1',
        generated_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        material_version='mat_1',
        recommendations=[],
    )

    published = recommendation_db.save_projection(
        'u1',
        projection=projection,
        decisions=[],
        device_scope='macbook',
        account_generation=0,
        firestore_client=fake_firestore,
    )
    assert published.evaluation_id == 'eval_current'
    assert (*decisions_col, 'dec_naive_expired') not in fake_firestore.rows
    assert (*decisions_col, 'dec_iso_active') in fake_firestore.rows
    assert (*decisions_col, 'dec_aware_active') in fake_firestore.rows


def test_projection_and_snapshot_readers_accept_naive_now_and_iso_override_expiry(fake_firestore):
    projection = WhatMattersNowProjection(
        evaluation_id='eval_1',
        output_version='out_1',
        generated_at=NOW,
        expires_at=NOW + timedelta(hours=2),
        material_version='mat_1',
        recommendations=[
            Recommendation(
                intervention_id='int_1',
                output_version='out_1',
                dedupe_key='dedupe_1',
                subject_kind=RecommendationSubjectKind.task,
                subject_id='task_1',
                feedback_subject_kind=FeedbackSubjectKind.task,
                feedback_subject_id='task_1',
                destination_task_id='task_1',
                headline='Ship fix',
                why_now='Due today.',
                recommended_action='Start now',
                evidence_preview='Due today.',
                evidence_refs=[EvidenceRef(kind=EvidenceKind.external, id='task_1', scope=EvidenceScope.canonical)],
                expires_at=NOW + timedelta(hours=2),
            )
        ],
    )
    recommendation_db.save_projection(
        'u1',
        projection=projection,
        decisions=[],
        device_scope='macbook',
        account_generation=0,
        firestore_client=fake_firestore,
    )

    naive_now = NOW.replace(tzinfo=None)
    assert (
        recommendation_db.get_projection(
            'u1', device_scope='macbook', now=naive_now, account_generation=0, firestore_client=fake_firestore
        )
        is not None
    )
    assert (
        recommendation_db.get_evaluation_projection(
            'u1',
            'eval_1',
            device_scope='macbook',
            now=naive_now,
            account_generation=0,
            firestore_client=fake_firestore,
        )
        is not None
    )

    request = FeedbackCreate(
        action=TaskIntelligenceFeedbackAction.dismiss,
        reason=TaskIntelligenceFeedbackReason.already_handled,
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task_1',
        intervention_id='int_1',
    )
    override_expires_at = NOW + timedelta(hours=6)
    record, created = recommendation_db.create_feedback(
        'u1',
        request,
        idempotency_key='idem_1',
        now=NOW,
        override_expires_at=override_expires_at,
        account_generation=0,
        firestore_client=fake_firestore,
    )
    assert created is True

    # Simulate legacy ISO-8601 _override_expires_at on stored feedback doc and missing override doc
    feedback_path = ('users', 'u1', recommendation_db.FEEDBACK_COLLECTION, record.feedback_id)
    fake_firestore.rows[feedback_path]['_override_expires_at'] = override_expires_at.isoformat().replace('+00:00', 'Z')
    override_id = recommendation_db._stable_id('override', 'u1', 0, 'dedupe_1')
    override_path = ('users', 'u1', recommendation_db.ATTENTION_OVERRIDES_COLLECTION, override_id)
    fake_firestore.rows.pop(override_path, None)

    replayed, created_again = recommendation_db.create_feedback(
        'u1',
        request,
        idempotency_key='idem_1',
        now=NOW,
        override_expires_at=override_expires_at,
        account_generation=0,
        firestore_client=fake_firestore,
    )
    assert created_again is False
    assert replayed.feedback_id == record.feedback_id
    assert override_path in fake_firestore.rows
    assert fake_firestore.rows[override_path]['expires_at'] == override_expires_at


def test_recommendations_helpers_accept_iso_strings_and_naive_now():
    naive_now = datetime(2026, 7, 9, 12, 0, 0)
    assert recommendations._days_to_due('2026-07-11T12:00:00Z', naive_now) == 2.0
    assert recommendations._recent('2026-07-08T12:00:00+00:00', naive_now) is True
    assert recommendations._iso_token('2026-07-09T12:00:00Z') == '2026-07-09T12:00:00+00:00'

    state = {
        'goals': [{'goal_id': 'g1', 'title': 'Launch', 'status': 'focused', 'is_active': True}],
        'workstreams': [
            {
                'workstream_id': 'w1',
                'goal_id': 'g1',
                'title': 'Core',
                'status': 'open',
                'updated_at': '2026-07-09T10:00:00Z',
                'next_review_at': '2026-07-10T12:00:00Z',
            }
        ],
        'workstream_events': [],
        'tasks': [
            {
                'task_id': 't1',
                'goal_id': 'g1',
                'workstream_id': 'w1',
                'description': 'Prepare release notes',
                'status': 'active',
                'source': 'manual',
                'owner': 'user',
                'created_at': '2026-07-09T08:00:00Z',
                'updated_at': '2026-07-09T09:00:00Z',
                'due_at': '2026-07-10T12:00:00Z',
            }
        ],
        'candidates': [],
        'artifacts': [],
    }
    loop_snapshot = OpenLoopSnapshot(
        device_id='macbook',
        owner='u1',
        runtime_id='rt1',
        workstream_id='w1',
        conversation_id='conv1',
        context_packet_version='v1',
        generated_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
        open_loop_snapshot=[
            OpenLoopDescriptor(
                loop_id='loop1',
                kind=OpenLoopKind.decision,
                subject_id='dec1',
                status=OpenLoopStatus.awaiting_user,
                next_action_code='approve_plan',
                updated_at=NOW - timedelta(minutes=5),
            )
        ],
    )
    subjects = recommendations._build_subjects(
        state,
        context=None,
        open_loop_snapshots=[loop_snapshot],
        now=naive_now,
    )
    by_id = {s.subject_id: s for s in subjects}
    assert by_id['t1'].facts.days_to_due == 1.0
    assert by_id['t1'].eligibility.recent_material_activity is True
    assert by_id['w1'].facts.days_to_due == 1.0
    assert by_id['dec1'].eligibility.unexpired is True
