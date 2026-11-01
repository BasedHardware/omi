"""Invisible work on the current settled row; never regenerates visible notes."""

import hashlib
import json
import time

from utils.sync import processing_hold

from database import conversations as conversations_db
from utils.conversations.factory import deserialize_conversation
from utils.conversations.silent_redrive import is_silent_redrive

CHECKPOINT = 'demand_enrichment_applied_hash'


def fingerprint(conversation) -> str:
    # Only effective inputs, not processing/engagement timestamps or this checkpoint.
    row = conversation.model_dump(mode='json')
    fields = ('transcript_segments', 'structured', 'photos', 'source', 'language')
    return hashlib.sha256(json.dumps({key: row.get(key) for key in fields}, sort_keys=True).encode()).hexdigest()


def enrich_settled(uid: str, conversation_id: str, language: str) -> None:
    from utils.conversations.process_conversation import apply_settled_enrichment

    row = conversations_db.get_conversation(uid, conversation_id)
    if not row or row.get('deleted') or row.get('discarded') or is_silent_redrive(row):
        return
    # Active capture and a smart-merge donor never own final enrichment.
    if row.get('status') != 'completed':
        raise RuntimeError('conversation has not settled')
    if (row.get('smart_merge') or {}).get('survivor_id'):
        return
    state = row.get(processing_hold.FIELD) or {}
    if state.get('held'):
        # Intake keeps status completed while the transcript is ahead of notes.
        # Even past the quiet deadline, full processing must settle this revision
        # before tasks/memories may consume it (including while budget-paused).
        raise processing_hold.ProcessingDeferred('sync_hold', time.time() + 120)
    conversation = deserialize_conversation(row)
    digest = fingerprint(conversation)
    if row.get(CHECKPOINT) == digest:
        return
    apply_settled_enrichment(uid, conversation)
    # Existing writer applies deletion/privacy fences. A concurrent revision gets
    # its own dirty outbox version and a different input hash on the next run.
    conversations_db.record_demand_enrichment_checkpoint(uid, conversation_id, digest)
