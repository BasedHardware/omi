"""Backend-neutral persistence for fair-use tracking (storage port, WP2).

State and violation events live under ``users/{uid}/fair_use_state/current`` and
``users/{uid}/fair_use_events/{event_id}``. Two admin/lookup functions run cross-parent
collection-group queries via ``store.query_group`` — the backend must index them accordingly:

1. group ``fair_use_state`` — filter on ``stage``, ordered by ``updated_at`` (desc).
   Used by ``get_flagged_users()`` (admin dashboard).
2. group ``fair_use_events`` — filter on ``case_ref``.
   Used by ``lookup_fair_use_event_by_case_ref()`` (public case-reference lookup).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from database.store import get_document_store

logger = logging.getLogger(__name__)


def _store():
    return get_document_store()


# ---------------------------------------------------------------------------
# Fair-use state (users/{uid}/fair_use_state/current)
# ---------------------------------------------------------------------------


def get_fair_use_state(uid: str) -> Dict[str, Any]:
    """Get the current fair-use enforcement state for a user."""
    doc = _store().get(f'users/{uid}/fair_use_state/current')
    if doc.exists:
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    return {}


def update_fair_use_state(uid: str, updates: Dict[str, Any]) -> None:
    """Update fair-use state atomically."""
    updates['updated_at'] = datetime.now(timezone.utc)
    _store().set(f'users/{uid}/fair_use_state/current', updates, merge=True)


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
    event_id = uuid.uuid4().hex
    event_data['created_at'] = datetime.now(timezone.utc)
    event_data['case_ref'] = _generate_case_ref()
    _store().create(f'users/{uid}/fair_use_events/{event_id}', event_data)
    return event_id


def get_fair_use_events(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent fair-use events for a user, newest first."""
    docs = _store().query(f'users/{uid}/fair_use_events', order_by='created_at', direction='desc', limit=limit)
    events: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        events.append(data)
    return events


def get_violation_counts(uid: str) -> Dict[str, int]:
    """Count violations in the last 7 and 30 days."""
    now = datetime.now(timezone.utc)

    count_7d = 0
    count_30d = 0
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d = now - timedelta(days=7)

    docs = _store().query(f'users/{uid}/fair_use_events', filters=[('created_at', '>=', cutoff_30d)])
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
    _store().update(
        f'users/{uid}/fair_use_events/{event_id}',
        {
            'resolved': True,
            'resolved_at': datetime.now(timezone.utc),
            'resolved_by': admin_uid,
            'admin_notes': notes,
        },
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
    # Query all users who have fair_use_state with stage != 'none'.
    # This is a collection-group query on fair_use_state, ordered by updated_at.
    if stage_filter:
        filters = [('stage', '==', stage_filter)]
    else:
        # Use 'in' filter instead of '!=' to allow order_by on 'updated_at'
        # Firestore requires first order_by to match the inequality field
        filters = [('stage', 'in', ['warning', 'throttle', 'restrict'])]

    docs = _store().query_group(
        'fair_use_state', filters=filters, order_by='updated_at', direction='desc', limit=limit
    )

    results: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        # Extract uid from document path: users/{uid}/fair_use_state/current
        path_parts = doc.path.split('/')
        if len(path_parts) >= 2:
            data['uid'] = path_parts[1]
        data['id'] = doc.id
        results.append(data)
    return results


def lookup_fair_use_event_by_case_ref(case_ref: str) -> Optional[Dict[str, Any]]:
    """Find a fair-use event by its case reference across all users (collection group).

    Returns the event dict with 'uid' and 'event_id' added, or None if not found.
    Requires the fair_use_events collection-group index on case_ref (see module header).
    """
    docs = _store().query_group('fair_use_events', filters=[('case_ref', '==', case_ref)], limit=1)
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        path_parts = doc.path.split('/')
        if len(path_parts) >= 2:
            data['uid'] = path_parts[1]
        data['event_id'] = doc.id
        return data
    return None
