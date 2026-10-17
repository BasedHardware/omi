"""Legacy sync assignment transaction runner and shared write codec."""

from typing import Any
import os
from google.cloud import firestore
import config.speaker_match_scores as match_scores


def encode_sync_assignment_plan(uid: str, client: Any, transaction: Any, payload: dict, current: dict | None) -> dict:
    from database import conversations

    if current and current.get('has_transcript_corrections'):
        from utils.agent_capabilities.transcripts import load_entries, preserves_correction_anchors
        from utils.sync.assignment_errors import SyncAssignmentConflict

        captured = conversations.decode_transcript_segments_verified(
            uid, current.get('transcript_segments') or [], bool(current.get('transcript_segments_compressed'))
        )
        corrections = load_entries(uid, payload['id'], firestore_client=client, transaction=transaction)
        if not preserves_correction_anchors(captured, payload.get('transcript_segments') or [], corrections):
            raise SyncAssignmentConflict('sync append changed corrected speech', subtype='other')
    encoded = conversations._prepare_conversation_for_write(  # type: ignore[reportPrivateUsage]
        payload,
        uid,
        payload.get('data_protection_level') or 'enhanced',
        preserve_transcript_identity=bool(current and current.get('has_transcript_corrections')),
    )
    conversations.guard_match_score_size(encoded, current)
    if (
        current
        and match_scores.FIELD in current
        and match_scores.FIELD not in encoded
        and current.get('data_protection_level') != payload.get('data_protection_level')
    ):
        encoded[match_scores.FIELD] = firestore.DELETE_FIELD
    return encoded


def run_sync_assignment(client: Any, assign: Any, full_ids: frozenset[str], *, retry_contention: bool = False):
    from database._client import run_transactional
    from database.firestore_transaction_retry import run_with_transaction_contention_retry

    if (
        not retry_contention
        and os.getenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'false').strip().lower() != 'true'
    ):
        return run_transactional(client, assign, full_ids=full_ids)
    return run_with_transaction_contention_retry(
        client.transaction,
        lambda transaction: run_transactional(client, assign, full_ids=full_ids, initial_transaction=transaction),
        operation_name='sync_assignment',
    )
