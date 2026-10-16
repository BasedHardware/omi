"""Invisible work on the current settled row; never regenerates visible notes."""

import hashlib
import json

from database import conversations as conversations_db
from utils.conversations.factory import deserialize_conversation
from utils.conversations.processing_trigger import ProcessingTrigger

CHECKPOINT = 'demand_enrichment_applied_hash'


def fingerprint(conversation) -> str:
    # Only effective inputs, not processing/engagement timestamps or this checkpoint.
    row = conversation.model_dump(mode='json')
    fields = ('transcript_segments', 'structured', 'photos', 'source', 'language')
    return hashlib.sha256(json.dumps({key: row.get(key) for key in fields}, sort_keys=True).encode()).hexdigest()


def enrich_settled(uid: str, conversation_id: str, language: str) -> None:
    from utils.conversations.process_conversation import extract_memories, _save_action_items, save_structured_vector
    from database import users as users_db
    from models.other import Person

    row = conversations_db.get_conversation(uid, conversation_id)
    if not row or row.get('deleted') or row.get('discarded'):
        return
    # Active capture and a smart-merge donor never own final enrichment.
    if row.get('status') != 'completed':
        raise RuntimeError('conversation has not settled')
    if (row.get('smart_merge') or {}).get('survivor_id'):
        return
    conversation = deserialize_conversation(row)
    digest = fingerprint(conversation)
    if row.get(CHECKPOINT) == digest:
        return
    extract_memories(uid, conversation)
    person_ids = list(set(conversation.get_person_ids()))
    people = Person.deserialize_many_safe(users_db.get_people_by_ids(uid, person_ids)) if person_ids else []
    _save_action_items(uid, conversation, people, ProcessingTrigger.SYNC_UPDATE)
    if save_structured_vector(uid, conversation) is False:
        raise RuntimeError('conversation vector is not ready')
    # Existing writer applies deletion/privacy fences. A concurrent revision gets
    # its own dirty outbox version and a different input hash on the next run.
    conversations_db.update_conversation(uid, conversation_id, {CHECKPOINT: digest})
