"""People preferences that sit beside the /v1/users/people CRUD in routers/users.py."""

from fastapi import APIRouter, Depends, HTTPException

from database import people as people_db
from models.other import Person
from utils.other import endpoints as auth

router = APIRouter()


@router.patch('/v1/users/people/{person_id}/pinned', tags=['v1'], response_model=Person)
def set_person_pinned(person_id: str, value: bool, uid: str = Depends(auth.get_current_user_uid)):
    """Pin (keep, and expect in conversations) or unpin a person. Returns the updated person."""
    person = people_db.set_person_pinned(uid, person_id, value)
    if person is None:
        raise HTTPException(status_code=404, detail='Person not found')
    people = Person.deserialize_many_safe([person])
    if not people:
        raise HTTPException(status_code=404, detail='Person not found')
    return people[0]
