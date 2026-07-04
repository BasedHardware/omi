import copy
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database._client import db
from database.helpers import set_data_protection_level, prepare_for_write, prepare_for_read
from utils import encryption

phone_numbers_collection = 'phone_numbers'


# ************************************************
# *********** ENCRYPTION HELPERS *****************
# ************************************************


def _hash_phone_number(phone_number: str) -> str:
    """Create a deterministic hash of a phone number for queryable lookup."""
    return hashlib.sha256(phone_number.encode('utf-8')).hexdigest()


def _prepare_phone_number_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    """Encrypt phone_number field if data protection level is enhanced."""
    data = copy.deepcopy(data)
    if level == 'enhanced' and 'phone_number' in data:
        # Store hash for lookup queries
        data['phone_number_hash'] = _hash_phone_number(data['phone_number'])
        # Encrypt the actual phone number
        data['phone_number'] = encryption.encrypt(data['phone_number'], uid)
    return data


def _prepare_phone_number_for_read(data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Decrypt phone_number field if data protection level is enhanced."""
    if not data:
        return data
    data = copy.deepcopy(data)
    level = data.get('data_protection_level')
    if level == 'enhanced' and 'phone_number' in data:
        data['phone_number'] = encryption.decrypt(data['phone_number'], uid)
    return data


# ************************************************
# *********** VERIFIED PHONE NUMBERS *************
# ************************************************


@set_data_protection_level(data_arg_name='phone_number_data')
@prepare_for_write(data_arg_name='phone_number_data', prepare_func=_prepare_phone_number_for_write)
def upsert_phone_number(uid: str, phone_number_data: Dict[str, Any]) -> None:
    """Create or update a verified phone number for a user."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_data['id'])
    phone_ref.set(phone_number_data)


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_numbers(uid: str) -> List[Dict[str, Any]]:
    """Get all verified phone numbers for a user."""
    user_ref = db.collection('users').document(uid)
    phone_refs = user_ref.collection(phone_numbers_collection).stream()
    out: List[Dict[str, Any]] = []
    for doc in phone_refs:
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            out.append(cast(Dict[str, Any], raw))
    return out


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_number(uid: str, phone_number_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific verified phone number."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    doc = phone_ref.get()
    if getattr(doc, "exists", False):
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_phone_number_by_number(uid: str, phone_number: str) -> Optional[Dict[str, Any]]:
    """Get a verified phone number by the actual phone number string.

    For enhanced protection, queries by hash since the phone_number field is encrypted.
    Falls back to plaintext query for standard protection (backward compatibility).
    """
    user_ref = db.collection('users').document(uid)
    phone_hash = _hash_phone_number(phone_number)

    # Try hash-based lookup first (encrypted records)
    query = user_ref.collection(phone_numbers_collection).where('phone_number_hash', '==', phone_hash).limit(1)
    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        return _prepare_phone_number_for_read(data, uid)

    # Fallback: plaintext query for records written before encryption was enabled
    query = user_ref.collection(phone_numbers_collection).where('phone_number', '==', phone_number).limit(1)
    docs = list(query.stream())
    if docs:
        raw = docs[0].to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None

    return None


def delete_phone_number(uid: str, phone_number_id: str) -> None:
    """Delete a verified phone number."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    phone_ref.delete()


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_primary_phone_number(uid: str) -> Optional[Dict[str, Any]]:
    """Get the user's primary verified phone number."""
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(phone_numbers_collection).where('is_primary', '==', True).limit(1)
    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    # Fallback to first available number
    all_numbers = get_phone_numbers(uid)
    if all_numbers:
        return all_numbers[0]
    return None


def set_primary_phone_number(uid: str, phone_number_id: str) -> bool:
    """Make one verified number the user's primary outbound caller ID.

    Sets is_primary=True on the chosen number and False on all others in a single batch. Returns
    False if the id does not belong to the user. is_primary is unencrypted, so this touches only
    that flag and never the encrypted phone_number field.
    """
    numbers = get_phone_numbers(uid)
    if not any(n.get('id') == phone_number_id for n in numbers):
        return False
    col = db.collection('users').document(uid).collection(phone_numbers_collection)
    batch = db.batch()
    for n in numbers:
        batch.update(col.document(n['id']), {'is_primary': n['id'] == phone_number_id})
    batch.commit()
    return True


def rename_phone_number(uid: str, phone_number_id: str, friendly_name: str) -> bool:
    """Rename a verified number's friendly_name label.

    Returns False if the number does not exist. friendly_name is unencrypted, so this is a targeted
    field update that leaves the encrypted phone_number untouched.
    """
    phone_ref = db.collection('users').document(uid).collection(phone_numbers_collection).document(phone_number_id)
    if not phone_ref.get().exists:
        return False
    phone_ref.update({'friendly_name': friendly_name})
    return True


# ************************************************
# ********** PENDING VERIFICATIONS ***************
# ************************************************

PENDING_VERIFICATION_TTL_SECONDS = 300  # 5 minutes


def set_pending_verification(uid: str, phone_number: str) -> None:
    """Record that a user initiated verification for a phone number.

    Uses a hash of the phone number as the document ID for efficient lookup.
    """
    doc_id = _hash_phone_number(phone_number)
    db.collection('pending_verifications').document(doc_id).set(
        {
            'uid': uid,
            'phone_number_hash': doc_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
    )


def get_pending_verification_uid(phone_number: str) -> Optional[str]:
    """Get the UID of the user who initiated verification for a phone number.

    Returns None if no pending verification exists or if it has expired.
    """
    doc_id = _hash_phone_number(phone_number)
    doc = db.collection('pending_verifications').document(doc_id).get()
    if not getattr(doc, "exists", False):
        return None
    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    try:
        created_at_raw = data.get('created_at')
        created_at = (
            datetime.fromisoformat(str(created_at_raw))
            if created_at_raw is not None
            else datetime.min.replace(tzinfo=timezone.utc)
        )
    except (TypeError, ValueError):
        # Malformed/legacy pending verification (missing or non-ISO created_at); treat as expired.
        db.collection('pending_verifications').document(doc_id).delete()
        return None
    # A stored created_at without a timezone (legacy/naive value) would raise on the aware/naive
    # subtraction below; normalize it to UTC so the elapsed-time check never 500s.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
    if elapsed > PENDING_VERIFICATION_TTL_SECONDS:
        db.collection('pending_verifications').document(doc_id).delete()
        return None
    uid_value = data.get('uid')
    return str(uid_value) if uid_value is not None else None


def delete_pending_verification(phone_number: str) -> None:
    """Delete a pending verification record after it has been processed."""
    doc_id = _hash_phone_number(phone_number)
    db.collection('pending_verifications').document(doc_id).delete()
