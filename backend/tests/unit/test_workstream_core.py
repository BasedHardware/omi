from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock

import pytest

import database.action_items as action_items_db
import database.goals as goals_db
import database.recurrence_inbox as recurrence_inbox_db
import database.workstreams as workstreams_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.candidate import CandidateCreate, CandidateRecord, CandidateStatus
from models.goal import (
    GoalCreate,
    GoalMetric,
    GoalProgressEventCreate,
    GoalRelationshipDisposition,
    GoalStatus,
)
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.workstream_association import RecurrenceOutcomeKind
from models.workstream import (
    ArtifactDescriptorCreate,
    ArtifactStatusTransitionRequest,
    ContinuationCheckpointUpsert,
    GoalOriginWorkIntent,
    TaskGoalLinkImportRequest,
    TaskOriginWorkIntent,
    WorkstreamEventCreate,
    WorkstreamStatus,
    WorkstreamUpdate,
)


class FakeSnapshot:
    def __init__(self, database, path, data=None):
        self.database = database
        self.path = path
        self.id = path[-1]
        self._data = deepcopy(data)
        self.exists = data is not None
        self.reference = FakeRef(database, path)

    def to_dict(self):
        return deepcopy(self._data)


class FakeRef:
    def __init__(self, database, path):
        self.database = database
        self.path = path
        self.id = path[-1]

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        return FakeSnapshot(self.database, self.path, self.database.rows.get(self.path))

    def create(self, payload):
        if self.path in self.database.rows:
            raise RuntimeError('already exists')
        self.database.rows[self.path] = deepcopy(payload)

    def set(self, payload, merge=False):
        if merge and self.path in self.database.rows:
            self.database.rows[self.path].update(deepcopy(payload))
        else:
            self.database.rows[self.path] = deepcopy(payload)

    def update(self, patch):
        if self.path not in self.database.rows:
            raise RuntimeError('missing row')
        self.database.rows[self.path].update(deepcopy(patch))

    def delete(self):
        self.database.rows.pop(self.path, None)


class FakeQuery:
    def __init__(self, database, path, filters=None, order=None, limit_value=None):
        self.database = database
        self.path = path
        self.filters = list(filters or [])
        self.order = order
        self.limit_value = limit_value

    def where(self, filter):
        field, operator, value = filter.field_path, filter.op_string, filter.value
        return FakeQuery(
            self.database, self.path, [*self.filters, (field, operator, value)], self.order, self.limit_value
        )

    def order_by(self, field, direction=None):
        return FakeQuery(self.database, self.path, self.filters, (field, direction), self.limit_value)

    def limit(self, value):
        return FakeQuery(self.database, self.path, self.filters, self.order, value)

    def stream(self, transaction=None):
        rows = []
        expected_length = len(self.path) + 1
        for path, payload in self.database.rows.items():
            if len(path) != expected_length or path[:-1] != self.path:
                continue
            if all(self._matches(payload.get(field), operator, value) for field, operator, value in self.filters):
                rows.append(FakeSnapshot(self.database, path, payload))
        if self.order is not None:
            field, direction = self.order
            reverse = str(direction).endswith('DESCENDING')
            rows.sort(key=lambda snapshot: snapshot.to_dict().get(field, 0), reverse=reverse)
        return iter(rows[: self.limit_value] if self.limit_value is not None else rows)

    @staticmethod
    def _matches(actual, operator, expected):
        if operator == '==':
            return actual == expected
        if operator == '>':
            return actual is not None and actual > expected
        raise AssertionError(f'unsupported fake filter: {operator}')


class FakeCollection(FakeQuery):
    def document(self, name=None):
        if name is None:
            name = f'auto-{len(self.database.rows) + 1}'
        return FakeRef(self.database, (*self.path, name))


class FakeTransaction:
    def __init__(self, database):
        self.database = database
        self.lock = database.lock

    def create(self, ref, payload):
        ref.create(payload)

    def set(self, ref, payload):
        ref.set(payload)

    def update(self, ref, patch):
        ref.update(patch)


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.lock = RLock()

    def collection(self, name):
        return FakeCollection(self, (name,))

    def transaction(self):
        return FakeTransaction(self)


