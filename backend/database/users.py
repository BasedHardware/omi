from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional

from ._client import db, document_id_from_seed
from database.redis_db import try_acquire_user_platform_write_lock
from models.users import Subscription, PlanLimits, PlanType, SubscriptionStatus
from utils.subscription import get_default_basic_subscription
import logging

logger = logging.getLogger(__name__)


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
    if not raw or not isinstance(raw, str):
        return None, None
    os_value = raw.strip().lower()
    if not os_value:
        return None, None
    coarse = _PLATFORM_ALIASES.get(os_value)
    return coarse, os_value


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

        updates = {
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
            data = snapshot.to_dict() or {}
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


def is_exists_user(uid: str):
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return False
    return True


def get_user_profile(uid: str) -> dict:
    """Gets the full user profile document."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        return user_doc.to_dict()
    return {}


def get_user_store_recording_permission(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('store_recording_permission', False)


def set_user_store_recording_permission(uid: str, value: bool):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'store_recording_permission': value})


def get_user_private_cloud_sync_enabled(uid: str) -> bool:
    """Check if user has private cloud sync enabled."""
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('private_cloud_sync_enabled', True)


def set_user_private_cloud_sync_enabled(uid: str, value: bool):
    """Enable or disable private cloud sync for a user."""
    user_ref = db.collection('users').document(uid)
    user_ref.update({'private_cloud_sync_enabled': value})


def set_user_cancellation_feedback(uid: str, reason: str, reason_details: Optional[str] = None):
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


def get_byok_state(uid: str) -> dict:
    user_ref = db.collection('users').document(uid)
    data = user_ref.get().to_dict() or {}
    return data.get('byok', {})


def is_byok_active(uid: str) -> bool:
    """True if user has a live BYOK activation (heartbeat within TTL)."""
    state = get_byok_state(uid)
    if not state.get('active'):
        return False
    last_seen = state.get('last_seen_at')
    if not last_seen:
        return False
    if isinstance(last_seen, datetime):
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    else:
        return False
    return age <= BYOK_HEARTBEAT_TTL_SECONDS


def set_byok_active(uid: str, fingerprints: dict):
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


def clear_byok_active(uid: str):
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


def set_user_deletion_feedback(uid: str, reason: Optional[str], reason_details: Optional[str] = None):
    # Stored in a top-level collection so it survives the user record being deleted.
    db.collection('account_deletions').document(uid).set(
        {
            'uid': uid,
            'reason': reason or '',
            'reason_details': reason_details or '',
            'timestamp': datetime.now(timezone.utc),
        }
    )


def create_person(uid: str, data: dict):
    people_ref = db.collection('users').document(uid).collection('people')
    people_ref.document(data['id']).set(data)
    return data


def get_person(uid: str, person_id: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()
    if not person_doc.exists:
        return None
    person_data = person_doc.to_dict()
    person_data.setdefault('id', person_doc.id)
    return person_data


def get_people(uid: str):
    people_ref = db.collection('users').document(uid).collection('people')
    result = []
    for person in people_ref.stream():
        data = person.to_dict()
        data.setdefault('id', person.id)
        result.append(data)
    return result


def get_person_by_name(uid: str, name: str):
    people_ref = db.collection('users').document(uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name)).limit(1)
    docs = list(query.stream())
    if docs:
        data = docs[0].to_dict()
        data.setdefault('id', docs[0].id)
        return data
    return None


def get_people_by_ids(uid: str, person_ids: list[str]):
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
    all_people = []
    for doc in db.get_all(doc_refs):
        if doc.exists:
            data = doc.to_dict()
            data.setdefault('id', doc.id)
            all_people.append(data)
    return all_people


def update_person(uid: str, person_id: str, name: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.update({'name': name})


def delete_person(uid: str, person_id: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.delete()


@transactional
def _add_sample_transaction(transaction, person_ref, sample_path, transcript, max_samples):
    """Transaction to atomically add sample and transcript."""
    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False

    person_data = snapshot.to_dict()
    samples = person_data.get('speech_samples', [])

    if len(samples) >= max_samples:
        return False

    samples.append(sample_path)
    update_data = {
        'speech_samples': samples,
        'updated_at': datetime.now(timezone.utc),
    }

    if transcript is not None:
        transcripts = person_data.get('speech_sample_transcripts', [])
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

    person_data = person_doc.to_dict()
    return len(person_data.get('speech_samples', []))


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
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_data = person_doc.to_dict()
    samples = person_data.get('speech_samples', [])
    transcripts = person_data.get('speech_sample_transcripts', [])

    # Find index of sample to remove
    try:
        idx = samples.index(sample_path)
    except ValueError:
        return False  # Sample not found

    # Remove from both arrays by index
    samples.pop(idx)
    if idx < len(transcripts):
        transcripts.pop(idx)

    person_ref.update(
        {
            'speech_samples': samples,
            'speech_sample_transcripts': transcripts,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def set_user_speaker_embedding(uid: str, embedding: list) -> bool:
    """Store speaker embedding for the user's own voice on their user document."""
    user_ref = db.collection('users').document(uid)
    user_ref.update(
        {
            'speaker_embedding': embedding,
            'speaker_embedding_updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def get_user_speaker_embedding(uid: str) -> Optional[list]:
    """Get the user's own speaker embedding from their user document."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return None
    return user_doc.to_dict().get('speaker_embedding')


def set_person_speaker_embedding(uid: str, person_id: str, embedding: list) -> bool:
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


def get_person_speaker_embedding(uid: str, person_id: str) -> Optional[list]:
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

    person_data = person_doc.to_dict()
    return person_data.get('speaker_embedding')


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

    person_data = person_doc.to_dict()
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
    samples: list,
    transcripts: list,
    version: int,
    speaker_embedding: Optional[list] = None,
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

    update_data = {
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


def _delete_collection_recursive(collection_ref, batch_size: int = 450):
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


def delete_user_data(uid: str):
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


def set_conversation_summary_rating_score(uid: str, conversation_id: str, value: int):
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


def get_conversation_summary_rating_score(conversation_id: str):
    doc_id = document_id_from_seed('memory_summary' + conversation_id)
    doc_ref = db.collection('analytics').document(doc_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_all_ratings(rating_type: str = 'memory_summary'):
    ratings = db.collection('analytics').where('type', '==', rating_type).stream()
    return [rating.to_dict() for rating in ratings]


def set_chat_message_rating_score(
    uid: str, message_id: str, value: int, reason: str = None, platform: str = None, app_version: str = None
):
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
    data = {
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


def get_stripe_connect_account_id(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('stripe_account_id', None)


def set_stripe_connect_account_id(uid: str, account_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_account_id': account_id})


def set_paypal_payment_details(uid: str, data: dict):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'paypal_details': data})


def get_paypal_payment_details(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('paypal_details', None)


def set_default_payment_method(uid: str, payment_method_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'default_payment_method': payment_method_id})


def get_default_payment_method(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('default_payment_method', None)


def get_stripe_customer_id(uid: str) -> Optional[str]:
    """Get the Stripe customer ID for a user."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('stripe_customer_id')
    return None


def set_stripe_customer_id(uid: str, customer_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_customer_id': customer_id})


def get_user_by_stripe_customer_id(customer_id: str):
    users_ref = db.collection('users')
    query = users_ref.where(filter=FieldFilter('stripe_customer_id', '==', customer_id)).limit(1)
    docs = list(query.stream())
    if docs:
        user_dict = docs[0].to_dict()
        user_dict['uid'] = docs[0].id
        return user_dict
    return None


def update_user_subscription(uid: str, subscription_data: dict):
    """Updates the user's subscription information, removing dynamic fields before storing."""
    subscription_data_to_store = subscription_data.copy()
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
        user_data = user_doc.to_dict()
        return user_data.get('data_protection_level', 'enhanced')

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


def set_migration_status(uid: str, target_level: str):
    """Sets the migration status on the user's profile."""
    user_ref = db.collection('users').document(uid)
    migration_status = {'target_level': target_level, 'status': 'in_progress', 'started_at': datetime.now(timezone.utc)}
    user_ref.set({'migration_status': migration_status}, merge=True)


def finalize_migration(uid: str, target_level: str):
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
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('language', '')

    return ''  # Return empty string if not set


def set_user_language_preference(uid: str, language: str) -> None:
    """
    Set the user's preferred language.

    Args:
        uid: User ID
        language: Language code (e.g., 'en', 'vi')
    """
    user_ref = db.collection('users').document(uid)
    user_ref.set({'language': language}, merge=True)


def get_user_onboarding_state(uid: str) -> dict:
    """Get the user's onboarding state from Firestore."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('onboarding', {})
    return {}


def set_user_onboarding_state(uid: str, onboarding_data: dict) -> None:
    """Update the user's onboarding state in Firestore (merge with existing)."""
    user_ref = db.collection('users').document(uid)
    user_ref.set({'onboarding': onboarding_data}, merge=True)


def get_user_subscription(uid: str) -> Subscription:
    """Gets the user's subscription, creating a default free one if it doesn't exist."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get(['subscription'])
    if user_doc.exists:
        user_data = user_doc.to_dict()
        if 'subscription' in user_data:
            sub_data = user_data['subscription']
            # Handle migration for old 'free' plan identifier
            if sub_data.get('plan') == 'free':
                sub_data['plan'] = PlanType.basic.value
                update_user_subscription(uid, sub_data)
            return Subscription(**sub_data)

    # If subscription doesn't exist for the user, create and return a default free plan.
    default_subscription = get_default_basic_subscription()
    # Strip dynamic fields before storing
    sub_to_store = default_subscription.dict()
    sub_to_store.pop('features', None)
    sub_to_store.pop('limits', None)
    user_ref.set({'subscription': sub_to_store}, merge=True)
    return default_subscription


def get_user_training_data_opt_in(uid: str) -> Optional[dict]:
    """Get user's training data opt-in status."""
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('training_data_opt_in', None)


def set_user_training_data_opt_in(uid: str, status: str):
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


def get_task_integrations(uid: str) -> dict:
    """
    Get all task integration connections for a user.

    Args:
        uid: User ID

    Returns:
        Dictionary with app_key as keys and connection details as values
    """
    user_ref = db.collection('users').document(uid)
    integrations_ref = user_ref.collection('task_integrations')

    integrations = {}
    for doc in integrations_ref.stream():
        integrations[doc.id] = doc.to_dict()

    return integrations


def get_task_integration(uid: str, app_key: str) -> Optional[dict]:
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
        return doc.to_dict()
    return None


def set_task_integration(uid: str, app_key: str, data: dict) -> None:
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
        user_data = user_doc.to_dict()
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
        user_data = user_doc.to_dict()
        return user_data.get('default_task_integration')

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


def get_integration(uid: str, app_key: str) -> Optional[dict]:
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
        return doc.to_dict()
    return None


def set_integration(uid: str, app_key: str, data: dict) -> None:
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


def get_user_transcription_preferences(uid: str) -> dict:
    """
    Get the user's transcription preferences.

    Returns:
        dict with 'single_language_mode' (bool), 'vocabulary' (List[str]), and 'language' (str)
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        prefs = user_data.get('transcription_preferences', {})
        return {
            'single_language_mode': prefs.get('single_language_mode', False),
            'vocabulary': prefs.get('vocabulary', []),
            'language': user_data.get('language', ''),
        }

    return {'single_language_mode': False, 'vocabulary': [], 'language': ''}


def get_agent_vm(uid: str) -> Optional[dict]:
    """Get the user's agent VM info from Firestore.

    Returns:
        Dict with VM details (ip, auth_token, status, etc.) or None if no VM.
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('agentVm')

    return None


def set_user_transcription_preferences(uid: str, single_language_mode: bool = None, vocabulary: list = None) -> None:
    """
    Set the user's transcription preferences.

    Args:
        uid: User ID
        single_language_mode: If True, use exact language instead of multi-language detection
        vocabulary: List of custom keywords/terms for better transcription accuracy
    """
    user_ref = db.collection('users').document(uid)
    update_data = {}

    if single_language_mode is not None:
        update_data['transcription_preferences.single_language_mode'] = single_language_mode

    if vocabulary is not None:
        # Limit vocabulary to 100 terms max
        update_data['transcription_preferences.vocabulary'] = vocabulary[:100]

    if update_data:
        user_ref.update(update_data)


# ============================================================================
# DESKTOP USER SETTINGS — fields on users/{uid} document
# ============================================================================


def get_notification_settings(uid: str) -> dict:
    """Return notification settings with Swift-compatible field names.

    Firestore stores ``notifications_enabled`` / ``notification_frequency`` on
    the user doc.  The Swift ``NotificationSettingsResponse`` decodes
    ``enabled`` / ``frequency``, so we map to the wire names here.
    """
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {'enabled': True, 'frequency': 3}
    data = doc.to_dict()
    return {
        'enabled': data.get('notifications_enabled', True),
        'frequency': data.get('notification_frequency', 3),
    }


def update_notification_settings(uid: str, enabled: bool = None, frequency: int = None) -> dict:
    user_ref = db.collection('users').document(uid)
    updates = {}
    if enabled is not None:
        updates['notifications_enabled'] = enabled
    if frequency is not None:
        updates['notification_frequency'] = frequency
    if updates:
        user_ref.update(updates)
    return get_notification_settings(uid)


def _get_raw_assistant_settings(uid: str) -> dict:
    """Read only the assistant_settings sub-map (without update_channel injection)."""
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {}
    return doc.to_dict().get('assistant_settings') or {}


def get_assistant_settings(uid: str) -> dict:
    """Read assistant settings for the API response.

    Injects top-level ``update_channel`` into the response dict (it lives
    outside ``assistant_settings`` in Firestore but the API returns it together).
    """
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    result = (data.get('assistant_settings') or {}).copy()
    if data.get('update_channel') is not None:
        result['update_channel'] = data['update_channel']
    return result


def update_assistant_settings(uid: str, settings: dict) -> dict:
    """Deep-merge partial settings into existing assistant_settings.

    The Swift client sends tiny partial updates (e.g. {"focus": {"enabled": true}})
    on every toggle.  A naive overwrite would erase sibling sections.

    ``update_channel`` is a special case — it lives as a top-level field on the
    user doc (not inside assistant_settings), matching Rust backend behavior.
    """
    # Read raw sub-map (without injected update_channel) to avoid leaking it back
    existing = _get_raw_assistant_settings(uid)

    # Extract update_channel — it goes to a top-level user doc field
    update_channel = settings.pop('update_channel', None)

    for section, values in settings.items():
        if isinstance(values, dict) and isinstance(existing.get(section), dict):
            existing[section].update(values)
        else:
            existing[section] = values

    user_ref = db.collection('users').document(uid)
    updates = {'assistant_settings': existing}
    if update_channel is not None:
        updates['update_channel'] = update_channel
    user_ref.update(updates)

    # Build response (include update_channel for the caller)
    if update_channel is not None:
        existing['update_channel'] = update_channel
    return existing


def get_ai_user_profile(uid: str) -> Optional[dict]:
    user_ref = db.collection('users').document(uid)
    doc = user_ref.get()
    if not doc.exists:
        return None
    return doc.to_dict().get('ai_user_profile')


def update_ai_user_profile(
    uid: str, profile_text: str = None, generated_at=None, data_sources_used: int = None
) -> dict:
    """Update AI user profile.  Only writes non-None fields (partial update)."""
    # Read existing profile and merge updates
    existing = get_ai_user_profile(uid) or {}
    if profile_text is not None:
        existing['profile_text'] = profile_text
    if generated_at is not None:
        existing['generated_at'] = generated_at
    if data_sources_used is not None:
        existing['data_sources_used'] = data_sources_used
    user_ref = db.collection('users').document(uid)
    user_ref.update({'ai_user_profile': existing})
    return existing
