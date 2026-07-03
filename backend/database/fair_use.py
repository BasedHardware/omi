"""Firestore CRUD for fair-use tracking.

Required Firestore composite indexes (create before deploying):

1. Collection group: fair_use_state
   Fields: stage (Ascending), updated_at (Descending)
   Scope: Collection group
   Used by: get_flagged_users() — admin dashboard

2. Collection group: fair_use_events
   Fields: case_ref (Ascending)
   Scope: Collection group
   Used by: lookup_case(), get_public_case_status() — case reference lookup

Create via gcloud:
  gcloud firestore indexes composite create --project=<PROJECT> \\
    --collection-group=fair_use_state \\
    --query-scope=collection-group \\
    --field-config=field-path=stage,order=ascending \\
    --field-config=field-path=updated_at,order=descending

  gcloud firestore indexes composite create --project=<PROJECT> \\
    --collection-group=fair_use_events \\
    --query-scope=collection-group \\
    --field-config=field-path=case_ref,order=ascending
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore

from ._client import db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fair-use state (users/{uid}/fair_use_state/current)
# ---------------------------------------------------------------------------


def get_fair_use_state(uid: str) -> Dict[str, Any]:
    """Get the current fair-use enforcement state for a user."""
    ref = db.collection('users').document(uid).collection('fair_use_state').document('current')
    doc = ref.get()
    if getattr(doc, "exists", False):
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    return {}


def update_fair_use_state(uid: str, updates: Dict[str, Any]) -> None:
    """Update fair-use state atomically."""
    ref = db.collection('users').document(uid).collection('fair_use_state').document('current')
    updates['updated_at'] = datetime.now(timezone.utc)
    ref.set(updates, merge=True)


def set_fair_use_stage(uid: str, stage: str, **kwargs: Any) -> None:
    """Set enforcement stage with optional extra fields."""
    updates: Dict[str, Any] = {'stage': stage, **kwargs}
    update_fair_use_state(uid, updates)


# ---------------------------------------------------------------------------
# Fair-use events (users/{uid}/fair_use_events/{event_id})
# ---------------------------------------------------------------------------


def _generate_case_ref() -> str:
    """Generate a human-readable case reference like FU-A1B2C3D4E5F6.

    Uses 12 hex chars from UUID4 (16^12 ≈ 281 trillion possibilities),
    safe for public unauthenticated lookup without enumeration risk.
    """
    return f'FU-{uuid.uuid4().hex[:12].upper()}'


def create_fair_use_event(uid: str, event_data: Dict[str, Any]) -> str:
    """Create a new fair-use violation event. Returns the event ID."""
    ref = db.collection('users').document(uid).collection('fair_use_events').document()
    event_data['created_at'] = datetime.now(timezone.utc)
    event_data['case_ref'] = _generate_case_ref()
    ref.set(event_data)
    return str(ref.id)


def get_fair_use_events(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent fair-use events for a user, newest first."""
    ref = db.collection('users').document(uid).collection('fair_use_events')
    docs = ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).stream()
    events: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        events.append(data)
    return events


def get_violation_counts(uid: str) -> Dict[str, int]:
    """Count violations in the last 7 and 30 days."""
    ref = db.collection('users').document(uid).collection('fair_use_events')
    now = datetime.now(timezone.utc)

    count_7d = 0
    count_30d = 0
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d = now - timedelta(days=7)

    docs = ref.where('created_at', '>=', cutoff_30d).stream()
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        created = data.get('created_at')
        if created:
            # Normalize to aware UTC for comparison (Firestore may return aware datetimes)
            if isinstance(created, datetime) and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            count_30d += 1
            if created >= cutoff_7d:
                count_7d += 1

    return {'violation_count_7d': count_7d, 'violation_count_30d': count_30d}


def resolve_fair_use_event(uid: str, event_id: str, admin_uid: str, notes: str = "") -> None:
    """Mark a fair-use event as resolved by admin."""
    ref = db.collection('users').document(uid).collection('fair_use_events').document(event_id)
    ref.update(
        {
            'resolved': True,
            'resolved_at': datetime.now(timezone.utc),
            'resolved_by': admin_uid,
            'admin_notes': notes,
        }
    )


def reset_fair_use_state(uid: str, admin_uid: str) -> None:
    """Reset a user's fair-use state to clean (admin action)."""
    update_fair_use_state(
        uid,
        {
            'stage': 'none',
            'violation_count_7d': 0,
            'violation_count_30d': 0,
            'last_violation_at': None,
            'throttle_until': None,
            'restrict_until': None,
            'last_classifier_score': 0.0,
            'last_classifier_type': 'none',
            'reset_by': admin_uid,
            'reset_at': datetime.now(timezone.utc),
        },
    )


# ---------------------------------------------------------------------------
# Admin queries
# ---------------------------------------------------------------------------


def get_flagged_users(stage_filter: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get users with active fair-use enforcement, for admin dashboard."""
    # Query all users who have fair_use_state with stage != 'none'
    # This requires a collection group query on fair_use_state
    query = db.collection_group('fair_use_state')
    if stage_filter:
        query = query.where('stage', '==', stage_filter)
    else:
        # Use 'in' filter instead of '!=' to allow order_by on 'updated_at'
        # Firestore requires first order_by to match the inequality field
        query = query.where('stage', 'in', ['warning', 'throttle', 'restrict'])

    query = query.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(limit)

    results: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        # Extract uid from document path: users/{uid}/fair_use_state/current
        path_parts = doc.reference.path.split('/')
        if len(path_parts) >= 2:
            data['uid'] = path_parts[1]
        data['id'] = doc.id
        results.append(data)
    return results
