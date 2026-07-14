import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from models.workstream import Workstream, WorkstreamStatus
from models.workstream_association import (
    AssociationEvidence,
    AssociationJudgment,
    AssociationOutcomeKind,
    AssociationReason,
    RecurrenceOutcomeKind,
    RecurrenceInboxReceipt,
    RecurrenceInboxStatus,
)
from utils.memory.memory_system import MemorySystem
from utils.memory.canonical_consolidation import (
    CONSOLIDATION_AGENT_PROMPT,
    ConsolidationAgentBatch,
    ConsolidationReport,
)
from utils.memory import canonical_short_term_maintenance_cron as maintenance_cron
from utils.memory.short_term_promotion import CanonicalShortTermMaintenanceReport
from utils.task_intelligence import workstream_association as association
from utils.task_intelligence import workstream_index
from database import vector_db

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / 'fixtures' / 'task_intelligence' / 'association_v1.json'
NOW = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)


def _workstream(payload: dict) -> Workstream:
    return Workstream(
        workstream_id=payload['workstream_id'],
        title=payload['objective'][:100],
        objective=payload['objective'],
        status=WorkstreamStatus.open,
        current_state_summary=payload['current_state_summary'],
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(association, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        association.workstreams_db,
        'get_task_workflow_control',
        lambda uid, firestore_client=None: TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.write,
            account_generation=7,
        ),
    )


def test_golden_association_fixtures_append_only_material_intent_match(enabled):
    fixture = json.loads(FIXTURE.read_text())
    appended: list[tuple[str, str]] = []

    for case in fixture['cases']:
        records = {item['workstream_id']: _workstream(item) for item in case['candidate_workstreams']}

        def append(uid, workstream_id, event, *, idempotency_key, **kwargs):
            appended.append((case['id'], idempotency_key))
            return SimpleNamespace(event_id=f'event-{case["id"]}')

        judgment = case['recorded_judgment']
        outcome = association.associate_canonical_evidence(
            'uid-1',
            AssociationEvidence(evidence_id=case['id'], **case['evidence']),
            firestore_client=object(),
            retrieve_ids=lambda uid, summary, **kwargs: list(records),
            hydrate=lambda uid, workstream_id, **kwargs: records.get(workstream_id),
            adjudicate=lambda request: AssociationJudgment(
                workstream_id=judgment['workstream_id'],
                material=judgment['material'],
                event_summary='Pricing change affects the investor note.' if judgment['material'] else None,
                reason=(
                    AssociationReason.selected
                    if judgment['material']
                    else AssociationReason.immaterial
                    if judgment['workstream_id']
                    else AssociationReason.no_match
                ),
            ),
            append_event=append,
        )
        expected = {
            'intent_match': AssociationOutcomeKind.appended,
            'entity_only': AssociationOutcomeKind.no_match,
            'immaterial_repeat': AssociationOutcomeKind.immaterial,
        }
        assert outcome.outcome == expected[case['id']]

    assert [case_id for case_id, _ in appended] == ['intent_match']


def test_retrieval_hydrates_authority_and_purges_missing_or_closed_hits(enabled):
    open_record = _workstream(
        {
            'workstream_id': 'open-1',
            'objective': 'Ship the investor note',
            'current_state_summary': 'Drafting',
        }
    )
    closed_record = open_record.model_copy(update={'workstream_id': 'closed-1', 'status': WorkstreamStatus.completed})
    records = {'open-1': open_record, 'closed-1': closed_record}
    purged: list[str] = []
    seen_candidates: list[str] = []

    outcome = association.associate_canonical_evidence(
        'uid-1',
        AssociationEvidence(
            evidence_id='memory-1',
            summary='Pricing changed',
            evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
        ),
        firestore_client=object(),
        retrieve_ids=lambda uid, summary, **kwargs: ['missing-1', 'closed-1', 'open-1'],
        hydrate=lambda uid, workstream_id, **kwargs: records.get(workstream_id),
        purge_stale=lambda uid, workstream_id, **kwargs: purged.append(workstream_id) is None,
        adjudicate=lambda request: (
            seen_candidates.extend(item.workstream_id for item in request.candidates)
            or AssociationJudgment(material=False, reason=AssociationReason.no_match)
        ),
    )

    assert purged == ['missing-1', 'closed-1']
    assert seen_candidates == ['open-1']
    assert outcome.hydrated_candidate_ids == ['open-1']


