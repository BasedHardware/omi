from datetime import datetime, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_state_head import MEMORY_STATE_HEAD_SCHEMA_VERSION, MEMORY_STATE_HEAD_SOURCE
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.memory.jit_trigger_snapshot import read_authoritative_trigger_snapshot

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, identifier, payload, *, exists=True):
        self.id = identifier
        self._payload = payload
        self.exists = exists

    def to_dict(self):
        return self._payload


class _Document:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get(self):
        return self.snapshot


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def where(self, *, filter):
        assert filter.field_path == 'kind'
        return self

    def limit(self, count):
        assert count == 501
        return self

    def stream(self):
        return iter(self.rows)


class _Client:
    def __init__(self, rows, generation=3, trailing_head=None):
        self.rows = rows
        self.generation = generation
        self.trailing_head = trailing_head
        self.head_reads = 0

    def document(self, _path):
        self.head_reads += 1
        generation, head_commit_id, commit_sequence = (
            self.trailing_head if self.head_reads > 1 and self.trailing_head else (self.generation, 'head-7', 7)
        )
        return _Document(
            _Snapshot(
                'head',
                {
                    'schema_version': MEMORY_STATE_HEAD_SCHEMA_VERSION,
                    'source': MEMORY_STATE_HEAD_SOURCE,
                    'uid': 'owner',
                    'account_generation': generation,
                    'head_commit_id': head_commit_id,
                    'commit_sequence': commit_sequence,
                },
            )
        )

    def collection(self, _path):
        return _Query(self.rows)


def _trigger(identifier='trigger-1', *, generation=3, status=MemoryItemStatus.active):
    return MemoryItem(
        memory_id=identifier,
        uid='owner',
        version=1,
        tier=MemoryLayer.long_term,
        status=status,
        processing_state=ProcessingState.processed,
        content='Release trigger',
        evidence=[
            MemoryEvidence(
                evidence_id='evidence-1',
                source_type='chat_turn',
                source_id='turn-1',
                source_version='v1',
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id='head-7',
        ledger_sequence=7,
        account_generation=generation,
        ledger_schema_version='knowledge_ledger.v1',
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        trigger_condition={
            'keywords': ['release'],
            'action': {'type': 'agent_prompt', 'prompt': 'Find the next release step.'},
        },
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
        arguments={'wakeup_budget_per_day': 2},
    )


def _row(item):
    return _Snapshot(item.memory_id, item.model_dump(mode='python'))


def test_exhaustive_snapshot_carries_head_generation_revision_and_action():
    result = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(_trigger())]))

    assert result.complete is True
    assert result.account_generation == 3
    assert result.commit_sequence == 7
    assert len(result.snapshot_revision) == 64
    assert result.rows[0].action.prompt == 'Find the next release step.'
    assert result.rows[0].wakeup_budget_per_day == 2


def test_closed_rows_are_exhaustively_observed_but_deleted_from_active_projection():
    closed = _trigger(status=MemoryItemStatus.tombstoned)
    result = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(closed)]))

    assert result.complete is True
    assert result.rows == ()
    assert result.snapshot_revision


def test_mixed_generation_or_actionless_active_row_invalidates_whole_snapshot():
    mixed = read_authoritative_trigger_snapshot(
        'owner', firestore_client=_Client([_row(_trigger(generation=2))], generation=3)
    )
    actionless_item = _trigger().model_copy(update={'trigger_condition': {'keywords': ['release']}})
    actionless = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(actionless_item)]))

    assert mixed.complete is False and mixed.failure_reason == 'row_invalid'
    assert actionless.complete is False and actionless.failure_reason == 'row_invalid'


def test_torn_head_read_never_certifies_complete_snapshot():
    result = read_authoritative_trigger_snapshot(
        'owner', firestore_client=_Client([_row(_trigger())], trailing_head=(3, 'head-8', 8))
    )

    assert result.complete is False
    assert result.failure_reason == 'authority_changed'
    assert result.snapshot_revision == ''
    assert result.rows == ()


def test_revision_binds_condition_action_budget_and_canonical_order():
    first = _trigger('a')
    second = _trigger('b')
    baseline = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(second), _row(first)]))
    reordered = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(first), _row(second)]))
    changed_action = first.model_copy(
        update={
            'trigger_condition': {
                'keywords': ['release'],
                'action': {'type': 'agent_prompt', 'prompt': 'A different safe prompt.'},
            }
        }
    )
    changed_condition = first.model_copy(
        update={
            'trigger_condition': {
                'keywords': ['different condition'],
                'action': {'type': 'agent_prompt', 'prompt': 'Find the next release step.'},
            }
        }
    )
    changed_budget = first.model_copy(update={'arguments': {'wakeup_budget_per_day': 3}})

    assert baseline.snapshot_revision == reordered.snapshot_revision
    assert (
        baseline.snapshot_revision
        != read_authoritative_trigger_snapshot(
            'owner', firestore_client=_Client([_row(changed_action), _row(second)])
        ).snapshot_revision
    )
    assert (
        baseline.snapshot_revision
        != read_authoritative_trigger_snapshot(
            'owner', firestore_client=_Client([_row(changed_condition), _row(second)])
        ).snapshot_revision
    )
    assert (
        baseline.snapshot_revision
        != read_authoritative_trigger_snapshot(
            'owner', firestore_client=_Client([_row(changed_budget), _row(second)])
        ).snapshot_revision
    )
