import copy
import hashlib
from typing import List, Optional

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


def _prepare_phone_number_for_write(data: dict, uid: str, level: str) -> dict:
    """Encrypt phone_number field if data protection level is enhanced."""
    data = copy.deepcopy(data)
    if level == 'enhanced' and 'phone_number' in data:
        # Store hash for lookup queries
        data['phone_number_hash'] = _hash_phone_number(data['phone_number'])
        # Encrypt the actual phone number
        data['phone_number'] = encryption.encrypt(data['phone_number'], uid)
    return data


def _prepare_phone_number_for_read(data: dict, uid: str) -> dict:
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
def upsert_phone_number(uid: str, phone_number_data: dict):
    """Create or update a verified phone number for a user."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_data['id'])
    phone_ref.set(phone_number_data)


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_numbers(uid: str) -> List[dict]:
    """Get all verified phone numbers for a user."""
    user_ref = db.collection('users').document(uid)
    phone_refs = user_ref.collection(phone_numbers_collection).stream()
    return [doc.to_dict() for doc in phone_refs]


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_number(uid: str, phone_number_id: str) -> Optional[dict]:
    """Get a specific verified phone number."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    doc = phone_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_phone_number_by_number(uid: str, phone_number: str) -> Optional[dict]:
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
        data = docs[0].to_dict()
        return _prepare_phone_number_for_read(data, uid)

    # Fallback: plaintext query for records written before encryption was enabled
    query = user_ref.collection(phone_numbers_collection).where('phone_number', '==', phone_number).limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].to_dict()

    return None


def delete_phone_number(uid: str, phone_number_id: str):
    """Delete a verified phone number."""
    user_ref = db.collection('users').document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    phone_ref.delete()


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_primary_phone_number(uid: str) -> Optional[dict]:
    """Get the user's primary verified phone number."""
    user_ref = db.collection('users').document(uid)
    query = user_ref.collection(phone_numbers_collection).where('is_primary', '==', True).limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].to_dict()
    # Fallback to first available number
    all_numbers = get_phone_numbers(uid)
    if all_numbers:
        return all_numbers[0]
    return None
