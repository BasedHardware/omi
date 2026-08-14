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
    # A Firestore 'in' filter rejects more than 30 values; chunk like the FCM sibling
    # (get_users_for_daily_summary) so an hour bucket with >30 timezones still resolves (cubic 10887 B3).
    unique = list(dict.fromkeys(time_zones))
    for i in range(0, len(unique), 30):
        for user in store.query('users', filters=[('time_zone', 'in', unique[i : i + 30])]):
            endpoints.extend(get_all_endpoints(user.id))
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


def get_users_for_daily_summary(timezones: list[str], target_local_hour: int) -> List[Tuple[str, List[str], Any]]:
    """
    Get users who should receive daily summary notifications.

    This function queries users who:
    1. Are in one of the provided timezones (where it's currently target_local_hour)
    2. Have daily_summary_hour_local set to target_local_hour OR have no preference (uses default)
    3. Have daily_summary_enabled not explicitly set to False

    Args:
        timezones: List of IANA timezone names where it's currently target_local_hour
        target_local_hour: The local hour we're sending notifications for (0-23)

    Returns:
        List of (uid, [tokens], time_zone) tuples.
    """
    if not timezones:
        return []

    users: List[Tuple[str, List[str], Any]] = []

    # Which recipients this deployment delivers to: FCM tokens, or (in a UnifiedPush deployment, where
    # NO user has FCM tokens) each user's UnifiedPush endpoints. Without this the "no tokens -> skip"
    # below drops EVERY user and sends zero daily summaries on UnifiedPush (cubic PR 10887 B2). Lazy
    # import: utils.push imports this module.
    from utils.push.base import UNIFIEDPUSH
    from utils.push.selector import resolve_push_backend

    unifiedpush = resolve_push_backend() == UNIFIEDPUSH

    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        chunk_users: List[Tuple[str, List[str], Any]] = []
        try:
            # Query users in these timezones
            query = db.collection('users').where(filter=FieldFilter('time_zone', 'in', chunk))

            for user_doc in query.stream():
                uid = str(user_doc.id)
                user_data = _typed_doc(user_doc)

                # Check if daily summary is enabled (default: True)
                if user_data.get('daily_summary_enabled') is False:
                    continue

                # Check if user's preferred hour matches target hour
                # If not set, use default (22 = 10 PM)
                user_hour = user_data.get('daily_summary_hour_local', DEFAULT_DAILY_SUMMARY_HOUR_LOCAL)
                if user_hour != target_local_hour:
                    continue

                # Collect the recipients the active backend delivers to. For UnifiedPush the per-user
                # send (_send_to_user) looks the endpoints up by uid, so the list only needs to be
                # non-empty to keep the user in the fan-out; for FCM it carries the tokens to send.
                recipients: List[Any]
                if unifiedpush:
                    recipients = list(get_all_endpoints(uid))
                else:
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
                    recipients = tokens

                # Skip users with no deliverable recipient on this backend
                if not recipients:
                    continue

                time_zone = user_data.get('time_zone')
                chunk_users.append((uid, recipients, time_zone))

        except Exception as e:
            logger.error(f"Error querying chunk for daily summary: {e}")
        users.extend(chunk_users)

    return users


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