def test_retry_coalesces_same_evidence_into_one_event_key(enabled):
    record = _workstream({'workstream_id': 'ws-1', 'objective': 'Send update', 'current_state_summary': 'Drafting'})
    events: dict[str, SimpleNamespace] = {}

    def append(uid, workstream_id, event, *, idempotency_key, **kwargs):
        return events.setdefault(idempotency_key, SimpleNamespace(event_id=f'event-{len(events) + 1}'))

    evidence = AssociationEvidence(
        evidence_id='memory-1',
        summary='The pricing assumption changed',
        evidence_refs=[
            EvidenceRef(
                kind=EvidenceKind.memory_item,
                id='memory-1',
                version='3',
                scope=EvidenceScope.canonical,
            )
        ],
    )
    kwargs = {
        'firestore_client': object(),
        'retrieve_ids': lambda uid, summary, **kwargs: ['ws-1'],
        'hydrate': lambda uid, workstream_id, **kwargs: record,
        'adjudicate': lambda request: AssociationJudgment(
            workstream_id='ws-1',
            material=True,
            reason=AssociationReason.selected,
            event_summary='Pricing assumptions changed.',
        ),
        'append_event': append,
    }
    first = association.associate_canonical_evidence('uid-1', evidence, **kwargs)
    second = association.associate_canonical_evidence('uid-1', evidence, **kwargs)

    assert len(events) == 1
    assert first.event_id == second.event_id


def test_material_event_uses_minimized_adjudicator_summary_not_memory_content(enabled):
    record = _workstream({'workstream_id': 'ws-1', 'objective': 'Send update', 'current_state_summary': 'Drafting'})
    appended = []
    raw_memory = 'Sarah said the exact confidential pricing is 12345 and asked us to change the draft.'

    association.associate_canonical_evidence(
        'uid-1',
        AssociationEvidence(
            evidence_id='memory-1',
            summary=raw_memory,
            evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
        ),
        firestore_client=object(),
        retrieve_ids=lambda *args, **kwargs: ['ws-1'],
        hydrate=lambda *args, **kwargs: record,
        adjudicate=lambda request: AssociationJudgment(
            workstream_id='ws-1',
            material=True,
            reason=AssociationReason.selected,
            event_summary='The pricing assumption changed and the draft needs revision.',
        ),
        append_event=lambda uid, workstream_id, event, **kwargs: (
            appended.append((event, kwargs)) or SimpleNamespace(event_id='event-1')
        ),
    )

    assert appended[0][0].summary == 'The pricing assumption changed and the draft needs revision.'
    assert raw_memory not in appended[0][0].summary
    assert appended[0][1]['required_status'] == WorkstreamStatus.open


def test_shadow_association_adjudicates_but_does_not_append(enabled, monkeypatch):
    monkeypatch.setattr(
        association.workstreams_db,
        'get_task_workflow_control',
        lambda uid, firestore_client=None: TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.shadow,
            account_generation=7,
        ),
    )
    record = _workstream({'workstream_id': 'ws-1', 'objective': 'Send update', 'current_state_summary': 'Drafting'})
    appended = []
    outcome = association.associate_canonical_evidence(
        'uid-1',
        AssociationEvidence(
            evidence_id='memory-1',
            summary='The pricing assumption changed.',
            evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
        ),
        retrieve_ids=lambda *args, **kwargs: ['ws-1'],
        hydrate=lambda *args, **kwargs: record,
        adjudicate=lambda request: AssociationJudgment(
            workstream_id='ws-1',
            material=True,
            reason=AssociationReason.selected,
            event_summary='Revise the draft for the changed pricing assumption.',
        ),
        append_event=lambda *args, **kwargs: appended.append('event'),
    )

    assert outcome.outcome == AssociationOutcomeKind.would_append
    assert appended == []


def test_verbatim_material_summary_fails_closed_without_append(enabled):
    record = _workstream({'workstream_id': 'ws-1', 'objective': 'Send update', 'current_state_summary': 'Drafting'})
    appended = []
    outcome = association.associate_canonical_evidence(
        'uid-1',
        AssociationEvidence(
            evidence_id='memory-1',
            summary='The pricing assumption changed.\nSarah expects the note tomorrow.',
            evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
        ),
        retrieve_ids=lambda *args, **kwargs: ['ws-1'],
        hydrate=lambda *args, **kwargs: record,
        adjudicate=lambda request: AssociationJudgment(
            workstream_id='ws-1',
            material=True,
            reason=AssociationReason.selected,
            event_summary='  THE pricing assumption changed. ',
        ),
        append_event=lambda *args, **kwargs: appended.append('event'),
    )

    assert outcome.outcome == AssociationOutcomeKind.minimization_rejected
    assert appended == []


