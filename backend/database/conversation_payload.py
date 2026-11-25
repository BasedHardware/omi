"""Atomic storage for bounded conversation payloads.

Callers own authorization, deletion and revision fences. Both the parent read
and those fence reads belong in the same transaction as any publication.
"""

import os
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.field_path import FieldPath

from models.conversation_enums import ConversationSource
from utils.conversation_payload import (
    CHUNK_BYTES,
    PAYLOAD_FIELD,
    PROJECTION_BYTES,
    ConversationProjectionTooLarge,
    InvalidConversationPayload,
    hydrate_conversation,
    pack_conversation,
    payload_descriptor,
)
from utils.firestore_document_size import estimate_firestore_document_bytes
from utils.other.list_budget import ListReadBudgetExhausted, budgeted_document_get, budgeted_get_all

PAYLOAD_CHUNKS = 'conversation_payload_chunks'
# Limit the single-row atomic path to 2 MiB of new chunks, with the same bound
# on retiring old chunks. Multi-row callers must also budget the entire commit.
MAX_ATOMIC_CHUNKS = 8


def integration_payload_writes_enabled(row):
    return (
        row.get('source') == ConversationSource.external_integration
        and os.getenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES') == 'on'
    )


def v3_payload_writes_enabled():
    return os.getenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES') == 'on'


def _chunk_refs(ref, parent):
    if PAYLOAD_FIELD not in parent:
        return []
    generation, size, _ = payload_descriptor(parent[PAYLOAD_FIELD])
    count = (size + CHUNK_BYTES - 1) // CHUNK_BYTES
    if count > MAX_ATOMIC_CHUNKS:
        raise ConversationProjectionTooLarge('conversation payload exceeds the atomic chunk budget')
    collection = ref.collection(PAYLOAD_CHUNKS)
    return [collection.document(f'{generation}-{index:08d}') for index in range(count)]


def read_conversation_payload(
    client, transaction, snapshot, *, read_budget=None, field_paths=None, max_wire_bytes=None
):
    """Hydrate prepared values from the same authorized transaction snapshot."""
    parent = snapshot.to_dict()
    if parent is None or PAYLOAD_FIELD not in parent:
        return parent

    if max_wire_bytes is not None and payload_descriptor(parent[PAYLOAD_FIELD])[1] > max_wire_bytes:
        raise ConversationProjectionTooLarge('conversation payload exceeds the reader byte budget')
    refs = _chunk_refs(snapshot.reference, parent)
    if read_budget is not None and len(refs) > read_budget.remaining_documents:
        read_budget.mark_exhausted('documents')
        raise ListReadBudgetExhausted('documents')
    # BatchGet does not guarantee request order.
    chunks = {
        chunk.reference.id: (chunk.to_dict() or {}).get('data')
        for chunk in budgeted_get_all(client, refs, read_budget, transaction=transaction)
    }
    if any(ref.id not in chunks for ref in refs):
        raise InvalidConversationPayload('conversation payload chunk is unavailable')
    hydrated = hydrate_conversation(parent, (chunks[ref.id] for ref in refs), client=client)
    if field_paths is None:
        return hydrated

    # Firestore applied the mask to the parent. Apply it to the spilled fields
    # too, including nested fields such as structured.overview.
    spilled = {key: hydrated[key] for key in hydrated.keys() - parent.keys()}
    parent.pop(PAYLOAD_FIELD)
    for name in field_paths:
        path = FieldPath.from_api_repr(name)
        try:
            value = _helpers.get_field_value(spilled, path)
        except (KeyError, TypeError):
            continue
        _helpers.set_field_value(parent, path, value)
    return parent


def get_conversation_with_payload(client, ref):
    """Return prepared data and its parent snapshot for an authorized point read."""
    snapshot = ref.get()
    parent = snapshot.to_dict()
    if parent is None or PAYLOAD_FIELD not in parent:
        return parent, snapshot

    @firestore.transactional
    def load(transaction):
        # Read a fresh parent together with its chunks. The first generation
        # may have been retired between the initial point read and this read.
        current = ref.get(transaction=transaction)
        return read_conversation_payload(client, transaction, current), current

    return load(client.transaction(read_only=True))


def read_list_conversation_payload(client, snapshot, budget, *, field_paths=None):
    """Read chunks for the selected list revision, preserving its mask and budget."""

    @firestore.transactional
    def load(transaction):
        current = budgeted_document_get(snapshot.reference, budget, field_paths=field_paths, transaction=transaction)
        if not current.exists or current.update_time != snapshot.update_time:
            return None
        return read_conversation_payload(client, transaction, current, read_budget=budget, field_paths=field_paths)

    return load(client.transaction(read_only=True))


