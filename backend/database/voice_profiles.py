"""Voice-profile preferences, tag-prompt pacing state, and owner voice confirmations."""

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


def _clean_uid(uid: Any) -> Optional[str]:
    if not uid or not isinstance(uid, str):
        return None
    clean = uid.strip()
    return clean if clean else None


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
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return dict(SETTINGS_DEFAULTS)
    data = _client(firestore_client).collection('users').document(clean_uid).get().to_dict() or {}
    return _resolve_settings(data)


def get_voice_profile_context(uid: str, *, firestore_client: Any = None) -> Tuple[Dict[str, bool], bool]:
    """Settings plus whether the owner has a voiceprint, from one user-document read."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return dict(SETTINGS_DEFAULTS), False
    data = _client(firestore_client).collection('users').document(clean_uid).get().to_dict() or {}
    return _resolve_settings(data), bool(data.get('speaker_embedding'))


def set_voice_profile_settings(uid: str, updates: Dict[str, bool], *, firestore_client: Any = None) -> None:
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    if not isinstance(updates, dict):
        raise ValueError("updates must be a dictionary")
    unknown = set(updates) - set(SETTINGS_DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown voice profile setting(s): {", ".join(sorted(unknown))}')
    if not updates:
        return
    ref = _client(firestore_client).collection('users').document(clean_uid)
    ref.set({key: bool(value) for key, value in updates.items()}, merge=True)


def _state_ref(uid: str, firestore_client: Any = None) -> Any:
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    return (
        _client(firestore_client)
        .collection('users')
        .document(clean_uid)
        .collection(_STATE_COLLECTION)
        .document(_STATE_DOCUMENT)
    )


def get_tag_prompt_state(uid: str, *, firestore_client: Any = None) -> Dict[str, Any]:
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        return {}
    return _state_ref(clean_uid, firestore_client).get().to_dict() or {}


def _pruned_answers(state: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    cutoff = (as_utc(now) or datetime.now(timezone.utc)) - ANSWERED_PROMPT_RETENTION
    answered = state.get('answered') or {}
    return {k: at_utc for k, at in answered.items() if (at_utc := as_utc(at)) is not None and at_utc >= cutoff}


def record_tag_prompts_shown(uid: str, now: datetime, *, firestore_client: Any = None) -> bool:
    """Stamp a shown set. Returns True when this was the first set ever shown."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    now_utc = as_utc(now) or datetime.now(timezone.utc)
    client = _client(firestore_client)
    ref = _state_ref(clean_uid, client)

    @firestore.transactional
    def stamp(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        first = not state.get('first_shown_at')
        update: Dict[str, Any] = {
            'last_shown_at': now_utc,
            'shown_sets': int(state.get('shown_sets') or 0) + 1,
        }
        if first:
            update['first_shown_at'] = now_utc
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
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    now_utc = as_utc(now) or datetime.now(timezone.utc)
    _state_ref(clean_uid, firestore_client).set({'last_empty_check_at': now_utc}, merge=True)


def record_tag_prompts_dismissed(uid: str, now: datetime, *, firestore_client: Any = None) -> int:
    """Count a set closed without any answer. Returns the new streak length."""
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    now_utc = as_utc(now) or datetime.now(timezone.utc)
    client = _client(firestore_client)
    ref = _state_ref(clean_uid, client)

    @firestore.transactional
    def bump(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        streak = int(state.get('consecutive_dismissals') or 0) + 1
        update = {'consecutive_dismissals': streak, 'last_dismissed_at': now_utc}
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return streak

    return run_transactional(client, bump)


def record_tag_prompt_answered(uid: str, prompt_id: str, now: datetime, *, firestore_client: Any = None) -> None:
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    if not prompt_id or not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError("prompt_id must be a non-empty string")
    clean_prompt_id = prompt_id.strip()
    now_utc = as_utc(now) or datetime.now(timezone.utc)
    client = _client(firestore_client)
    ref = _state_ref(clean_uid, client)

    @firestore.transactional
    def record(transaction: Any) -> None:
        snapshot = ref.get(transaction=transaction)
        answered = _pruned_answers(snapshot.to_dict() or {}, now_utc)
        answered[clean_prompt_id] = now_utc
        update = {'answered': answered, 'consecutive_dismissals': 0, 'last_answered_at': now_utc}
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
    clean_uid = _clean_uid(uid)
    if not clean_uid:
        raise ValueError("uid must be a non-empty string")
    if not embedding or not isinstance(embedding, (list, tuple)):
        raise ValueError("embedding must be a non-empty sequence of floats")
    if not callable(pool):
        raise ValueError("pool must be a callable")
    if not conversation_id or not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id must be a non-empty string")
    clean_conv_id = conversation_id.strip()

    client = _client(firestore_client)
    ref = client.collection('users').document(clean_uid)

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
        confirmations.append({'embedding': list(embedding), 'conversation_id': clean_conv_id, 'at': now})
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