def test_adjudication_reason_requires_consistent_selection_shape():
    with pytest.raises(ValueError, match='requires immaterial reason'):
        AssociationJudgment(
            workstream_id='ws-1',
            material=False,
            reason=AssociationReason.no_match,
        )
    with pytest.raises(ValueError, match='requires a workstream selection'):
        AssociationJudgment(material=False, reason=AssociationReason.immaterial)


def test_noncanonical_user_executes_no_retrieval_or_recurrence_mutation(monkeypatch):
    monkeypatch.setattr(association, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)
    calls: list[str] = []
    evidence = AssociationEvidence(
        evidence_id='memory-1',
        summary='Something changed',
        evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
    )
    outcome = association.associate_canonical_evidence(
        'uid-1',
        evidence,
        retrieve_ids=lambda *args, **kwargs: calls.append('retrieve') or [],
    )
    recurrence = association.consume_recurrence_signal(
        'uid-1',
        _recurrence_signal(distinct_days=3),
        create_candidate=lambda *args, **kwargs: calls.append('candidate'),
    )

    assert outcome.outcome == AssociationOutcomeKind.not_canonical_cohort
    assert recurrence.outcome == RecurrenceOutcomeKind.not_canonical_cohort
    assert calls == []


def _recurrence_signal(*, distinct_days: int) -> CanonicalRecurrenceSignal:
    return CanonicalRecurrenceSignal(
        signal_id='signal-1',
        title='Investor update',
        objective='Send Sarah the revised investor update',
        anchor_task_description='Prepare the revised investor email',
        occurrence_count=distinct_days,
        distinct_day_count=distinct_days,
        unresolved=True,
        confidence=0.9,
        first_seen_at=NOW - timedelta(days=max(0, distinct_days - 1)),
        last_seen_at=NOW,
        evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id='memory-1', scope=EvidenceScope.canonical)],
    )


def test_canonical_consolidation_emits_neutral_recurrence_contract_only():
    signal = _recurrence_signal(distinct_days=3)
    batch = ConsolidationAgentBatch.model_validate({'decisions': [], 'recurrence_signals': [signal.model_dump()]})

    assert batch.recurrence_signals == [signal]
    assert 'at least two distinct days' in ' '.join(CONSOLIDATION_AGENT_PROMPT.split())


def test_maintenance_orchestrator_hands_recurrence_to_workflow_callback(monkeypatch):
    signal = _recurrence_signal(distinct_days=3)
    monkeypatch.setenv('MEMORY_CANONICAL_PROMOTION_CRON_ENABLED', 'true')
    monkeypatch.setattr(maintenance_cron, 'list_canonical_cohort_uids', lambda: ['uid-1'])
    maintenance_kwargs = {}

    def run_maintenance(uid, **kwargs):
        maintenance_kwargs.update(kwargs)
        return CanonicalShortTermMaintenanceReport(
            uid=uid,
            consolidation=ConsolidationReport(uid=uid, recurrence_signals=[signal]),
        )

    monkeypatch.setattr(maintenance_cron, 'run_canonical_short_term_maintenance', run_maintenance)
    consumed: list[CanonicalRecurrenceSignal] = []

    summary = maintenance_cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=object(),
        now=NOW,
        run_id='run-1',
        recurrence_signal_persister=lambda *args, **kwargs: 1,
        recurrence_signal_consumer=lambda uid, signals, firestore_client=None: (
            consumed.extend(signals) or len(signals)
        ),
    )

    assert consumed == [signal]
    assert summary.recurrence_candidates_total == 1
    assert maintenance_kwargs['recurrence_signal_sink'] is not None


def test_recurrence_requires_multiple_days_and_is_idempotent_across_retries(enabled):
    created: dict[str, SimpleNamespace] = {}

    def create(uid, proposal, *, idempotency_key, account_generation):
        assert proposal.subject_kind.value == 'workstream'
        assert account_generation == 7
        return created.setdefault(idempotency_key, SimpleNamespace(candidate_id=f'candidate-{len(created) + 1}'))

    one_off = association.consume_recurrence_signal(
        'uid-1',
        _recurrence_signal(distinct_days=1),
        account_generation=7,
        firestore_client=object(),
        create_candidate=create,
    )
    first = association.consume_recurrence_signal(
        'uid-1',
        _recurrence_signal(distinct_days=3),
        account_generation=7,
        firestore_client=object(),
        create_candidate=create,
    )
    second = association.consume_recurrence_signal(
        'uid-1',
        _recurrence_signal(distinct_days=3),
        account_generation=7,
        firestore_client=object(),
        create_candidate=create,
    )

    assert one_off.outcome == RecurrenceOutcomeKind.below_threshold
    assert first.outcome == RecurrenceOutcomeKind.candidate_created
    assert first.candidate_id == second.candidate_id
    assert len(created) == 1


