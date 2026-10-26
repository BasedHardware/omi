"""Vector enrollment first; existing verified audio teaching remains the fallback."""

from database import conversations, speaker_auto_enroll, users
from database._client import get_firestore_client
from utils.other.storage import download_owner_evidence_cache
from utils.speakers import auto_enroll as policy


def enroll(uid: str, person_id: str, conversation_id: str, segment_ids: list) -> str | None:
    if not policy.enabled():
        return None
    client = get_firestore_client()
    user = client.collection('users').document(uid).get().to_dict() or {}
    if not policy.retained(user):
        return 'disabled'
    if policy.unit(user.get('speaker_embedding')) is None:
        return 'rejected_embedding'
    person = users.get_person(uid, person_id)
    conversation = conversations.get_conversation(uid, conversation_id)
    if not person or not conversation:
        return 'person_missing' if not person else 'conversation_missing'
    if conversation.get('private_cloud_sync_enabled') is not True:
        return 'disabled'
    evidence = policy.decode_evidence(download_owner_evidence_cache(uid, conversation_id))
    if not evidence:
        return None  # Only absent evidence may try independently guarded audio.
    receipt = conversation.get('manual_speaker_assignments') or {}
    if not policy.candidate(conversation, person_id, segment_ids, evidence, user.get('speaker_embedding')):
        wanted = {
            policy.binding(s) for s in conversation.get('transcript_segments') or [] if s.get('id') in segment_ids
        }
        if not any(row.get('binding') in wanted for row in evidence.values()):
            return None  # Other voices' evidence is not evidence for this requested tag.
        return 'rejected_quality'
    stored = speaker_auto_enroll.publish(
        uid,
        person_id,
        conversation_id,
        segment_ids,
        evidence,
        person.get('updated_at'),
        receipt.get('generation'),
        expected_privacy_version=user.get(speaker_auto_enroll.PRIVACY_VERSION, 0),
        firestore_client=client,
    )
    return 'stored' if stored else 'stale_assignment'
