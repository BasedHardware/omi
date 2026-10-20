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
from models.agent_refs import base_ref
from models.memory_apply import memory_content_hash, WriterAdmissionError
from models.memory_evidence import MemoryEvidence, ArtifactPreservationState
from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    LedgerWriteReason,
    default_short_term_expiry,
    normalized_memory_content_key,
)
from models.review import ReviewChange
from config.memory_secret_patterns import SECRET_PATTERNS
from database.dream_dirty import dream_writing


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


def _conversation_refs(edit):
    # Canonical conversation identities cited by this edit. base_ref strips
    # segment citations (conversations/x#seg) down to the durable row id.
    return sorted({base_ref(ref) for ref in edit.evidence if base_ref(ref).partition('/')[0] == 'conversations'})


def _supersede_evidence(uid, edit, edit_key, change):
    """One evidence object per cited conversation, in deterministic order.

    Conversation deletion/reprocessing discovers affected rows through
    MemoryItem.source_ids, which is computed from each evidence object's
    source_id/conversation_id alone; quote_refs are display-only. Binding
    every cited conversation keeps the new active fact inside its sources'
    cohort, so deleting or reprocessing the conversation reaches this row.
    """
    cited = _conversation_refs(edit)
    others = [ref for ref in edit.evidence if base_ref(ref).partition('/')[0] != 'conversations']
    return [
        MemoryEvidence(
            evidence_id='ev_'
            + deterministic_contract_id(
                'dream-supersede-evidence', {'uid': uid, 'key': edit_key, 'conversation': conversation}
            )[:32],
            source_type='agent_conclusion',
            source_id=change.change_id,
            # Canonical evidence stores the bare conversation id: source-cohort
            # discovery matches MemoryItem.source_ids with array_contains on the
            # raw id, never the conversations/<id> ref.
            conversation_id=conversation.partition('/')[2],
            source_version='v1',
            artifact_preservation=ArtifactPreservationState.not_applicable,
            quote_refs=[
                *[{'ref': ref} for ref in others if index == 0],
                *[
                    {'ref': ref}
                    for ref in edit.evidence
                    if base_ref(ref).partition('/')[0] == 'conversations' and base_ref(ref) == conversation
                ],
            ],
        )
        for index, conversation in enumerate(cited)
    ]


def _effective_from(edit, now):
    # A replacement became true when its evidence says it did, not when Dream
    # happened to run. Unstated or malformed times fall back to apply time;
    # a time after `now` cannot be evidenced by already-captured speech.
    raw = (getattr(edit, 'effective_from', '') or '').strip()
    if not raw:
        return now
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return now
    except (TypeError, ValueError):
        return now
    if parsed > now:
        return now
    return parsed


def _replacement_sensitivity_labels(text, inherited):
    """Conservative labels for free-form replacement content.

    Never drop the predecessor's restricted labels, and screen the new text
    with the shared ingestion secret patterns: an inherited-unrestricted label
    set would otherwise clear newly secret-shaped content for vector delivery.
    """
    labels = set(inherited)
    if any(pattern.regex.search(text or '') for pattern in SECRET_PATTERNS):
        labels.add('credential')
    return sorted(labels)


def _background_pass():
    # dream_writing is set only around the scheduled Dream effect loop; the
    # user-accepted Review proposal path runs outside it.
    return bool(dream_writing.get())


