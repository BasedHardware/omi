"""Version-fenced voice-learning state writes on person documents.

The speaker-learning attempt snapshot is fenced by the person document's
`updated_at`: a concurrent relabel bumps it, so a stale attempt's diagnostic
write is dropped. The write never touches `updated_at` itself — bumping it
would invalidate the snapshot the attempt legitimately published against.
"""

import math
from typing import Any, Optional

from google.cloud.firestore_v1 import transactional

from models.other import VoiceReadiness, voice_readiness

from ._client import get_firestore_client, run_transactional

_MAX_IDENTIFIER_LENGTH = 128
_MAX_LABEL_LENGTH = 64
_RESERVED_SEGMENTS = frozenset({'', '.', '..', '__reserved__'})
_LEARNING_STATES = frozenset({'learned', 'disabled'})


def _clean_document_id(value: object, *, label: str) -> Optional[str]:
    """A Firestore document id that cannot escape its collection or nest a path."""
    if not isinstance(value, str) or isinstance(value, bool):
        return None
    token = value.strip()
    if token in _RESERVED_SEGMENTS or len(token) > _MAX_IDENTIFIER_LENGTH:
        return None
    if any(char in token for char in '/\\') or '..' in token:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        return None
    return token


def _clean_label(value: object, *, label: str) -> Optional[str]:
    if not isinstance(value, str) or isinstance(value, bool):
        return None
    token = value.strip()
    if not token or len(token) > _MAX_LABEL_LENGTH:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        return None
    return token


def _clean_seconds(value: object) -> Optional[float]:
    """A finite, non-negative duration; booleans, NaN and infinities are dropped."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _clean_snapshot(snapshot: Any) -> Optional[dict]:
    """The document payload; a snapshot whose payload is not a mapping is unusable."""
    if snapshot is None or not getattr(snapshot, 'exists', False):
        return None
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        return None
    return payload


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
    person = _clean_snapshot(person_ref.get(transaction=transaction))
    if person is None:
        return None
    user_payload = _clean_snapshot(user_ref.get(transaction=transaction))
    settings = user_payload if user_payload is not None else {}
    if person.get('updated_at') != expected_updated_at:
        return False
    if not settings.get('save_other_voice_profiles', True):
        state = 'disabled'
    elif state != 'disabled' and voice_readiness(person) == VoiceReadiness.ready:
        state = 'learned'
    if state in _LEARNING_STATES:
        needed_seconds = None
        if person.get('voice_speech_seconds') is not None:
            speech_seconds = person.get('voice_speech_seconds')
    transaction.update(
        person_ref,
        {
            'voice_learning_state': state,
            'voice_learning_outcome': outcome,
            'voice_speech_seconds': _clean_seconds(speech_seconds),
            'voice_needed_seconds': _clean_seconds(needed_seconds),
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
    since the attempt read the person), ``None`` when the person is gone or the
    arguments cannot address a person document at all.
    """
    clean_uid = _clean_document_id(uid, label='uid')
    clean_person_id = _clean_document_id(person_id, label='person_id')
    clean_outcome = _clean_label(outcome, label='outcome')
    clean_state = _clean_label(state, label='state')
    if clean_uid is None or clean_person_id is None or clean_outcome is None or clean_state is None:
        return None
    if firestore_client is not None:
        client = firestore_client
    else:
        try:
            client = get_firestore_client()
        except Exception:
            return None
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
        _clean_seconds(speech_seconds),
        _clean_seconds(needed_seconds),
    )
