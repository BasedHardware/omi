"""Version-fenced voice-learning state writes on person documents.

The speaker-learning attempt snapshot is fenced by the person document's
`updated_at`: a concurrent relabel bumps it, so a stale attempt's diagnostic
write is dropped. The write never touches `updated_at` itself — bumping it
would invalidate the snapshot the attempt legitimately published against.
"""

import math
from typing import Any, Dict, Optional, cast

from google.cloud.firestore_v1 import transactional

from models.other import VoiceReadiness, voice_readiness

from ._client import get_firestore_client, run_transactional


def _sanitize_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a non-empty string')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError(f'{field_name} must be a safe document id')
    return cleaned


def _sanitize_label(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a non-empty string')
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{field_name} must be a non-empty string')
    return cleaned


def _normalize_seconds(value: object) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        coerced = float(value)
        if not math.isfinite(coerced):
            return None
        return coerced if coerced >= 0.0 else 0.0
    return None


@transactional
def _update_voice_learning_transaction(
    transaction: Any,
    person_ref: Any,
    user_ref: Any,
    expected_updated_at: Any,
    outcome: str,
    state: str,
    speech_seconds: Optional[float],
    needed_seconds: Optional[float],
) -> Optional[bool]:
    snapshot = person_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return None
    raw_person: object = snapshot.to_dict()
    person: Dict[str, Any] = cast(Dict[str, Any], raw_person) if isinstance(raw_person, dict) else {}
    user_snapshot = user_ref.get(transaction=transaction)
    raw_settings: object = user_snapshot.to_dict() if getattr(user_snapshot, 'exists', False) else {}
    settings: Dict[str, Any] = cast(Dict[str, Any], raw_settings) if isinstance(raw_settings, dict) else {}
    if person.get('updated_at') != expected_updated_at:
        return False
    speech_seconds = _normalize_seconds(speech_seconds)
    needed_seconds = _normalize_seconds(needed_seconds)
    if not settings.get('save_other_voice_profiles', True):
        state = 'disabled'
    elif state != 'disabled' and voice_readiness(person) == VoiceReadiness.ready:
        state = 'learned'
    if state in ('learned', 'disabled'):
        needed_seconds = None
        stored_speech = _normalize_seconds(person.get('voice_speech_seconds'))
        if stored_speech is not None:
            speech_seconds = stored_speech
    transaction.update(
        person_ref,
        {
            'voice_learning_state': state,
            'voice_learning_outcome': outcome,
            'voice_speech_seconds': speech_seconds,
            'voice_needed_seconds': needed_seconds,
        },
    )
    return True


def update_person_voice_learning(
    uid: str,
    person_id: str,
    expected_updated_at: Any,
    *,
    outcome: str,
    state: str,
    speech_seconds: Optional[float],
    needed_seconds: Optional[float],
    firestore_client: Optional[Any] = None,
) -> Optional[bool]:
    """Persist a bounded voice-learning outcome and its public state.

    Returns ``True`` on write, ``False`` when the snapshot is stale (relabel
    since the attempt read the person), ``None`` when the person is gone.
    """
    clean_uid = _sanitize_id(uid, 'uid')
    clean_person_id = _sanitize_id(person_id, 'person_id')
    clean_outcome = _sanitize_label(outcome, 'outcome')
    clean_state = _sanitize_label(state, 'state')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(clean_uid)
    person_ref = user_ref.collection('people').document(clean_person_id)
    return run_transactional(
        client,
        _update_voice_learning_transaction,
        person_ref,
        user_ref,
        expected_updated_at,
        clean_outcome,
        clean_state,
        speech_seconds,
        needed_seconds,
    )
