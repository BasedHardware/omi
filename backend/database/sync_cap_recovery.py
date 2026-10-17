"""Piece-lineage proof committed in the exact conversation-ingest transaction."""

import time
from typing import Any

from database._client import get_firestore_client


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
            **context['receipt'],
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
