"""
Notifications database module

Structure:
users/{uid}/fcm_tokens (subcollection)
  └── {device_key} (document)
      ├── token: "actual_token_value"
      ├── created_at: timestamp
      └── time_zone: "America/New_York"

Backend-neutral persistence via the storage port (WP2, ADR-0002). FCM tokens live in the
per-user ``fcm_tokens`` subcollection; ``remove_invalid_token`` / ``remove_bulk_tokens`` run
cross-parent collection-group queries over the ``fcm_tokens`` group (backends must index the
``token`` field accordingly).

UnifiedPush endpoints (ADR-0011 on-prem push) mirror the same model in the per-user
``unifiedpush_endpoints`` subcollection (``{endpoint, p256dh, auth, created_at, time_zone}``);
``remove_bulk_endpoints`` runs the same collection-group cleanup over the ``unifiedpush_endpoints``
group (backends must index the ``endpoint`` field). ``p256dh``/``auth`` are the recipient's WebPush
key set (base64url) used by the send channel to encrypt the body (RFC 8291); absent for endpoints
registered by a pre-encryption client, in which case the send falls back to plaintext.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from database.store import get_document_store
from database.store.sentinels import DELETE, SERVER_TIMESTAMP

from .cache import get_memory_cache

logger = logging.getLogger(__name__)


def _store():
    return get_document_store()


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


@dataclass(frozen=True)
class UnifiedPushEndpoint:
    """A registered UnifiedPush endpoint with its optional WebPush key set.

    ``url`` is the push-server address; ``p256dh``/``auth`` (base64url) are present when the client
    registered encryption keys — the send channel encrypts for them, else POSTs plaintext.
    """

    url: str
    p256dh: Optional[str] = None
    auth: Optional[str] = None


def _endpoint_from_doc(doc: Any) -> Optional[UnifiedPushEndpoint]:
    data = _typed_doc(doc)
    url = data.get('endpoint')
    if not url:
        return None
    return UnifiedPushEndpoint(url=str(url), p256dh=data.get('p256dh'), auth=data.get('auth'))


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

    store = _store()
    user_path = f'users/{uid}'
    tokens_path = f'{user_path}/fcm_tokens'

    # Step 1: Migrate legacy token if exists
    user_doc = store.get(user_path)
    if user_doc.exists:
        user_data = _typed_doc(user_doc)
        legacy_token = user_data.get('fcm_token')

        if legacy_token:
            # Check if legacy token already exists in subcollection
            existing_tokens: List[object] = [
                t for t in (_typed_doc(d).get('token') for d in store.query(tokens_path))
            ]

            if legacy_token not in existing_tokens:
                # Migrate to unknown_default
                store.set(
                    f'{tokens_path}/unknown_default',
                    {
                        'token': legacy_token,
                        'time_zone': user_data.get('time_zone'),
                        'created_at': SERVER_TIMESTAMP,
                    },
                    merge=True,
                )

            # Remove legacy field
            store.update(user_path, {'fcm_token': DELETE})

    # Step 2: If new token has proper device_key, replace unknown_default
    if device_key != 'unknown_default':
        unknown_path = f'{tokens_path}/unknown_default'
        unknown_doc = store.get(unknown_path)
        if unknown_doc.exists:
            unknown_token = _typed_doc(unknown_doc).get('token')
            # Only delete if it's the same token being migrated to proper device_key
            if unknown_token == token:
                store.delete(unknown_path)

    # Step 3: Save new token to subcollection
    store.set(
        f'{tokens_path}/{device_key}',
        {'token': token, 'time_zone': time_zone, 'created_at': SERVER_TIMESTAMP},
        merge=True,
    )

    # Also update time_zone in main user document (for backward compatibility and efficient queries)
    if time_zone:
        store.set(user_path, {'time_zone': time_zone}, merge=True)


def get_user_time_zone(uid: str) -> Optional[str]:
    """Get timezone from main user document"""
    user_doc = _store().get(f'users/{uid}')
    if user_doc.exists:
        user_data = _typed_doc(user_doc)
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
    user_doc = _store().get(f'users/{uid}')
    if user_doc.exists:
        user_data = _typed_doc(user_doc)
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

    _store().set(f'users/{uid}', {'daily_summary_hour_local': hour_local}, merge=True)
    return True


def get_daily_summary_enabled(uid: str) -> bool:
    """Check if daily summary is enabled for user. Enabled by default."""
    user_doc = _store().get(f'users/{uid}')
    if user_doc.exists:
        user_data = _typed_doc(user_doc)
        return bool(user_data.get('daily_summary_enabled', True))
    return True


def set_daily_summary_enabled(uid: str, enabled: bool) -> bool:
    """Enable or disable daily summary for user."""
    _store().set(f'users/{uid}', {'daily_summary_enabled': enabled}, merge=True)
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
        doc = _store().get(f'users/{uid}', fields=['mentor_notification_frequency'])
        if doc.exists:
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

    _store().set(f'users/{uid}', {'mentor_notification_frequency': frequency}, merge=True)
    # Invalidate local cache so this instance sees the update immediately
    get_memory_cache().delete(f"mentor_frequency:{uid}")
    return True


def get_all_tokens(uid: str) -> list[str]:
    """Get all device tokens for a user from subcollection and legacy field"""
    tokens: List[str] = []

    store = _store()

    # Get tokens from new subcollection
    token_docs = store.query(f'users/{uid}/fcm_tokens')
    for doc in token_docs:
        token_data = _typed_doc(doc)
        token_value = token_data.get('token')
        if token_value:
            tokens.append(str(token_value))

    # Get legacy token from main user document (backward compatibility)
    user_doc = store.get(f'users/{uid}')
    if user_doc.exists:
        user_data = _typed_doc(user_doc)
        legacy_token = user_data.get('fcm_token')
        if legacy_token and legacy_token not in tokens:
            tokens.append(str(legacy_token))

    return tokens


def remove_invalid_token(token: str) -> None:
    """Remove invalid token using collection group query (rare operation)"""
    # Query across ALL users' fcm_tokens subcollections
    docs = _store().query_group('fcm_tokens', filters=[('token', '==', token)], limit=1)

    for doc in docs:
        _store().delete(doc.path)
        return


def remove_bulk_tokens(tokens: list[str]) -> None:
    """Remove multiple invalid tokens efficiently using IN queries and batch deletes"""
    if not tokens:
        return

    store = _store()

    # Firestore IN queries support up to 30 items
    chunk_size = 30
    token_chunks = [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]

    for chunk in token_chunks:
        # Query for all tokens in this chunk at once
        docs = store.query_group('fcm_tokens', filters=[('token', 'in', chunk)])

        # Batch delete for efficiency
        batch = store.batch()
        count = 0

        for doc in docs:
            batch.delete(doc.path)
            count += 1

            # Firestore batch limit is 500 operations
            if count >= 500:
                batch.commit()
                batch = store.batch()
                count = 0

        # Commit remaining deletes
        if count > 0:
            batch.commit()


def save_endpoint(uid: str, data: Dict[str, Any]) -> None:
    """Store a UnifiedPush endpoint URL keyed by device (ADR-0011 on-prem push).

    Structure: users/{uid}/unifiedpush_endpoints/{device_key}. Mirrors ``save_token`` but has no
    legacy top-level field to migrate. ``time_zone`` is also mirrored onto the user document so the
    daily-summary timezone queries work regardless of the active push backend.
    """
    device_key = data.get('device_key', 'unknown_default')
    endpoint = data.get('endpoint')
    time_zone = data.get('time_zone')

    store = _store()
    user_path = f'users/{uid}'
    record: Dict[str, Any] = {'endpoint': endpoint, 'time_zone': time_zone, 'created_at': SERVER_TIMESTAMP}
    # WebPush key set (RFC 8291), when the client registers encryption keys. Stored so the send
    # channel can encrypt the body for this endpoint; omitted keys mean a plaintext-only client.
    if data.get('p256dh'):
        record['p256dh'] = data.get('p256dh')
    if data.get('auth'):
        record['auth'] = data.get('auth')
    store.set(f'{user_path}/unifiedpush_endpoints/{device_key}', record, merge=True)

    # Also update time_zone in main user document (parity with save_token, for tz queries)
    if time_zone:
        store.set(user_path, {'time_zone': time_zone}, merge=True)


def get_all_endpoints(uid: str) -> List[UnifiedPushEndpoint]:
    """Get all UnifiedPush endpoints (URL + optional WebPush key set) registered for a user."""
    endpoints: List[UnifiedPushEndpoint] = []
    for doc in _store().query(f'users/{uid}/unifiedpush_endpoints'):
        endpoint = _endpoint_from_doc(doc)
        if endpoint is not None:
            endpoints.append(endpoint)
    return endpoints


def remove_bulk_endpoints(endpoints: list[str]) -> None:
    """Remove dead UnifiedPush endpoints (HTTP 404/410) via collection-group IN queries + batch deletes."""
    if not endpoints:
        return

    store = _store()

    # IN queries support up to 30 items
    chunk_size = 30
    endpoint_chunks = [endpoints[i : i + chunk_size] for i in range(0, len(endpoints), chunk_size)]

    for chunk in endpoint_chunks:
        docs = store.query_group('unifiedpush_endpoints', filters=[('endpoint', 'in', chunk)])

        batch = store.batch()
        count = 0

        for doc in docs:
            batch.delete(doc.path)
            count += 1

            if count >= 500:
                batch.commit()
                batch = store.batch()
                count = 0

        if count > 0:
            batch.commit()


def get_users_token_in_timezones(timezones: list[str]) -> List[str]:
    return _get_users_in_timezones(timezones, 'fcm_token')


def get_users_id_in_timezones(timezones: list[str]) -> List[Union[str, Tuple[str, List[str], Any]]]:
    return _get_users_in_timezones(timezones, 'id')


def get_users_endpoints_in_timezones(timezones: list[str]) -> List[UnifiedPushEndpoint]:
    """Flat list of UnifiedPush endpoints (URL + optional WebPush key set) for all users currently
    in the given timezones.

    UnifiedPush counterpart of ``get_users_token_in_timezones`` for the bulk daily notification.
    """
    endpoints: List[UnifiedPushEndpoint] = []
    store = _store()

    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        try:
            user_docs = store.query('users', filters=[('time_zone', 'in', chunk)])
            for user_doc in user_docs:
                uid = str(user_doc.id)
                for doc in store.query(f'users/{uid}/unifiedpush_endpoints'):
                    endpoint = _endpoint_from_doc(doc)
                    if endpoint is not None:
                        endpoints.append(endpoint)
        except Exception as e:
            logger.error(f"Error querying endpoints chunk for timezones: {e}")

    return endpoints


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

    store = _store()
    users: List[Tuple[str, List[str], Any]] = []

    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        chunk_users: List[Tuple[str, List[str], Any]] = []
        try:
            # Query users in these timezones
            user_docs = store.query('users', filters=[('time_zone', 'in', chunk)])

            for user_doc in user_docs:
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

                # Collect tokens from subcollection
                tokens: List[str] = []
                token_docs = store.query(f'users/{uid}/fcm_tokens')
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

                time_zone = user_data.get('time_zone')
                chunk_users.append((uid, tokens, time_zone))

        except Exception as e:
            logger.error(f"Error querying chunk for daily summary: {e}")
        users.extend(chunk_users)

    return users


def _get_users_in_timezones(timezones: list[str], filter: str) -> List[Any]:
    """Query main user documents by timezone, then get tokens from subcollection and legacy field"""
    users: List[Any] = []

    store = _store()

    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    for chunk in timezone_chunks:
        chunk_users: List[Any] = []
        try:
            # Query main user documents by time_zone
            user_docs = store.query('users', filters=[('time_zone', 'in', chunk)])

            for user_doc in user_docs:
                uid = str(user_doc.id)
                user_data = _typed_doc(user_doc)

                # Collect tokens from subcollection
                tokens: List[str] = []
                token_docs = store.query(f'users/{uid}/fcm_tokens')
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
