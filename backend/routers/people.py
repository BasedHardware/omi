"""People preferences that sit beside the /v1/users/people CRUD in routers/users.py."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from database import people as people_db
from models.other import Person
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


def _clean_id(raw: Any) -> str:
    """Return stripped string or empty string if None."""
    if not raw or not isinstance(raw, str):
        return ""
    return raw.strip()


@router.patch('/v1/users/people/{person_id}/pinned', tags=['v1'], response_model=Person)
def set_person_pinned(person_id: str, value: bool, uid: str = Depends(auth.get_current_user_uid)):
    """Pin (keep, and expect in conversations) or unpin a person. Returns the updated person."""
    clean_person_id = _clean_id(person_id)
    if not clean_person_id or len(clean_person_id) > 256:
        raise HTTPException(status_code=400, detail='Invalid person ID')

    try:
        person = people_db.set_person_pinned(uid, clean_person_id, value)
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning('Invalid person ID for pin: %s', sanitize(exc))
        raise HTTPException(status_code=400, detail='Invalid person ID') from exc
    except LookupError as exc:
        logger.warning('Person not found for pin: %s', sanitize(exc))
        raise HTTPException(status_code=404, detail='Person not found') from exc
    except Exception as exc:
        logger.error(f'Failed to update pin status for person {clean_person_id}: {sanitize(exc)}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to update person pin status') from exc

    if person is None:
        raise HTTPException(status_code=404, detail='Person not found')

    try:
        people = Person.deserialize_many_safe([person])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f'Failed to deserialize person {clean_person_id}: {sanitize(exc)}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to update person pin status') from exc

    if not people:
        raise HTTPException(status_code=404, detail='Person not found')

    return people[0]
