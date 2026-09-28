"""GET /v1/conversations/{id}/photos must serve a photo doc that has no ``base64``.

The route declares ``response_model=List[ConversationPhoto]`` and ``ConversationPhoto.base64`` is a
required ``str``, but it returned the stored photo dicts as-is. A photo doc without ``base64`` (the
pre-marker ``legacy-only-photo`` shape ``scripts/listen_lifecycle_emulator_test.py`` seeds) failed
response validation, so the whole list came back as HTTP 500 and none of the conversation's photos
could be loaded.

Such a doc carries no inline pixels, which the model already expresses with ``base64=''`` (the value
stored for GCS-backed frame evidence). The route now reads it that way: the photo keeps its place
in the list with its id and description, and well-formed photos are returned unchanged.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.conversations as conversations_db
import routers.conversations as conversations_router

UID = 'photos-user'
CONVERSATION_ID = 'photos-conversation'
PHOTOS_PATH = '/v1/conversations/{conversation_id}/photos'

GOOD_PHOTO = {
    'id': 'inline-photo',
    'base64': 'aGVsbG8=',
    'description': 'whiteboard',
    'created_at': '2026-01-01T10:00:00+00:00',
    'discarded': False,
    'data_protection_level': 'standard',
}
LEGACY_PHOTO = {
    'id': 'legacy-only-photo',
    'description': 'pre-marker photo-only listen conversation',
    'created_at': '2026-01-01T10:01:00+00:00',
}


class _PhotosDB:
    """Serves the given docs from users/{uid}/conversations/{id}/photos."""

    def __init__(self, docs):
        self._docs = docs

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def stream(self):
        return [SimpleNamespace(to_dict=lambda doc=doc: dict(doc)) for doc in self._docs]


def _client(monkeypatch, photo_docs) -> TestClient:
    monkeypatch.setattr(conversations_db, 'db', _PhotosDB(photo_docs))
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid, **_kwargs: {'id': cid})
    app = FastAPI()
    app.include_router(conversations_router.router)
    # The uid dependency is a with_rate_limit closure; override it like the plain auth dependency.
    photos_route = next(route for route in app.routes if getattr(route, 'path', None) == PHOTOS_PATH)
    (uid_dependency,) = photos_route.dependant.dependencies
    app.dependency_overrides[uid_dependency.call] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


def _get_photos(client: TestClient):
    return client.get(PHOTOS_PATH.format(conversation_id=CONVERSATION_ID))


def test_a_photo_doc_without_base64_does_not_500_the_list(monkeypatch):
    response = _get_photos(_client(monkeypatch, [GOOD_PHOTO, LEGACY_PHOTO]))

    assert response.status_code == 200
    body = response.json()
    assert [photo['id'] for photo in body] == ['inline-photo', 'legacy-only-photo']
    assert body[0]['base64'] == 'aGVsbG8='
    assert body[1]['base64'] == ''
    assert body[1]['description'] == 'pre-marker photo-only listen conversation'


@pytest.mark.parametrize('stored_base64', [None, ''])
def test_a_null_or_empty_base64_is_served_as_empty(monkeypatch, stored_base64):
    response = _get_photos(_client(monkeypatch, [{**LEGACY_PHOTO, 'base64': stored_base64}]))

    assert response.status_code == 200
    assert [(photo['id'], photo['base64']) for photo in response.json()] == [('legacy-only-photo', '')]


def test_well_formed_photos_are_served_unchanged(monkeypatch):
    response = _get_photos(_client(monkeypatch, [GOOD_PHOTO]))

    assert response.status_code == 200
    assert response.json() == [
        {
            'id': 'inline-photo',
            'base64': 'aGVsbG8=',
            'storage_id': None,
            'content_type': None,
            'description': 'whiteboard',
            'created_at': '2026-01-01T10:00:00Z',
            'discarded': False,
            'data_protection_level': 'standard',
        }
    ]
