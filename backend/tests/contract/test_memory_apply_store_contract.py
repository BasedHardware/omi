"""Dual-backend contract for the canonical memory apply store (ADR-0044 facade + ADR-0002 port).

`database/memory_apply_store.py` is the write boundary of the canonical memory pipeline: one
transaction turns a proposed patch into a materialized memory item, a ledger commit, an advanced
control head, a trusted state-head document and two outbox events — or into nothing at all.

    transaction   `_apply_long_term_patch_firestore_transaction` re-reads control state, the
                  operation and the evidence INSIDE the transaction and never trusts the caller's
                  snapshot (the module's own docstring says so). Three consequences if the read is not
                  part of the write:
                    - a replayed apply materializes the memory a SECOND time, so the user sees a
                      duplicate memory that no later deduplication removes — it has a different id and
                      a valid commit behind it;
                    - a patch written against a superseded account generation lands anyway, which is
                      how content from a deleted-and-recreated account reappears;
                    - a partial apply leaves a commit with no memory item, or a memory item pointing at
                      a commit that was never written, and the projection worker then loops on it.

**Where this suite comes from, and why it exists.** The same proof already existed as
`scripts/firestore_python_apply_emulator_test.py` — a hand-run script, against the Firestore emulator
only, that no lane executes. The unit suite next to it (`tests/unit/test_memory_apply_store.py`)
covers far more, but it stubs `google.cloud.firestore_v1.transactional` with a fake and drives a
`_FakeTransaction`: it proves the module's logic, not that a transaction survives the storage layer we
deploy. Neither answered the question this file asks, which is whether the Mongo leg does the same
thing. So the script's assertions are re-expressed here, on both backends, and the fences it never
exercised are added.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
Requires ``MEMORY_ENABLED=on``: every entry point is fenced by `_require_canonical_intake_enabled`,
which raises `CanonicalMemoryIntakePausedError` when canonical intake is globally paused.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('MEMORY_ENABLED', '').strip().lower() != 'on',
    reason='canonical memory intake is fenced by MEMORY_ENABLED=on',
)


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def apply_case(bind_store):
    """A control state, one preserved evidence record, and a matching operation + patch payload."""
    from database.memory_collections import MemoryCollections
    from models.memory_apply import MemoryControlState
    from models.memory_contracts import DurablePatchDecision, LifecycleState
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence
    from models.memory_operations import MemoryOperation, MemoryOperationType

    run = uuid.uuid4().hex[:8]
    uid = f'apply-{run}'
    collections = MemoryCollections(uid=uid)

    control = MemoryControlState(uid=uid, head_commit_id='head0', account_generation=3, source_generation=5)
    evidence = MemoryEvidence(
        evidence_id=f'ev-{run}',
        source_type='conversation',
        source_id=f'conv-{run}',
        source_version='v1',
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    memory_text = 'The user prefers concise updates.'
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f'packet-{run}',
        target_memory_id=None,
        evidence_ids=[evidence.evidence_id],
        logical_payload={'decision': 'add', 'memory_text': memory_text, 'result_status': 'active'},
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    patch_payload = {
        'patch_id': f'patch-{run}',
        'packet_id': f'packet-{run}',
        'run_id': f'run-{run}',
        'observed_head_commit_id': control.head_commit_id,
        'idempotency_key': f'idem-{run}',
        'decision': DurablePatchDecision.add.value,
        'result_status': LifecycleState.active.value,
        'evidence_ids': [evidence.evidence_id],
        'memory_text': memory_text,
        'confidence': 'medium',
        'relationship_to_user': 'self',
        'subject_entity_id': 'user',
        'subject_label': 'the user',
        'aboutness': 'primary_user',
    }

    bind_store.set(collections.memory_apply_control_state, control.model_dump(mode='json'))
    bind_store.set(f'{collections.memory_evidence}/{evidence.evidence_id}', evidence.model_dump(mode='json'))

    yield {
        'uid': uid,
        'run': run,
        'store': bind_store,
        'collections': collections,
        'control': control,
        'operation': operation,
        'patch_payload': patch_payload,
        'memory_text': memory_text,
    }

    for collection in (
        collections.memory_items,
        collections.memory_operations,
        collections.memory_commits,
        collections.memory_outbox,
        collections.memory_evidence,
        f'users/{uid}/memory_state',
        f'users/{uid}/memory_apply_control',
    ):
        for document in bind_store.query(collection):
            bind_store.delete(document.path)


def _apply(apply_case, **overrides):
    import database.memory_apply_store as apply_store

    kwargs = {
        'uid': apply_case['uid'],
        'operation_id': apply_case['operation'].operation_id,
        'patch_payload': apply_case['patch_payload'],
        'proposed_operation': apply_case['operation'],
        'db_client': _client(),
    }
    kwargs.update(overrides)
    return apply_store.apply_long_term_patch_firestore(**kwargs)


def _doc(apply_case, path):
    stored = apply_case['store'].get(path)
    return stored.data if stored is not None and stored.exists else None


# --- transaction: one apply writes the whole set, or none of it ----------------------------------


def test_a_committed_apply_materializes_the_memory_and_advances_the_head(apply_case):
    """The whole set lands together. The pieces are useless apart: a commit with no memory item is a
    history entry for something the user cannot see, and a memory item whose `ledger_commit_id` names
    a commit that was never written is a row the projection worker retries forever."""
    from models.memory_apply import ApplyStatus

    collections = apply_case['collections']

    result = _apply(apply_case)

    assert result.status == ApplyStatus.committed, result.reason
    assert len(result.memory_items) == 1
    head = result.control_state.head_commit_id

    assert _doc(apply_case, collections.memory_apply_control_state)['head_commit_id'] == head
    stored_memory = _doc(apply_case, f'{collections.memory_items}/{result.memory_items[0].memory_id}')
    assert stored_memory['uid'] == apply_case['uid']
    assert stored_memory['ledger_commit_id'] == head
    stored_commit = _doc(apply_case, f'{collections.memory_commits}/{head}')
    assert stored_commit['memory_item_ids'] == [result.memory_items[0].memory_id]


def test_the_committed_memory_keeps_the_account_generation_fence(apply_case):
    """The generation is stamped onto the row, and it is what a later account cutover uses to tell
    content of THIS account from content of the one before it. A row that loses it survives a deletion
    the user asked for."""
    result = _apply(apply_case)

    stored = _doc(apply_case, f"{apply_case['collections'].memory_items}/{result.memory_items[0].memory_id}")
    assert stored['account_generation'] == apply_case['control'].account_generation


def test_the_operation_records_its_own_commit(apply_case):
    """The operation document is the replay key. Without the committed head written back onto it, the
    next attempt cannot tell "already done" from "never started"."""
    collections = apply_case['collections']

    result = _apply(apply_case)

    stored = _doc(apply_case, f"{collections.memory_operations}/{apply_case['operation'].operation_id}")
    assert stored['status'] == 'committed'
    assert stored['committed_head_commit_id'] == result.control_state.head_commit_id


def test_the_trusted_state_head_is_written_for_readers_outside_the_pipeline(apply_case):
    """`users/{uid}/memory_state/head` is what the trusted account-generation reader consults; other
    subsystems trust it precisely because the apply transaction wrote it. A head that lags is a reader
    that fences on a generation the pipeline has already left behind."""
    from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

    result = _apply(apply_case)

    stored = _doc(apply_case, apply_case['collections'].memory_state_head)
    assert stored['uid'] == apply_case['uid']
    assert stored['head_commit_id'] == result.control_state.head_commit_id
    assert stored['account_generation'] == result.control_state.account_generation

    trusted = read_memory_v3_trusted_account_generation(uid=apply_case['uid'], db_client=_client())
    assert trusted.read_error_reason is None
    assert trusted.head_commit_id == result.control_state.head_commit_id


def test_both_outbox_events_are_enqueued_in_the_same_transaction(apply_case):
    """Projection and vector sync are how the memory becomes searchable and retrievable. An event that
    is not written in the same transaction as the commit is a memory that exists and cannot be found —
    with nothing anywhere reporting a failure."""
    collections = apply_case['collections']

    result = _apply(apply_case)

    assert len(result.outbox_events) == 2
    stored = [_doc(apply_case, f'{collections.memory_outbox}/{event.event_id}') for event in result.outbox_events]
    assert sorted(event['event_type'] for event in stored) == ['projection_sync', 'vector_sync']


# --- transaction: the fences ----------------------------------------------------------------------


def test_replaying_the_same_apply_is_an_idempotent_skip(apply_case):
    """The read the transaction makes of the OPERATION document, and the most valuable thing it buys.
    A retry after a timeout is the ordinary case; without the read it materializes the memory a second
    time under a new id, and the user sees a duplicate that nothing later removes."""
    from models.memory_apply import ApplyStatus

    first = _apply(apply_case)
    replay = _apply(apply_case, proposed_operation=None)

    assert replay.status == ApplyStatus.idempotent_skip
    assert replay.operation.committed_memory_item_ids == [first.memory_items[0].memory_id]
    items = list(apply_case['store'].query(apply_case['collections'].memory_items))
    assert len(items) == 1, 'the replay must not materialize a second memory'


def test_a_patch_written_against_a_superseded_account_generation_is_refused(apply_case):
    """The generation fence, read from storage rather than taken from the caller. A stale generation is
    what an apply in flight across an account cutover carries; letting it land is how content from the
    previous account reappears in the new one."""
    from models.memory_apply import ApplyStatus

    collections = apply_case['collections']
    apply_case['store'].set(
        collections.memory_apply_control_state,
        {**_doc(apply_case, collections.memory_apply_control_state), 'account_generation': 9},
    )

    result = _apply(apply_case)

    assert result.status == ApplyStatus.generation_mismatch
    assert list(apply_case['store'].query(collections.memory_items)) == [], 'nothing may be materialized'
    assert _doc(apply_case, collections.memory_apply_control_state)['head_commit_id'] == 'head0'


def test_a_patch_observing_a_head_that_has_moved_is_told_to_retry(apply_case):
    """The head fence. The caller planned against a head that is no longer current, so its plan may be
    built on state that changed; the transaction refuses and asks for a replan rather than committing
    a patch onto a history it did not read."""
    from models.memory_apply import ApplyStatus

    collections = apply_case['collections']
    apply_case['store'].set(
        collections.memory_apply_control_state,
        {**_doc(apply_case, collections.memory_apply_control_state), 'head_commit_id': 'head-moved'},
    )

    result = _apply(apply_case)

    assert result.status == ApplyStatus.retryable_head_mismatch
    assert list(apply_case['store'].query(collections.memory_items)) == []


def test_an_apply_for_an_operation_that_does_not_exist_and_is_not_proposed_is_refused(apply_case):
    """The operation is read from storage. A caller that neither stored it nor proposed it is asking
    the pipeline to commit something with no provenance."""
    import database.memory_apply_store as apply_store

    with pytest.raises(apply_store.MissingMemoryDocument):
        _apply(apply_case, proposed_operation=None)

    assert list(apply_case['store'].query(apply_case['collections'].memory_items)) == []


def test_an_operation_belonging_to_another_user_is_refused(apply_case):
    """Read back and compared inside the transaction. Applying another user's operation under this uid
    would write their memory into this account."""
    import database.memory_apply_store as apply_store

    foreign = apply_case['operation'].model_copy(update={'uid': f"someone-else-{apply_case['run']}"})

    with pytest.raises(apply_store.MemoryFirestoreApplyError):
        _apply(apply_case, proposed_operation=foreign)

    assert list(apply_case['store'].query(apply_case['collections'].memory_items)) == []


def test_intake_that_is_globally_paused_refuses_before_touching_storage(apply_case, monkeypatch):
    """`_require_canonical_intake_enabled` fences every entry point. The pause is the deployment-level
    off switch; an apply that slips past it writes into a pipeline nobody is draining."""
    import database.memory_apply_store as apply_store

    monkeypatch.setenv('MEMORY_ENABLED', 'off')

    with pytest.raises(apply_store.CanonicalMemoryIntakePausedError):
        _apply(apply_case)

    assert list(apply_case['store'].query(apply_case['collections'].memory_items)) == []
