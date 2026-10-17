"""Stable person rename and bounded exact-alias retention."""

from datetime import datetime, timezone
from database import chat_edits
from typing import Any, Optional

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import FieldFilter, transactional


def normalized_person_alias(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = ' '.join(value.split()).strip()
    if not normalized or len(normalized) > 128:
        return None
    return normalized


@transactional
def update_person_name_transaction(
    transaction: Any, person_ref: Any, name: str, expected_chat_state: dict | None = None
) -> bool:
    """Rename one stable person while retaining bounded exact aliases."""

    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
    if expected_chat_state is not None:
        fields = {key: data[key] for key in chat_edits.FIELDS['person'] if key in data}
        if chat_edits.encode(fields) != expected_chat_state['before']:
            raise PermissionError('Person changed before rename')
    normalized_name = normalized_person_alias(name)
    if normalized_name is None:
        return False

    aliases: list[str] = []
    seen: set[str] = {normalized_name.casefold()}
    stored_aliases = data.get('aliases')
    if isinstance(stored_aliases, list):
        for value in stored_aliases:
            alias = normalized_person_alias(value)
            if alias is None or alias.casefold() in seen:
                continue
            seen.add(alias.casefold())
            aliases.append(alias)
    prior_name = normalized_person_alias(data.get('name'))
    if prior_name is not None and prior_name.casefold() not in seen:
        aliases.append(prior_name)
    patch = {
        'name': normalized_name,
        'aliases': aliases[-24:],
        'updated_at': datetime.now(timezone.utc),
        'is_user_created': True,
    }
    transaction.update(person_ref, patch)
    if expected_chat_state is not None:
        expected_chat_state['after'] = chat_edits.encode(patch)
    return True


import logging

logger = logging.getLogger(__name__)

_MAX_ID_LENGTH = 256
# Firestore document IDs are path segments: separators and the reserved colon
# must never reach the collection/document path builder.
_UNSAFE_ID_CHARS = ('/', '\\', ':')


def _clean_id(value: Any) -> Optional[str]:
    """Return a safe Firestore path segment, or None when the value is unsafe.

    Person identifiers are used verbatim as `users/{uid}/people/{person_id}`
    path segments, so non-string, empty, oversized, and separator-bearing
    values are rejected before any query or transaction is opened.
    """
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_ID_LENGTH:
        return None
    if cleaned in ('.', '..'):
        return None
    if any(char in cleaned for char in _UNSAFE_ID_CHARS):
        return None
    return cleaned


def rename_person_retaining_aliases(
    db_client: Any, uid: str, person_id: str, name: str, *, expected_chat_state: dict | None = None
) -> bool:
    """Rename an owner-scoped person and map concurrent deletion to missing."""

    clean_uid = _clean_id(uid)
    clean_person_id = _clean_id(person_id)
    if clean_uid is None or clean_person_id is None:
        logger.warning('Refusing person rename for invalid identifiers')
        return False

    person_ref = db_client.collection('users').document(clean_uid).collection('people').document(clean_person_id)
    try:
        if expected_chat_state is not None:
            return update_person_name_transaction(db_client.transaction(), person_ref, name, expected_chat_state)
        return update_person_name_transaction(db_client.transaction(), person_ref, name)
    except NotFound:
        return False
    except PermissionError:
        # Optimistic-concurrency conflicts are meaningful to callers; let them through.
        raise
    except Exception:
        logger.exception('Person rename failed for uid=%s person_id=%s', clean_uid, clean_person_id)
        return False


@transactional
def dismiss_person_transaction(transaction: Any, person_ref: Any) -> bool:
    """Soft-dismiss one person while preserving its history and voice data."""

    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
    if data.get('is_dismissed') is True:
        return True
    now = datetime.now(timezone.utc)
    transaction.update(
        person_ref,
        {
            'is_dismissed': True,
            'dismissed_at': now,
            'updated_at': now,
        },
    )
    return True


def dismiss_person_soft(db_client: Any, uid: str, person_id: str) -> bool:
    """Soft-dismiss an owner-scoped person and map concurrent deletion to missing."""

    clean_uid = _clean_id(uid)
    clean_person_id = _clean_id(person_id)
    if clean_uid is None or clean_person_id is None:
        logger.warning('Refusing person dismissal for invalid identifiers')
        return False

    person_ref = db_client.collection('users').document(clean_uid).collection('people').document(clean_person_id)
    try:
        return dismiss_person_transaction(db_client.transaction(), person_ref)
    except NotFound:
        return False
    except Exception:
        logger.exception('Person dismissal failed for uid=%s person_id=%s', clean_uid, clean_person_id)
        return False


def list_people(
    db_client: Any, uid: str, *, include_dismissed: bool = False, limit: Optional[int] = None
) -> list[dict[str, Any]]:
    """List owner-scoped people, hiding soft-dismissed records by default."""

    clean_uid = _clean_id(uid)
    if clean_uid is None:
        logger.warning('Refusing person listing for invalid identifier')
        return []
    uid = clean_uid

    people_ref = db_client.collection('users').document(uid).collection('people')
    if limit is not None:
        people_ref = people_ref.limit(limit)
    result = []
    for person in people_ref.stream():
        data = person.to_dict()
        if not include_dismissed and data.get('is_dismissed') is True:
            continue
        data.setdefault('id', person.id)
        result.append(data)
    return result


def find_person_by_name(db_client: Any, uid: str, name: str) -> dict[str, Any] | None:
    """Find the first active owner-scoped person with an exact display name."""

    clean_uid = _clean_id(uid)
    if clean_uid is None:
        logger.warning('Refusing person lookup for invalid identifier')
        return None

    people_ref = db_client.collection('users').document(clean_uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name))
    for person in query.stream():
        data = person.to_dict()
        if data.get('is_dismissed') is True:
            continue
        data.setdefault('id', person.id)
        return data
    return None


def get_person_aliases(db_client: Any, uid: str, person_id: str) -> list[str]:
    """Return the retained exact aliases for one person, or [] when unavailable."""

    clean_uid = _clean_id(uid)
    clean_person_id = _clean_id(person_id)
    if clean_uid is None or clean_person_id is None:
        logger.warning('Refusing person alias lookup for invalid identifiers')
        return []

    person_ref = db_client.collection('users').document(clean_uid).collection('people').document(clean_person_id)
    try:
        snapshot = person_ref.get()
    except Exception:
        logger.exception('Person alias lookup failed for uid=%s person_id=%s', clean_uid, clean_person_id)
        return []
    if not getattr(snapshot, 'exists', False):
        return []
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
    stored = data.get('aliases')
    if not isinstance(stored, list):
        return []
    return [alias for alias in (normalized_person_alias(value) for value in stored) if alias is not None]
