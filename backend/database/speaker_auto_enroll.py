"""Direct-document transactions for explicit, retained vector-only voice learning."""

from datetime import datetime, timezone
import logging
from typing import Any

from google.cloud import firestore

from database.people_generation import bump_people_generation
from database._client import get_firestore_client
from database import _client, speaker_profile_authority
from database.legal_holds import external_write_fence
from utils.speakers import auto_enroll as policy
from utils.stt.voiceprints import usable_person_voiceprint

OWNER_INDEX = 'speaker_auto_enroll_people'
PRIVACY_VERSION = 'speaker_auto_enroll_privacy_version'
MAX_PEOPLE = policy.MAX_PEOPLE
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
        policy.AUTHORITY_FIELD: user.get(policy.AUTHORITY_FIELD) or {},
    }


def authorize_audio(
    transaction, user_ref, user_doc, person_id, source, embedding, privacy_version, *, firestore_client
) -> bool:
    uid, cid = source[:2]
    with external_write_fence(uid, transaction=transaction, firestore_client=firestore_client):
        row = user_ref.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
        deleted = user_ref.collection('deleted_conversations').document(cid).get(transaction=transaction).exists
        current = speaker_profile_authority.current_source(transaction, user_ref, uid, cid, source[3])
        if current is None:
            return False
        segments, receipt = current
        explicit = policy.explicit_segments(
            {'transcript_segments': segments, 'manual_speaker_assignments': receipt}, person_id
        )
        return (
            not deleted
            and bool(source[2])
            and set(source[2]).issubset({s.get('id') for s in explicit})
            and row.get('private_cloud_sync_enabled') is True
            and policy.audio_allowed(
                user_doc,
                embedding,
                privacy_version,
            )
        )


def context(uid: str, *, firestore_client: Any = None) -> dict:
    try:
        return audio_guard(uid, firestore_client=firestore_client) if policy.enabled() else {}
    except Exception as error:
        logger.warning('speaker_auto_enroll consent unavailable exception_type=%s', type(error).__name__)
        return {}


def publish(
    uid: str,
    person_id: str,
    conversation_id: str,
    requested: list,
    evidence: dict,
    expected_updated_at: Any,
    generation: int | None,
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
            if (
                tombstone.exists
                or not policy.retained(owner)
                or not current
                or current.get('is_dismissed')
                or current.get(policy.REVOKED_FIELD)
            ):
                return False
            if owner.get(PRIVACY_VERSION, 0) != expected_privacy_version:
                return False
            if (
                current.get('updated_at') != expected_updated_at
                or raw_source.get('private_cloud_sync_enabled') is not True
            ):
                return False
            authorized = speaker_profile_authority.current_source(transaction, user, uid, conversation_id, generation)
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
            if entries is None or policy.vector(entries, now.timestamp(), owner.get('speaker_embedding')) is None:
                return False
            blob = policy.seal(uid, person_id, entries)
            authority_update = policy.authority_after(owner, {person_id: blob})
            # All reads precede writes. A retry sees corrections, consent and deletion
            # atomically; never resurrect a profile from a stale audio snapshot.
            transaction.update(
                person,
                {
                    policy.POOL_FIELD: blob,
                    'updated_at': now,
                    'voice_learning_state': 'learned',
                    'voice_learning_outcome': 'stored',
                    'voice_speech_seconds': contribution['seconds'],
                    'voice_needed_seconds': 0,
                },
            )
            bump_people_generation(transaction, person)
            transaction.update(source, {OWNER_INDEX: sorted(set([*source_index, person_id]))})
            transaction.update(user, {OWNER_INDEX: sorted(set([*index, person_id])), **authority_update})
            return True

    return _client.run_transactional(client, commit)


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
            bump_people_generation(transaction, ref)
        version = owner.get(PRIVACY_VERSION, 0)
        if type(version) is not int:
            raise ValueError('Invalid speaker enrollment privacy version')
        patch = {
            **updates,
            PRIVACY_VERSION: version + 1,
            **({OWNER_INDEX: [], policy.AUTHORITY_FIELD: {}} if not policy.retained(following) else {}),
        }
        if owner:
            transaction.update(user, patch)
        else:
            transaction.set(user, patch)

    _client.run_transactional(client, commit)


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
        owner_snapshot = user.get(transaction=transaction)
        owner = owner_snapshot.to_dict() or {}
        source_ids = {conversation_id, *(row.get('sync_merged_from') or [])}
        people = set(row.get(OWNER_INDEX) or [])
        if len(source_ids) > 1:
            # Donor cleanup is best-effort upstream. Revoke every immutable
            # source even if a donor row/index was already removed by an old writer.
            people.update(owner.get(OWNER_INDEX) or [])
        changes = []
        for pid in sorted(people):
            ref = user.collection('people').document(pid)
            person = ref.get(transaction=transaction).to_dict() or {}
            change = policy.retract(uid, pid, person.get(policy.POOL_FIELD), source_ids)
            if change:
                changes.append((ref, change))
        for ref, change in changes:
            transaction.update(ref, change)
            bump_people_generation(transaction, ref)
        if changes and owner_snapshot.exists:
            transaction.update(
                user, policy.authority_after(owner, {ref.id: change[policy.POOL_FIELD] for ref, change in changes})
            )
        # Even a source without published contributions must fence in-flight work.
        transaction.update(source, {'deleted': True, OWNER_INDEX: []})

    _client.run_transactional(client, commit)


def revoke_person(uid: str, person_id: str, *, firestore_client: Any = None) -> None:
    """Revoke cached authority and fence new publication before a person is hard-deleted."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    person = user.collection('people').document(person_id)

    @firestore.transactional
    def commit(transaction):
        owner_snapshot = user.get(transaction=transaction)
        owner = owner_snapshot.to_dict() or {}
        snapshot = person.get(transaction=transaction)
        authority_update = policy.authority_after(owner, {person_id: None})
        if snapshot.exists:
            transaction.update(
                person,
                {
                    policy.POOL_FIELD: firestore.DELETE_FIELD,
                    policy.REVOKED_FIELD: True,
                    'updated_at': datetime.now(timezone.utc),
                },
            )
            bump_people_generation(transaction, person)
        if owner_snapshot.exists:
            transaction.update(
                user,
                {**authority_update, OWNER_INDEX: [pid for pid in owner.get(OWNER_INDEX) or [] if pid != person_id]},
            )

    _client.run_transactional(client, commit)
