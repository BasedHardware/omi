"""Sealed private recurring profiles; bounded direct-document transactions only."""

import base64
import hashlib
import json
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud import firestore

from database import _client
from database._client import get_firestore_client
from database.legal_holds import external_write_fence
from database.people_generation import generation_ref
from utils import encryption
from utils.speakers import auto_enroll as pools, recurring_voices as policy
from utils.observability.recurring_voices import profile_event, match_outcome

INDEX = 'speaker_recurring_voices'
COLLECTION = 'speaker_recurring_voices'
PRIVACY_VERSION = 'speaker_auto_enroll_privacy_version'


def _aad(uid, voice_id):
    return json.dumps(['speaker-recurring-voice', 1, uid, voice_id], separators=(',', ':')).encode()


def seal(uid, voice_id, profile):
    nonce = os.urandom(12)
    payload = json.dumps({'v': 1, 'model': pools.MODEL, **profile}, allow_nan=False, separators=(',', ':')).encode()
    return base64.b64encode(
        nonce + AESGCM(encryption.derive_key(uid)).encrypt(nonce, payload, _aad(uid, voice_id))
    ).decode()


def open_profile(uid, voice_id, blob):
    try:
        if not isinstance(blob, str) or len(blob) > 128 * 1024:
            return None
        raw = base64.b64decode(blob, validate=True)
        profile = json.loads(AESGCM(encryption.derive_key(uid)).decrypt(raw[:12], raw[12:], _aad(uid, voice_id)))
        entries = profile.get('entries')
        if (
            profile.get('v') != 1
            or profile.get('model') != pools.MODEL
            or profile.get('state') not in {'candidate', 'recurring', 'bound', 'rejected'}
            or not isinstance(entries, list)
            or not 1 <= len(entries) <= pools.MAX_CONTRIBUTIONS
            or any(
                not isinstance(e, dict)
                or pools.unit(e.get('vector')) is None
                or not isinstance(e.get('conversation_id'), str)
                or not isinstance(e.get('at'), (float, int))
                for e in entries
            )
        ):
            return None
        if len({e['conversation_id'] for e in entries}) != len(entries):
            return None
        return profile
    except Exception:
        return None


def _index(owner):
    index = owner.get(INDEX) or {}
    if not isinstance(index, dict) or len(index) > policy.MAX_PROFILES:
        raise ValueError('Invalid recurring profile authority')
    return index


def read_profiles(transaction, user, owner):
    if not pools.retained(owner):
        return {}
    profiles = {}
    for vid, token in _index(owner).items():
        row = user.collection(COLLECTION).document(vid).get(transaction=transaction).to_dict() or {}
        blob = row.get('sealed')
        if pools.pool_token(blob) == token:
            profile = open_profile(user.id, vid, blob)
            if profile is not None:
                profiles[vid] = profile
    return profiles


def write_profiles(transaction, user, owner, profiles):
    index = {}
    for vid in set(_index(owner)) | set(profiles):
        profile = profiles.get(vid)
        ref = user.collection(COLLECTION).document(vid)
        if not profile:
            transaction.delete(ref)
            continue
        blob = seal(user.id, vid, profile)
        expiry = min(e['at'] + pools.MAX_AGE_SECONDS for e in profile['entries'])
        if profile['state'] == 'candidate':
            expiry = min(expiry, min(e['at'] for e in profile['entries']) + policy.CANDIDATE_AGE)
        transaction.set(
            ref,
            {'sealed': blob, 'expires_at': datetime.fromtimestamp(expiry, timezone.utc)},
        )
        index[vid] = pools.pool_token(blob)
    transaction.update(user, {INDEX: index})


def _source_token(source):
    # Detect concurrent assignment, opt-out, reprocess and deletion while GPU runs.
    return hashlib.sha256(json.dumps(source, sort_keys=True, default=str).encode()).hexdigest()


