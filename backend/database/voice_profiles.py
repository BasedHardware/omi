"""Voice-profile preferences, tag-prompt pacing state, and owner voice confirmations.

Three small records back the speaker tag prompts:

- ``users/{uid}`` fields ``speaker_tag_prompts_enabled`` and
  ``save_other_voice_profiles`` (both default on; a missing field means on).
- ``users/{uid}/speaker_tag_prompts/state`` holds pacing: when a set was last
  shown, the dismissal streak, and which prompts were already answered.
- ``users/{uid}.owner_voice_confirmations`` keeps the few clip voiceprints the
  owner confirmed with "That's me". The live ``speaker_embedding`` becomes the
  pooled centroid of the enrollment voiceprint plus those confirmations.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from google.cloud import firestore

from ._client import get_firestore_client, run_transactional

SETTINGS_DEFAULTS: Dict[str, bool] = {
    'speaker_tag_prompts_enabled': True,
    'save_other_voice_profiles': True,
}
OWNER_VOICE_CONFIRMATIONS_MAX = 5
ANSWERED_PROMPT_RETENTION = timedelta(days=7)
_STATE_COLLECTION = 'speaker_tag_prompts'
_STATE_DOCUMENT = 'state'


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def get_voice_profile_settings(uid: str, *, firestore_client: Any = None) -> Dict[str, bool]:
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    return {key: bool(data.get(key, default)) for key, default in SETTINGS_DEFAULTS.items()}


def get_voice_profile_context(uid: str, *, firestore_client: Any = None) -> Tuple[Dict[str, bool], bool]:
    """Settings plus whether the owner has a voiceprint, from one user-document read."""
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    settings = {key: bool(data.get(key, default)) for key, default in SETTINGS_DEFAULTS.items()}
    return settings, bool(data.get('speaker_embedding'))


def set_voice_profile_settings(uid: str, updates: Dict[str, bool], *, firestore_client: Any = None) -> None:
    unknown = set(updates) - set(SETTINGS_DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown voice profile setting(s): {", ".join(sorted(unknown))}')
    if not updates:
        return
    ref = _client(firestore_client).collection('users').document(uid)
    ref.set({key: bool(value) for key, value in updates.items()}, merge=True)


def _state_ref(uid: str, firestore_client: Any = None) -> Any:
    return (
        _client(firestore_client)
        .collection('users')
        .document(uid)
        .collection(_STATE_COLLECTION)
        .document(_STATE_DOCUMENT)
    )


def get_tag_prompt_state(uid: str, *, firestore_client: Any = None) -> Dict[str, Any]:
    return _state_ref(uid, firestore_client).get().to_dict() or {}


def _pruned_answers(state: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    cutoff = now - ANSWERED_PROMPT_RETENTION
    answered = state.get('answered') or {}
    return {key: at for key, at in answered.items() if isinstance(at, datetime) and at >= cutoff}


def record_tag_prompts_shown(uid: str, now: datetime, *, firestore_client: Any = None) -> bool:
    """Stamp a shown set. Returns True when this was the first set ever shown."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def stamp(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        first = not state.get('first_shown_at')
        update: Dict[str, Any] = {
            'last_shown_at': now,
            'shown_sets': int(state.get('shown_sets') or 0) + 1,
        }
        if first:
            update['first_shown_at'] = now
        if snapshot.exists:
            if state.get('last_empty_check_at') is not None:
                update['last_empty_check_at'] = firestore.DELETE_FIELD
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return first

    return run_transactional(client, stamp)


def mark_tag_prompts_empty(uid: str, now: datetime, *, firestore_client: Any = None) -> None:
    """Remember that nothing was worth asking, so repeated opens skip the 48h scan."""
    _state_ref(uid, firestore_client).set({'last_empty_check_at': now}, merge=True)


def record_tag_prompts_dismissed(uid: str, now: datetime, *, firestore_client: Any = None) -> int:
    """Count a set closed without any answer. Returns the new streak length."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def bump(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        streak = int(state.get('consecutive_dismissals') or 0) + 1
        update = {'consecutive_dismissals': streak, 'last_dismissed_at': now}
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return streak

    return run_transactional(client, bump)


def record_tag_prompt_answered(uid: str, prompt_id: str, now: datetime, *, firestore_client: Any = None) -> None:
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def record(transaction: Any) -> None:
        snapshot = ref.get(transaction=transaction)
        answered = _pruned_answers(snapshot.to_dict() or {}, now)
        answered[prompt_id] = now
        update = {'answered': answered, 'consecutive_dismissals': 0, 'last_answered_at': now}
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)

    run_transactional(client, record)


def answered_prompt_ids(state: Dict[str, Any], now: Optional[datetime] = None) -> set:
    return set(_pruned_answers(state, now or datetime.now(timezone.utc)))


def add_owner_voice_confirmation(
    uid: str,
    embedding: Sequence[float],
    pool: Callable[[List[List[float]]], List[float]],
    *,
    conversation_id: str,
    firestore_client: Any = None,
) -> int:
    """Pool a confirmed owner clip into the owner's voiceprint in one transaction.

    ``speaker_embedding_base`` preserves the enrollment voiceprint the first time
    we pool, and again whenever another writer (speech-profile upload, live
    rebuild) replaced ``speaker_embedding`` after our last pooling. The stored
    centroid is ``pool([base, *confirmations])``. Returns the confirmation count.
    """
    client = _client(firestore_client)
    ref = client.collection('users').document(uid)

    @firestore.transactional
    def pool_in(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        current = data.get('speaker_embedding')
        base = data.get('speaker_embedding_base')
        pooled_at = data.get('owner_voice_pooled_at')
        updated_at = data.get('speaker_embedding_updated_at')
        if current and (pooled_at is None or (updated_at is not None and updated_at > pooled_at)):
            base = current
        now = datetime.now(timezone.utc)
        confirmations = list(data.get('owner_voice_confirmations') or [])
        confirmations.append({'embedding': list(embedding), 'conversation_id': conversation_id, 'at': now})
        confirmations = confirmations[-OWNER_VOICE_CONFIRMATIONS_MAX:]
        vectors = ([list(base)] if base else []) + [list(item['embedding']) for item in confirmations]
        update: Dict[str, Any] = {
            'speaker_embedding': pool(vectors),
            'speaker_embedding_updated_at': now,
            'owner_voice_pooled_at': now,
            'owner_voice_confirmations': confirmations,
        }
        if base:
            update['speaker_embedding_base'] = list(base)
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return len(confirmations)

    return run_transactional(client, pool_in)
