"""Missing owner print repair on the authoritative customer data plane."""

from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, cast

from google.cloud import firestore

from database._client import get_data_plane_firestore_client as get_firestore_client, run_transactional
from database.account_deletion_marker import account_deletion_document

logger = logging.getLogger(__name__)


def _sanitize_uid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('uid must be a non-empty string')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError('uid must be a safe document id')
    return cleaned


def _clean_optional_uid(value: object) -> str:
    try:
        return _sanitize_uid(value)
    except ValueError:
        return ''


def _validate_embedding(value: object) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) == 0:
        raise ValueError('embedding must be a non-empty list of finite numbers')
    normalized: List[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError('embedding elements must be finite numbers')
        coerced = float(item)
        if not math.isfinite(coerced):
            raise ValueError('embedding elements must be finite numbers')
        normalized.append(coerced)
    return normalized


def get_user_speaker_embedding_recovery_state(
    uid: str, *, firestore_client: Optional[Any] = None
) -> Optional[Tuple[Any, Any]]:
    """Existing owner publication timestamp and vector, observed before repair."""
    clean_uid = _clean_optional_uid(uid)
    if not clean_uid:
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = client.collection('users').document(clean_uid).get()
    except Exception as exc:
        logger.warning('Failed to read speaker embedding recovery state for %s: %s', clean_uid, exc)
        return None
    if not getattr(snapshot, 'exists', False):
        return None
    raw_data: object = snapshot.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw_data) if isinstance(raw_data, dict) else {}
    return data.get('speaker_embedding_updated_at'), data.get('speaker_embedding')


def recover_user_speaker_embedding(
    uid: str,
    embedding: list,
    *,
    expected_updated_at: Any,
    firestore_client: Optional[Any] = None,
) -> bool:
    """Repair only an unchanged missing vector; enrollment/teaching/deletion win."""
    clean_uid = _sanitize_uid(uid)
    clean_embedding = _validate_embedding(embedding)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(clean_uid)
    marker = account_deletion_document(clean_uid, firestore_client=client)

    @firestore.transactional
    def repair(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        deleting = marker.get(transaction=transaction)
        raw_data: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else {}
        data: Dict[str, Any] = cast(Dict[str, Any], raw_data) if isinstance(raw_data, dict) else {}
        if (
            not getattr(snapshot, 'exists', False)
            or getattr(deleting, 'exists', False)
            or data.get('speaker_embedding')
            or data.get('speaker_embedding_updated_at') != expected_updated_at
        ):
            return False
        transaction.update(
            ref, {'speaker_embedding': clean_embedding, 'speaker_embedding_updated_at': datetime.now(timezone.utc)}
        )
        return True

    return bool(run_transactional(client, repair))
