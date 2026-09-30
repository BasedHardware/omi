"""Stable person rename and bounded exact-alias retention."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Optional

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import transactional

from database._client import get_firestore_client

logger = logging.getLogger(__name__)

MAX_PERSON_ALIASES = 24


def _clean_id(id_val: Optional[str]) -> str:
    """Validate and sanitize user or person ID."""
    if not isinstance(id_val, str):
        return ''
    cleaned = id_val.strip()
    if not cleaned or len(cleaned) > 128 or '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        return ''
    return cleaned


def normalized_person_alias(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = ' '.join(value.split()).strip()
    if not normalized or len(normalized) > 128 or '\x00' in normalized:
        return None
    return normalized


@transactional
def update_person_name_transaction(transaction: Any, person_ref: Any, name: str) -> bool:
    """Rename one stable person while retaining bounded exact aliases."""

    snapshot = person_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
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
            'aliases': aliases[-MAX_PERSON_ALIASES:],
            'updated_at': datetime.now(timezone.utc),
        },
    )
    return True


def rename_person_retaining_aliases(
    db_client: Any = None,
    uid: str = '',
    person_id: str = '',
    name: str = '',
) -> bool:
    """Rename an owner-scoped person and map concurrent deletion or invalid IDs to failure."""
    clean_uid = _clean_id(uid)
    clean_pid = _clean_id(person_id)
    if not clean_uid or not clean_pid:
        return False

    normalized_name = normalized_person_alias(name)
    if normalized_name is None:
        return False

    client = db_client if db_client is not None else get_firestore_client()
    if client is None:
        return False
    try:
        person_ref = client.collection('users').document(clean_uid).collection('people').document(clean_pid)
        return bool(update_person_name_transaction(client.transaction(), person_ref, normalized_name))
    except NotFound:
        return False
    except Exception:
        logger.exception('Unexpected error renaming person %s for uid %s', clean_pid, clean_uid)
        raise
