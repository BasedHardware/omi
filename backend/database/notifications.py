"""
Notifications database module

Structure:
users/{uid}/fcm_tokens (subcollection)
  └── {device_key} (document)
      ├── token: "actual_token_value"
      ├── created_at: timestamp
      └── time_zone: "America/New_York"
"""

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from google.cloud.firestore import DELETE_FIELD
from ._client import db
from .cache import get_memory_cache
from database.store import ensure_id_segment, get_document_store
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union, cast

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UnifiedPush endpoints (ADR-0011) — the on-prem push counterpart of FCM tokens.
# Stored at users/{uid}/unifiedpush_endpoints/{device_key} through the neutral store port (so it runs
# on Mongo/Firestore alike), mirroring the FCM-token subcollection shape one-for-one.
# ---------------------------------------------------------------------------


@dataclass
class UnifiedPushEndpoint:
    """A registered UnifiedPush delivery endpoint. ``url`` is the distributor POST target; ``p256dh``/
    ``auth`` are the optional WebPush encryption keys (absent = plaintext POST)."""

    url: str
    device_key: str = ''
    time_zone: Optional[str] = None
    p256dh: Optional[str] = None
    auth: Optional[str] = None


_UNIFIEDPUSH_COLLECTION = 'unifiedpush_endpoints'


def _endpoint_from_doc(doc: Any) -> UnifiedPushEndpoint:
    d = doc.to_dict() or {}
    return UnifiedPushEndpoint(
        url=str(d.get('endpoint', '')),
        device_key=str(d.get('device_key', '')),
        time_zone=d.get('time_zone'),
        p256dh=d.get('p256dh'),
        auth=d.get('auth'),
    )


def save_endpoint(uid: str, data: Dict[str, Any]) -> None:
    """Register/replace a UnifiedPush endpoint for one device (keyed by device_key, like fcm_tokens).

    Mirrors the endpoint's ``time_zone`` onto the user doc (parity with ``save_token``) so the
    daily-summary timezone queries see UnifiedPush-only users too.
    """
    # device_key comes from client headers (platform + X-Device-Id-Hash). A '/' would make an invalid
    # logical path and diverge across backends (Firestore rejects the odd segment count; Mongo would
    # store it outside the endpoints collection, so get_all_endpoints never finds it). Reject unsafe
    # segments at the boundary (cubic PR 10887 B1) rather than composing a corrupt path.
    device_key = ensure_id_segment(str(data.get('device_key') or 'unknown_default'), label='device_key')
    store = get_document_store()
    store.set(
        f'users/{uid}/{_UNIFIEDPUSH_COLLECTION}/{device_key}',
        {
            'endpoint': data['endpoint'],
            'device_key': device_key,
            'time_zone': data.get('time_zone'),
            'p256dh': data.get('p256dh'),
            'auth': data.get('auth'),
            'created_at': datetime.now(timezone.utc),
        },
    )
    time_zone = data.get('time_zone')
    if time_zone:
        store.set(f'users/{uid}', {'time_zone': time_zone}, merge=True)


def get_all_endpoints(uid: str) -> List[UnifiedPushEndpoint]:
    store = get_document_store()
    return [_endpoint_from_doc(doc) for doc in store.query(f'users/{uid}/{_UNIFIEDPUSH_COLLECTION}')]


def remove_bulk_endpoints(urls: List[str]) -> None:
    """Delete every stored endpoint whose url is in ``urls``, across all users (dead-endpoint cleanup
    on 404/410). Collection-group scan so a distributor URL retired on one device is purged
    everywhere it was registered."""
    if not urls:
        return
    dead = set(urls)
    store = get_document_store()
    for doc in store.query_group(_UNIFIEDPUSH_COLLECTION):
        if (doc.to_dict() or {}).get('endpoint') in dead:
            store.delete(doc.path)


