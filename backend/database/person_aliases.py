"""Stable person rename and bounded exact-alias retention."""

from datetime import datetime, timezone
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import transactional


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