def record_change(uid, change, edit, edit_key, *, expected_records=None):
    store.require_enabled(uid)
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change.change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key))
    target_id = edit.target.split('/', 1)[1]
    other_id = edit.other.split('/', 1)[1] if edit.other else None
    # Validators treat a whitespace-only `after` as empty (exactly-one-of
    # other/after); the apply path must make the same decision on the same
    # normalized value or it will try to create a blank replacement tail.
    replacement_text = edit.after.strip() if edit.after else ''
    merging = edit.kind == 'merge_memories'
    if merging and (not other_id or other_id == target_id or not replacement_text):
        raise store.ReviewConflict('A memory merge requires two facts and combined text')
    new_id = (
        'mem_' + deterministic_contract_id('dream-memory-supersede', {'uid': uid, 'key': edit_key})[:32]
        if replacement_text
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
        if blocked and not store.is_user_request(uid):
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
        other = None
        if other_id:
            other = fact(uid, other_id, before[other_id])
            if other.status != MemoryItemStatus.active or any(
                getattr(target, field) != getattr(other, field)
                for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot', 'tier')
            ):
                raise store.ReviewConflict('Replacement must be an active fact for the same subject and attribute')
            if not merging and (other.valid_from or other.captured_at) <= (target.valid_from or target.captured_at):
                raise store.ReviewConflict('Replacement fact must be newer')
        predecessors = [target]
        if merging:
            if other is None:
                raise store.ReviewConflict('Canonical merge sources missing')
            predecessors.append(other)
        inherited_evidence = list({ev.evidence_id: ev for source in predecessors for ev in source.evidence}.values())
        new_evidence: list = []
        if new_id:
            receipt = (
                store.user(uid)
                .collection('memory_deletion_receipts')
                .document(memory_apply_store.privacy_deletion_receipt_id(uid, new_id))
                .get(transaction=tx)
            )
            if before[new_id] is not None or receipt.exists:
                raise store.ReviewConflict('Replacement identity unavailable')
            new_evidence = _supersede_evidence(uid, edit, edit_key, change)
            for existing in new_evidence:
                evidence_ref = store.user(uid).collection('memory_evidence').document(existing.evidence_id)
                if evidence_ref.get(transaction=tx).exists:
                    raise store.ReviewConflict('Replacement evidence identity unavailable')
            # Same ledger fields as an agent fact append; no inherited graph claims.
            effective = _effective_from(edit, now)
            replacement_fields = {
                'memory_id': new_id,
                'content': replacement_text,
                'evidence': [*new_evidence, *inherited_evidence],
                'normalized_content_key': normalized_memory_content_key(replacement_text),
                'content_hash': memory_content_hash(
                    content=replacement_text,
                    evidence_ids=[ev.evidence_id for ev in [*new_evidence, *inherited_evidence]],
                ),
                'captured_at': now,
                'updated_at': now,
                'valid_from': effective,
                'valid_to': None,
                'version': 1,
                'item_revision': 1,
                'superseded_by': None,
                'canonical_memory_id': None,
                'user_asserted': False,
                'write_reason': (
                    # A tail written by the scheduled background pass is the
                    # daily reconciliation channel (rank 300): the request-
                    # serving agent-conclusion reason (rank 400) would outrank
                    # the sweep's own later corrections. A user-accepted Review
                    # proposal keeps the agent-conclusion reason.
                    LedgerWriteReason.daily_reconciliation
                    if _background_pass()
                    else LedgerWriteReason.agent_reusable_conclusion
                ),
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
                'sensitivity_labels': _replacement_sensitivity_labels(
                    replacement_text, [label for source in predecessors for label in source.sensitivity_labels]
                ),
            }
            if target.tier == MemoryLayer.short_term:
                # A fresh tail earns a fresh short-term window from its own
                # capture time. Inheriting the predecessor's expires_at can
                # invalidate the tail outright once that row is past its TTL
                # (expires_at <= captured_at) and would otherwise only ever
                # grant the old row's remaining lifetime.
                replacement_fields['expires_at'] = default_short_term_expiry(now)
            fresh = target.model_copy(update=replacement_fields)
            after[new_id] = fresh.model_dump(mode='python')
        after[target_id] = {
            **before[target_id],
            'status': 'superseded',
            'valid_to': now,
            'updated_at': now,
            'version': target.version + 1,
            'item_revision': target.item_revision + 1,
            'superseded_by': new_id if merging else other_id or new_id,
        }
        if merging and other is not None:
            after[other_id] = {
                **before[other_id],
                'status': 'superseded',
                'valid_to': now,
                'updated_at': now,
                'version': other.version + 1,
                'item_revision': other.item_revision + 1,
                'superseded_by': new_id,
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
            new_evidence=new_evidence or None,
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
            key: (None if key in {target_id, new_id} or (merging and key == other_id) else graph)
            for key, graph in graphs.items()
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
        _, committed = commit_items(
            tx,
            uid,
            f"review:{change_id}:{data['revision'] + 1}:{undone}",
            changed,
            source_generation=journal['source_generation'],
            # Restored rows must carry the reversal commit: the outbox events
            # of this commit are stamped with it, and vector hydration rejects
            # any hit whose projection commit differs from the authoritative
            # row's ledger_commit_id. An unstamped restore would leave the
            # row's events pointing at a commit the row never held, silently
            # dropping it from vector-backed search.
            stamp=True,
        )
        for row in committed:
            destination[row['memory_id']].update(
                ledger_commit_id=row['ledger_commit_id'], ledger_sequence=row['ledger_sequence']
            )
        if undone:
            journal['undone_rows'] = destination
        else:
            # Redo re-stamps the applied state with this reversal's commit;
            # persist it so a later Undo fences against the real stored rows,
            # not the original apply-time stamps.
            journal['after'] = destination
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