@pytest.fixture
def fake_db(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

    set_canonical_cohort(monkeypatch, 'u1')
    database = FakeDB()

    def transactional(function):
        def run(transaction):
            with transaction.lock:
                return function(transaction)

        return run

    monkeypatch.setattr(goals_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(workstreams_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(recurrence_inbox_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(action_items_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(action_items_db, 'db', database)
    return database


def create_goal(fake_db, goal_id, *, status='background', focus_rank=None):
    result = goals_db.create_goal(
        'u1',
        {
            'id': goal_id,
            'title': goal_id,
            'desired_outcome': f'Outcome {goal_id}',
            'status': status,
            'focus_rank': focus_rank,
        },
        firestore_client=fake_db,
    )
    fake_db.rows[('users', 'u1', 'goals', goal_id)]['account_generation'] = 3
    return result


def seed_control(fake_db, generation=3, mode='read'):
    fake_db.rows[('users', 'u1', 'task_intelligence_control', 'state')] = {
        'workflow_mode': mode,
        'account_generation': generation,
    }


def test_goal_contract_supports_qualitative_outcomes_and_never_evicts_on_create(fake_db):
    qualitative = GoalCreate(title='Launch desktop', why_it_matters='Trust', success_criteria=['Shipped'])
    assert qualitative.metric is None
    for index in range(7):
        create_goal(fake_db, f'g{index}')

    goals = goals_db.get_all_goals('u1', include_inactive=True, firestore_client=fake_db)
    assert len(goals) == 7
    assert {goal['status'] for goal in goals} == {'background'}
    assert all(goal['is_active'] for goal in goals)


def test_canonical_goal_create_is_generation_scoped_and_idempotent(fake_db):
    seed_control(fake_db, generation=3)
    request = {
        'title': 'Investor pipeline',
        'desired_outcome': 'Build a repeatable investor pipeline',
        'why_it_matters': 'Fund the next stage',
        'success_criteria': ['Ten qualified conversations'],
        'status': 'background',
        'source': 'user',
    }

    first = goals_db.create_goal_idempotent(
        'u1', request, idempotency_key='create-occurrence', account_generation=3, firestore_client=fake_db
    )
    replay = goals_db.create_goal_idempotent(
        'u1', request, idempotency_key='create-occurrence', account_generation=3, firestore_client=fake_db
    )

    assert replay == first
    assert len(goals_db.get_all_goals('u1', include_inactive=True, firestore_client=fake_db)) == 1
    with pytest.raises(goals_db.GoalConflictError, match='different content'):
        goals_db.create_goal_idempotent(
            'u1',
            {**request, 'title': 'Different goal'},
            idempotency_key='create-occurrence',
            account_generation=3,
            firestore_client=fake_db,
        )
    with pytest.raises(goals_db.GoalConflictError, match='generation mismatch'):
        goals_db.create_goal_idempotent(
            'u1', request, idempotency_key='another-occurrence', account_generation=4, firestore_client=fake_db
        )


def test_focus_cap_requires_explicit_replacement_and_keeps_all_goals(fake_db):
    seed_control(fake_db)
    for index in range(6):
        create_goal(fake_db, f'g{index}')
    for index in range(5):
        goals_db.focus_goal(
            'u1',
            f'g{index}',
            idempotency_key=f'focus-{index}',
            account_generation=3,
            focus_rank=index,
            firestore_client=fake_db,
        )

    with pytest.raises(goals_db.GoalConflictError):
        goals_db.focus_goal(
            'u1', 'g5', idempotency_key='focus-overflow', account_generation=3, firestore_client=fake_db
        )

    focused = goals_db.focus_goal(
        'u1',
        'g5',
        idempotency_key='focus-replace',
        account_generation=3,
        replacement_goal_id='g0',
        focus_rank=0,
        firestore_client=fake_db,
    )
    all_goals = goals_db.get_all_goals('u1', include_inactive=True, firestore_client=fake_db)
    assert focused['status'] == 'focused'
    assert len(all_goals) == 6
    assert len([goal for goal in all_goals if goal['status'] == 'focused']) == 5
    assert goals_db.get_goal_by_id('u1', 'g0', firestore_client=fake_db)['status'] == 'background'


def test_canonical_goal_mutations_are_generation_fenced(fake_db):
    create_goal(fake_db, 'g1')
    seed_control(fake_db, generation=4, mode='read')
    with pytest.raises(goals_db.GoalConflictError):
        goals_db.focus_goal('u1', 'g1', idempotency_key='focus-g1', account_generation=3, firestore_client=fake_db)
    first = goals_db.focus_goal('u1', 'g1', idempotency_key='focus-g1', account_generation=4, firestore_client=fake_db)
    replay = goals_db.focus_goal('u1', 'g1', idempotency_key='focus-g1', account_generation=4, firestore_client=fake_db)
    assert replay == first


def test_goal_lifecycle_disposition_detaches_without_deleting_dependents(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    fake_db.rows[('users', 'u1', 'action_items', 't1')] = {'id': 't1', 'goal_id': 'g1', 'completed': False}
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')] = {
        'workstream_id': 'w1',
        'goal_id': 'g1',
        'title': 'Thread',
        'objective': 'Advance',
        'status': 'open',
        'current_state_summary': '',
        'latest_event_sequence': 0,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    fake_db.rows[('users', 'u1', 'workstreams', 'w1', 'artifact_refs', 'a1')] = {'artifact_id': 'a1'}

    goals_db.transition_goal_lifecycle(
        'u1',
        'g1',
        status=GoalStatus.abandoned,
        relationship_disposition=GoalRelationshipDisposition.detach,
        idempotency_key='detach-g1',
        account_generation=3,
        firestore_client=fake_db,
    )

    assert fake_db.rows[('users', 'u1', 'action_items', 't1')]['goal_id'] is None
    assert fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] is None
    assert ('users', 'u1', 'action_items', 't1') in fake_db.rows
    assert ('users', 'u1', 'workstreams', 'w1', 'artifact_refs', 'a1') in fake_db.rows


def test_goal_lifecycle_retain_keeps_historical_relationships(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    seed_task(fake_db, 't1', goal_id='g1')

    goals_db.transition_goal_lifecycle(
        'u1',
        'g1',
        status=GoalStatus.achieved,
        relationship_disposition=GoalRelationshipDisposition.retain,
        idempotency_key='retain-g1',
        account_generation=3,
        firestore_client=fake_db,
    )

    assert fake_db.rows[('users', 'u1', 'action_items', 't1')]['goal_id'] == 'g1'
    assert goals_db.get_goal_by_id('u1', 'g1', firestore_client=fake_db)['status'] == 'achieved'


def test_task_relationship_validation_and_goal_detach_share_the_write_transaction(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    seed_workstream(fake_db, 'w1')
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] = 'g1'

    def create_linked_task():
        try:
            return action_items_db.create_action_item(
                'u1',
                {
                    'description': 'Draft follow-up',
                    'goal_id': 'g1',
                    'workstream_id': 'w1',
                },
                document_id='race-task',
            )
        except action_items_db.TaskRelationshipConflictError:
            return None

    def detach_goal():
        return goals_db.transition_goal_lifecycle(
            'u1',
            'g1',
            status=GoalStatus.abandoned,
            relationship_disposition=GoalRelationshipDisposition.detach,
            idempotency_key='race-detach',
            account_generation=3,
            firestore_client=fake_db,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        create_result, _ = list(executor.map(lambda function: function(), (create_linked_task, detach_goal)))

    assert fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] is None
    if create_result is not None:
        task = fake_db.rows[('users', 'u1', 'action_items', 'race-task')]
        assert task['goal_id'] is None and task['workstream_id'] == 'w1'


def test_goal_progress_journal_is_append_only_idempotent_and_metric_optional(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    evidence = EvidenceRef(kind='conversation', id='c1', scope='canonical')
    first = goals_db.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(kind='evidence', summary='Customer confirmed launch', evidence_refs=[evidence]),
        idempotency_key='event-1',
        account_generation=3,
        firestore_client=fake_db,
    )
    replay = goals_db.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(kind='evidence', summary='Customer confirmed launch', evidence_refs=[evidence]),
        idempotency_key='event-1',
        account_generation=3,
        firestore_client=fake_db,
    )
    with pytest.raises(goals_db.GoalConflictError):
        goals_db.append_goal_progress_event(
            'u1',
            'g1',
            GoalProgressEventCreate(kind='milestone', summary='A different event'),
            idempotency_key='event-1',
            account_generation=3,
            firestore_client=fake_db,
        )
    second = goals_db.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(
            kind='metric_update',
            summary='Reached 4 pilots',
            metric=GoalMetric(type='numeric', current=4, target=10, unit='pilots'),
        ),
        idempotency_key='event-2',
        account_generation=3,
        firestore_client=fake_db,
    )

    assert first.event_id == replay.event_id
    assert (first.sequence, second.sequence) == (1, 2)
    assert goals_db.get_goal_by_id('u1', 'g1', firestore_client=fake_db)['metric']['current'] == 4


def seed_task(fake_db, task_id='t1', goal_id=None):
    fake_db.rows[('users', 'u1', 'action_items', task_id)] = {
        'id': task_id,
        'task_id': task_id,
        'description': 'Send Sarah the budget',
        'completed': False,
        'status': 'active',
        'goal_id': goal_id,
        'workstream_id': None,
        'account_generation': 3,
    }


def test_explicit_task_intent_reuses_one_workstream_across_idempotency_keys(fake_db):
    seed_control(fake_db)
    seed_task(fake_db)
    request = TaskOriginWorkIntent(task_id='t1')

    first = workstreams_db.resolve_work_intent(
        'u1', request, idempotency_key='first-click', account_generation=3, firestore_client=fake_db
    )
    replay = workstreams_db.resolve_work_intent(
        'u1', request, idempotency_key='first-click', account_generation=3, firestore_client=fake_db
    )
    second_key = workstreams_db.resolve_work_intent(
        'u1', request, idempotency_key='second-click', account_generation=3, firestore_client=fake_db
    )

    assert first.workstream_id == replay.workstream_id == second_key.workstream_id
    assert first.task_id == replay.task_id == second_key.task_id == 't1'
    assert replay == first
    assert first.newly_created is True
    assert second_key.newly_created is False
    assert len([path for path in fake_db.rows if path[-2:-1] == ('workstreams',)]) == 1


def test_explicit_task_intent_rejects_existing_task_workstream_goal_mismatch(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    create_goal(fake_db, 'g2')
    seed_task(fake_db, goal_id='g1')
    seed_workstream(fake_db, 'w1')
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] = 'g2'
    fake_db.rows[('users', 'u1', 'action_items', 't1')]['workstream_id'] = 'w1'

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.resolve_work_intent(
            'u1',
            TaskOriginWorkIntent(task_id='t1'),
            idempotency_key='mismatch',
            account_generation=3,
            firestore_client=fake_db,
        )


def test_goal_origin_intent_atomically_creates_anchor_task_and_workstream(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    request = GoalOriginWorkIntent(
        goal_id='g1',
        title='Investor outreach',
        objective='Prepare Sarah outreach',
        anchor_task_description='Draft Sarah email',
    )

    receipts = list(
        ThreadPoolExecutor(max_workers=2).map(
            lambda _: workstreams_db.resolve_work_intent(
                'u1', request, idempotency_key='goal-click', account_generation=3, firestore_client=fake_db
            ),
            range(2),
        )
    )

    assert receipts[0] == receipts[1]
    assert receipts[0].newly_created is True
    task = fake_db.rows[('users', 'u1', 'action_items', receipts[0].task_id)]
    assert (task['goal_id'], task['workstream_id']) == ('g1', receipts[0].workstream_id)


def test_workstream_candidate_acceptance_is_atomic_and_idempotent(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'workstream',
            'proposed_action': 'create',
            'workstream_proposal': {
                'title': 'Investor outreach',
                'objective': 'Prepare Sarah outreach',
                'anchor_task': {
                    'description': 'Draft Sarah email',
                    'owner': 'user',
                    'due_at': datetime(2026, 7, 20, tzinfo=timezone.utc),
                    'due_confidence': 0.9,
                    'priority': 'high',
                    'recurrence_rule': 'FREQ=WEEKLY',
                    'recurrence_parent_id': 'task-parent',
                },
            },
            'capture_confidence': 0.9,
            'ownership_confidence': 1,
            'goal_id': 'g1',
            'evidence_refs': [{'kind': 'conversation', 'id': 'c1', 'scope': 'canonical'}],
            'source_surface': 'conversation',
        }
    )
    candidate = CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id='cand-1',
        account_generation=3,
        idempotency_key='idem-1',
        created_at=datetime.now(timezone.utc),
    )
    fake_db.rows[('users', 'u1', 'candidates', 'cand-1')] = candidate.model_dump(mode='python')

    first = workstreams_db.resolve_workstream_candidate('u1', candidate, 3, firestore_client=fake_db)
    second = workstreams_db.resolve_workstream_candidate('u1', candidate, 3, firestore_client=fake_db)

    assert first.workstream_id == second.workstream_id
    assert first.task_id == second.task_id
    assert first.newly_resolved is True and second.newly_resolved is False
    assert len([path for path in fake_db.rows if len(path) == 4 and path[-2] == 'workstreams']) == 1
    assert fake_db.rows[('users', 'u1', 'candidates', 'cand-1')]['status'] == CandidateStatus.accepted.value
    outbox = fake_db.rows[('users', 'u1', 'candidate_integration_outbox', 'cand-1')]
    assert outbox['task_id'] == first.task_id and outbox['status'] == 'pending'
    anchor_task = fake_db.rows[('users', 'u1', 'action_items', first.task_id)]
    assert anchor_task['due_at'] == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert anchor_task['due_confidence'] == 0.9
    assert anchor_task['priority'] == 'high'
    assert anchor_task['recurrence_rule'] == 'FREQ=WEEKLY'
    assert anchor_task['recurrence_parent_id'] == 'task-parent'


def seed_workstream(fake_db, workstream_id='w1', latest_sequence=0, generation=3):
    now = datetime.now(timezone.utc)
    fake_db.rows[('users', 'u1', 'workstreams', workstream_id)] = {
        'workstream_id': workstream_id,
        'title': 'Investor outreach',
        'objective': 'Prepare Sarah outreach',
        'status': 'open',
        'current_state_summary': '',
        'latest_event_sequence': latest_sequence,
        'created_at': now,
        'updated_at': now,
        'account_generation': generation,
    }


def test_recurrence_inbox_is_durable_idempotent_and_generation_scoped(fake_db):
    seed_control(fake_db, generation=3)
    now = datetime.now(timezone.utc)
    signal = CanonicalRecurrenceSignal(
        signal_id='observation-1',
        title='Investor update',
        objective='Send the revised investor update',
        anchor_task_description='Prepare the investor email',
        occurrence_count=2,
        distinct_day_count=2,
        unresolved=True,
        confidence=0.9,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
    )
    first = recurrence_inbox_db.enqueue_recurrence_signal('u1', signal, account_generation=3, firestore_client=fake_db)
    replay = recurrence_inbox_db.enqueue_recurrence_signal(
        'u1',
        signal.model_copy(update={'signal_id': 'observation-2'}),
        account_generation=3,
        firestore_client=fake_db,
    )
    seed_control(fake_db, generation=4)
    next_generation = recurrence_inbox_db.enqueue_recurrence_signal(
        'u1', signal, account_generation=4, firestore_client=fake_db
    )

    assert replay.receipt_id == first.receipt_id
    assert replay.signal.signal_id == 'observation-1'
    assert next_generation.receipt_id != first.receipt_id
    assert recurrence_inbox_db.list_pending_recurrence_receipts(
        'u1', account_generation=3, firestore_client=fake_db
    ) == [replay]

    with pytest.raises(recurrence_inbox_db.RecurrenceGenerationMismatchError):
        recurrence_inbox_db.complete_recurrence_receipt(
            'u1',
            first.receipt_id,
            outcome=RecurrenceOutcomeKind.candidate_created,
            account_generation=3,
            firestore_client=fake_db,
        )
    assert recurrence_inbox_db.list_pending_recurrence_receipts(
        'u1', account_generation=3, firestore_client=fake_db
    ) == [replay]


def test_journal_artifact_versions_and_checkpoints_preserve_structured_continuity(fake_db):
    seed_control(fake_db)
    seed_workstream(fake_db)
    local_ref = EvidenceRef(kind='local_screen', id='screen-1', scope='device_local', device_id='mac-1')
    first_event = workstreams_db.append_workstream_event(
        'u1',
        'w1',
        WorkstreamEventCreate(kind='user_note', summary='Draft pricing changed', evidence_refs=[local_ref]),
        idempotency_key='note-1',
        account_generation=3,
        firestore_client=fake_db,
    )
    replay = workstreams_db.append_workstream_event(
        'u1',
        'w1',
        WorkstreamEventCreate(kind='user_note', summary='Draft pricing changed', evidence_refs=[local_ref]),
        idempotency_key='note-1',
        account_generation=3,
        firestore_client=fake_db,
    )
    fake_db.rows[('users', 'u1', 'workstreams', 'closed-race')] = {
        **fake_db.rows[('users', 'u1', 'workstreams', 'w1')],
        'workstream_id': 'closed-race',
        'status': WorkstreamStatus.completed.value,
    }
    with pytest.raises(workstreams_db.WorkstreamConflictError, match='must be open'):
        workstreams_db.append_workstream_event(
            'u1',
            'closed-race',
            WorkstreamEventCreate(kind='system', summary='Late association'),
            idempotency_key='late-association',
            account_generation=3,
            firestore_client=fake_db,
            required_status=WorkstreamStatus.open,
        )
    v1 = workstreams_db.create_artifact_descriptor(
        'u1',
        'w1',
        ArtifactDescriptorCreate(
            logical_key='investor_email:sarah',
            version=1,
            kind='email_draft',
            uri='omi-artifact://w1/sarah/1',
            content_hash='a' * 64,
            evidence_event_ids=[first_event.event_id],
            evidence_refs=[local_ref],
        ),
        idempotency_key='artifact-v1',
        account_generation=3,
        firestore_client=fake_db,
    )
    v2 = workstreams_db.create_artifact_descriptor(
        'u1',
        'w1',
        ArtifactDescriptorCreate(
            logical_key='investor_email:sarah',
            version=2,
            supersedes_artifact_id=v1.artifact_id,
            kind='email_draft',
            uri='omi-artifact://w1/sarah/2',
            content_hash='b' * 64,
            evidence_event_ids=[first_event.event_id],
            evidence_refs=[local_ref],
        ),
        idempotency_key='artifact-v2',
        account_generation=3,
        firestore_client=fake_db,
    )
    awaiting_review = workstreams_db.transition_artifact_status(
        'u1',
        'w1',
        v2.artifact_id,
        ArtifactStatusTransitionRequest(status='awaiting_review'),
        idempotency_key='artifact-v2-awaiting',
        account_generation=3,
        firestore_client=fake_db,
    )
    approved = workstreams_db.transition_artifact_status(
        'u1',
        'w1',
        v2.artifact_id,
        ArtifactStatusTransitionRequest(status='approved'),
        idempotency_key='artifact-v2-approved',
        account_generation=3,
        firestore_client=fake_db,
    )
    delivered = workstreams_db.transition_artifact_status(
        'u1',
        'w1',
        v2.artifact_id,
        ArtifactStatusTransitionRequest(status='delivered'),
        idempotency_key='artifact-v2-delivered',
        account_generation=3,
        firestore_client=fake_db,
    )
    replay_v2 = workstreams_db.create_artifact_descriptor(
        'u1',
        'w1',
        ArtifactDescriptorCreate(
            logical_key='investor_email:sarah',
            version=2,
            supersedes_artifact_id=v1.artifact_id,
            kind='email_draft',
            uri='omi-artifact://w1/sarah/2',
            content_hash='b' * 64,
            evidence_event_ids=[first_event.event_id],
            evidence_refs=[local_ref],
        ),
        idempotency_key='artifact-v2-later-retry',
        account_generation=3,
        firestore_client=fake_db,
    )
    checkpoint = workstreams_db.upsert_continuation_checkpoint(
        'u1',
        'w1',
        ContinuationCheckpointUpsert(
            runtime_id='runtime-mac-1',
            last_event_sequence=6,
            context_summary='Pricing changed; v2 awaits review.',
            evidence_refs=[local_ref],
        ),
        idempotency_key='checkpoint-runtime-mac-1',
        account_generation=3,
        firestore_client=fake_db,
    )
    checkpoint_replay = workstreams_db.upsert_continuation_checkpoint(
        'u1',
        'w1',
        ContinuationCheckpointUpsert(
            runtime_id='runtime-mac-1',
            last_event_sequence=6,
            context_summary='Pricing changed; v2 awaits review.',
            evidence_refs=[local_ref],
        ),
        idempotency_key='checkpoint-runtime-mac-1-retry',
        account_generation=3,
        firestore_client=fake_db,
    )
    with pytest.raises(workstreams_db.WorkstreamConflictError, match='backwards'):
        workstreams_db.upsert_continuation_checkpoint(
            'u1',
            'w1',
            ContinuationCheckpointUpsert(
                runtime_id='runtime-mac-1',
                last_event_sequence=5,
                context_summary='Stale context.',
            ),
            idempotency_key='checkpoint-stale',
            account_generation=3,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamConflictError, match='different content'):
        workstreams_db.upsert_continuation_checkpoint(
            'u1',
            'w1',
            ContinuationCheckpointUpsert(
                runtime_id='runtime-mac-1',
                last_event_sequence=6,
                context_summary='Conflicting context.',
            ),
            idempotency_key='checkpoint-conflict',
            account_generation=3,
            firestore_client=fake_db,
        )

    assert first_event.event_id == replay.event_id
    assert (first_event.sequence, v1.version, v2.version) == (1, 1, 2)
    assert fake_db.rows[('users', 'u1', 'workstreams', 'w1', 'artifact_refs', v1.artifact_id)]['status'] == 'superseded'
    assert [awaiting_review.status, approved.status, delivered.status, replay_v2.status] == [
        'awaiting_review',
        'approved',
        'delivered',
        'delivered',
    ]
    assert checkpoint.last_event_sequence == 6
    assert checkpoint_replay == checkpoint
    assert checkpoint.model_dump().keys().isdisjoint({'run_status', 'attempt_id', 'execution_state'})
    assert checkpoint.evidence_refs[0].device_id == 'mac-1'


def test_artifact_and_checkpoint_reject_unreproducible_positions(fake_db):
    seed_control(fake_db)
    seed_workstream(fake_db)

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.create_artifact_descriptor(
            'u1',
            'w1',
            ArtifactDescriptorCreate(
                logical_key='draft',
                version=1,
                kind='email_draft',
                uri='omi-artifact://w1/draft/1',
                content_hash='a' * 64,
                evidence_event_ids=['missing-event'],
            ),
            idempotency_key='missing-evidence',
            account_generation=3,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.upsert_continuation_checkpoint(
            'u1',
            'w1',
            ContinuationCheckpointUpsert(
                runtime_id='runtime-1',
                last_event_sequence=1,
                context_summary='Cannot be ahead of the journal.',
            ),
            idempotency_key='future-checkpoint',
            account_generation=3,
            firestore_client=fake_db,
        )

    v1 = workstreams_db.create_artifact_descriptor(
        'u1',
        'w1',
        ArtifactDescriptorCreate(
            logical_key='draft',
            version=1,
            kind='email_draft',
            uri='omi-artifact://w1/draft/1',
            content_hash='a' * 64,
        ),
        idempotency_key='valid-v1',
        account_generation=3,
        firestore_client=fake_db,
    )
    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.create_artifact_descriptor(
            'u1',
            'w1',
            ArtifactDescriptorCreate(
                logical_key='draft',
                version=2,
                supersedes_artifact_id=v1.artifact_id,
                kind='email_draft',
                uri='omi-artifact://w1/draft/2',
                content_hash='b' * 64,
            ),
            idempotency_key='uncited-v2',
            account_generation=3,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.create_artifact_descriptor(
            'u1',
            'w1',
            ArtifactDescriptorCreate(
                logical_key='draft',
                version=3,
                supersedes_artifact_id=v1.artifact_id,
                kind='email_draft',
                uri='omi-artifact://w1/draft/3',
                content_hash='c' * 64,
            ),
            idempotency_key='invalid-v3',
            account_generation=3,
            firestore_client=fake_db,
        )


def test_concurrent_journal_appends_allocate_stable_unique_sequences(fake_db):
    seed_control(fake_db)
    seed_workstream(fake_db)

    events = list(
        ThreadPoolExecutor(max_workers=8).map(
            lambda index: workstreams_db.append_workstream_event(
                'u1',
                'w1',
                WorkstreamEventCreate(kind='user_note', summary=f'Update {index}'),
                idempotency_key=f'event-{index}',
                account_generation=3,
                firestore_client=fake_db,
            ),
            range(20),
        )
    )

    assert sorted(event.sequence for event in events) == list(range(1, 21))
    assert workstreams_db.get_workstream('u1', 'w1', firestore_client=fake_db).latest_event_sequence == 20


def test_workstream_mutations_are_generation_fenced_and_receipt_idempotent(fake_db):
    seed_control(fake_db, mode='read')
    seed_workstream(fake_db)

    seed_control(fake_db, generation=4, mode='read')
    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError):
        workstreams_db.update_workstream(
            'u1',
            'w1',
            WorkstreamUpdate(current_state_summary='Stale generation'),
            idempotency_key='update-1',
            account_generation=3,
            firestore_client=fake_db,
        )

    seed_workstream(fake_db, generation=4)
    first = workstreams_db.update_workstream(
        'u1',
        'w1',
        WorkstreamUpdate(current_state_summary='Ready for review'),
        idempotency_key='update-2',
        account_generation=4,
        firestore_client=fake_db,
    )
    replay = workstreams_db.update_workstream(
        'u1',
        'w1',
        WorkstreamUpdate(current_state_summary='Ready for review'),
        idempotency_key='update-2',
        account_generation=4,
        firestore_client=fake_db,
    )
    assert replay == first
    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.update_workstream(
            'u1',
            'w1',
            WorkstreamUpdate(current_state_summary='Different payload'),
            idempotency_key='update-2',
            account_generation=4,
            firestore_client=fake_db,
        )


def test_workstream_mutations_reject_stored_workstream_generation_mismatch(fake_db):
    seed_control(fake_db, generation=4, mode='write')
    seed_workstream(fake_db, generation=3)

    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError, match='workstream account generation'):
        workstreams_db.update_workstream(
            'u1',
            'w1',
            WorkstreamUpdate(current_state_summary='Cross-generation write'),
            idempotency_key='stale-ws-update',
            account_generation=4,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError, match='workstream account generation'):
        workstreams_db.append_workstream_event(
            'u1',
            'w1',
            WorkstreamEventCreate(kind='user_note', summary='Cross-generation note'),
            idempotency_key='stale-ws-event',
            account_generation=4,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError, match='workstream account generation'):
        workstreams_db.create_artifact_descriptor(
            'u1',
            'w1',
            ArtifactDescriptorCreate(
                logical_key='draft',
                version=1,
                kind='email_draft',
                uri='omi-artifact://w1/draft/1',
                content_hash='a' * 64,
            ),
            idempotency_key='stale-ws-artifact',
            account_generation=4,
            firestore_client=fake_db,
        )
    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError, match='workstream account generation'):
        workstreams_db.upsert_continuation_checkpoint(
            'u1',
            'w1',
            ContinuationCheckpointUpsert(
                runtime_id='runtime-1',
                last_event_sequence=0,
                context_summary='Cross-generation checkpoint',
            ),
            idempotency_key='stale-ws-checkpoint',
            account_generation=4,
            firestore_client=fake_db,
        )

    seed_workstream(fake_db, generation=4)
    artifact = workstreams_db.create_artifact_descriptor(
        'u1',
        'w1',
        ArtifactDescriptorCreate(
            logical_key='draft',
            version=1,
            kind='email_draft',
            uri='omi-artifact://w1/draft/1',
            content_hash='a' * 64,
        ),
        idempotency_key='matching-ws-artifact',
        account_generation=4,
        firestore_client=fake_db,
    )
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['account_generation'] = 3
    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError, match='workstream account generation'):
        workstreams_db.transition_artifact_status(
            'u1',
            'w1',
            artifact.artifact_id,
            ArtifactStatusTransitionRequest(status='awaiting_review'),
            idempotency_key='stale-ws-transition',
            account_generation=4,
            firestore_client=fake_db,
        )


def test_workstream_reads_are_user_scoped(fake_db):
    seed_workstream(fake_db)

    assert workstreams_db.get_workstream('u1', 'w1', firestore_client=fake_db) is not None
    assert workstreams_db.get_workstream('another-user', 'w1', firestore_client=fake_db) is None


def test_task_goal_link_import_is_idempotent_and_rejects_mismatches(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    create_goal(fake_db, 'g2')
    seed_task(fake_db, 't1')
    seed_task(fake_db, 't2', goal_id='g2')
    request = TaskGoalLinkImportRequest(links=[{'task_id': 't1', 'goal_id': 'g1'}, {'task_id': 't2', 'goal_id': 'g1'}])

    first = workstreams_db.import_task_goal_links(
        'u1', request, idempotency_key='import-1', account_generation=3, firestore_client=fake_db
    )
    replay = workstreams_db.import_task_goal_links(
        'u1', request, idempotency_key='import-1', account_generation=3, firestore_client=fake_db
    )
    second = workstreams_db.import_task_goal_links(
        'u1',
        TaskGoalLinkImportRequest(links=[{'task_id': 't1', 'goal_id': 'g1'}]),
        idempotency_key='import-2',
        account_generation=3,
        firestore_client=fake_db,
    )

    assert (first.imported, first.failed, first.failure_task_ids) == (1, 1, ['t2'])
    assert replay == first
    assert (second.imported, second.unchanged) == (0, 1)

    seed_workstream(fake_db, 'w1')
    fake_db.rows[('users', 'u1', 'action_items', 't1')]['workstream_id'] = 'w1'
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] = 'g2'
    corrupt_existing = workstreams_db.import_task_goal_links(
        'u1',
        TaskGoalLinkImportRequest(links=[{'task_id': 't1', 'goal_id': 'g1'}]),
        idempotency_key='import-3',
        account_generation=3,
        firestore_client=fake_db,
    )
    assert (corrupt_existing.unchanged, corrupt_existing.failed) == (0, 1)


def test_task_goal_link_import_resumes_partial_receipt_and_fences_payload_reuse(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    seed_task(fake_db, 't1', goal_id='g1')
    seed_task(fake_db, 't2')
    seed_task(fake_db, 't3')
    request = TaskGoalLinkImportRequest(links=[{'task_id': 't1', 'goal_id': 'g1'}, {'task_id': 't2', 'goal_id': 'g1'}])
    request_payload = request.model_dump(mode='json')
    receipt_ref = workstreams_db._mutation_receipt_ref(
        'u1',
        operation='task-goal-link-import',
        idempotency_key='resume-import',
        account_generation=3,
        firestore_client=fake_db,
    )
    first_item_timestamp = datetime(2026, 7, 9, tzinfo=timezone.utc)
    fake_db.rows[('users', 'u1', 'action_items', 't1')]['updated_at'] = first_item_timestamp
    fake_db.rows[receipt_ref.path] = {
        'request_hash': workstreams_db._mutation_hash(request_payload),
        'status': 'processing',
        'outcomes': {'0': 'imported'},
        'created_at': first_item_timestamp,
        'updated_at': first_item_timestamp,
    }

    report = workstreams_db.import_task_goal_links(
        'u1',
        request,
        idempotency_key='resume-import',
        account_generation=3,
        firestore_client=fake_db,
    )

    assert (report.imported, report.unchanged, report.failed) == (2, 0, 0)
    assert fake_db.rows[('users', 'u1', 'action_items', 't1')]['updated_at'] == first_item_timestamp
    assert fake_db.rows[('users', 'u1', 'action_items', 't2')]['goal_id'] == 'g1'
    assert fake_db.rows[receipt_ref.path]['status'] == 'complete'
    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.import_task_goal_links(
            'u1',
            TaskGoalLinkImportRequest(links=[{'task_id': 't3', 'goal_id': 'g1'}]),
            idempotency_key='resume-import',
            account_generation=3,
            firestore_client=fake_db,
        )
    assert fake_db.rows[('users', 'u1', 'action_items', 't3')]['goal_id'] is None


def test_goal_detail_aggregates_threads_tasks_and_progress_without_client_n_plus_one(fake_db):
    seed_control(fake_db)
    create_goal(fake_db, 'g1')
    seed_task(fake_db, 't1', goal_id='g1')
    seed_workstream(fake_db, 'w1')
    fake_db.rows[('users', 'u1', 'workstreams', 'w1')]['goal_id'] = 'g1'
    goals_db.append_goal_progress_event(
        'u1',
        'g1',
        GoalProgressEventCreate(kind='milestone', summary='First draft complete'),
        idempotency_key='goal-detail-progress',
        account_generation=3,
        firestore_client=fake_db,
    )

    detail = workstreams_db.get_goal_detail('u1', 'g1', firestore_client=fake_db)

    assert detail.goal.goal_id == 'g1'
    assert [thread.workstream_id for thread in detail.active_threads] == ['w1']
    assert [task.id for task in detail.tasks] == ['t1']
    assert [event.summary for event in detail.progress_events] == ['First draft complete']


def test_device_local_evidence_requires_device_identity():
    with pytest.raises(ValueError):
        EvidenceRef(kind='local_screen', id='screen-1', scope='device_local')