def stage_conversation_payload(
    transaction, snapshot, prepared, *, spill_fields, allow_promotion=False, retire_children=None
):
    """Stage a full prepared row and its chunks alongside the caller's fenced writes.

    The switch controls the first spill. Compatible binaries continue to read,
    replace and erase already-spilled rows when promotion is disabled.
    """
    ref = snapshot.reference
    previous = snapshot.to_dict() or {}
    old_refs = _chunk_refs(ref, previous)
    # The Home commit hook sees only inline fields. Preserve the full-write
    # invalidation stamp when the transcript or corrections move to chunks.
    if {'transcript_segments', 'user_corrections'} & prepared.keys():
        prepared = {**prepared, 'home_content_invalidated': 'structured' not in prepared}
    write = pack_conversation(prepared, ref.path, spill_fields=spill_fields, generation=uuid4().hex)
    if write.chunks and not old_refs and not allow_promotion:
        raise ConversationProjectionTooLarge('conversation payload promotion is disabled')
    cost = _stage_replacement_chunks(transaction, ref, previous, old_refs, write)
    if retire_children is not None:
        referenced = set(old_refs)
        for child in retire_children:
            if child not in referenced:
                transaction.delete(child)
    if snapshot.exists:
        transaction.set(ref, write.parent)
    else:
        transaction.create(ref, write.parent)
    return cost


def stage_conversation_payload_patch(transaction, snapshot, hydrated, patch, *, overflow_fields, allow_promotion=False):
    """Apply a whole-field patch after the caller hydrates and authorizes the snapshot.

    Keep the current generation when only inline fields change and they still fit.
    """
    ref = snapshot.reference
    previous = snapshot.to_dict() or {}
    old_refs = _chunk_refs(ref, previous)
    if not old_refs and not allow_promotion:
        raise ValueError('expected an existing conversation payload or promotion permission')
    spilled = hydrated.keys() - previous.keys()
    deletes = {key for key, value in patch.items() if value is firestore.DELETE_FIELD}
    projected = {
        key: value for key, value in {**previous, **patch}.items() if key not in spilled and key not in deletes
    }
    inline_fits = estimate_firestore_document_bytes(projected, ref.path) <= PROJECTION_BYTES
    if inline_fits and not (spilled & patch.keys()):
        transaction.update(ref, patch)
        return 0, 0
    if not inline_fits:
        spilled |= overflow_fields
    logical = {key: value for key, value in {**hydrated, **patch}.items() if key not in deletes}
    write = pack_conversation(
        logical, ref.path, spill_fields=spilled, generation=uuid4().hex, force_spill=bool(spilled & logical.keys())
    )
    moved = logical.keys() - write.parent.keys()
    inline_patch = {key: value for key, value in patch.items() if key not in moved}
    inline_patch.update({key: write.parent[key] for key in spilled & write.parent.keys()})
    inline_patch.update({key: firestore.DELETE_FIELD for key in (moved | deletes) & previous.keys()})
    inline_patch[PAYLOAD_FIELD] = write.parent.get(PAYLOAD_FIELD, firestore.DELETE_FIELD)
    cost = _stage_replacement_chunks(transaction, ref, previous, old_refs, write)
    transaction.update(ref, inline_patch)
    return cost


def stage_conversation_notes_patch(transaction, snapshot, hydrated, patch):
    """Apply a patch with direct children of structured to a chunked row."""
    structured = dict(hydrated.get('structured') or {})
    row_patch = {}
    for path, value in patch.items():
        if path.startswith('structured.'):
            key = path.removeprefix('structured.')
            if value is firestore.DELETE_FIELD:
                structured.pop(key, None)
            else:
                structured[key] = value
        else:
            row_patch[path] = value
    stage_conversation_payload_patch(
        transaction, snapshot, hydrated, {**row_patch, 'structured': structured}, overflow_fields={'structured'}
    )


def _stage_replacement_chunks(transaction, ref, previous, old_refs, write):
    new_refs = _chunk_refs(ref, write.parent)
    # Validate the whole chunk set before staging, and create immutable chunks.
    for chunk_ref, chunk in zip(new_refs, write.chunks, strict=True):
        transaction.create(chunk_ref, {'data': chunk})
    for chunk_ref in old_refs:
        transaction.delete(chunk_ref)
    retired_bytes = payload_descriptor(previous[PAYLOAD_FIELD])[1] if old_refs else 0
    return len(old_refs) + len(new_refs), retired_bytes + sum(map(len, write.chunks))


def read_payload_children_for_delete(transaction, ref):
    """Enumerate children before staging writes, even with a broken descriptor."""
    collection = ref.collection(PAYLOAD_CHUNKS)
    chunks = list(collection.limit(MAX_ATOMIC_CHUNKS + 1).stream(transaction=transaction))
    if len(chunks) > MAX_ATOMIC_CHUNKS:
        raise ConversationProjectionTooLarge('conversation payload requires recursive erasure')
    size = sum(estimate_firestore_document_bytes(chunk.to_dict() or {}, chunk.reference.path) for chunk in chunks)
    return [chunk.reference for chunk in chunks], size
