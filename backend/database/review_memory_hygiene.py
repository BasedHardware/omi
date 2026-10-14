"""Atomic reversible canonical fact lifecycle edits, with Dream's Review journal.

Retirement closes a row as superseded history without deleting it. Replacement
links that history to an existing newer fact or a new ledger tail. Undo restores
all prior row fields and graph assertions; a new tail remains closed history.
"""

from copy import deepcopy
from typing import Any
from datetime import datetime, timezone

from google.cloud import firestore

from database import memory_apply_store, memory_review_apply, review_store as store
from database.read_boundary import parse_payload_strict
from database.legal_holds import DestructiveOperationInProgress, LegalHoldAuthorityUnavailable
from models.memory_apply import memory_content_hash, WriterAdmissionError
from models.memory_evidence import MemoryEvidence, ArtifactPreservationState
from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    LedgerWriteReason,
    normalized_memory_content_key,
)
from models.review import ReviewChange


def fact(uid, key, raw):
    if raw is None:
        raise store.ReviewConflict('Canonical memory unavailable')
    row = parse_payload_strict(MemoryItem, raw, document_path=f'users/{uid}/memory_items/{key}')
    if (
        row.uid != uid
        or row.memory_id != key
        or row.kind != MemoryKind.fact
        or row.ledger_schema_version != 'knowledge_ledger.v1'
    ):
        raise store.ReviewConflict('Only canonical ledger facts support memory hygiene')
    return row


def commit_items(tx, uid, operation_id, items, **kwargs):
    try:
        return memory_review_apply.commit_review_memory_items(tx, store.client(), uid, operation_id, items, **kwargs)
    except (
        memory_apply_store.MemoryFirestoreApplyError,
        WriterAdmissionError,
        DestructiveOperationInProgress,
        LegalHoldAuthorityUnavailable,
    ) as exc:
        raise store.ReviewConflict('Memory lifecycle authority changed or is unavailable') from exc


def record_change(uid, change, edit, edit_key, *, expected_records=None):
    store.require_enabled()
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change.change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key))
    target_id = edit.target.split('/', 1)[1]
    other_id = edit.other.split('/', 1)[1] if edit.other else None
    new_id = (
        'mem_' + deterministic_contract_id('dream-memory-supersede', {'uid': uid, 'key': edit_key})[:32]
        if edit.after
        else None
    )

    @firestore.transactional
    def apply(tx):
        prior = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        blocked = marker.get(transaction=tx).exists
        if prior:
            if prior['edit_key'] != edit_key or prior['memory_hygiene']['edit'] != edit.model_dump(
                exclude={'value', 'why_it_matters'}
            ):
                raise store.ReviewConflict('Memory change identity conflict')
            return parse_payload_strict(ReviewChange, prior['change'], document_path='review_changes')
        store.validate_records(uid, tx, expected_records)
        if blocked:
            raise store.ReviewConflict('Memory operation was undone')
        keys = [target_id, *([other_id] if other_id else []), *([new_id] if new_id else [])]
        before = {
            key: store.user(uid).collection('memory_items').document(key).get(transaction=tx).to_dict() for key in keys
        }
        graphs = {
            key: store.user(uid).collection('memory_graph_assertions').document(key).get(transaction=tx).to_dict()
            for key in keys
        }
        target = fact(uid, target_id, before[target_id])
        if target.status != MemoryItemStatus.active:
            raise store.ReviewConflict('Memory has a newer edit')
        now = max(datetime.now(timezone.utc), target.updated_at, target.valid_from or target.captured_at)
        after = deepcopy(before)
        if other_id:
            other = fact(uid, other_id, before[other_id])
            if other.status != MemoryItemStatus.active or any(
                getattr(target, field) != getattr(other, field)
                for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot')
            ):
                raise store.ReviewConflict('Replacement must be an active fact for the same subject and attribute')
            if (other.valid_from or other.captured_at) <= (target.valid_from or target.captured_at):
                raise store.ReviewConflict('Replacement fact must be newer')
        evidence = None
        if new_id:
            receipt = (
                store.user(uid)
                .collection('memory_deletion_receipts')
                .document(memory_apply_store.privacy_deletion_receipt_id(uid, new_id))
                .get(transaction=tx)
            )
            if before[new_id] is not None or receipt.exists:
                raise store.ReviewConflict('Replacement identity unavailable')
            evidence = MemoryEvidence(
                evidence_id='ev_'
                + deterministic_contract_id('dream-supersede-evidence', {'uid': uid, 'key': edit_key})[:32],
                source_type='agent_conclusion',
                source_id=change.change_id,
                source_version='v1',
                artifact_preservation=ArtifactPreservationState.not_applicable,
                quote_refs=[{'ref': ev} for ev in edit.evidence],
            )
            evidence_ref = store.user(uid).collection('memory_evidence').document(evidence.evidence_id)
            if evidence_ref.get(transaction=tx).exists:
                raise store.ReviewConflict('Replacement evidence identity unavailable')
            # Same ledger fields as an agent fact append; no inherited graph claims.
            fresh = target.model_copy(
                update={
                    'memory_id': new_id,
                    'content': edit.after,
                    'evidence': [evidence, *target.evidence],
                    'normalized_content_key': normalized_memory_content_key(edit.after),
                    'content_hash': memory_content_hash(
                        content=edit.after, evidence_ids=[ev.evidence_id for ev in [evidence, *target.evidence]]
                    ),
                    'captured_at': now,
                    'updated_at': now,
                    'valid_from': now,
                    'valid_to': None,
                    'version': 1,
                    'item_revision': 1,
                    'superseded_by': None,
                    'canonical_memory_id': None,
                    'user_asserted': False,
                    'write_reason': LedgerWriteReason.agent_reusable_conclusion,
                    'intent_backed': True,
                    'body': None,
                    'predicate': None,
                    'arguments': {},
                    'promotion': None,
                    'graph_ready': False,
                    'kg_extracted': False,
                    'graph_assertion_id': None,
                    'graph_plan_hash': None,
                    'source_commit_id': None,
                    'source_commit_sequence': None,
                }
            )
            after[new_id] = fresh.model_dump(mode='python')
        after[target_id] = {
            **before[target_id],
            'status': 'superseded',
            'valid_to': now,
            'updated_at': now,
            'version': target.version + 1,
            'item_revision': target.item_revision + 1,
            'superseded_by': other_id or new_id,
        }
        # Commit only changed rows; existing newer facts stay byte-for-byte intact.
        changed = [fact(uid, key, row) for key, row in after.items() if row != before[key]]
        generation, committed = commit_items(
            tx,
            uid,
            'review:' + change.change_id,
            changed,
            source_generation=None,
            stamp=True,
            new_evidence=evidence,
        )
        for row in committed:
            key = row['memory_id']
            if before[key] is None:
                after[key] = row
            else:
                # Lifecycle edits own only their status/time/lineage fields.
                # Preserve absent optional and future storage fields too.
                after[key].update(ledger_commit_id=row['ledger_commit_id'], ledger_sequence=row['ledger_sequence'])
                tx.set(store.user(uid).collection('memory_items').document(key), after[key])
        data: dict[str, Any] = {
            'change': change.model_dump(mode='python'),
            'created_at': change.created_at,
            'edit_key': edit_key,
            'memory_hygiene': {
                'edit': edit.model_dump(exclude={'value', 'why_it_matters'}),
                'before': before,
                'after': after,
                'graphs': graphs,
                'source_generation': generation,
            },
            'revision': 0,
        }
        data['memory_hygiene']['after_graphs'] = {
            key: (None if key == target_id or key == new_id else graph) for key, graph in graphs.items()
        }
        tx.set(ref, store.encode_doc(uid, data))
        return change

    return apply(store.client().transaction())


