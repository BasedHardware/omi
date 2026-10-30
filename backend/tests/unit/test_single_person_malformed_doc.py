"""A malformed stored person doc must 404 on the single fetch, not 500.

The people list endpoint was hardened with `Person.deserialize_many_safe` (#8264), but
`GET /v1/users/people/{person_id}` kept a raw `Person(**person)` build: a legacy row missing the
required `name` (the same fixture as `test_person_deserialize_many_safe.py`) raised
`ValidationError`, so the mobile person detail view 500s for that user until the doc is repaired.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest
from fastapi import HTTPException

import routers.users as users_router

# Missing the required 'name' field -> Person(**record) raises ValidationError.
_MALFORMED = {'id': 'p3'}


def test_malformed_person_doc_reads_as_not_found(monkeypatch):
    monkeypatch.setattr(users_router, 'get_person', lambda uid, person_id: dict(_MALFORMED))

    with pytest.raises(HTTPException) as exc_info:
        users_router.get_single_person('p3', uid='u1')

    assert exc_info.value.status_code == 404


def test_valid_person_is_returned(monkeypatch):
    monkeypatch.setattr(users_router, 'get_person', lambda uid, person_id: {'id': 'p1', 'name': 'Alex'})

    person = users_router.get_single_person('p1', uid='u1')

    assert person.id == 'p1'
    assert person.name == 'Alex'
