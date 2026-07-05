from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional  # type: ignore[reportUnknownMemberType]  # firestore transactional is untyped

from ._client import db, document_id_from_seed
from database.firestore_cache import CachePolicy, get_or_fetch, invalidate
from database.redis_db import try_acquire_client_device_write_lock, try_acquire_user_platform_write_lock
from models.users import Subscription, PlanType, SubscriptionStatus
from utils.subscription import get_default_basic_subscription
import logging

logger = logging.getLogger(__name__)

# Conservative low-risk user projections. Do NOT use these policies for
# entitlement, BYOK, data-protection, privacy-consent, or full user-doc caching.
_USER_LANGUAGE_CACHE = CachePolicy(namespace='user_language', version=1, ttl_seconds=300)
_USER_TRANSCRIPTION_PREFS_CACHE = CachePolicy(namespace='user_transcription_prefs', version=1, ttl_seconds=120)
_USER_AI_PROFILE_CACHE = CachePolicy(namespace='user_ai_profile', version=1, ttl_seconds=300)


class UserDoc(TypedDict, total=False):
    """Typed contract for the users/{uid} Firestore document.

    All keys are optional (``total=False``) because the document is patched
    incrementally across many features. Scalar datetimes are typed as ``Any``
    because the firestore SDK returns ``DatetimeWithNanoseconds`` which is not
    statically exported.
    """

    # Identity / lifecycle
    uid: str
    id: str
    created_at: Any  # datetime from firestore
    deleted_at: Any  # datetime from firestore

    # Telemetry (record_user_platform)
    signup_platform: str
    signup_os: str
    signup_platform_at: Any  # datetime
    last_active_platform: str
    last_active_os: str
    last_active_at: Any  # datetime
    platforms_used: List[str]

    # Privacy / permissions
    store_recording_permission: bool
    private_cloud_sync_enabled: bool
    training_data_opt_in: Dict[str, Any]
    data_protection_level: str
    migration_status: Dict[str, Any]

    # BYOK
    byok: Dict[str, Any]

    # Audio / speaker
    speaker_embedding: List[Any]
    speaker_embedding_updated_at: Any  # datetime

    # Payments
    stripe_account_id: Optional[str]
    stripe_customer_id: Optional[str]
    paypal_details: Optional[Dict[str, Any]]
    default_payment_method: Optional[str]
    subscription: Dict[str, Any]
    cancellation_feedback: Dict[str, Any]

    # Onboarding / preferences
    onboarding: Dict[str, Any]
    language: str
    transcription_preferences: Dict[str, Any]
    default_task_integration: Optional[str]
    agentVm: Optional[Dict[str, Any]]

    # Desktop settings
    notifications_enabled: bool
    notification_frequency: int
    assistant_settings: Dict[str, Any]
    update_channel: Optional[str]
    ai_user_profile: Dict[str, Any]


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for Firestore ``DocumentSnapshot.to_dict()``.

    Coerces the untyped SDK return into ``Dict[str, Any]`` so call sites can
    read fields without each one re-narrowing. Returns ``{}`` for missing or
    malformed payloads.
    """
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


# Industry-standard two-field pattern (Mixpanel / Amplitude / PostHog):
#   signup_platform       — set once at account creation, immutable
#   last_active_platform  — overwritten on every authenticated request
#   platforms_used        — array union of every platform the user has ever
#                           authenticated from (for cross-platform segmentation)
#
# We normalize the raw header into a coarse `desktop | mobile` bucket, matching
# the profitability dashboard splits, and preserve the granular value
# (`ios`/`android`/`macos`) in `last_active_os` for finer drill-down.
_PLATFORM_ALIASES = {
    'macos': 'desktop',
    'mac': 'desktop',
    'mac os x': 'desktop',
    'desktop': 'desktop',
    'ios': 'mobile',
    'iphone os': 'mobile',
    'android': 'mobile',
    'mobile': 'mobile',
    'web': 'web',
    'browser': 'web',
}


def _normalize_platform(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (coarse_platform, os_value) for a raw `X-App-Platform` header.

    `coarse_platform` is one of 'desktop' / 'mobile' (None if unrecognized).
    `os_value` is the normalized OS string preserved for drill-down.
    """
    if not raw:
        return None, None
    os_value = raw.strip().lower()
    if not os_value:
        return None, None
    coarse = _PLATFORM_ALIASES.get(os_value)
    return coarse, os_value