def set_undone(uid, change_id, undone):
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change_id))

    @firestore.transactional
    def reverse(tx):
        data = store.require_doc(uid, ref.get(transaction=tx).to_dict())
        if data['change']['undone'] == undone:
            return parse_payload_strict(ReviewChange, data['change'], document_path='review_changes')
        journal = data['memory_hygiene']
        expected = journal['after'] if undone else journal['undone_rows']
        destination = deepcopy(journal['before'] if undone else journal['after'])
        rows = {
            key: store.user(uid).collection('memory_items').document(key).get(transaction=tx).to_dict()
            for key in expected
        }
        current_graphs = {
            key: store.user(uid).collection('memory_graph_assertions').document(key).get(transaction=tx).to_dict()
            for key in expected
        }
        expected_graphs = journal['after_graphs'] if undone else journal['graphs']
        if rows != expected or current_graphs != expected_graphs:
            raise store.ReviewConflict('Memory has a newer edit')
        # New replacement tails are retained as closed history, never deleted.
        for key, raw in destination.items():
            if raw is None:
                destination[key] = {
                    **rows[key],
                    'status': 'superseded',
                    'valid_to': rows[key]['valid_from'] or rows[key]['captured_at'],
                }
        changed = [fact(uid, key, raw) for key, raw in destination.items() if raw != rows[key]]
        if not changed:
            raise store.ReviewConflict('Memory reversal unavailable')
        commit_items(
            tx,
            uid,
            f"review:{change_id}:{data['revision'] + 1}:{undone}",
            changed,
            source_generation=journal['source_generation'],
        )
        if undone:
            journal['undone_rows'] = destination
        desired_graphs = journal['graphs'] if undone else journal['after_graphs']
        for key, graph in desired_graphs.items():
            graph_ref = store.user(uid).collection('memory_graph_assertions').document(key)
            if graph is None:
                tx.delete(graph_ref)
            else:
                tx.set(graph_ref, graph)
        for key, raw in destination.items():
            if raw != rows[key]:
                tx.set(store.user(uid).collection('memory_items').document(key), raw)
        data.update(change={**data['change'], 'undone': undone}, revision=data['revision'] + 1)
        if undone:
            marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(data['edit_key']))
            tx.set(
                marker, {'edit_key': data['edit_key'], 'change_id': change_id, 'created_at': datetime.now(timezone.utc)}
            )
        tx.set(ref, store.encode_doc(uid, data))
        return parse_payload_strict(ReviewChange, data['change'], document_path='review_changes')

    return reverse(store.client().transaction())
