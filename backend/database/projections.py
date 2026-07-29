"""
Projections database module

A projection is a generated image carrying a single future-tense imperative. It is
persisted per user and read back over the authenticated API, following the same
document shape and access pattern as `database/daily_summaries.py`.

Structure:
users/{uid}/projections/{projection_id}
    ├── id: str
    ├── created_at: timestamp
    ├── imperative: str
    ├── image_url: str
    └── generation: Dict[str, Any]  (model, size, quality, prompt)
"""

from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore

from ._client import get_firestore_client

PROJECTIONS_COLLECTION = 'projections'


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
