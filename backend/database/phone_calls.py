import copy
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database._client import db
from database.helpers import set_data_protection_level, prepare_for_write, prepare_for_read
from utils import encryption

phone_numbers_collection = "phone_numbers"


def _resolve_db(client: Any = None, firestore_client: Any = None) -> Any:
    """Resolve target Firestore client with injection precedence over global db."""
    if firestore_client is not None:
        return firestore_client
    if client is not None:
        return client
    return db


# ************************************************
# *********** ENCRYPTION HELPERS *****************
# ************************************************


def _hash_phone_number(phone_number: str) -> str:
    """Create a deterministic hash of a phone number for queryable lookup."""
    return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()


def _prepare_phone_number_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    """Encrypt phone_number field if data protection level is enhanced."""
    data = copy.deepcopy(data)
    if level == "enhanced" and "phone_number" in data:
        # Store hash for lookup queries
        data["phone_number_hash"] = _hash_phone_number(data["phone_number"])
        # Encrypt the actual phone number
        data["phone_number"] = encryption.encrypt(data["phone_number"], uid)
    return data


def _prepare_phone_number_for_read(data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Decrypt phone_number field if data protection level is enhanced."""
    if not data:
        return data
    data = copy.deepcopy(data)
    level = data.get("data_protection_level")
    if level == "enhanced" and "phone_number" in data:
        data["phone_number"] = encryption.decrypt(data["phone_number"], uid)
    return data


# ************************************************
# *********** VERIFIED PHONE NUMBERS *************
# ************************************************


@set_data_protection_level(data_arg_name="phone_number_data")
@prepare_for_write(data_arg_name="phone_number_data", prepare_func=_prepare_phone_number_for_write)
def upsert_phone_number(
    uid: str,
    phone_number_data: Dict[str, Any],
    client: Any = None,
    firestore_client: Any = None,
) -> None:
    """Create or update a verified phone number for a user."""
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_data["id"])
    phone_ref.set(phone_number_data)


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_numbers(uid: str, client: Any = None, firestore_client: Any = None) -> List[Dict[str, Any]]:
    """Get all verified phone numbers for a user."""
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    phone_refs = user_ref.collection(phone_numbers_collection).stream()
    out: List[Dict[str, Any]] = []
    for doc in phone_refs:
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            out.append(cast(Dict[str, Any], raw))
    return out


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_phone_number(
    uid: str, phone_number_id: str, client: Any = None, firestore_client: Any = None
) -> Optional[Dict[str, Any]]:
    """Get a specific verified phone number."""
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    doc = phone_ref.get()
    if getattr(doc, "exists", False):
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_phone_number_by_number(
    uid: str, phone_number: str, client: Any = None, firestore_client: Any = None
) -> Optional[Dict[str, Any]]:
    """Get a verified phone number by the actual phone number string.

    For enhanced protection, queries by hash since the phone_number field is encrypted.
    Falls back to plaintext query for standard protection (backward compatibility).
    """
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    phone_hash = _hash_phone_number(phone_number)

    # Try hash-based lookup first (encrypted records)
    query = user_ref.collection(phone_numbers_collection).where("phone_number_hash", "==", phone_hash).limit(1)
    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        return _prepare_phone_number_for_read(data, uid)

    # Fallback: plaintext query for records written before encryption was enabled
    query = user_ref.collection(phone_numbers_collection).where("phone_number", "==", phone_number).limit(1)
    docs = list(query.stream())
    if docs:
        raw = docs[0].to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None

    return None


def delete_phone_number(uid: str, phone_number_id: str, client: Any = None, firestore_client: Any = None) -> bool:
    """Delete a verified phone number with existence check.

    Guards against concurrent deletions by checking document existence prior to deletion.
    Note: get()-then-delete() is not strictly atomic, but Firestore deletions are idempotent
    and this pre-check surfaces concurrent deletions as a clean not-found (False) instead
    of an unhandled error.

    Returns True if document existed and was deleted, False if already deleted/missing.
    """
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    phone_ref = user_ref.collection(phone_numbers_collection).document(phone_number_id)
    if not getattr(phone_ref.get(), "exists", False):
        return False
    phone_ref.delete()
    return True


@prepare_for_read(decrypt_func=_prepare_phone_number_for_read)
def get_primary_phone_number(uid: str, client: Any = None, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """Get the user's primary verified phone number."""
    target_db = _resolve_db(client, firestore_client)
    user_ref = target_db.collection("users").document(uid)
    query = user_ref.collection(phone_numbers_collection).where("is_primary", "==", True).limit(1)
    docs = list(query.stream())
    if docs:
        raw: object = docs[0].to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    # Fallback to first available number
    all_numbers = get_phone_numbers(uid, firestore_client=target_db)
    if all_numbers:
        return all_numbers[0]
    return None


# ************************************************
# ********** PENDING VERIFICATIONS ***************
# ************************************************

PENDING_VERIFICATION_TTL_SECONDS = 300  # 5 minutes


def set_pending_verification(uid: str, phone_number: str, client: Any = None, firestore_client: Any = None) -> None:
    """Record that a user initiated verification for a phone number.

    Uses a hash of the phone number as the document ID for efficient lookup.
    """
    target_db = _resolve_db(client, firestore_client)
    doc_id = _hash_phone_number(phone_number)
    target_db.collection("pending_verifications").document(doc_id).set(
        {
            "uid": uid,
            "phone_number_hash": doc_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def get_pending_verification_uid(phone_number: str, client: Any = None, firestore_client: Any = None) -> Optional[str]:
    """Get the UID of the user who initiated verification for a phone number.

    Returns None if no pending verification exists or if it has expired.
    """
    target_db = _resolve_db(client, firestore_client)
    doc_id = _hash_phone_number(phone_number)
    doc = target_db.collection("pending_verifications").document(doc_id).get()
    if not getattr(doc, "exists", False):
        return None
    raw: object = doc.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    try:
        created_at_raw = data.get("created_at")
        created_at = (
            datetime.fromisoformat(str(created_at_raw))
            if created_at_raw is not None
            else datetime.min.replace(tzinfo=timezone.utc)
        )
    except (TypeError, ValueError):
        # Malformed/legacy pending verification (missing or non-ISO created_at); treat as expired.
        target_db.collection("pending_verifications").document(doc_id).delete()
        return None
    # A stored created_at without a timezone (legacy/naive value) would raise on the aware/naive
    # subtraction below; normalize it to UTC so the elapsed-time check never 500s.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
    if elapsed > PENDING_VERIFICATION_TTL_SECONDS:
        target_db.collection("pending_verifications").document(doc_id).delete()
        return None
    uid_value = data.get("uid")
    return str(uid_value) if uid_value is not None else None


def delete_pending_verification(phone_number: str, client: Any = None, firestore_client: Any = None) -> None:
    """Delete a pending verification record after it has been processed."""
    target_db = _resolve_db(client, firestore_client)
    doc_id = _hash_phone_number(phone_number)
    target_db.collection("pending_verifications").document(doc_id).delete()
