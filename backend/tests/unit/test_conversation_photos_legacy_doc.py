"""A conversation photo doc without ``base64`` must not 500 the conversation reads that carry it.

``ConversationPhoto.base64`` is a required ``str``. ``database.conversations.get_conversation_photos``
returned the stored photo dicts as-is, both to ``GET /v1/conversations/{id}/photos``
(``response_model=List[ConversationPhoto]``) and, through ``@with_photos``, to every conversation
read such as ``GET /v1/conversations/{id}`` (``response_model=Conversation``). A photo doc without
``base64`` (the pre-marker ``legacy-only-photo`` shape ``scripts/listen_lifecycle_emulator_test.py``
seeds) failed response validation, so opening the conversation, or listing its photos, came back
as HTTP 500.

Such a doc carries no inline pixels, which the model already expresses with ``base64=''`` (the value
stored for GCS-backed frame evidence). The photo read now serves it that way: the photo keeps its
place with its id and description, well-formed photos are unchanged, and every heal is logged by
document path and field name and counted through ``record_fallback`` so the record stays visible.
"""

import logging
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.conversations as conversations_db
import routers.conversations as conversations_router
from utils.other import endpoints as auth

UID = 'photos-user'
CONVERSATION_ID = 'photos-conversation'
CONVERSATION_PATH = f'users/{UID}/conversations/{CONVERSATION_ID}'
DETAIL_PATH = '/v1/conversations/{conversation_id}'
PHOTOS_PATH = '/v1/conversations/{conversation_id}/photos'

CONVERSATION = {
    'id': CONVERSATION_ID,
    'created_at': datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    'started_at': None,
    'finished_at': None,
    'structured': {'title': 'photo walk'},
}
GOOD_PHOTO = {
    'id': 'inline-photo',
    'base64': 'aGVsbG8=',
    'description': 'whiteboard',
    'created_at': '2026-01-01T10:00:00+00:00',
    'discarded': False,
    'data_protection_level': 'standard',
}
LEGACY_DESCRIPTION = 'pre-marker photo-only listen conversation'
LEGACY_PHOTO = {'id': 'legacy-only-photo', 'description': LEGACY_DESCRIPTION}
LEGACY_PHOTO_PATH = f'{CONVERSATION_PATH}/photos/legacy-only-photo'
HEAL_LOG = f'path={LEGACY_PHOTO_PATH} field=base64'
HEAL_EVENT = 'component=firestore_read from=firestore_document to=empty_photo_base64 reason=malformed_doc'


class _Snapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.exists = data is not None
        self.update_time = None
        self._data = data

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Ref:
    """Path-addressed Firestore fake: ``get`` reads one doc, ``stream`` its direct children."""

    def __init__(self, docs, path=''):
        self._docs = docs
        self.path = path

    def collection(self, name):
        return _Ref(self._docs, f'{self.path}/{name}' if self.path else name)

    def document(self, name):
        return _Ref(self._docs, f'{self.path}/{name}')

    def get(self):
        return _Snapshot(self, self._docs.get(self.path))

    def stream(self):
        children = (path for path in self._docs if path.rsplit('/', 1)[0] == self.path)
        return [_Snapshot(_Ref(self._docs, path), self._docs[path]) for path in children]


def _client(monkeypatch, photo_docs) -> TestClient:
    docs = {CONVERSATION_PATH: CONVERSATION}
    docs.update({f'{CONVERSATION_PATH}/photos/{doc["id"]}': doc for doc in photo_docs})
    monkeypatch.setattr(conversations_db, 'db', _Ref(docs))
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    # The photos uid dependency is a with_rate_limit closure; override it the same way.
    photos_route = next(route for route in app.routes if getattr(route, 'path', None) == PHOTOS_PATH)
    (uid_dependency,) = photos_route.dependant.dependencies
    app.dependency_overrides[uid_dependency.call] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


def _get(client: TestClient, path: str):
    return client.get(path.format(conversation_id=CONVERSATION_ID))


def _warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


def test_opening_a_conversation_with_a_photo_without_base64_does_not_500(monkeypatch):
    response = _get(_client(monkeypatch, [GOOD_PHOTO, LEGACY_PHOTO]), DETAIL_PATH)

    assert response.status_code == 200
    photos = response.json()['photos']
    assert [(photo['id'], photo['base64']) for photo in photos] == [
        ('inline-photo', 'aGVsbG8='),
        ('legacy-only-photo', ''),
    ]
    assert photos[1]['description'] == LEGACY_DESCRIPTION


def test_listing_photos_with_a_doc_without_base64_does_not_500(monkeypatch):
    response = _get(_client(monkeypatch, [GOOD_PHOTO, LEGACY_PHOTO]), PHOTOS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [(photo['id'], photo['base64']) for photo in body] == [
        ('inline-photo', 'aGVsbG8='),
        ('legacy-only-photo', ''),
    ]
    assert body[1]['description'] == LEGACY_DESCRIPTION


def test_a_healed_photo_is_logged_and_counted_without_its_content(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)

    # The detail route reads the photos once, so one read heals, logs and counts once.
    response = _get(_client(monkeypatch, [{**LEGACY_PHOTO, 'base64': None}]), DETAIL_PATH)

    assert response.status_code == 200
    assert [(photo['id'], photo['base64']) for photo in response.json()['photos']] == [('legacy-only-photo', '')]
    warnings = _warnings(caplog)
    assert sum(HEAL_LOG in message for message in warnings) == 1
    assert sum(HEAL_EVENT in message for message in warnings) == 1
    assert not any(LEGACY_DESCRIPTION in message for message in warnings)


@pytest.mark.parametrize('photo', [GOOD_PHOTO, {**LEGACY_PHOTO, 'base64': ''}], ids=['inline', 'empty-base64'])
def test_well_formed_photos_are_served_unchanged_and_not_counted(monkeypatch, caplog, photo):
    caplog.set_level(logging.WARNING)

    response = _get(_client(monkeypatch, [photo]), PHOTOS_PATH)

    assert response.status_code == 200
    (served,) = response.json()
    assert (served['id'], served['base64'], served['description']) == (
        photo['id'],
        photo['base64'],
        photo['description'],
    )
    assert not any('empty_photo_base64' in message or 'field=base64' in message for message in _warnings(caplog))
