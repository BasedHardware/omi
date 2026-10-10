"""Atomic, field-scoped issuance and delivery receipts for owner excerpts."""

from typing import Any

from google.cloud import firestore

from database import conversations
from utils.speaker_tag_prompts.owner_confirmation import (
    FIELD as OWNER_CONFIRMATION_FIELD,
    StaleOwnerConfirmation,
    validate_binding as validate_owner_confirmation,
)


def record(
    uid: str, conversation_id: str, action: str, binding: dict, *, pcm_sha256: str = '', firestore_client=None
) -> bool:
    """Claim the durable conversation quota, or stamp the exact shown/played card."""
    client = firestore_client if firestore_client is not None else conversations.get_firestore_client()
    ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations.conversations_collection)
        .document(conversation_id)
    )

    @firestore.transactional
    def record(transaction):
        raw = ref.get(transaction=transaction).to_dict()
        if not raw:
            raise StaleOwnerConfirmation('Conversation not found')
        if action == 'shown':
            # Visibility acknowledges an issued card, not current assignment
            # authority. Answers may already have changed labels/fingerprints.
            stored = dict(raw.get(OWNER_CONFIRMATION_FIELD) or {})
            if (
                not stored
                or stored.get('prompt_id') != binding.get('prompt_id')
                or stored.get('evidence_id') != binding.get('evidence_id')
                or stored.get('segment_ids') != binding.get('segment_ids')
                or stored.get('speaker_id') != binding.get('speaker_id')
            ):
                raise StaleOwnerConfirmation('Owner question was not issued')
            if stored.get('shown'):
                return False
            stored['shown'] = True
            transaction.update(ref, {OWNER_CONFIRMATION_FIELD: stored})
            return True
        current: dict[str, Any] = dict(raw, id=conversation_id)
        try:
            current['transcript_segments'] = conversations.decode_transcript_segments_verified(
                uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
            )
        except ValueError as error:
            raise StaleOwnerConfirmation('Owner excerpt transcript is unreadable') from error
        current['manual_speaker_assignments'] = conversations.decode_manual_speaker_assignments(
            uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
        )
        if action == 'claim':
            if current.get(OWNER_CONFIRMATION_FIELD):
                return False
            current[OWNER_CONFIRMATION_FIELD] = binding
        stored = dict(
            validate_owner_confirmation(
                current, binding['prompt_id'], binding['evidence_id'], binding.get('segment_ids'), require_played=False
            )
        )
        if binding.get('speaker_id', stored['speaker_id']) != stored['speaker_id']:
            raise StaleOwnerConfirmation('Owner excerpt speaker changed')
        if action == 'played':
            if not pcm_sha256:
                raise StaleOwnerConfirmation('Missing played audio')
            if stored.get('selected_pcm_sha256') != pcm_sha256 or (
                stored.get('played_pcm_sha256') and stored['played_pcm_sha256'] != pcm_sha256
            ):
                raise StaleOwnerConfirmation('Owner excerpt audio changed')
            stored['played_pcm_sha256'] = pcm_sha256
        elif action == 'skip':
            stored['answered'] = 'skip'
        elif action != 'claim':
            raise ValueError('Unknown owner confirmation action')
        transaction.update(ref, {OWNER_CONFIRMATION_FIELD: stored})
        return True

    return conversations.run_transactional(client, record)