def test_recurrence_shadow_evaluates_without_candidate_mutation(monkeypatch):
    monkeypatch.setattr(association, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        association.workstreams_db,
        'get_task_workflow_control',
        lambda uid, firestore_client=None: TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.shadow,
            account_generation=7,
        ),
    )
    calls = []

    result = association.consume_recurrence_signal(
        'uid-1',
        _recurrence_signal(distinct_days=3),
        account_generation=7,
        create_candidate=lambda *args, **kwargs: calls.append('candidate'),
    )

    assert result.outcome == RecurrenceOutcomeKind.would_create
    assert result.idempotency_key
    assert calls == []


def test_durable_recurrence_inbox_retries_failures_and_continues(enabled, monkeypatch):
    first = _recurrence_signal(distinct_days=3)
    second = first.model_copy(
        update={
            'signal_id': 'signal-2',
            'evidence_refs': [
                EvidenceRef(kind=EvidenceKind.memory_item, id='memory-second', scope=EvidenceScope.canonical)
            ],
        }
    )
    receipts = [
        RecurrenceInboxReceipt(
            receipt_id=f'receipt-{index}',
            loop_key=signal.stable_loop_key,
            account_generation=7,
            status=RecurrenceInboxStatus.pending,
            signal=signal,
            created_at=NOW,
            updated_at=NOW,
        )
        for index, signal in enumerate((first, second), start=1)
    ]
    enqueued = []
    completed = []
    retried = []

    def consume(uid, signal, **kwargs):
        if signal.stable_loop_key == first.stable_loop_key:
            raise RuntimeError('transient')
        return SimpleNamespace(outcome=RecurrenceOutcomeKind.candidate_created)

    monkeypatch.setattr(association, 'consume_recurrence_signal', consume)
    created = association.consume_recurrence_signals_for_maintenance(
        'uid-1',
        [first, second],
        firestore_client=object(),
        enqueue=lambda uid, signal, **kwargs: enqueued.append(signal.stable_loop_key) or receipts[0],
        list_pending=lambda *args, **kwargs: receipts,
        complete=lambda uid, receipt_id, **kwargs: completed.append(receipt_id),
        retry=lambda uid, receipt_id, **kwargs: retried.append(receipt_id),
    )

    assert enqueued == [first.stable_loop_key, second.stable_loop_key]
    assert retried == ['receipt-1']
    assert completed == ['receipt-2']
    assert created == 1


def test_recurrence_identity_is_stable_across_independent_evolving_signals(enabled):
    first = _recurrence_signal(distinct_days=2)
    later = CanonicalRecurrenceSignal(
        signal_id='later-observation',
        title='Revised investor note',
        objective='Deliver the latest investor note after pricing changed',
        anchor_task_description='Revise and send the investor email',
        occurrence_count=3,
        distinct_day_count=3,
        unresolved=True,
        confidence=0.95,
        first_seen_at=first.first_seen_at,
        last_seen_at=first.last_seen_at + timedelta(days=1),
        evidence_refs=[
            first.evidence_refs[0],
            EvidenceRef(kind=EvidenceKind.memory_item, id='memory-2', scope=EvidenceScope.canonical),
        ],
    )
    keys = []

    def create(uid, proposal, *, idempotency_key, account_generation):
        keys.append(idempotency_key)
        return SimpleNamespace(candidate_id='candidate-1')

    association.consume_recurrence_signal('uid-1', first, account_generation=7, create_candidate=create)
    association.consume_recurrence_signal('uid-1', later, account_generation=7, create_candidate=create)

    assert keys[0] == keys[1]


def test_recurrence_contract_rejects_impossible_temporal_counts():
    payload = _recurrence_signal(distinct_days=3).model_dump()
    payload['occurrence_count'] = 2
    with pytest.raises(ValueError, match='distinct_day_count'):
        CanonicalRecurrenceSignal.model_validate(payload)


