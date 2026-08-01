"""
Projections database module

A projection is a generated image carrying a single imperative. It is persisted per
user and read back over the authenticated API. Scheduled generation first reserves the
deterministic daily id in Firestore, then finalizes only while the same attempt still
owns that reservation.

Structure:
users/{uid}/projections/{projection_id}
    ├── id: str
    ├── created_at: timestamp
    ├── imperative: str
    ├── image_url: str
    └── generation: Dict[str, Any]  (model, size, quality, prompt)

users/{uid}/projection_generation_reservations/{projection_id}
    ├── attempt_token: str
    ├── cadence_key: str
    ├── expires_at: timestamp
    └── status: "reserved" | "finalized"
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore

from ._client import get_firestore_client

PROJECTIONS_COLLECTION = 'projections'
PROJECTION_RESERVATIONS_COLLECTION = 'projection_generation_reservations'


def _projection_refs(client: Any, uid: str, projection_id: str) -> tuple[Any, Any]:
    user_ref = client.collection('users').document(uid)
    return (
        user_ref.collection(PROJECTIONS_COLLECTION).document(projection_id),
        user_ref.collection(PROJECTION_RESERVATIONS_COLLECTION).document(projection_id),
    )


def reserve_projection_generation(
    uid: str,
    projection_id: str,
    cadence_key: str,
    attempt_token: str,
    *,
    now: datetime,
    expires_at: datetime,
    firestore_client: Any = None,
) -> bool:
    """Atomically reserve a scheduled projection id for one bounded attempt."""
    if now.tzinfo is None or expires_at.tzinfo is None:
        raise ValueError('projection reservation timestamps must be timezone-aware')
    if expires_at <= now:
        raise ValueError('projection reservation expiry must be in the future')
    if not attempt_token:
        raise ValueError('projection reservation attempt token is required')

    client = firestore_client or get_firestore_client()
    projection_ref, reservation_ref = _projection_refs(client, uid, projection_id)
    transaction = client.transaction()

    @firestore.transactional
    def _reserve(transaction: Any) -> bool:
        projection_snapshot = projection_ref.get(transaction=transaction)
        reservation_snapshot = reservation_ref.get(transaction=transaction)
        if getattr(projection_snapshot, 'exists', False):
            return False

        reservation = reservation_snapshot.to_dict() if getattr(reservation_snapshot, 'exists', False) else None
        current_expiry = reservation.get('expires_at') if isinstance(reservation, dict) else None
        if isinstance(current_expiry, datetime) and current_expiry > now:
            return False

        transaction.set(
            reservation_ref,
            {
                'projection_id': projection_id,
                'cadence_key': cadence_key,
                'attempt_token': attempt_token,
                'reserved_at': now,
                'expires_at': expires_at,
                'status': 'reserved',
            },
        )
        return True

    return bool(_reserve(transaction))


def finalize_projection_generation(
    uid: str,
    projection_data: Dict[str, Any],
    attempt_token: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> bool:
    """Persist a generated projection only while ``attempt_token`` owns its reservation."""
    if now.tzinfo is None:
        raise ValueError('projection finalization timestamp must be timezone-aware')
    projection_id = cast(str, projection_data['id'])
    client = firestore_client or get_firestore_client()
    projection_ref, reservation_ref = _projection_refs(client, uid, projection_id)
    transaction = client.transaction()

    @firestore.transactional
    def _finalize(transaction: Any) -> bool:
        projection_snapshot = projection_ref.get(transaction=transaction)
        reservation_snapshot = reservation_ref.get(transaction=transaction)
        if getattr(projection_snapshot, 'exists', False) or not getattr(reservation_snapshot, 'exists', False):
            return False

        reservation = reservation_snapshot.to_dict()
        if not isinstance(reservation, dict):
            return False
        expires_at = reservation.get('expires_at')
        if (
            reservation.get('status') != 'reserved'
            or reservation.get('attempt_token') != attempt_token
            or not isinstance(expires_at, datetime)
            or expires_at <= now
        ):
            return False

        transaction.create(projection_ref, projection_data)
        transaction.update(
            reservation_ref,
            {
                'status': 'finalized',
                'finalized_at': now,
            },
        )
        return True

    return bool(_finalize(transaction))


def create_projection(uid: str, projection_data: Dict[str, Any], *, firestore_client: Any = None) -> str:
    """Create a projection document and return its id."""
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    projection_ref = user_ref.collection(PROJECTIONS_COLLECTION).document(projection_data['id'])
    projection_ref.set(projection_data)
    return cast(str, projection_data['id'])


def get_projection(uid: str, projection_id: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """Get a single projection by id, or None if it does not exist."""
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    doc = user_ref.collection(PROJECTIONS_COLLECTION).document(projection_id).get()

    if getattr(doc, 'exists', False):
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_projections(
    uid: str, limit: int = 30, offset: int = 0, *, firestore_client: Any = None
) -> List[Dict[str, Any]]:
    """List projections newest first."""
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    query = (
        user_ref.collection(PROJECTIONS_COLLECTION)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
        .offset(offset)
    )
    results: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            results.append(cast(Dict[str, Any], raw))
    return results


def set_projection_feedback(
    uid: str,
    projection_id: str,
    rating: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Set the owner's latest explicit response signal, or return False if absent."""
    client = firestore_client or get_firestore_client()
    projection_ref = client.collection('users').document(uid).collection(PROJECTIONS_COLLECTION).document(projection_id)
    if not getattr(projection_ref.get(), 'exists', False):
        return False
    projection_ref.update(
        {
            'feedback': {
                'rating': rating,
                'updated_at': firestore.SERVER_TIMESTAMP,
            }
        }
    )
    return True
