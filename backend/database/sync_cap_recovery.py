"""Piece-lineage proof committed in the exact conversation-ingest transaction."""

import time
from typing import Any

from database._client import get_firestore_client
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from database.legal_holds import external_write_fence

# Leave 256KiB for ingest proofs, usage/finalization and concurrent receipt fields.
# The SDK map Value encloses all document fields plus a conservative wrapper;
# it includes earlier encrypted results without importing another SDK module.
RESULT_DOCUMENT_BUDGET = 768 * 1024


def bounded_provider_updates(row: dict, piece: str, updates: dict) -> dict:
    if 'provider_result' not in updates:
        return updates
    receipts = dict(row.get('piece_receipts') or {})
    receipts[piece] = {**receipts.get(piece, {}), **updates}
    proposed = {**row, 'piece_receipts': receipts}
    if _helpers.encode_value(proposed)._pb.ByteSize() <= RESULT_DOCUMENT_BUDGET:
        return updates
    # Never discard previously committed results. The usable response continues
    # to ordinary ingestion; only this response's crash cache is omitted.
    return {**{k: v for k, v in updates.items() if k != 'provider_result'}, 'provider_cache_omitted': True}


class RecoveryIngestFenced(RuntimeError):
    """An expired/replaced recovery attempt cannot append conversation content."""


def ingest_hooks(uid: str, context: dict, incoming: dict):
    ref = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection('stt_cap_holds')
        .document(context['hold_id'])
    )
    current = {}
    piece = context['piece']

    def before(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        receipt = (row.get('piece_receipts') or {}).get(piece) or {}
        if (
            row.get('lease_token') != context['lease_token']
            or row.get('lease_until', 0) <= time.time()
            or receipt.get('state') != 'dispatched'
            or receipt.get('attempt', 1) != context['attempt']
        ):
            raise RecoveryIngestFenced('held piece ingest ownership changed')
        current.clear()
        current.update(row.get('piece_ingests') or {})

    def after(transaction, assigned):
        conversation, created, _ = assigned
        cid = conversation['id']
        response: dict[str, Any] = {'new_memories': [], 'updated_memories': []}
        repeat = conversation.get('_sync_lineage_repeat_only')
        if not repeat:
            response['new_memories' if created else 'updated_memories'] = [cid]
        if conversation.get('sync_relevance') == 'keep' and (
            not repeat or conversation.get('_sync_lineage_completion_pending')
        ):
            response['_merged'] = {cid: incoming.get('language')}
        current[piece] = {
            **{k: v for k, v in context['receipt'].items() if k != 'provider_result'},
            'state': 'transcribed',
            'has_content': True,
            'response': response,
            'lineage_anchor': incoming['id'],
            'conversation_id': cid,
        }
        # No reads here: assignment has already staged its conversation writes.
        transaction.update(ref, {'piece_ingests': dict(current)})

    return before, after


def ingested_piece(uid: str, hold_id: str, piece: str) -> dict | None:
    row = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection('stt_cap_holds')
        .document(hold_id)
        .get()
        .to_dict()
        or {}
    )
    return (row.get('piece_ingests') or {}).get(piece)


def provider_checkpoint(uid: str, context: dict, updates: dict) -> bool:
    """Fence dispatch start/result before another attempt may reuse this piece."""
    client = get_firestore_client()
    ref = client.collection('users').document(uid).collection('stt_cap_holds').document(context['hold_id'])

    committed_updates = {}

    @firestore.transactional
    def commit(tx):
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            row = ref.get(transaction=tx).to_dict() or {}
            receipts = dict(row.get('piece_receipts') or {})
            receipt = receipts.get(context['piece']) or {}
            if (
                row.get('lease_token') != context['lease_token']
                or row.get('lease_until', 0) <= time.time()
                or receipt.get('state') != 'dispatched'
                or receipt.get('attempt', 1) != context['attempt']
            ):
                return False
            committed_updates.clear()
            committed_updates.update(bounded_provider_updates(row, context['piece'], updates))
            receipts[context['piece']] = {**receipt, **committed_updates}
            tx.update(ref, {'piece_receipts': receipts})
            return True

    result = commit(client.transaction())
    if result:
        context.setdefault('receipt', {}).update(committed_updates)
    return result
