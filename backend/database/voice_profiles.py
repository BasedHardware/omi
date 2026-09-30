"""Voice-profile preferences, tag-prompt pacing state, and owner voice confirmations."""

from datetime import datetime, timedelta, timezone
import math
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


def _validate_uid(uid: str) -> str:
    if not uid or not uid.strip():
        raise ValueError("uid must be a non-empty string")
    return uid.strip()


def _validate_str_id(val: str, name: str) -> str:
    if not val or not val.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return val.strip()


def _sanitize_embedding(embedding: Sequence[float]) -> List[float]:
    if not embedding or len(embedding) == 0:
        raise ValueError("embedding must be a non-empty sequence")
    sanitized: List[float] = []
    for item in embedding:
        val = float(item)
        if type(item) is bool or not math.isfinite(val):
            raise ValueError(f"embedding contains invalid or non-finite coordinate: {item!r}")
        sanitized.append(val)
    return sanitized


def _sanitize_pooled_vector(vector: Sequence[float]) -> List[float]:
    if not vector or len(vector) == 0:
        raise ValueError("pooled vector must be a non-empty sequence")
    sanitized: List[float] = []
    for item in vector:
        val = float(item)
        if type(item) is bool or not math.isfinite(val):
            raise ValueError(f"pooled vector contains invalid or non-finite coordinate: {item!r}")
        sanitized.append(val)
    return sanitized



def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) if isinstance(value, datetime) else None


def _resolve_settings(data: Dict[str, Any]) -> Dict[str, bool]:
    return {
        key: default if data.get(key) is None else bool(data.get(key)) for key, default in SETTINGS_DEFAULTS.items()
    }


def get_voice_profile_settings(uid: str, *, firestore_client: Any = None) -> Dict[str, bool]:
    uid = _validate_uid(uid)
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    return _resolve_settings(data)


def get_voice_profile_context(uid: str, *, firestore_client: Any = None) -> Tuple[Dict[str, bool], bool]:
    """Settings plus whether the owner has a voiceprint, from one user-document read."""
    uid = _validate_uid(uid)
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    return _resolve_settings(data), bool(data.get('speaker_embedding'))


def set_voice_profile_settings(uid: str, updates: Dict[str, bool], *, firestore_client: Any = None) -> None:
    uid = _validate_uid(uid)
    unknown = set(updates) - set(SETTINGS_DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown voice profile setting(s): {", ".join(sorted(unknown))}')
    if not updates:
        return
    ref = _client(firestore_client).collection('users').document(uid)
    ref.set({key: bool(value) for key, value in updates.items()}, merge=True)


def _state_ref(uid: str, firestore_client: Any = None) -> Any:
    uid = _validate_uid(uid)
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
    cutoff = (as_utc(now) or datetime.now(timezone.utc)) - ANSWERED_PROMPT_RETENTION
    answered = state.get('answered') or {}
    return {k: at_utc for k, at in answered.items() if (at_utc := as_utc(at)) is not None and at_utc >= cutoff}


def record_tag_prompts_shown(uid: str, now: datetime, *, firestore_client: Any = None) -> bool:
    """Stamp a shown set. Returns True when this was the first set ever shown."""
    ref = _state_ref(uid, firestore_client)
    client = _client(firestore_client)

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
    ref = _state_ref(uid, firestore_client)
    client = _client(firestore_client)

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
    prompt_id = _validate_str_id(prompt_id, "prompt_id")
    ref = _state_ref(uid, firestore_client)
    client = _client(firestore_client)

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
    """Pool a confirmed owner clip into the owner's voiceprint in one transaction."""
    uid = _validate_uid(uid)
    conversation_id = _validate_str_id(conversation_id, "conversation_id")
    clean_embedding = _sanitize_embedding(embedding)
    client = _client(firestore_client)
    ref = client.collection('users').document(uid)

    @firestore.transactional
    def pool_in(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        current = data.get('speaker_embedding')
        base = data.get('speaker_embedding_base')
        pooled_at = as_utc(data.get('owner_voice_pooled_at'))
        updated_at = as_utc(data.get('speaker_embedding_updated_at'))
        if current and (pooled_at is None or (updated_at is not None and updated_at > pooled_at)):
            base = current
        now = datetime.now(timezone.utc)
        confirmations = list(data.get('owner_voice_confirmations') or [])
        confirmations.append({'embedding': clean_embedding, 'conversation_id': conversation_id, 'at': now})
        confirmations = confirmations[-OWNER_VOICE_CONFIRMATIONS_MAX:]
        vectors = ([list(base)] if base else []) + [list(item['embedding']) for item in confirmations]
        pooled_result = pool(vectors)
        speaker_embedding = _sanitize_pooled_vector(pooled_result)
        update: Dict[str, Any] = {
            'speaker_embedding': speaker_embedding,
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
