"""Version-fenced voice-learning state writes on person documents.

The speaker-learning attempt snapshot is fenced by the person document's
`updated_at`: a concurrent relabel bumps it, so a stale attempt's diagnostic
write is dropped. The write never touches `updated_at` itself — bumping it
would invalidate the snapshot the attempt legitimately published against.
"""

from typing import Any, Optional

from google.cloud.firestore_v1 import transactional

from models.other import VoiceReadiness, voice_readiness

from ._client import get_firestore_client, run_transactional


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
    if not snapshot.exists:
        return None
    person = snapshot.to_dict()
    user_snapshot = user_ref.get(transaction=transaction)
    settings = (user_snapshot.to_dict() or {}) if user_snapshot.exists else {}
    if person.get('updated_at') != expected_updated_at:
        return False
    if not settings.get('save_other_voice_profiles', True):
        state = 'disabled'
    elif state != 'disabled' and voice_readiness(person) == VoiceReadiness.ready:
        state = 'learned'
    if state in ('learned', 'disabled'):
        needed_seconds = None
        if person.get('voice_speech_seconds') is not None:
            speech_seconds = person.get('voice_speech_seconds')
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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    person_ref = user_ref.collection('people').document(person_id)
    return run_transactional(
        client,
        _update_voice_learning_transaction,
        person_ref,
        user_ref,
        expected_updated_at,
        outcome,
        state,
        speech_seconds,
        needed_seconds,
    )
