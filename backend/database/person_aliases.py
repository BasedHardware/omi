"""Stable person rename and bounded exact-alias retention."""

from datetime import datetime, timezone
from typing import Any

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
def update_person_name_transaction(transaction: Any, person_ref: Any, name: str) -> bool:
    """Rename one stable person while retaining bounded exact aliases."""

    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
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
    transaction.update(
        person_ref,
        {
            'name': normalized_name,
            'aliases': aliases[-24:],
            'updated_at': datetime.now(timezone.utc),
        },
    )
    return True


def rename_person_retaining_aliases(db_client: Any, uid: str, person_id: str, name: str) -> bool:
    """Rename an owner-scoped person and map concurrent deletion to missing."""

    person_ref = db_client.collection('users').document(uid).collection('people').document(person_id)
    try:
        return update_person_name_transaction(db_client.transaction(), person_ref, name)
    except NotFound:
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

    person_ref = db_client.collection('users').document(uid).collection('people').document(person_id)
    try:
        return dismiss_person_transaction(db_client.transaction(), person_ref)
    except NotFound:
        return False


def list_people(db_client: Any, uid: str, *, include_dismissed: bool = False) -> list[dict[str, Any]]:
    """List owner-scoped people, hiding soft-dismissed records by default."""

    people_ref = db_client.collection('users').document(uid).collection('people')
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

    people_ref = db_client.collection('users').document(uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name))
    for person in query.stream():
        data = person.to_dict()
        if data.get('is_dismissed') is True:
            continue
        data.setdefault('id', person.id)
        return data
    return None
