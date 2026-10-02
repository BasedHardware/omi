```python
from fastapi import APIRouter, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from typing import Annotated
from pydantic import BaseModel
from ..models import Person
from ..db.people_db import people_db

router = APIRouter()

class Person(BaseModel):
    person_id: str

@router.patch("/v1/users/people/{person_id}/pinned")
async def update_pinned(person: Annotated[Person, Person]):
    try:
        person_id = person.person_id.strip()
        if not person_id:
            return JSONResponse(content={"error": "person_id is required"}, status_code=status.HTTP_400_BAD_REQUEST)
        
        try:
            person_db = people_db()
            person_db.set_person_pinned(person_id, person.pinned)
            return JSONResponse(content={"message": "Pinned status updated successfully"}, status_code=status.HTTP_200_OK)
        except (ValueError, LookupError) as e:
            return JSONResponse(content={"error": str(e)}, status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return JSONResponse(content={"error": "Internal server error"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

def test_update_pinned_success():
    person = Person(person_id="123", pinned=True)
    response = update_pinned(person)
    assert response.status_code == 200
    assert response.json() == {"message": "Pinned status updated successfully"}

def test_update_pinned_whitespace_person_id():
    person = Person(person_id=" 123 ")
    response = update_pinned(person)
    assert response.status_code == 200
    assert response.json() == {"message": "Pinned status updated successfully"}

def test_update_pinned_empty_person_id():
    person = Person(person_id="")
    response = update_pinned(person)
    assert response.status_code == 400
    assert response.json() == {"error": "person_id is required"}

def test_update_pinned_error():
    person = Person(person_id="test_id")
    response = update_pinned(person)
    assert response.status_code == 500
    assert "error" in response.json()

def test_update_pinned_deserialization_error():
    person = Person(person_id="test_id", pinned="invalid")
    response = update_pinned(person)
    assert response.status_code == 400
    assert "error" in response.json()
```