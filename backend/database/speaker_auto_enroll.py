"""Direct-document transactions for explicit, retained vector-only voice learning."""

from datetime import datetime, timezone
import logging
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.legal_holds import external_write_fence
from database.speaker_profile_authority import _current_source
from utils.speakers import auto_enroll as policy
from utils.stt.voiceprints import usable_person_voiceprint

OWNER_INDEX = 'speaker_auto_enroll_people'
PRIVACY_VERSION = 'speaker_auto_enroll_privacy_version'
MAX_PEOPLE = 400
MAX_SOURCE_PEOPLE = 32
logger = logging.getLogger(__name__)


def audio_guard(uid: str, *, firestore_client: Any = None) -> dict:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid).get().to_dict() or {}
    return {
        'private_cloud_sync_enabled': user.get('private_cloud_sync_enabled', True) if user else False,
        'save_other_voice_profiles': user.get('save_other_voice_profiles', True) if user else False,
        'speaker_embedding': user.get('speaker_embedding'),
        PRIVACY_VERSION: user.get(PRIVACY_VERSION, 0),
    }


def authorize_audio(transaction, user_ref, user_doc, source, embedding, privacy_version, *, firestore_client) -> bool:
    uid, cid = source[:2]
    with external_write_fence(uid, transaction=transaction, firestore_client=firestore_client):
        row = user_ref.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
        deleted = user_ref.collection('deleted_conversations').document(cid).get(transaction=transaction).exists
        return (
            not deleted
            and row.get('private_cloud_sync_enabled') is True
            and policy.audio_allowed(
                user_doc,
                embedding,
                privacy_version,
            )
        )


def allowed(uid: str, *, firestore_client: Any = None) -> bool:
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        return policy.enabled() and policy.retained(client.collection('users').document(uid).get().to_dict() or {})
    except Exception as error:
        logger.warning('speaker_auto_enroll consent unavailable exception_type=%s', type(error).__name__)
        return False


def publish(
    uid: str,
    person_id: str,
    conversation_id: str,
    requested: list,
    evidence: dict,
    expected_updated_at: Any,
    generation: int,
    *,
    expected_privacy_version: int = 0,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    person = user.collection('people').document(person_id)
    source = user.collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(transaction):
        if not policy.enabled():
            return False
        with external_write_fence(uid, transaction=transaction, firestore_client=client):
            owner = user.get(transaction=transaction).to_dict() or {}
            current = person.get(transaction=transaction).to_dict() or {}
            raw_source = source.get(transaction=transaction).to_dict() or {}
            tombstone = user.collection('deleted_conversations').document(conversation_id).get(transaction=transaction)
            if tombstone.exists or not policy.retained(owner) or not current or current.get('is_dismissed'):
                return False
            if owner.get(PRIVACY_VERSION, 0) != expected_privacy_version:
                return False
            if (
                current.get('updated_at') != expected_updated_at
                or raw_source.get('private_cloud_sync_enabled') is not True
            ):
                return False
            authorized = _current_source(transaction, user, uid, conversation_id, generation)
            if authorized is None:
                return False
            segments, receipt = authorized
            contribution = policy.candidate(
                {'transcript_segments': segments, 'manual_speaker_assignments': receipt},
                person_id,
                requested,
                evidence,
                owner.get('speaker_embedding'),
            )
            if contribution is None:
                return False
            legacy = usable_person_voiceprint(current)
            if legacy is not None:
                legacy_vector = policy.unit(legacy)
                if (
                    legacy_vector is None
                    or 1 - legacy_vector @ policy.unit(contribution['vector']) > policy.MAX_DISTANCE
                ):
                    return False
            index = list(owner.get(OWNER_INDEX) or [])
            source_index = list(raw_source.get(OWNER_INDEX) or [])
            if (person_id not in index and len(index) >= MAX_PEOPLE) or (
                person_id not in source_index and len(source_index) >= MAX_SOURCE_PEOPLE
            ):
                return False
            now = datetime.now(timezone.utc)
            contribution.update(conversation_id=conversation_id, generation=receipt.get('generation'))
            entries = policy.refresh(
                policy.open_pool(uid, person_id, current.get(policy.POOL_FIELD)),
                contribution,
                now.timestamp(),
            )
            if entries is None:
                return False
            # All reads precede writes. A retry sees corrections, consent and deletion
            # atomically; never resurrect a profile from a stale audio snapshot.
            transaction.update(
                person,
                {
                    policy.POOL_FIELD: policy.seal(uid, person_id, entries),
                    'updated_at': now,
                    'voice_learning_state': 'learned',
                    'voice_learning_outcome': 'stored',
                    'voice_speech_seconds': contribution['seconds'],
                    'voice_needed_seconds': 0,
                },
            )
            transaction.update(source, {OWNER_INDEX: sorted(set([*source_index, person_id]))})
            transaction.update(user, {OWNER_INDEX: sorted(set([*index, person_id]))})
            return True

    return run_transactional(client, commit)


def update_privacy(uid: str, updates: dict, *, firestore_client: Any = None) -> None:
    """Privacy opt-out clears the indexed pools in the same transaction as consent."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)

    @firestore.transactional
    def commit(transaction):
        owner = user.get(transaction=transaction).to_dict() or {}
        following = {**owner, **updates}
        people = []
        if not policy.retained(following):
            for pid in owner.get(OWNER_INDEX) or []:
                ref = user.collection('people').document(pid)
                if ref.get(transaction=transaction).exists:
                    people.append(ref)
        for ref in people:
            transaction.update(
                ref, {policy.POOL_FIELD: firestore.DELETE_FIELD, 'updated_at': datetime.now(timezone.utc)}
            )
        version = owner.get(PRIVACY_VERSION, 0)
        if type(version) is not int:
            raise ValueError('Invalid speaker enrollment privacy version')
        patch = {
            **updates,
            PRIVACY_VERSION: version + 1,
            **({OWNER_INDEX: []} if not policy.retained(following) else {}),
        }
        if owner:
            transaction.update(user, patch)
        else:
            transaction.set(user, patch)

    run_transactional(client, commit)


def retract_conversation(uid: str, conversation_id: str, *, firestore_client: Any = None) -> None:
    """Fence further publication and retract every indexed contribution before deletion."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    source = user.collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(transaction):
        row = source.get(transaction=transaction).to_dict()
        if not row:
            return
        changes = []
        for pid in row.get(OWNER_INDEX) or []:
            ref = user.collection('people').document(pid)
            person = ref.get(transaction=transaction).to_dict() or {}
            change = policy.retract(uid, pid, person.get(policy.POOL_FIELD), [conversation_id])
            if change:
                changes.append((ref, change))
        for ref, change in changes:
            transaction.update(ref, change)
        # Even a source without published contributions must fence in-flight work.
        transaction.update(source, {'deleted': True, OWNER_INDEX: []})

    run_transactional(client, commit)
