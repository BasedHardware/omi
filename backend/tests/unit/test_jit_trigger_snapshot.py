from datetime import datetime, timedelta, timezone

import pytest

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
from utils.memory.jit_trigger_snapshot import (
    _budget_authority,
    is_authoritative_trigger_for_paid_work,
    read_authoritative_trigger_snapshot,
)

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def test_budget_authority_uses_profile_timezone_across_local_midnight_and_dst():
    class _ProfileClient:
        def document(self, path):
            assert path == 'users/owner'
            return _Document(_Snapshot('owner', {'time_zone': 'America/Los_Angeles'}))

    # 05:30 UTC is already Aug 24 in New York but still Aug 23 in Los Angeles.
    assert _budget_authority('owner', datetime(2026, 8, 24, 5, 30, tzinfo=timezone.utc), _ProfileClient()) == (
        '2026-08-23',
        'America/Los_Angeles',
    )
    # The DST jump does not change the local-day contract.
    assert _budget_authority('owner', datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc), _ProfileClient()) == (
        '2026-03-08',
        'America/Los_Angeles',
    )


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
    def __init__(self, rows, generation=3, trailing_head=None, *, missing_head=False, head_error=False):
        self.rows = rows
        self.generation = generation
        self.trailing_head = trailing_head
        self.missing_head = missing_head
        self.head_error = head_error
        self.head_reads = 0

    def document(self, _path):
        self.head_reads += 1
        if self.head_error:
            raise RuntimeError('state head read failed')
        if self.head_reads > 1 and self.trailing_head:
            generation, head_commit_id, commit_sequence = self.trailing_head
        elif self.missing_head:
            return _Document(_Snapshot('head', None, exists=False))
        else:
            generation, head_commit_id, commit_sequence = (self.generation, 'head-7', 7)
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
        arguments={'wakeup_budget_per_day': 1},
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
    assert result.rows[0].wakeup_budget_per_day == 1
    assert result.rows[0].snoozed_until is None


def test_snapshot_carries_snooze_and_paid_authority_resumes_only_after_expiry():
    snoozed_until = NOW + timedelta(days=2)
    base_trigger = _trigger()
    trigger = base_trigger.model_copy(
        update={
            'arguments': {
                **base_trigger.arguments,
                'jit_trigger_feedback': {
                    'snoozed_until': snoozed_until.isoformat(),
                },
            }
        }
    )

    result = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(trigger)]))

    assert result.complete is True
    assert result.rows[0].snoozed_until == snoozed_until
    assert is_authoritative_trigger_for_paid_work(trigger, NOW + timedelta(days=1)) is False
    assert is_authoritative_trigger_for_paid_work(trigger, snoozed_until) is True
    assert (
        result.snapshot_revision
        != read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(_trigger())])).snapshot_revision
    )


def test_malformed_snooze_invalidates_snapshot_and_paid_authority():
    trigger = _trigger().model_copy(update={'arguments': {'jit_trigger_feedback': {'snoozed_until': 'not-a-time'}}})

    result = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([_row(trigger)]))

    assert result.complete is False
    assert result.failure_reason == 'row_invalid'
    assert is_authoritative_trigger_for_paid_work(trigger, NOW) is False


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


def test_missing_head_returns_complete_empty_watchlist():
    client = _Client([], missing_head=True)
    result = read_authoritative_trigger_snapshot('owner', firestore_client=client)

    assert result.complete is True
    assert result.owner_id == 'owner'
    assert result.account_generation == 0
    assert result.head_commit_id == ''
    assert result.commit_sequence == 0
    assert result.rows == ()
    assert result.failure_reason is None
    assert len(result.snapshot_revision) == 64
    assert client.head_reads == 3, 'absence must be fenced by a trailing re-read and budget authority read'


def test_empty_watchlist_revision_is_stable_and_owner_bound():
    first = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([], missing_head=True))
    second = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([], missing_head=True))
    other_owner = read_authoritative_trigger_snapshot('stranger', firestore_client=_Client([], missing_head=True))

    assert first.snapshot_revision == second.snapshot_revision
    assert first.snapshot_revision != other_owner.snapshot_revision


def test_head_appearing_mid_read_never_certifies_empty_generation():
    result = read_authoritative_trigger_snapshot(
        'owner', firestore_client=_Client([], missing_head=True, trailing_head=(3, 'head-7', 7))
    )

    assert result.complete is False
    assert result.failure_reason == 'generation_unavailable'
    assert result.snapshot_revision == ''
    assert result.rows == ()


def test_unreadable_head_stays_incomplete():
    result = read_authoritative_trigger_snapshot('owner', firestore_client=_Client([], head_error=True))

    assert result.complete is False
    assert result.failure_reason == 'generation_unavailable'


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
    invalid_budget = read_authoritative_trigger_snapshot(
        'owner', firestore_client=_Client([_row(changed_budget), _row(second)])
    )
    assert invalid_budget.complete is False
    assert invalid_budget.failure_reason == 'row_invalid'


@pytest.mark.parametrize("arguments", [{}, {"wakeup_budget_per_day": 0}, {"wakeup_budget_per_day": 2}])
def test_missing_zero_or_nonpolicy_trigger_budget_invalidates_the_snapshot(arguments):
    invalid = _trigger().model_copy(update={"arguments": arguments})

    result = read_authoritative_trigger_snapshot("owner", firestore_client=_Client([_row(invalid)]))

    assert result.complete is False
    assert result.failure_reason == "row_invalid"


def test_embedding_trigger_is_nonactionable_until_the_policy_attests_a_real_local_scorer():
    embedding = _trigger().model_copy(
        update={
            "trigger_condition": {
                "embedding": {
                    "prototype_id": "release-review",
                    "prototype_revision": "prototype-v1",
                    "model_id": "local-embedder",
                    "model_version": "v1",
                    "language": "en",
                    "min_similarity": 0.82,
                },
                "action": {"type": "agent_prompt", "prompt": "Find the next release step."},
            }
        }
    )

    result = read_authoritative_trigger_snapshot("owner", firestore_client=_Client([_row(embedding)]))

    assert result.complete is False
    assert result.failure_reason == "row_invalid"


def test_purged_or_evidence_less_active_trigger_invalidates_the_snapshot():
    trigger = _trigger()
    for invalid in (
        trigger.model_copy(update={"source_state": SourceState.purged}),
        trigger.model_copy(update={"evidence": []}),
    ):
        result = read_authoritative_trigger_snapshot("owner", firestore_client=_Client([_row(invalid)]))
        assert result.complete is False
        assert result.failure_reason == "row_invalid"
