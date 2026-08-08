import copy
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database.store import Filter, get_document_store
from database.helpers import set_data_protection_level, prepare_for_write, prepare_for_read
from utils import encryption

phone_numbers_collection = 'phone_numbers'
pending_verifications_collection = 'pending_verifications'


def _store():
    return get_document_store()


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _phone_numbers_path(uid: str) -> str:
    return f'users/{uid}/{phone_numbers_collection}'


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
    _store().set(f'{_phone_numbers_path(uid)}/{phone_number_data["id"]}', phone_number_data)


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_numbers(uid: str) -> List[Dict[str, Any]]:
    """Get all verified phone numbers for a user."""
    return [_typed_doc(doc) for doc in _store().query(_phone_numbers_path(uid))]


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_number(uid: str, phone_number_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific verified phone number."""
    doc = _store().get(f'{_phone_numbers_path(uid)}/{phone_number_id}')
    if doc.exists:
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_phone_number_by_number(uid: str, phone_number: str) -> Optional[Dict[str, Any]]:
    """Get a verified phone number by the actual phone number string.

    For enhanced protection, queries by hash since the phone_number field is encrypted.
    Falls back to plaintext query for standard protection (backward compatibility).
    """
    phone_hash = _hash_phone_number(phone_number)

    # Try hash-based lookup first (encrypted records)
    hash_filters: List[Filter] = [('phone_number_hash', '==', phone_hash)]
    docs = _store().query(_phone_numbers_path(uid), filters=hash_filters, limit=1)
    if docs:
        data = _typed_doc(docs[0])
        return _prepare_phone_number_for_read(data, uid)

    # Fallback: plaintext query for records written before encryption was enabled
    plain_filters: List[Filter] = [('phone_number', '==', phone_number)]
    docs = _store().query(_phone_numbers_path(uid), filters=plain_filters, limit=1)
    if docs:
        return _typed_doc(docs[0])

    return None


def delete_phone_number(uid: str, phone_number_id: str) -> None:
    """Delete a verified phone number."""
    _store().delete(f'{_phone_numbers_path(uid)}/{phone_number_id}')


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_primary_phone_number(uid: str) -> Optional[Dict[str, Any]]:
    """Get the user's primary verified phone number."""
    primary_filters: List[Filter] = [('is_primary', '==', True)]
    docs = _store().query(_phone_numbers_path(uid), filters=primary_filters, limit=1)
    if docs:
        return _typed_doc(docs[0])
    # Fallback to first available number
    all_numbers = get_phone_numbers(uid)
    if all_numbers:
        return all_numbers[0]
    return None


# ************************************************
# ********** PENDING VERIFICATIONS ***************
# ************************************************

PENDING_VERIFICATION_TTL_SECONDS = 300  # 5 minutes


def set_pending_verification(uid: str, phone_number: str) -> None:
    """Record that a user initiated verification for a phone number.

    Uses a hash of the phone number as the document ID for efficient lookup.
    """
    doc_id = _hash_phone_number(phone_number)
    _store().set(
        f'{pending_verifications_collection}/{doc_id}',
        {
            'uid': uid,
            'phone_number_hash': doc_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
    )


def get_pending_verification_uid(phone_number: str) -> Optional[str]:
    """Get the UID of the user who initiated verification for a phone number.

    Returns None if no pending verification exists or if it has expired.
    """
    doc_id = _hash_phone_number(phone_number)
    path = f'{pending_verifications_collection}/{doc_id}'
    doc = _store().get(path)
    if not doc.exists:
        return None
    data = _typed_doc(doc)
    try:
        created_at_raw = data.get('created_at')
        created_at = (
            datetime.fromisoformat(str(created_at_raw))
            if created_at_raw is not None
            else datetime.min.replace(tzinfo=timezone.utc)
        )
    except (TypeError, ValueError):
        # Malformed/legacy pending verification (missing or non-ISO created_at); treat as expired.
        _store().delete(path)
        return None
    # A stored created_at without a timezone (legacy/naive value) would raise on the aware/naive
    # subtraction below; normalize it to UTC so the elapsed-time check never 500s.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
    if elapsed > PENDING_VERIFICATION_TTL_SECONDS:
        _store().delete(path)
        return None
    uid_value = data.get('uid')
    return str(uid_value) if uid_value is not None else None


def delete_pending_verification(phone_number: str) -> None:
    """Delete a pending verification record after it has been processed."""
    doc_id = _hash_phone_number(phone_number)
    _store().delete(f'{pending_verifications_collection}/{doc_id}')