def record_client_device(
    uid: str,
    *,
    client_device_id: Optional[str],
    platform: Optional[str],
    app_version: Optional[str] = None,
    label: Optional[str] = None,
) -> None:
    """Upsert users/{uid}/client_devices/{client_device_id} from request headers.

    Throttled via Redis (same 10-minute window as record_user_platform). Fail-open telemetry.
    """
    if not client_device_id or not platform:
        return

    try:
        if not try_acquire_client_device_write_lock(uid, client_device_id):
            return

        now = datetime.now(timezone.utc)
        coarse, _os_value = _normalize_platform(platform)
        doc_ref = db.collection('users').document(uid).collection('client_devices').document(client_device_id)
        updates: Dict[str, Any] = {
            'platform': platform,
            'device_class': coarse,
            'last_seen_at': now,
        }
        if app_version:
            updates['app_version'] = app_version
        if label:
            updates['label'] = label

        snapshot = doc_ref.get()
        if not snapshot.exists:
            updates['first_seen_at'] = now

        doc_ref.set(updates, merge=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("record_client_device failed for uid=%s: %s", uid, e)


def record_user_platform(uid: str, raw_platform: Optional[str]) -> None:
    """Write the user-platform fields from an `X-App-Platform` header value.

    Called on every authenticated request. Throttled to one Firestore write
    per (uid, coarse_platform) every 10 minutes via Redis so chatty endpoints
    don't hot-spot the user doc. Fail-open: any error is logged and swallowed
    because this is a telemetry side-effect, not a request-correctness path.

    - `signup_platform` is set once via `Firestore.ArrayUnion` semantics:
      we read the doc and only write it if it's not already present.
    - `last_active_platform` / `last_active_os` / `last_active_at` are
      overwritten every throttle-window.
    - `platforms_used` accumulates via `firestore.ArrayUnion`.
    """
    coarse, os_value = _normalize_platform(raw_platform)
    if not coarse:
        return

    try:
        if not try_acquire_user_platform_write_lock(uid, coarse):
            return

        now = datetime.now(timezone.utc)
        user_ref = db.collection('users').document(uid)

        updates: Dict[str, Any] = {
            'last_active_platform': coarse,
            'last_active_os': os_value,
            'last_active_at': now,
            f'last_active_at_{coarse}': now,
            'platforms_used': firestore.ArrayUnion([coarse]),
        }

        # `signup_platform` is set_once. Read the doc (single read) and only
        # include the field in the write if it's not already present. Cheaper
        # than a transaction for a field that almost never changes.
        snapshot = user_ref.get()
        if snapshot.exists:
            data: Dict[str, Any] = _typed_doc(snapshot)
            if not data.get('signup_platform'):
                updates['signup_platform'] = coarse
                updates['signup_os'] = os_value
                updates['signup_platform_at'] = data.get('created_at') or now
        else:
            # First-ever auth'd request for this uid — treat as sign-up.
            updates['signup_platform'] = coarse
            updates['signup_os'] = os_value
            updates['signup_platform_at'] = now

        user_ref.set(updates, merge=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("record_user_platform failed for uid=%s: %s", uid, e)


def is_exists_user(uid: str) -> bool:
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return False
    return True


def get_user_profile(uid: str) -> Dict[str, Any]:
    """Gets the full user profile document."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        return _typed_doc(user_doc)
    return {}


def get_user_store_recording_permission(uid: str) -> bool:
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('store_recording_permission', False)
    return cast(bool, value)


def set_user_store_recording_permission(uid: str, value: bool) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.update({'store_recording_permission': value})


def get_user_private_cloud_sync_enabled(uid: str) -> bool:
    """Check if user has private cloud sync enabled."""
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('private_cloud_sync_enabled', True)
    return cast(bool, value)


def set_user_private_cloud_sync_enabled(uid: str, value: bool) -> None:
    """Enable or disable private cloud sync for a user."""
    user_ref = db.collection('users').document(uid)
    user_ref.update({'private_cloud_sync_enabled': value})


def set_user_cancellation_feedback(uid: str, reason: str, reason_details: Optional[str] = None) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.set(
        {
            'cancellation_feedback': {
                'reason': reason,
                'reason_details': reason_details or '',
                'timestamp': datetime.now(timezone.utc),
            }
        },
        merge=True,
    )


# BYOK (Bring Your Own Keys) — free-plan flag.
# We never store keys themselves; only SHA-256 fingerprints so we can detect
# rotation. `active` is the subscription-bypass gate.

BYOK_HEARTBEAT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def get_byok_state(uid: str) -> Dict[str, Any]:
    user_ref = db.collection('users').document(uid)
    data: Dict[str, Any] = _typed_doc(user_ref.get())
    byok: object = data.get('byok', {})
    return cast(Dict[str, Any], byok) if isinstance(byok, dict) else {}


def is_byok_active(uid: str) -> bool:
    """True if user has a live BYOK activation (heartbeat within TTL)."""
    state = get_byok_state(uid)
    if not state.get('active'):
        return False
    last_seen: object = state.get('last_seen_at')
    if not last_seen:
        return False
    if isinstance(last_seen, datetime):
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    else:
        return False
    return age <= BYOK_HEARTBEAT_TTL_SECONDS


def set_byok_active(uid: str, fingerprints: Dict[str, Any]) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.set(
        {
            'byok': {
                'active': True,
                'fingerprints': fingerprints,
                'last_seen_at': datetime.now(timezone.utc),
            }
        },
        merge=True,
    )


def clear_byok_active(uid: str) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.set(
        {
            'byok': {
                'active': False,
                'fingerprints': {},
                'last_seen_at': datetime.now(timezone.utc),
            }
        },
        merge=True,
    )


def set_user_deletion_feedback(uid: str, reason: Optional[str], reason_details: Optional[str] = None) -> None:
    # Stored in a top-level collection so it survives the user record being deleted.
    # Use merge=True so a retried delete request does not erase a durable wipe marker
    # (pending/failed/retrying/deleting_auth) already written to the same document.
    db.collection('account_deletions').document(uid).set(
        {
            'uid': uid,
            'reason': reason or '',
            'reason_details': reason_details or '',
            'timestamp': datetime.now(timezone.utc),
        },
        merge=True,
    )


def mark_user_deletion_wipe_started(uid: str) -> None:
    """Mark that the background data wipe has been queued but not yet completed.

    Persisted in the top-level ``account_deletions`` collection so it survives a
    deploy or pod restart. A reconciliation worker can query for documents where
    ``wipe_status == 'pending'`` and re-enqueue incomplete wipes, ensuring the
    in-process ``cleanup_executor`` backlog is not silently lost.

    The worker transitions the marker to ``'running'`` (via
    ``mark_user_deletion_wipe_running``) as soon as it actually starts
    executing, so the reconciler can distinguish a genuinely orphaned queued
    wipe from one that is actively executing but slow.
    """
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'pending', 'wipe_queued_at': datetime.now(timezone.utc)},
        merge=True,
    )


def mark_user_deletion_wipe_running(uid: str) -> None:
    """Transition a queued wipe marker to ``running`` once the worker starts.

    Called by ``background_wipe_user_data`` at the top of the executor future.
    This lets the reconciler distinguish a genuinely orphaned ``pending`` wipe
    (queued in the executor backlog but never picked up — safe to re-enqueue)
    from a ``running`` wipe (actively executing — only recovered if the claim
    is stale, i.e. the worker probably crashed).

    Without this, a slow but live wipe could be reclaimed as orphaned after
    ``stale_after`` (default 10 min) and re-enqueued concurrently, leading to
    duplicate work where a later failure overwrites a successful completion.
    """
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'running', 'wipe_running_at': datetime.now(timezone.utc)},
        merge=True,
    )


def mark_user_deletion_wipe_intent(uid: str) -> None:
    """Persist a non-actionable deletion intent *before* auth deletion.

    Written BEFORE ``auth.delete_account()`` succeeds. The reconciler only
    recovers stale ``'deleting_auth'`` records *after* verifying the Firebase
    auth user is actually gone, so a crash between this write and the confirmed
    auth deletion cannot trigger a premature data wipe for a user whose Firebase
    account still exists.

    Call ``mark_user_deletion_wipe_started`` to transition the marker to the
    actionable ``'pending'`` state once auth deletion is confirmed.
    """
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'deleting_auth', 'wipe_intent_at': datetime.now(timezone.utc)},
        merge=True,
    )


def mark_user_deletion_wipe_completed(uid: str) -> None:
    """Mark the background data wipe as finished."""
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)},
        merge=True,
    )


def mark_user_deletion_wipe_failed(uid: str) -> None:
    """Mark the background data wipe as failed so a reconciliation worker can retry."""
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'failed', 'wipe_failed_at': datetime.now(timezone.utc)},
        merge=True,
    )


def cancel_user_deletion_wipe(uid: str) -> None:
    """Cancel a pending deletion-wipe marker.

    Called when the Firebase auth deletion fails after the marker was already
    persisted. Without this, the reconciliation worker would later wipe the
    user's data even though their Firebase account still exists.
    """
    db.collection('account_deletions').document(uid).set(
        {'wipe_status': 'cancelled', 'wipe_cancelled_at': datetime.now(timezone.utc)},
        merge=True,
    )


def get_pending_deletion_wipes(
    limit: int = 100,
    stale_after: timedelta = timedelta(minutes=10),
    running_stale_after: timedelta = timedelta(minutes=30),
) -> List[Dict[str, Any]]:
    """Return account_deletions documents whose wipe needs retry.

    Queries ``failed`` records (always actionable), stale ``pending`` records
    (queued more than ``stale_after`` ago), stale ``deleting_auth`` records
    (intent written but never transitioned to ``pending`` — usually a crash
    after ``auth.delete_account()`` succeeded), stale ``running`` records (worker
    started but hasn't finished within ``running_stale_after`` — probably
    crashed), and stale ``retrying`` claims (worker probably crashed). Fresh
    ``pending``, ``deleting_auth``, and ``running`` markers from in-progress
    deletions are excluded so the reconciler doesn't double-enqueue a wipe that
    is still running.

    The caller is responsible for verifying the Firebase auth user is actually
    gone before recovering a ``deleting_auth`` record — this function returns
    candidates, and ``claim_deletion_wipe`` also age-guards inside a transaction.

    All queries are single-field equality filters on ``wipe_status`` to avoid
    requiring Firestore composite indexes. Age filtering is done in Python.
    """
    stale_cutoff = datetime.now(timezone.utc) - stale_after
    running_cutoff = datetime.now(timezone.utc) - running_stale_after
    budget = limit
    result: List[Dict[str, Any]] = []

    failed_docs = db.collection('account_deletions').where('wipe_status', '==', 'failed').limit(budget).stream()
    for doc in failed_docs:
        data: Dict[str, Any] = _typed_doc(doc)
        result.append(data | {'uid': doc.id})

    if len(result) < limit:
        # Over-fetch *all* pending docs and age-filter in Python. A tight
        # ``.limit(budget)`` would cap the query before stale records beyond the
        # first page of fresh pending docs, leaving them permanently unqueued.
        # The ``account_deletions`` collection only holds deletion events so
        # the full scan is bounded.
        pending_docs = db.collection('account_deletions').where('wipe_status', '==', 'pending').stream()
        for doc in pending_docs:
            if len(result) >= limit:
                break
            data = _typed_doc(doc)
            queued_at = data.get('wipe_queued_at')
            if queued_at and queued_at < stale_cutoff:
                result.append(data | {'uid': doc.id})

    if len(result) < limit:
        # Recover stale ``running`` markers — the worker started but hasn't
        # finished within ``running_stale_after``. This is much longer than the
        # ``pending`` stale window because a legitimately slow wipe (queued
        # behind other cleanup jobs) can take several minutes; we only want to
        # reclaim a ``running`` marker when the worker has almost certainly
        # crashed or the pod was killed mid-execution.
        running_docs = db.collection('account_deletions').where('wipe_status', '==', 'running').stream()
        for doc in running_docs:
            if len(result) >= limit:
                break
            data = _typed_doc(doc)
            running_at = data.get('wipe_running_at')
            if running_at and running_at < running_cutoff:
                result.append(data | {'uid': doc.id})

    if len(result) < limit:
        # Over-fetch all 'deleting_auth' docs and age-filter in Python. A stale
        # 'deleting_auth' record (intent written but never transitioned to
        # 'pending') usually means a crash/deploy after auth.delete_account()
        # succeeded. The reconciler verifies the Firebase user is gone before
        # recovering these — see reconcile_pending_deletion_wipes.
        deleting_auth_docs = db.collection('account_deletions').where('wipe_status', '==', 'deleting_auth').stream()
        for doc in deleting_auth_docs:
            if len(result) >= limit:
                break
            data = _typed_doc(doc)
            intent_at = data.get('wipe_intent_at')
            if intent_at and intent_at < stale_cutoff:
                result.append(data | {'uid': doc.id})

    if len(result) < limit:
        retrying_docs = db.collection('account_deletions').where('wipe_status', '==', 'retrying').stream()
        for doc in retrying_docs:
            if len(result) >= limit:
                break
            data = _typed_doc(doc)
            claimed_at = data.get('wipe_claimed_at')
            # Use the longer ``running_stale_after`` window so a queued-but-
            # not-yet-running retrying claim is not returned as a candidate
            # before the executor future has had a chance to start.
            if claimed_at and claimed_at < running_cutoff:
                result.append(data | {'uid': doc.id})

    return result


@transactional
def _claim_deletion_wipe_txn(
    transaction: Any, doc_ref: Any, stale_after: timedelta, running_stale_after: timedelta
) -> str | None:
    """Atomically claim a wipe for re-enqueueing inside a Firestore transaction.

    Transitions ``wipe_status`` from ``failed``, stale ``pending``, stale
    ``deleting_auth`` (auth user verified gone by caller), stale ``running``
    (worker crashed mid-execution), or stale ``retrying`` to ``retrying`` so
    concurrent workers cannot re-enqueue the same wipe. Fresh ``pending``,
    ``deleting_auth``, and ``running`` markers (recently written by an
    in-progress deletion) are left untouched to avoid wiping data before
    Firebase auth deletion succeeds or interrupting a live worker. ``retrying``
    claims that are not yet stale are also refused (another worker owns them).
    """
    snapshot = doc_ref.get(transaction=transaction)
    if not snapshot.exists:
        return None
    data: Dict[str, Any] = _typed_doc(snapshot)
    status = data.get('wipe_status')
    now = datetime.now(timezone.utc)
    if status == 'deleting_auth':
        # Recoverable only after the caller verified the Firebase auth user is
        # gone. Re-validate the age inside the transaction so a fresh intent
        # from an in-progress deletion is never claimed prematurely.
        intent_at = data.get('wipe_intent_at')
        if intent_at and intent_at >= now - stale_after:
            return None
        transaction.update(doc_ref, {'wipe_status': 'retrying', 'wipe_claimed_at': now})
        return snapshot.id
    if status == 'pending':
        # Re-validate the pending marker age *inside* the transaction. The
        # reconciler query may have returned a stale record that was since
        # refreshed by a new delete request; claiming a fresh marker could
        # enqueue a wipe before Firebase auth deletion has succeeded.
        queued_at = data.get('wipe_queued_at')
        if queued_at and queued_at >= now - stale_after:
            return None
        transaction.update(doc_ref, {'wipe_status': 'retrying', 'wipe_claimed_at': now})
        return snapshot.id
    if status == 'running':
        # A ``running`` marker means the worker started executing. Only reclaim
        # it if it's stale beyond ``running_stale_after`` — the worker almost
        # certainly crashed or the pod was killed mid-execution. A fresh or
        # moderately recent ``running`` marker belongs to a live worker.
        running_at = data.get('wipe_running_at')
        if running_at and running_at >= now - running_stale_after:
            return None
        transaction.update(doc_ref, {'wipe_status': 'retrying', 'wipe_claimed_at': now})
        return snapshot.id
    if status == 'failed':
        transaction.update(doc_ref, {'wipe_status': 'retrying', 'wipe_claimed_at': now})
        return snapshot.id
    if status == 'retrying':
        claimed_at = data.get('wipe_claimed_at')
        # Use the longer ``running_stale_after`` window (not ``stale_after``)
        # because a retrying wipe was just claimed by the reconciler and
        # enqueued. If the executor backlog is full, the future may sit queued
        # beyond ``stale_after`` (10 min) without transitioning to ``running``.
        # Using the short window would let the periodic reconciler enqueue
        # another copy every pass, causing duplicate wipes to race.
        if claimed_at and claimed_at < now - running_stale_after:
            # Stale claim (worker probably crashed). Re-claim it.
            transaction.update(doc_ref, {'wipe_claimed_at': now})
            return snapshot.id
    return None


def claim_deletion_wipe(
    uid: str,
    stale_after: timedelta = timedelta(minutes=10),
    running_stale_after: timedelta = timedelta(minutes=30),
) -> str | None:
    """Attempt to claim a pending/failed/stale wipe for re-enqueueing.

    Returns the uid if claimed (caller should enqueue the wipe), or ``None`` if
    another worker already owns a non-stale claim. This prevents the same wipe
    from being re-enqueued concurrently by multiple workers or scheduler runs.
    """
    doc_ref = db.collection('account_deletions').document(uid)
    transaction = db.transaction()
    return _claim_deletion_wipe_txn(transaction, doc_ref, stale_after, running_stale_after)


def create_person(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    people_ref = db.collection('users').document(uid).collection('people')
    people_ref.document(data['id']).set(data)
    return data


def get_person(uid: str, person_id: str) -> Optional[Dict[str, Any]]:
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()
    if not person_doc.exists:
        return None
    person_data: Dict[str, Any] = _typed_doc(person_doc)
    person_data.setdefault('id', person_doc.id)
    return person_data


def get_people(uid: str) -> List[Dict[str, Any]]:
    people_ref = db.collection('users').document(uid).collection('people')
    result: List[Dict[str, Any]] = []
    for person in people_ref.stream():
        data: Dict[str, Any] = _typed_doc(person)
        data.setdefault('id', person.id)
        result.append(data)
    return result


def get_person_by_name(uid: str, name: str) -> Optional[Dict[str, Any]]:
    people_ref = db.collection('users').document(uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name)).limit(1)
    docs = list(query.stream())
    if docs:
        data: Dict[str, Any] = _typed_doc(docs[0])
        data.setdefault('id', docs[0].id)
        return data
    return None


def get_people_by_ids(uid: str, person_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch people docs by ID using db.get_all().

    Note: db.get_all() returns results in arbitrary order (Firestore behavior).
    Callers must not assume the result order matches person_ids order.
    """
    if not person_ids:
        return []
    people_ref = db.collection('users').document(uid).collection('people')
    # Use document ID fetches instead of where("id", "in", ...) to handle
    # legacy docs that may not have a stored 'id' field.
    doc_refs = [people_ref.document(pid) for pid in person_ids]
    all_people: List[Dict[str, Any]] = []
    for doc in db.get_all(doc_refs):
        if doc.exists:
            data: Dict[str, Any] = _typed_doc(doc)
            data.setdefault('id', doc.id)
            all_people.append(data)
    return all_people


def update_person(uid: str, person_id: str, name: str) -> None:
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.update({'name': name})


def delete_person(uid: str, person_id: str) -> None:
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.delete()


@transactional
def _add_sample_transaction(
    transaction: Any,
    person_ref: Any,
    sample_path: str,
    transcript: Optional[str],
    max_samples: int,
) -> bool:
    """Transaction to atomically add sample and transcript."""
    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False

    person_data: Dict[str, Any] = _typed_doc(snapshot)
    samples: List[Any] = cast(List[Any], person_data.get('speech_samples', []))

    if len(samples) >= max_samples:
        return False

    samples.append(sample_path)
    update_data: Dict[str, Any] = {
        'speech_samples': samples,
        'updated_at': datetime.now(timezone.utc),
    }

    if transcript is not None:
        transcripts: List[Any] = cast(List[Any], person_data.get('speech_sample_transcripts', []))
        # Ensure transcript array alignment with samples:
        # If we're adding a transcript but existing samples don't have transcripts,
        # pad with empty strings for the existing samples first (Dart expects non-null)
        existing_sample_count = len(samples) - 1  # samples already has new one appended
        if len(transcripts) < existing_sample_count:
            # Pad with empty strings for each existing sample without a transcript
            transcripts.extend([''] * (existing_sample_count - len(transcripts)))
        transcripts.append(transcript)
        update_data['speech_sample_transcripts'] = transcripts
        update_data['speech_samples_version'] = 3

    transaction.update(person_ref, update_data)
    return True


def add_person_speech_sample(
    uid: str, person_id: str, sample_path: str, transcript: Optional[str] = None, max_samples: int = 5
) -> bool:
    """
    Append speech sample path to person's speech_samples list.
    Limits to max_samples to prevent unlimited growth.

    Uses Firestore transaction to ensure atomic read-modify-write,
    preventing array drift from concurrent updates.

    Args:
        uid: User ID
        person_id: Person ID
        sample_path: GCS path to the speech sample
        transcript: Optional transcript text for the sample
        max_samples: Maximum number of samples to keep (default 5)

    Returns:
        True if sample was added, False if limit reached or person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    transaction = db.transaction()
    return _add_sample_transaction(transaction, person_ref, sample_path, transcript, max_samples)


def get_person_speech_samples_count(uid: str, person_id: str) -> int:
    """Get the count of speech samples for a person."""
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return 0

    person_data: Dict[str, Any] = _typed_doc(person_doc)
    samples: Any = person_data.get('speech_samples', [])
    return len(samples)


@transactional
def _remove_sample_transaction(transaction: Any, person_ref: Any, sample_path: str) -> bool:
    """Atomically remove a sample and its aligned transcript."""
    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False

    person_data: Dict[str, Any] = _typed_doc(snapshot)
    samples: List[Any] = list(cast(List[Any], person_data.get('speech_samples', [])))
    transcripts: List[Any] = list(cast(List[Any], person_data.get('speech_sample_transcripts', [])))

    try:
        idx = samples.index(sample_path)
    except ValueError:
        return False

    samples.pop(idx)
    if idx < len(transcripts):
        transcripts.pop(idx)

    transaction.update(
        person_ref,
        {
            'speech_samples': samples,
            'speech_sample_transcripts': transcripts,
            'updated_at': datetime.now(timezone.utc),
        },
    )
    return True


def remove_person_speech_sample(uid: str, person_id: str, sample_path: str) -> bool:
    """
    Remove a speech sample path from person's speech_samples list.
    Also removes the corresponding transcript at the same index to keep arrays in sync.

    Args:
        uid: User ID
        person_id: Person ID
        sample_path: GCS path to remove

    Returns:
        True if removed, False if person or sample not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    transaction = db.transaction()
    return _remove_sample_transaction(transaction, person_ref, sample_path)


def set_user_speaker_embedding(uid: str, embedding: List[Any]) -> bool:
    """Store speaker embedding for the user's own voice on their user document."""
    user_ref = db.collection('users').document(uid)
    user_ref.update(
        {
            'speaker_embedding': embedding,
            'speaker_embedding_updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def get_user_speaker_embedding(uid: str) -> Optional[List[Any]]:
    """Get the user's own speaker embedding from their user document."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return None
    data: Dict[str, Any] = _typed_doc(user_doc)
    value: object = data.get('speaker_embedding')
    return cast(List[Any], value) if isinstance(value, list) else None


def set_person_speaker_embedding(uid: str, person_id: str, embedding: List[Any]) -> bool:
    """
    Store speaker embedding for a person.

    Args:
        uid: User ID
        person_id: Person ID
        embedding: List of floats representing the speaker embedding

    Returns:
        True if stored successfully, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_ref.update(
        {
            'speaker_embedding': embedding,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def get_person_speaker_embedding(uid: str, person_id: str) -> Optional[List[Any]]:
    """
    Get speaker embedding for a person.

    Args:
        uid: User ID
        person_id: Person ID

    Returns:
        List of floats representing the embedding, or None if not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return None

    person_data: Dict[str, Any] = _typed_doc(person_doc)
    value: object = person_data.get('speaker_embedding')
    return cast(List[Any], value) if isinstance(value, list) else None


def set_person_speech_sample_transcript(uid: str, person_id: str, sample_index: int, transcript: str) -> bool:
    """
    Update transcript at a specific index in the speech_sample_transcripts array.

    Args:
        uid: User ID
        person_id: Person ID
        sample_index: Index of the sample/transcript to update
        transcript: The transcript text to set

    Returns:
        True if updated successfully, False if person not found or index out of bounds
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_data: Dict[str, Any] = _typed_doc(person_doc)
    samples = person_data.get('speech_samples', [])
    transcripts = person_data.get('speech_sample_transcripts', [])

    # Validate index
    if sample_index < 0 or sample_index >= len(samples):
        return False

    # Extend transcripts array if needed
    while len(transcripts) < len(samples):
        transcripts.append('')

    transcripts[sample_index] = transcript

    person_ref.update(
        {
            'speech_sample_transcripts': transcripts,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def update_person_speech_samples_after_migration(
    uid: str,
    person_id: str,
    samples: List[Any],
    transcripts: List[Any],
    version: int,
    speaker_embedding: Optional[List[Any]] = None,
) -> bool:
    """
    Replace all samples/transcripts/embedding and set version atomically.
    Used after v1 to v2 migration to update all related fields together.

    Args:
        uid: User ID
        person_id: Person ID
        samples: List of sample paths (may have dropped invalid samples)
        transcripts: List of transcript strings (parallel array with samples)
        version: Version number to set (typically 2)
        speaker_embedding: Optional new speaker embedding, or None to clear

    Returns:
        True if updated successfully, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    update_data: Dict[str, Any] = {
        'speech_samples': samples,
        'speech_sample_transcripts': transcripts,
        'speech_samples_version': version,
        'updated_at': datetime.now(timezone.utc),
    }

    # Set or clear speaker embedding
    if speaker_embedding is not None:
        update_data['speaker_embedding'] = speaker_embedding
    else:
        update_data['speaker_embedding'] = firestore.DELETE_FIELD

    person_ref.update(update_data)
    return True


def clear_person_speaker_embedding(uid: str, person_id: str) -> bool:
    """
    Clear speaker embedding for a person.
    Used when all samples are dropped during migration.

    Args:
        uid: User ID
        person_id: Person ID

    Returns:
        True if cleared successfully, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_ref.update(
        {
            'speaker_embedding': firestore.DELETE_FIELD,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def update_person_speech_samples_version(uid: str, person_id: str, version: int) -> bool:
    """
    Update just the speech_samples_version field.

    Args:
        uid: User ID
        person_id: Person ID
        version: Version number to set

    Returns:
        True if updated successfully, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_ref.update(
        {
            'speech_samples_version': version,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def _delete_collection_recursive(collection_ref: Any, batch_size: int = 450) -> None:
    """Delete every document under a collection, descending into nested subcollections first."""
    while True:
        docs = list(collection_ref.limit(batch_size).stream())
        if not docs:
            return

        for doc in docs:
            for sub in doc.reference.collections():
                _delete_collection_recursive(sub, batch_size)

        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

        if len(docs) < batch_size:
            return


def delete_user_data(uid: str) -> Dict[str, str]:
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return {'status': 'error', 'message': 'User not found'}

    # Enumerate subcollections live instead of hardcoding a list — picks up
    # everything the user has written (conversations, memories, action_items,
    # folders, goals, integrations, task_integrations, fcm_tokens, fair_use_*,
    # hourly_usage, meetings, screen_activity, files, people, chat_sessions,
    # messages, and any future additions).
    for sub in user_ref.collections():
        logger.info(f"Deleting subcollection {sub.id} for user {uid}")
        _delete_collection_recursive(sub)

    logger.info(f"Deleting user document: {uid}")
    user_ref.delete()
    return {'status': 'ok', 'message': 'Account deleted successfully'}


# **************************************
# ************* Analytics **************
# **************************************


def set_conversation_summary_rating_score(uid: str, conversation_id: str, value: int) -> None:
    doc_id = document_id_from_seed('memory_summary' + conversation_id)
    db.collection('analytics').document(doc_id).set(
        {
            'id': doc_id,
            'memory_id': conversation_id,
            'uid': uid,
            'value': value,
            'created_at': datetime.now(timezone.utc),
            'type': 'memory_summary',
        }
    )


def get_conversation_summary_rating_score(conversation_id: str) -> Optional[Dict[str, Any]]:
    doc_id = document_id_from_seed('memory_summary' + conversation_id)
    doc_ref = db.collection('analytics').document(doc_id)
    doc = doc_ref.get()
    if doc.exists:
        return _typed_doc(doc)
    return None


def get_all_ratings(rating_type: str = 'memory_summary') -> List[Dict[str, Any]]:
    ratings = db.collection('analytics').where('type', '==', rating_type).stream()
    return [_typed_doc(rating) for rating in ratings]


def set_chat_message_rating_score(
    uid: str,
    message_id: str,
    value: int,
    reason: Optional[str] = None,
    platform: Optional[str] = None,
    app_version: Optional[str] = None,
) -> None:
    """
    Store chat message rating/feedback.

    Args:
        uid: User ID
        message_id: Message ID being rated
        value: Rating value (1 = thumbs up, -1 = thumbs down, 0 = neutral/removed)
        reason: Optional reason for thumbs down (e.g. 'too_verbose', 'incorrect_or_hallucination',
                'not_helpful_or_irrelevant', 'didnt_follow_instructions', 'other')
        platform: 'desktop' or 'mobile' — identifies where the rating came from
        app_version: App version string (e.g. '0.11.276') — maps to a specific prompt version
    """
    doc_id = document_id_from_seed('chat_message' + message_id)
    data: Dict[str, Any] = {
        'id': doc_id,
        'message_id': message_id,
        'uid': uid,
        'value': value,
        'created_at': datetime.now(timezone.utc),
        'type': 'chat_message',
    }
    if reason:
        data['reason'] = reason
    if platform:
        data['platform'] = platform
    if app_version:
        data['app_version'] = app_version
    db.collection('analytics').document(doc_id).set(data)


# **************************************
# ************** Payments **************
# **************************************


def get_stripe_connect_account_id(uid: str) -> Optional[str]:
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('stripe_account_id', None)
    return value if isinstance(value, str) else None


def set_stripe_connect_account_id(uid: str, account_id: str) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_account_id': account_id})


def set_paypal_payment_details(uid: str, data: Dict[str, Any]) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.update({'paypal_details': data})


def get_paypal_payment_details(uid: str) -> Optional[Dict[str, Any]]:
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('paypal_details', None)
    return cast(Dict[str, Any], value) if isinstance(value, dict) else None


def set_default_payment_method(uid: str, payment_method_id: str) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.update({'default_payment_method': payment_method_id})


def get_default_payment_method(uid: str) -> Optional[str]:
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('default_payment_method', None)
    return value if isinstance(value, str) else None


def get_stripe_customer_id(uid: str) -> Optional[str]:
    """Get the Stripe customer ID for a user."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        value: object = user_data.get('stripe_customer_id')
        return value if isinstance(value, str) else None
    return None


def set_stripe_customer_id(uid: str, customer_id: str) -> None:
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_customer_id': customer_id})


def get_user_by_stripe_customer_id(customer_id: str) -> Optional[Dict[str, Any]]:
    users_ref = db.collection('users')
    query = users_ref.where(filter=FieldFilter('stripe_customer_id', '==', customer_id)).limit(1)
    docs = list(query.stream())
    if docs:
        user_dict: Dict[str, Any] = _typed_doc(docs[0])
        user_dict['uid'] = docs[0].id
        return user_dict
    return None


def update_user_subscription(uid: str, subscription_data: Dict[str, Any]) -> None:
    """Updates the user's subscription information, removing dynamic fields before storing."""
    subscription_data_to_store: Dict[str, Any] = subscription_data.copy()
    subscription_data_to_store.pop('features', None)
    subscription_data_to_store.pop('limits', None)

    user_ref = db.collection('users').document(uid)
    user_ref.update({'subscription': subscription_data_to_store})


# **************************************
# ********* Data Protection ************
# **************************************


def get_data_protection_level(uid: str) -> str:
    """
    Get the user's data protection level.

    Args:
        uid: User ID

    Returns:
        'enhanced' or 'e2ee'. Defaults to 'enhanced'.
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        value: object = user_data.get('data_protection_level', 'enhanced')
        return value if isinstance(value, str) else 'enhanced'

    return 'enhanced'


def set_data_protection_level(uid: str, level: str) -> None:
    """
    Set the user's data protection level.

    Args:
        uid: User ID
        level: 'enhanced', or 'e2ee'
    """
    if level not in ['enhanced', 'e2ee']:
        raise ValueError("Invalid data protection level. Only 'enhanced' or 'e2ee' are supported.")
    user_ref = db.collection('users').document(uid)
    user_ref.set({'data_protection_level': level}, merge=True)


def set_migration_status(uid: str, target_level: str) -> None:
    """Sets the migration status on the user's profile."""
    user_ref = db.collection('users').document(uid)
    migration_status: Dict[str, Any] = {
        'target_level': target_level,
        'status': 'in_progress',
        'started_at': datetime.now(timezone.utc),
    }
    user_ref.set({'migration_status': migration_status}, merge=True)


def finalize_migration(uid: str, target_level: str) -> None:
    """Atomically sets the new protection level and removes the migration status field."""
    user_ref = db.collection('users').document(uid)
    user_ref.update({'data_protection_level': target_level, 'migration_status': firestore.DELETE_FIELD})


# **************************************
# ************* Language ***************
# **************************************


def get_user_language_preference(uid: str) -> str:
    """
    Get the user's preferred language.

    Args:
        uid: User ID

    Returns:
        Language code (e.g., 'en', 'vi') or empty string if not set
    """

    def fetch_language() -> str:
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get(['language'])

        if user_doc.exists:
            user_data: Dict[str, Any] = _typed_doc(user_doc)
            value: object = user_data.get('language', '')
            return value if isinstance(value, str) else ''

        return ''  # Return empty string if not set

    # DESIGN DECISION: cache this typed user projection, not the full users/{uid} doc.
    #
    # Rationale:
    # - Language preference is a low-risk, frequently-read setting used during
    #   listen startup.
    # - Full user-doc caching is intentionally avoided because users/{uid} also
    #   contains entitlement, BYOK, privacy, and data-protection fields.
    #
    # Safety: cache is disabled by default, Redis failures fall back to Firestore,
    # and set_user_language_preference() invalidates this namespace.
    return cast(str, get_or_fetch(_USER_LANGUAGE_CACHE, uid, fetch_language))


def set_user_language_preference(uid: str, language: str) -> None:
    """
    Set the user's preferred language.

    Args:
        uid: User ID
        language: Language code (e.g., 'en', 'vi')
    """
    user_ref = db.collection('users').document(uid)
    user_ref.set({'language': language}, merge=True)
    invalidate(_USER_LANGUAGE_CACHE, uid)
    invalidate(_USER_TRANSCRIPTION_PREFS_CACHE, uid)


def get_user_onboarding_state(uid: str) -> Dict[str, Any]:
    """Get the user's onboarding state from Firestore."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        value: object = user_data.get('onboarding', {})
        return cast(Dict[str, Any], value) if isinstance(value, dict) else {}
    return {}


def set_user_onboarding_state(uid: str, onboarding_data: Dict[str, Any]) -> None:
    """Update the user's onboarding state in Firestore (merge with existing)."""
    user_ref = db.collection('users').document(uid)
    user_ref.set({'onboarding': onboarding_data}, merge=True)


def get_user_subscription(uid: str) -> Subscription:
    """Gets the user's subscription, creating a default free one if it doesn't exist."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get(['subscription'])
    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        if 'subscription' in user_data:
            sub_data_raw: object = user_data['subscription']
            sub_data: Dict[str, Any] = cast(Dict[str, Any], sub_data_raw) if isinstance(sub_data_raw, dict) else {}
            # Handle migration for old 'free' plan identifier
            if sub_data.get('plan') == 'free':
                sub_data['plan'] = PlanType.basic.value
                update_user_subscription(uid, sub_data)
            return Subscription(**sub_data)

    # If subscription doesn't exist for the user, create and return a default free plan.
    default_subscription = get_default_basic_subscription()
    # Strip dynamic fields before storing
    sub_to_store: Dict[str, Any] = default_subscription.dict()
    sub_to_store.pop('features', None)
    sub_to_store.pop('limits', None)
    user_ref.set({'subscription': sub_to_store}, merge=True)
    return default_subscription


def get_existing_user_subscription(uid: str) -> Optional[Subscription]:
    """Gets the user's stored subscription without creating a default record."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get(['subscription'])
    if not user_doc.exists:
        return None

    user_data: Dict[str, Any] = _typed_doc(user_doc)
    if 'subscription' not in user_data:
        return None

    sub_data_raw: object = user_data['subscription']
    sub_data: Dict[str, Any] = cast(Dict[str, Any], sub_data_raw) if isinstance(sub_data_raw, dict) else {}
    if sub_data.get('plan') == 'free':
        sub_data['plan'] = PlanType.basic.value
    return Subscription(**sub_data)


def get_user_training_data_opt_in(uid: str) -> Optional[Dict[str, Any]]:
    """Get user's training data opt-in status."""
    user_ref = db.collection('users').document(uid)
    user_data: Dict[str, Any] = _typed_doc(user_ref.get())
    value: object = user_data.get('training_data_opt_in', None)
    return cast(Dict[str, Any], value) if isinstance(value, dict) else None


def set_user_training_data_opt_in(uid: str, status: str) -> None:
    """Set user's training data opt-in status. Status can be: pending_review, approved, rejected"""
    user_ref = db.collection('users').document(uid)
    user_ref.update(
        {
            'training_data_opt_in': {
                'status': status,
                'requested_at': datetime.now(timezone.utc),
            }
        }
    )


def get_user_valid_subscription(uid: str) -> Optional[Subscription]:
    """
    Gets the user's subscription if it is currently valid for use.

    A subscription is considered valid if:
    - It's a basic (free) plan with 'active' status.
    - It's a paid plan with a 'current_period_end' that has not passed yet.
      This allows users to use the service until the end of the billing period
      they paid for, even after cancelling.

    Returns the Subscription object if valid, otherwise None.
    """
    subscription = get_user_subscription(uid)

    # Basic (free) plans are only valid if their status is active.
    if subscription.plan == PlanType.basic:
        return subscription if subscription.status == SubscriptionStatus.active else None

    # For paid plans, validity is determined by the period end.
    if subscription.current_period_end:
        period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        if period_end_dt >= datetime.now(timezone.utc):
            return subscription

    # Fallback to default basic subscription
    return get_default_basic_subscription()


# **************************************
# ******** Task Integrations ***********
# **************************************


def get_task_integrations(uid: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all task integration connections for a user.

    Args:
        uid: User ID

    Returns:
        Dictionary with app_key as keys and connection details as values
    """
    user_ref = db.collection('users').document(uid)
    integrations_ref = user_ref.collection('task_integrations')

    integrations: Dict[str, Dict[str, Any]] = {}
    for doc in integrations_ref.stream():
        integrations[doc.id] = _typed_doc(doc)

    return integrations


def get_task_integration(uid: str, app_key: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific task integration connection.

    Args:
        uid: User ID
        app_key: Task integration app key (e.g., 'asana', 'todoist')

    Returns:
        Connection details or None if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)
    doc = integration_ref.get()

    if doc.exists:
        return _typed_doc(doc)
    return None


def set_task_integration(uid: str, app_key: str, data: Dict[str, Any]) -> None:
    """
    Save or update a task integration connection.

    Args:
        uid: User ID
        app_key: Task integration app key (e.g., 'asana', 'todoist')
        data: Connection details to save
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)

    # Add timestamp
    data['updated_at'] = datetime.now(timezone.utc)
    if not integration_ref.get().exists:
        data['created_at'] = datetime.now(timezone.utc)

    integration_ref.set(data, merge=True)


def delete_task_integration(uid: str, app_key: str) -> bool:
    """
    Delete a task integration connection.
    Also clears default_task_integration if it matches the deleted app.

    Args:
        uid: User ID
        app_key: Task integration app key

    Returns:
        True if deleted, False if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)

    if not integration_ref.get().exists:
        return False

    # Check if this is the default integration
    user_doc = user_ref.get()
    is_default = False
    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        is_default = user_data.get('default_task_integration') == app_key

    # Delete integration
    integration_ref.delete()

    # Clear default if needed
    if is_default:
        user_ref.update({'default_task_integration': firestore.DELETE_FIELD})

    return True


def get_default_task_integration(uid: str) -> Optional[str]:
    """
    Get the user's default task integration app.

    Args:
        uid: User ID

    Returns:
        App key of default integration or None
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        value: object = user_data.get('default_task_integration')
        return value if isinstance(value, str) else None

    return None


def set_default_task_integration(uid: str, app_key: str) -> None:
    """
    Set the user's default task integration app.

    Args:
        uid: User ID
        app_key: Task integration app key to set as default
    """
    user_ref = db.collection('users').document(uid)
    user_ref.set({'default_task_integration': app_key}, merge=True)


# **************************************
# ******** Integrations ********
# **************************************


def get_integration(uid: str, app_key: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific integration connection.

    Args:
        uid: User ID
        app_key: Integration app key (e.g., 'google_calendar', 'whoop')

    Returns:
        Connection details or None if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)
    doc = integration_ref.get()

    if doc.exists:
        return _typed_doc(doc)
    return None


def set_integration(uid: str, app_key: str, data: Dict[str, Any]) -> None:
    """
    Save or update an integration connection.

    Args:
        uid: User ID
        app_key: Integration app key (e.g., 'google_calendar', 'whoop')
        data: Connection details to save
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)

    # Add timestamp
    data['updated_at'] = datetime.now(timezone.utc)
    if not integration_ref.get().exists:
        data['created_at'] = datetime.now(timezone.utc)

    integration_ref.set(data, merge=True)


def delete_integration(uid: str, app_key: str) -> bool:
    """
    Delete an integration connection.

    Args:
        uid: User ID
        app_key: Integration app key

    Returns:
        True if deleted, False if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)

    if not integration_ref.get().exists:
        return False

    integration_ref.delete()
    return True


# **************************************
# ***** Transcription Preferences ******
# **************************************


def get_user_transcription_preferences(uid: str) -> Dict[str, Any]:
    """
    Get the user's transcription preferences.

    Returns:
        dict with 'single_language_mode' (bool), 'vocabulary' (List[str]), and 'language' (str)
    """

    def fetch_preferences() -> Dict[str, Any]:
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get(['transcription_preferences', 'language'])

        if user_doc.exists:
            user_data: Dict[str, Any] = _typed_doc(user_doc)
            prefs_raw: object = user_data.get('transcription_preferences', {})
            prefs: Dict[str, Any] = cast(Dict[str, Any], prefs_raw) if isinstance(prefs_raw, dict) else {}
            return {
                'single_language_mode': prefs.get('single_language_mode', False),
                'vocabulary': prefs.get('vocabulary', []),
                'language': user_data.get('language', ''),
                'uses_custom_stt': prefs.get('uses_custom_stt', False),
                'custom_stt_since': prefs.get('custom_stt_since'),
            }

        return {
            'single_language_mode': False,
            'vocabulary': [],
            'language': '',
            'uses_custom_stt': False,
            'custom_stt_since': None,
        }

    # DESIGN DECISION: cache this typed user projection, not the full users/{uid} doc.
    # It includes only transcription startup preferences and language. It does not
    # include entitlement, BYOK, data-protection, or privacy-consent fields.
    return cast(Dict[str, Any], get_or_fetch(_USER_TRANSCRIPTION_PREFS_CACHE, uid, fetch_preferences))


def get_agent_vm(uid: str) -> Optional[Dict[str, Any]]:
    """Get the user's agent VM info from Firestore.

    Returns:
        Dict with VM details (ip, auth_token, status, etc.) or None if no VM.
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data: Dict[str, Any] = _typed_doc(user_doc)
        value: object = user_data.get('agentVm')
        return cast(Dict[str, Any], value) if isinstance(value, dict) else None

    return None


def set_user_transcription_preferences(
    uid: str,
    single_language_mode: Optional[bool] = None,
    vocabulary: Optional[List[str]] = None,
) -> None:
    """
    Set the user's transcription preferences.

    Args:
        uid: User ID
        single_language_mode: If True, use exact language instead of multi-language detection
        vocabulary: List of custom keywords/terms for better transcription accuracy
    """
    user_ref = db.collection('users').document(uid)
    update_data: Dict[str, Any] = {}

    if single_language_mode is not None:
        update_data['transcription_preferences.single_language_mode'] = single_language_mode

    if vocabulary is not None:
        # Limit vocabulary to 100 terms max
        update_data['transcription_preferences.vocabulary'] = vocabulary[:100]

    if update_data:
        user_ref.update(update_data)
        invalidate(_USER_TRANSCRIPTION_PREFS_CACHE, uid)


def set_user_custom_stt_usage(uid: str, uses_custom_stt: bool) -> None:
    """Persist whether the user is using a custom (third-party) mobile STT provider.

    There is no other record that a user is on custom STT — the app only sends a
    per-session `custom_stt=enabled` WS param. This stamps it onto the user doc so
    custom-STT users are queryable/meterable (see #7690).

    - `transcription_preferences.uses_custom_stt`: current state (bool).
    - `transcription_preferences.custom_stt_since`: when the current custom-STT
      streak began (set on the off->on transition; cleared when turned off).

    Callers should only invoke this when the value actually changes, so the
    `_since` timestamp is not overwritten on every session and writes stay rare.
    """
    user_ref = db.collection('users').document(uid)
    update_data: Dict[str, Any] = {'transcription_preferences.uses_custom_stt': uses_custom_stt}
    update_data['transcription_preferences.custom_stt_since'] = datetime.now(timezone.utc) if uses_custom_stt else None
    user_ref.update(update_data)
    invalidate(_USER_TRANSCRIPTION_PREFS_CACHE, uid)


# ============================================================================
# DESKTOP USER SETTINGS — fields on users/{uid} document
# ============================================================================


def get_notification_settings(uid: str) -> Dict[str, Any]:
    """Return notification settings with Swift-compatible field names.

    Firestore stores ``notifications_enabled`` / ``notification_frequency`` on
    the user doc.  The Swift ``NotificationSettingsResponse`` decodes
    ``enabled`` / ``frequency``, so we map to the wire names here.
    """
    # Proactive desktop notifications are OFF by default (frequency 0). Users opt in
    # via the Settings frequency slider; an explicit stored value always wins.
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {'enabled': True, 'frequency': 0}
    data: Dict[str, Any] = _typed_doc(doc)
    return {
        'enabled': data.get('notifications_enabled', True),
        'frequency': data.get('notification_frequency', 0),
    }


def update_notification_settings(
    uid: str,
    enabled: Optional[bool] = None,
    frequency: Optional[int] = None,
) -> Dict[str, Any]:
    user_ref = db.collection('users').document(uid)
    updates: Dict[str, Any] = {}
    if enabled is not None:
        updates['notifications_enabled'] = enabled
    if frequency is not None:
        updates['notification_frequency'] = frequency
    if updates:
        user_ref.update(updates)
    return get_notification_settings(uid)


def _get_raw_assistant_settings(uid: str) -> Dict[str, Any]:
    """Read only the assistant_settings sub-map (without update_channel injection)."""
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {}
    data: Dict[str, Any] = _typed_doc(doc)
    value: object = data.get('assistant_settings')
    return cast(Dict[str, Any], value) if isinstance(value, dict) else {}


def get_assistant_settings(uid: str) -> Dict[str, Any]:
    """Read assistant settings for the API response.

    Injects top-level ``update_channel`` into the response dict (it lives
    outside ``assistant_settings`` in Firestore but the API returns it together).
    """
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {}
    data: Dict[str, Any] = _typed_doc(doc)
    result: Dict[str, Any] = (
        cast(Dict[str, Any], data.get('assistant_settings') or {}).copy()
        if isinstance(data.get('assistant_settings'), dict)
        else {}
    )
    raw_channel: object = data.get('update_channel')
    if raw_channel is not None:
        result['update_channel'] = raw_channel
    return result


def update_assistant_settings(uid: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge partial settings into existing assistant_settings.

    The Swift client sends tiny partial updates (e.g. {"focus": {"enabled": true}})
    on every toggle.  A naive overwrite would erase sibling sections.

    ``update_channel`` is a special case — it lives as a top-level field on the
    user doc (not inside assistant_settings), matching Rust backend behavior.
    """
    # Read raw sub-map (without injected update_channel) to avoid leaking it back
    existing: Dict[str, Any] = _get_raw_assistant_settings(uid)

    # Extract update_channel — it goes to a top-level user doc field
    update_channel = settings.pop('update_channel', None)

    for section, values in settings.items():
        existing_section: object = existing.get(section)
        if isinstance(values, dict) and isinstance(existing_section, dict):
            cast(Dict[str, Any], existing_section).update(cast(Dict[str, Any], values))
        else:
            existing[section] = values

    user_ref = db.collection('users').document(uid)
    updates: Dict[str, Any] = {'assistant_settings': existing}
    if update_channel is not None:
        updates['update_channel'] = update_channel
    user_ref.update(updates)

    # Build response (include update_channel for the caller)
    if update_channel is not None:
        existing['update_channel'] = update_channel
    return existing


def _get_ai_user_profile_from_firestore(uid: str) -> Optional[Dict[str, Any]]:
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get(['ai_user_profile'])
    if not doc.exists:
        return None
    data: Dict[str, Any] = _typed_doc(doc)
    value: object = data.get('ai_user_profile')
    return cast(Dict[str, Any], value) if isinstance(value, dict) else None


def get_ai_user_profile(uid: str) -> Optional[Dict[str, Any]]:
    # DESIGN DECISION: cache only the low-risk ai_user_profile projection.
    # Avoid full user-doc caching because high-risk entitlement/BYOK/privacy
    # fields live on the same Firestore document.
    return cast(
        Optional[Dict[str, Any]],
        get_or_fetch(_USER_AI_PROFILE_CACHE, uid, lambda: _get_ai_user_profile_from_firestore(uid)),
    )


def update_ai_user_profile(
    uid: str,
    profile_text: Optional[str] = None,
    generated_at: Any = None,
    data_sources_used: Optional[int] = None,
) -> Dict[str, Any]:
    """Update AI user profile.  Only writes non-None fields (partial update)."""
    # Read existing profile directly from Firestore — never from cache — because
    # this is a read-modify-write path. Using a stale cached projection here
    # could overwrite newer profile fields.
    existing_raw: Optional[Dict[str, Any]] = _get_ai_user_profile_from_firestore(uid)
    existing: Dict[str, Any] = existing_raw if existing_raw is not None else {}
    if profile_text is not None:
        existing['profile_text'] = profile_text
    if generated_at is not None:
        existing['generated_at'] = generated_at
    if data_sources_used is not None:
        existing['data_sources_used'] = data_sources_used
    user_ref = db.collection('users').document(uid)
    user_ref.update({'ai_user_profile': existing})
    invalidate(_USER_AI_PROFILE_CACHE, uid)
    return existing