def checkpoint(uid, conversation_id, *, receipt=None, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    generation = generation_ref(user).get().to_dict()
    owner = user.get().to_dict() or {}
    source = user.collection('conversations').document(conversation_id).get().to_dict() or {}
    if not pools.retained(owner) or source.get('private_cloud_sync_enabled') is not True:
        return None
    if receipt is not None:
        from database.conversations import decode_manual_speaker_assignments

        current = decode_manual_speaker_assignments(
            uid, source.get('manual_speaker_assignments'), bool(source.get('manual_speaker_assignments_compressed'))
        )
        if current != receipt:
            return None
    return (owner.get(PRIVACY_VERSION, 0), _source_token(source), generation)


def learn(uid, conversation, centroids, prints, expected, *, owner_reserved=False, firestore_client=None):
    from config.batch_conversation_speakers import recurring_enabled_for
    from utils.stt.voiceprints import usable_person_voiceprint

    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)

    @firestore.transactional
    def commit(transaction):
        if expected is None or not recurring_enabled_for(uid, conversation.transcript_segments):
            return {}, [], []
        with external_write_fence(uid, transaction=transaction, firestore_client=client):
            generation = generation_ref(user).get(transaction=transaction).to_dict()
            owner = user.get(transaction=transaction).to_dict() or {}
            source = (
                user.collection('conversations').document(conversation.id).get(transaction=transaction).to_dict() or {}
            )
            deleted = (
                user.collection('deleted_conversations').document(conversation.id).get(transaction=transaction).exists
            )
            if (
                deleted
                or source.get('deleted')
                or source.get('discarded')
                or source.get('is_locked')
                or not pools.retained(owner)
                or source.get('private_cloud_sync_enabled') is not True
                or expected != (owner.get(PRIVACY_VERSION, 0), _source_token(source), generation)
            ):
                return {}, [], []
            # Re-read every person competitor before writing; a print changed
            # during the pass must not authorize a stale match or binding.
            current_prints = {'user': owner.get('speaker_embedding')}
            for pid in prints:
                if pid == 'user':
                    continue
                row = user.collection('people').document(pid).get(transaction=transaction).to_dict() or {}
                current_prints[pid] = pools.usable(uid, {**row, 'id': pid}, owner) or usable_person_voiceprint(row)
            profiles = read_profiles(transaction, user, owner)
            now = datetime.now(timezone.utc).timestamp()
            first_at = source.get('speaker_recurring_observed_at', now)
            if not isinstance(first_at, (float, int)) or not 0 <= now - first_at <= pools.MAX_AGE_SECONDS:
                return {}, [], []
            created_ids = source.get('speaker_recurring_created_ids') or []
            following, labels, events, outcomes = policy.evaluate(
                centroids,
                current_prints,
                profiles,
                conversation.id,
                now,
                owner_reserved=owner_reserved,
                created_ids=created_ids,
                evidence_at=first_at,
            )
            events.extend('expired' for vid in profiles if policy.active(profiles[vid], now) is None)
            write_profiles(transaction, user, owner, following)
            transaction.update(
                user.collection('conversations').document(conversation.id),
                {
                    'speaker_recurring_observed_at': first_at,
                    'speaker_recurring_created_ids': sorted(set(created_ids) | (set(following) - set(profiles))),
                },
            )
            return labels, events, outcomes

    labels, events, outcomes = _client.run_transactional(client, commit)
    for event in events:
        profile_event(event)
    for outcome in outcomes:
        match_outcome(outcome)
    return labels


def prepare_retraction(transaction, user, owner, *, conversations=None, person_id=None, clear=False):
    """Read phase for existing deletion/consent transactions; never defer cleanup."""
    if clear or not pools.retained(owner):
        return {}
    profiles = read_profiles(transaction, user, owner)
    following = {}
    for vid, profile in profiles.items():
        if clear or (person_id and profile.get('bound_person_id') == person_id):
            continue
        updated = policy.retract(profile, conversations) if conversations else profile
        if updated:
            following[vid] = updated
    return following


def active_ids(transaction, user):
    """Read current authority in the caller's transaction, before any writes."""
    owner = user.get(transaction=transaction).to_dict() or {}
    if not pools.retained(owner):
        return set()
    profiles = read_profiles(transaction, user, owner)
    now = datetime.now(timezone.utc).timestamp()
    return {
        vid
        for vid, profile in profiles.items()
        if (current := policy.active(profile, now))
        and current['state'] in {'recurring', 'bound'}
        and policy.vector(current, now, owner.get('speaker_embedding')) is not None
    }


def suggestable_ids(uid, *, firestore_client=None):
    """Current retained authority, never a cached segment marker alone."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)

    @firestore.transactional
    def read(transaction):
        return active_ids(transaction, user)

    return _client.run_transactional(client, read)
