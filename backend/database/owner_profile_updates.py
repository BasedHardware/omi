"""Missing owner print repair on the authoritative customer data plane."""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore

from database._client import get_data_plane_firestore_client as get_firestore_client
from database._client import run_transactional
from database.account_deletion_marker import account_deletion_document

logger = logging.getLogger(__name__)

_MAX_ID_LENGTH = 128


def _sanitize_uid(uid: Any) -> str:
    """Return a Firestore-safe ``uid`` or raise ``ValueError``.

    A blank id, a path separator, a traversal segment, a control character or an
    overlong id either composes an invalid document path that the SDK rejects far
    from the call site, or silently addresses a different document (``a/b`` reads
    ``users/a/b`` rather than a user called ``a/b``).
    """
    if not isinstance(uid, str):
        raise ValueError('uid must be a string')
    text = uid.strip()
    if not text:
        raise ValueError('uid must not be empty')
    if len(text) > _MAX_ID_LENGTH:
        raise ValueError(f'uid must be at most {_MAX_ID_LENGTH} characters')
    if '/' in text or '\\' in text or '..' in text:
        raise ValueError('uid must not contain path separators or traversal segments')
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
        raise ValueError('uid must not contain control characters')
    return text


def _validate_embedding(embedding: Any) -> list[float]:
    """Return a non-empty finite numeric vector or raise ``ValueError``.

    ``voiceprint`` vectors are compared element-wise downstream; an empty vector,
    a ``bool``, a non-numeric entry or a ``NaN``/``inf`` value makes every later
    similarity score meaningless rather than failing, so the write is refused
    here instead of corrupting the stored print.
    """
    if not isinstance(embedding, (list, tuple)):
        raise ValueError('embedding must be a list or tuple')
    if not embedding:
        raise ValueError('embedding must not be empty')
    vector: list[float] = []
    for value in embedding:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('embedding entries must be numbers')
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('embedding entries must be finite')
        vector.append(number)
    return vector


def _as_mapping(value: Any) -> dict:
    """Return ``value`` when it is a mapping, otherwise an empty dict.

    ``snapshot.to_dict() or {}`` only guards ``None``: a corrupted or emulated
    snapshot that returns a truthy non-mapping (a list, a string) survives that
    guard and reaches ``.get``, raising ``AttributeError``.
    """
    return value if isinstance(value, dict) else {}


def get_user_speaker_embedding_recovery_state(uid: str, *, firestore_client: Optional[Any] = None):
    """Existing owner publication timestamp and vector, observed before repair.

    This is an opportunistic check on the enrollment path: a transient read
    failure must leave the caller's authoritative state untouched rather than
    aborting enrollment, so read errors are logged and reported as "no state".
    """
    safe_uid = _sanitize_uid(uid)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = client.collection('users').document(safe_uid).get()
    except Exception as error:  # noqa: BLE001 - opportunistic read must not break the caller
        logger.warning('owner voiceprint recovery state read failed uid=%s: %s', safe_uid, error)
        return None
    if not snapshot.exists:
        return None
    data = _as_mapping(snapshot.to_dict())
    return data.get('speaker_embedding_updated_at'), data.get('speaker_embedding')


def recover_user_speaker_embedding(
    uid: str,
    embedding: list,
    *,
    expected_updated_at,
    firestore_client: Optional[Any] = None,
) -> bool:
    """Repair only an unchanged missing vector; enrollment/teaching/deletion win."""
    safe_uid = _sanitize_uid(uid)
    vector = _validate_embedding(embedding)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(safe_uid)
    marker = account_deletion_document(safe_uid, firestore_client=client)

    @firestore.transactional
    def repair(transaction):
        snapshot = ref.get(transaction=transaction)
        deleting = marker.get(transaction=transaction)
        data = _as_mapping(snapshot.to_dict())
        if (
            not snapshot.exists
            or deleting.exists
            or data.get('speaker_embedding')
            or data.get('speaker_embedding_updated_at') != expected_updated_at
        ):
            return False
        transaction.update(
            ref, {'speaker_embedding': vector, 'speaker_embedding_updated_at': datetime.now(timezone.utc)}
        )
        return True

    return run_transactional(client, repair)