def get_users_endpoints_in_timezones(time_zones: List[str]) -> List[UnifiedPushEndpoint]:
    """UnifiedPush endpoints of every user whose ``time_zone`` is in ``time_zones`` (daily-summary
    fan-out parity with the FCM token path)."""
    if not time_zones:
        return []
    store = get_document_store()
    endpoints: List[UnifiedPushEndpoint] = []
    # ONE collection-group query per chunk, filtered by the endpoint's own ``time_zone`` — not a per-user
    # fan-out (query users in the tz, then get_all_endpoints per user = N+1 reads on the DB worker every
    # hour, cubic PR 10887 database/notifications.py:121). save_endpoint writes the endpoint's time_zone
    # and the user's together (parity), so for a UnifiedPush user they stay in sync; this returns exactly
    # the matched endpoints, bounded by matches (an index on the group's d.time_zone — provisioned by
    # reconcile_mongo_indexes — keeps it off a collection scan). A Firestore 'in' rejects >30 values, so
    # chunk. Per-chunk isolation: one failing timezone chunk must not abort the morning fan-out.
    unique = list(dict.fromkeys(time_zones))
    for i in range(0, len(unique), 30):
        try:
            for doc in store.query_group(_UNIFIEDPUSH_COLLECTION, filters=[('time_zone', 'in', unique[i : i + 30])]):
                endpoints.append(_endpoint_from_doc(doc))
        except Exception as e:
            logger.error(f'UnifiedPush timezone chunk {i // 30} failed (other chunks unaffected): {e}')
    return endpoints


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def save_token(uid: str, data: Dict[str, Any]) -> None:
    """
    Store token in subcollection with device key as document ID
    Structure: users/{uid}/fcm_tokens/{device_key}
    Also maintains time_zone in main user document for backward compatibility
    Migrates legacy fcm_token to subcollection
    """
    device_key = data.get('device_key', 'unknown_default')
    token = data.get('fcm_token')
    time_zone = data.get('time_zone')

    user_ref = db.collection('users').document(uid)

    # Step 1: Migrate legacy token if exists
    user_doc = user_ref.get()
    if getattr(user_doc, "exists", False):
        user_data = _typed_doc(user_doc)
        legacy_token = user_data.get('fcm_token')

        if legacy_token:
            # Check if legacy token already exists in subcollection
            existing_tokens: List[object] = [
                t for t in (_typed_doc(d).get('token') for d in user_ref.collection('fcm_tokens').stream())
            ]

            if legacy_token not in existing_tokens:
                # Migrate to unknown_default
                user_ref.collection('fcm_tokens').document('unknown_default').set(
                    {
                        'token': legacy_token,
                        'time_zone': user_data.get('time_zone'),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )

            # Remove legacy field
            user_ref.update({'fcm_token': DELETE_FIELD})

    # Step 2: If new token has proper device_key, replace unknown_default
    if device_key != 'unknown_default':
        unknown_ref = user_ref.collection('fcm_tokens').document('unknown_default')
        unknown_doc = unknown_ref.get()
        if getattr(unknown_doc, "exists", False):
            unknown_token = _typed_doc(unknown_doc).get('token')
            # Only delete if it's the same token being migrated to proper device_key
            if unknown_token == token:
                unknown_ref.delete()

    # Step 3: Save new token to subcollection
    user_ref.collection('fcm_tokens').document(device_key).set(
        {'token': token, 'time_zone': time_zone, 'created_at': firestore.SERVER_TIMESTAMP}, merge=True
    )

    # Also update time_zone in main user document (for backward compatibility and efficient queries)
    if time_zone:
        user_ref.set({'time_zone': time_zone}, merge=True)


def get_user_time_zone(uid: str) -> Optional[str]:
    """Get timezone from main user document"""
    user_ref = db.collection('users').document(uid).get()
    if getattr(user_ref, "exists", False):
        user_data = _typed_doc(user_ref)
        tz = user_data.get('time_zone')
        return str(tz) if tz is not None else None
    return None


# **************************************
# *** Daily Summary Time Preferences ***
# **************************************

# Default: 22:00 local time (10 PM)
DEFAULT_DAILY_SUMMARY_HOUR_LOCAL = 22


def get_daily_summary_hour_local(uid: str) -> int | None:
    """Get user's preferred daily summary hour in local time. Returns None if not set."""
    user_ref = db.collection('users').document(uid).get()
    if getattr(user_ref, "exists", False):
        user_data = _typed_doc(user_ref)
        value = user_data.get('daily_summary_hour_local')
        return int(value) if isinstance(value, (int, float)) else None
    return None


def set_daily_summary_hour_local(uid: str, hour_local: int) -> bool:
    """
    Set user's preferred daily summary hour in local time.

    Args:
        uid: User ID
        hour_local: Hour in local timezone (0-23)

    Returns:
        True if successful
    """
    if not (0 <= hour_local <= 23):
        raise ValueError(f"Invalid hour: {hour_local}. Must be 0-23.")

    user_ref = db.collection('users').document(uid)
    user_ref.set({'daily_summary_hour_local': hour_local}, merge=True)
    return True


def get_daily_summary_enabled(uid: str) -> bool:
    """Check if daily summary is enabled for user. Enabled by default."""
    user_ref = db.collection('users').document(uid).get()
    if getattr(user_ref, "exists", False):
        user_data = _typed_doc(user_ref)
        return bool(user_data.get('daily_summary_enabled', True))
    return True


def set_daily_summary_enabled(uid: str, enabled: bool) -> bool:
    """Enable or disable daily summary for user."""
    user_ref = db.collection('users').document(uid)
    user_ref.set({'daily_summary_enabled': enabled}, merge=True)
    return True


# **************************************
# *** Mentor Notification Frequency ***
# **************************************

# Default: 0 (disabled by default, user must explicitly enable)
# Range: 0-5 where 0=disabled, 1=most selective, 5=most proactive
DEFAULT_MENTOR_NOTIFICATION_FREQUENCY = 0


def get_mentor_notification_frequency(uid: str) -> int:
    """
    Get user's mentor notification frequency preference.
    Returns 0-5 where:
    - 0 = disabled
    - 1 = ultra selective (least frequent)
    - 3 = balanced (default)
    - 5 = very proactive (most frequent)

    Uses in-memory cache (30s TTL) + field projection to avoid reading the full
    user doc every 1s per stream. (#5439 sub-task 2)
    """
    cache = get_memory_cache()

    def fetch() -> int:
        doc = db.collection('users').document(uid).get(field_paths=['mentor_notification_frequency'])
        if getattr(doc, "exists", False):
            data = _typed_doc(doc)
            value = data.get('mentor_notification_frequency', DEFAULT_MENTOR_NOTIFICATION_FREQUENCY)
            return int(value) if isinstance(value, (int, float)) else DEFAULT_MENTOR_NOTIFICATION_FREQUENCY
        return DEFAULT_MENTOR_NOTIFICATION_FREQUENCY

    return cache.get_or_fetch(f"mentor_frequency:{uid}", fetch, ttl=30)


def set_mentor_notification_frequency(uid: str, frequency: int) -> bool:
    """
    Set user's mentor notification frequency preference.

    Args:
        uid: User ID
        frequency: Notification frequency (0-5)

    Returns:
        True if successful

    Raises:
        ValueError if frequency is not in valid range
    """
    if not (0 <= frequency <= 5):
        raise ValueError(f"Invalid frequency: {frequency}. Must be 0-5.")

    user_ref = db.collection('users').document(uid)
    user_ref.set({'mentor_notification_frequency': frequency}, merge=True)
    # Invalidate local cache so this instance sees the update immediately
    get_memory_cache().delete(f"mentor_frequency:{uid}")
    return True


def get_all_tokens(uid: str) -> list[str]:
    """Get all device tokens for a user from subcollection and legacy field"""
    tokens: List[str] = []

    # Get tokens from new subcollection
    token_docs = db.collection('users').document(uid).collection('fcm_tokens').stream()
    for doc in token_docs:
        token_data = _typed_doc(doc)
        token_value = token_data.get('token')
        if token_value:
            tokens.append(str(token_value))

    # Get legacy token from main user document (backward compatibility)
    user_ref = db.collection('users').document(uid).get()
    if getattr(user_ref, "exists", False):
        user_data = _typed_doc(user_ref)
        legacy_token = user_data.get('fcm_token')
        if legacy_token and legacy_token not in tokens:
            tokens.append(str(legacy_token))

    return tokens


def remove_invalid_token(token: str) -> None:
    """Remove invalid token using collection group query (rare operation)"""
    # Query across ALL users' fcm_tokens subcollections
    query = db.collection_group('fcm_tokens').where(filter=FieldFilter('token', '==', token)).limit(1)

    for doc in query.stream():
        doc.reference.delete()
        return


def remove_bulk_tokens(tokens: list[str]) -> None:
    """Remove multiple invalid tokens efficiently using IN queries and batch deletes"""
    if not tokens:
        return

    # Firestore IN queries support up to 30 items
    chunk_size = 30
    token_chunks = [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]

    for chunk in token_chunks:
        # Query for all tokens in this chunk at once
        query = db.collection_group('fcm_tokens').where(filter=FieldFilter('token', 'in', chunk))

        # Batch delete for efficiency
        batch = db.batch()
        count = 0

        for doc in query.stream():
            batch.delete(doc.reference)
            count += 1

            # Firestore batch limit is 500 operations
            if count >= 500:
                batch.commit()
                batch = db.batch()
                count = 0

        # Commit remaining deletes
        if count > 0:
            batch.commit()


def get_users_token_in_timezones(timezones: list[str]) -> List[str]:
    return _get_users_in_timezones(timezones, 'fcm_token')


def get_users_id_in_timezones(timezones: list[str]) -> List[Union[str, Tuple[str, List[str], Any]]]:
    return _get_users_in_timezones(timezones, 'id')


def get_users_for_daily_summary(
    timezones: list[str], target_local_hour: int
) -> List[Tuple[str, Dict[str, Any], Any]]:
    """Eligible daily-summary users in the given timezones: ``(uid, user_data, time_zone)``.

    Queries users who (1) are in one of the timezones (where it is currently ``target_local_hour``),
    (2) have ``daily_summary_hour_local`` == that hour (or no preference -> default), and (3) have not
    disabled daily summaries. Backend-NEUTRAL: it returns WHO to notify and their document; the service
    layer (utils/other/notifications.py) resolves the delivery backend and fetches the recipients —
    UnifiedPush endpoints via ``get_unifiedpush_endpoints_by_uid`` or FCM tokens via
    ``get_fcm_tokens_for_users``. This helper must not own delivery policy (cubic PR 10887 #427 / #3)."""
    if not timezones:
        return []

    users: List[Tuple[str, Dict[str, Any], Any]] = []
    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        chunk_users: List[Tuple[str, Dict[str, Any], Any]] = []
        try:
            query = db.collection('users').where(filter=FieldFilter('time_zone', 'in', chunk))
            for user_doc in query.stream():
                user_data = _typed_doc(user_doc)
                # Daily summary enabled (default: True)
                if user_data.get('daily_summary_enabled') is False:
                    continue
                # Preferred hour matches target (unset -> default 22 = 10 PM)
                user_hour = user_data.get('daily_summary_hour_local', DEFAULT_DAILY_SUMMARY_HOUR_LOCAL)
                if user_hour != target_local_hour:
                    continue
                chunk_users.append((str(user_doc.id), user_data, user_data.get('time_zone')))
        except Exception as e:
            logger.error(f"Error querying chunk for daily summary: {e}")
        users.extend(chunk_users)

    return users


def get_unifiedpush_endpoints_by_uid(time_zones: List[str]) -> Dict[str, List[UnifiedPushEndpoint]]:
    """UnifiedPush endpoints keyed by uid for every user whose ``time_zone`` is in ``time_zones``. ONE
    collection-group query per 30-chunk (not a per-user ``get_all_endpoints`` = N+1). ``save_endpoint``
    stamps the endpoint's ``time_zone`` with the user's, so the group filter returns exactly the matched
    users' endpoints. Neutral read — the service decides WHEN to use it (cubic PR 10887 #427)."""
    by_uid: Dict[str, List[UnifiedPushEndpoint]] = {}
    if not time_zones:
        return by_uid
    store = get_document_store()
    unique = list(dict.fromkeys(time_zones))
    for i in range(0, len(unique), 30):
        try:
            for doc in store.query_group(_UNIFIEDPUSH_COLLECTION, filters=[('time_zone', 'in', unique[i : i + 30])]):
                parts = doc.path.split('/')  # users/{uid}/unifiedpush_endpoints/{device_key}
                if len(parts) > 1:
                    by_uid.setdefault(parts[1], []).append(_endpoint_from_doc(doc))
        except Exception as e:
            logger.error(f'UnifiedPush timezone chunk {i // 30} failed (other chunks unaffected): {e}')
    return by_uid


def get_fcm_tokens_for_users(users: List[Tuple[str, Dict[str, Any], Any]]) -> Dict[str, List[str]]:
    """FCM tokens keyed by uid for the given eligible users (subcollection ``fcm_tokens`` + legacy
    ``user.fcm_token``). Runs in one DB-worker call for the whole batch; neutral read (cubic PR 10887 #427)."""
    tokens_by_uid: Dict[str, List[str]] = {}
    for uid, user_data, _tz in users:
        tokens: List[str] = []
        for token_doc in db.collection('users').document(uid).collection('fcm_tokens').stream():
            token_value = _typed_doc(token_doc).get('token')
            if token_value:
                tokens.append(str(token_value))
        legacy_token = user_data.get('fcm_token')  # add legacy token if present and not already listed
        if legacy_token and legacy_token not in tokens:
            tokens.append(str(legacy_token))
        tokens_by_uid[uid] = tokens
    return tokens_by_uid


def _get_users_in_timezones(timezones: list[str], filter: str) -> List[Any]:
    """Query main user documents by timezone, then get tokens from subcollection and legacy field"""
    users: List[Any] = []

    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        chunk_users: List[Any] = []
        try:
            # Query main user documents by time_zone
            query = db.collection('users').where(filter=FieldFilter('time_zone', 'in', chunk))

            for user_doc in query.stream():
                uid = str(user_doc.id)
                user_data = _typed_doc(user_doc)

                # Collect tokens from subcollection
                tokens: List[str] = []
                token_docs = db.collection('users').document(uid).collection('fcm_tokens').stream()
                for token_doc in token_docs:
                    token_data = _typed_doc(token_doc)
                    token_value = token_data.get('token')
                    if token_value:
                        tokens.append(str(token_value))

                # Add legacy token if exists and not already in list
                legacy_token = user_data.get('fcm_token')
                if legacy_token and legacy_token not in tokens:
                    tokens.append(str(legacy_token))

                # Skip users with no tokens
                if not tokens:
                    continue

                if filter == 'fcm_token':
                    # Return flat list of tokens
                    chunk_users.extend(tokens)
                else:
                    # Return list of (uid, [tokens], time_zone) tuples
                    time_zone = user_data.get('time_zone')
                    chunk_users.append((uid, tokens, time_zone))

        except Exception as e:
            logger.error(f"Error querying chunk {chunk}: {e}")
        users.extend(chunk_users)

    return users
