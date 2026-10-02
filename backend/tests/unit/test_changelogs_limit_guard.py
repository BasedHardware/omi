"""`/v1/announcements/changelogs` must reject non-positive limits instead of slicing the wrong set.

`limit: int = Query(5, ...)` had no lower bound and the data layer does `changelogs[:limit]`.
Python's negative slicing returned all-but-the-last changelog for `?limit=-1` (wrong data under a
"maximum number" contract) and an empty page for `limit=0`.

The guard lives in the handler rather than `Query(ge=1)`: adding a `minimum` bound to a published
parameter is a breaking change for the released app-client contract, while rejecting non-positive
values only affects invalid requests. The data layer also clamps for any non-HTTP caller.

Invalid-limit requests never reach the Firestore read, so these tests touch no database.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

import database.announcements as ann_db
from routers.announcements import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_negative_limit_is_rejected():
    response = _client().get("/v1/announcements/changelogs?limit=-1")

    assert response.status_code == 422


def test_limit_guard_stays_out_of_the_published_schema():
    # A Query(ge=...) bound would be a breaking change for released clients; the guard must
    # stay in the handler so the public contract is unchanged.
    schema = _client().app.openapi()
    params = schema["paths"]["/v1/announcements/changelogs"]["get"]["parameters"]
    limit = next(p for p in params if p["name"] == "limit")

    assert "minimum" not in (limit.get("schema") or {})


def test_zero_limit_is_rejected():
    response = _client().get("/v1/announcements/changelogs?limit=0")

    assert response.status_code == 422


class _Query:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return self

    def stream(self):
        return iter(self._docs)


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return _Query(self._docs)


class _DB:
    def __init__(self, docs):
        self._docs = docs

    def collection(self, name):
        return _Collection(self._docs)


def test_negative_limit_is_clamped_at_the_data_layer(monkeypatch):
    docs = [
        SimpleNamespace(to_dict=lambda v=v: {'type': 'changelog', 'active': True, 'app_version': v})
        for v in ('1.0.0', '1.1.0', '1.2.0')
    ]
    monkeypatch.setattr(ann_db, 'db', _DB(docs))

    assert ann_db.get_recent_changelogs(limit=-1) == []
    assert len(ann_db.get_recent_changelogs(limit=2)) == 2
