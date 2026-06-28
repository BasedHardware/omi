"""Shared orchestration for the people MCP tools (REST + SSE).

Wraps the people functions in ``database.users`` with the same validation the
REST people endpoints use, so the MCP REST endpoints (``routers/mcp.py``) and the
SSE dispatch (``routers/mcp_sse.py``) share one implementation and cannot drift.
This lets an assistant curate the people Omi has identified from the user's
conversations (rename a mislabeled speaker, register a known contact, remove a
duplicate) for the two-way memory bank (issue #4862).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import database.users as users_db
from utils.other.storage import delete_user_person_speech_samples

logger = logging.getLogger(__name__)


class PersonError(Exception):
    """Base error for people operations."""


class PersonNotFound(PersonError):
    """The person does not exist."""


class InvalidPersonRequest(PersonError):
    """The request is missing or has invalid fields."""


def _require_str(value, field: str) -> str:
    """The SSE transport forwards raw JSON arguments, so validate types here rather
    than let a non-string reach ``.strip()`` or Firestore and raise an uncaught error."""
    if not isinstance(value, str):
        raise InvalidPersonRequest(f"{field} must be a string")
    return value


def get_person(uid: str, person_id: str) -> dict:
    person_id = _require_str(person_id, "person_id")
    person = users_db.get_person(uid, person_id)
    if not person:
        raise PersonNotFound("Person not found")
    return person


def find_person_by_name(uid: str, name: str) -> Optional[dict]:
    """Return the person with this exact name, or None when there is no match."""
    name = _require_str(name, "name").strip()
    if not name:
        raise InvalidPersonRequest("name is required")
    return users_db.get_person_by_name(uid, name)


def create_person(uid: str, name: str) -> dict:
    name = _require_str(name, "name").strip()
    if not name:
        raise InvalidPersonRequest("Person name is required")
    # Idempotent by name, matching the REST people endpoint, so an assistant
    # cannot create duplicates of a person Omi already knows.
    existing = users_db.get_person_by_name(uid, name)
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    person_data = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": now,
        "updated_at": now,
    }
    return users_db.create_person(uid, person_data)


def update_person(uid: str, person_id: str, name: str) -> dict:
    person_id = _require_str(person_id, "person_id")
    name = _require_str(name, "name").strip()
    if not name:
        raise InvalidPersonRequest("Person name cannot be empty")
    if not users_db.get_person(uid, person_id):
        raise PersonNotFound("Person not found")
    users_db.update_person(uid, person_id, name)
    return users_db.get_person(uid, person_id)


def delete_person(uid: str, person_id: str) -> None:
    person_id = _require_str(person_id, "person_id")
    if not users_db.get_person(uid, person_id):
        raise PersonNotFound("Person not found")
    users_db.delete_person(uid, person_id)
    # Mirror the REST people endpoint and clean up the person's GCS speech-sample
    # blobs so deleting via MCP does not orphan storage. Best-effort: the person
    # doc is already gone, so a storage hiccup must not fail the delete.
    try:
        delete_user_person_speech_samples(uid, person_id)
    except Exception:
        logger.warning("delete_person: speech-sample cleanup failed for uid=%s person_id=%s", uid, person_id)