def test_index_rebuild_resets_and_indexes_only_open_authoritative_workstreams(monkeypatch):
    monkeypatch.setattr(workstream_index, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        workstream_index.workstreams_db,
        'get_task_workflow_control',
        lambda uid, firestore_client=None: TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.read, account_generation=7
        ),
    )
    open_record = _workstream(
        {'workstream_id': 'open-1', 'objective': 'Ship update', 'current_state_summary': 'Drafting'}
    )
    archived = open_record.model_copy(update={'workstream_id': 'archived-1', 'status': WorkstreamStatus.archived})
    resets: list[str] = []
    indexed: list[str] = []

    report = association.rebuild_workstream_association_index(
        'uid-1',
        list_source=lambda uid, **kwargs: [open_record, archived],
        reset_index=lambda uid, **kwargs: resets.append(uid) is None,
        upsert_index=lambda uid, workstream_id, **kwargs: indexed.append(workstream_id) is None or True,
    )

    assert resets == ['uid-1']
    assert indexed == ['open-1']
    assert report.source_count == 1
    assert report.indexed_count == 1


def test_index_refresh_upserts_open_deletes_closed_and_skips_noncanonical(monkeypatch):
    open_record = _workstream(
        {'workstream_id': 'open-1', 'objective': 'Ship update', 'current_state_summary': 'Drafting'}
    )
    closed_record = open_record.model_copy(update={'status': WorkstreamStatus.archived})
    indexed: list[str] = []
    deleted: list[str] = []

    monkeypatch.setattr(workstream_index, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        workstream_index.workstreams_db,
        'get_task_workflow_control',
        lambda uid, firestore_client=None: TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.read, account_generation=7
        ),
    )
    assert workstream_index.refresh_workstream_association_index(
        'uid-1',
        'open-1',
        hydrate=lambda *args, **kwargs: open_record,
        upsert_index=lambda uid, workstream_id, **kwargs: indexed.append(workstream_id) is None or True,
        delete_index=lambda uid, workstream_id, **kwargs: deleted.append(workstream_id) is None or True,
    )
    assert workstream_index.refresh_workstream_association_index(
        'uid-1',
        'open-1',
        hydrate=lambda *args, **kwargs: closed_record,
        upsert_index=lambda *args, **kwargs: False,
        delete_index=lambda uid, workstream_id, **kwargs: deleted.append(workstream_id) is None or True,
    )

    monkeypatch.setattr(workstream_index, 'resolve_memory_system', lambda uid, db_client=None: MemorySystem.LEGACY)
    assert not workstream_index.refresh_workstream_association_index(
        'uid-1',
        'legacy-1',
        hydrate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not hydrate')),
    )
    report = workstream_index.rebuild_workstream_association_index(
        'uid-1',
        list_source=lambda uid, **kwargs: (_ for _ in ()).throw(AssertionError('must not list')),
    )

    assert indexed == ['open-1']
    assert deleted == ['open-1']
    assert report.source_count == report.indexed_count == 0


def test_derived_vector_index_returns_ids_only_and_uses_versioned_namespace(monkeypatch):
    class FakeIndex:
        def __init__(self):
            self.upserts = []
            self.deletes = []

        def upsert(self, **kwargs):
            self.upserts.append(kwargs)

        def query(self, **kwargs):
            assert kwargs['namespace'] == vector_db.WORKSTREAM_ASSOCIATION_NAMESPACE
            return {
                'matches': [
                    {'metadata': {'workstream_id': 'ws-1'}},
                    {'metadata': {'workstream_id': 'ws-1'}},
                    {'metadata': {}},
                ]
            }

        def delete(self, **kwargs):
            self.deletes.append(kwargs)

    fake = FakeIndex()
    monkeypatch.setattr(vector_db, 'index', fake)
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=lambda text: [0.1, 0.2]))

    assert vector_db.upsert_workstream_association_vector(
        'uid-1',
        'ws-1',
        objective='Ship the update',
        current_state_summary='Drafting',
    )
    assert vector_db.query_workstream_association_candidates('uid-1', 'pricing changed') == ['ws-1']
    assert vector_db.delete_workstream_association_vector('uid-1', 'ws-1')
    assert vector_db.reset_workstream_association_vectors('uid-1')

    record = fake.upserts[0]['vectors'][0]
    assert 'objective' not in record['metadata']
    assert record['metadata']['schema_version'] == 1
    assert all(call['namespace'] == vector_db.WORKSTREAM_ASSOCIATION_NAMESPACE for call in fake.deletes)


def test_memory_domain_does_not_import_workflow_writers():
    forbidden = ('database.candidates', 'database.workstreams', 'utils.task_intelligence')
    violations: list[str] = []
    for path in (ROOT / 'utils' / 'memory').rglob('*.py'):
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            statement = line.lstrip()
            if statement.startswith(('import ', 'from ')) and any(name in statement for name in forbidden):
                violations.append(f'{path.name}:{line_number}')
    assert violations == []
