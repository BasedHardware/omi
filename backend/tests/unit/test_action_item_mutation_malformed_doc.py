"""The action-item PATCH routes must not write to a stored item they cannot return, then 500.

Until #19535, `PATCH /v1/action-items/{id}` accepted `{"description": null}` and stored it. An
item whose `description` is null (or missing) fails `ActionItemResponse` validation, so the lists
skip it. The two mutation routes still wrote to it and only then built `ActionItemResponse(**item)`:

  * `PATCH /v1/action-items/{id}` persisted the update, then returned HTTP 500;
  * `PATCH /v1/action-items/{id}/completed` persisted the toggle, then returned HTTP 500 (for a
    shared task with a null description, `len(None)` in the sender notification raised first).

Both routes now check the item as the mutation would leave it, before writing. If it still could
not be served, they answer 404 "Action item not found" and write nothing. A PATCH that supplies a
description repairs the item and returns 200, as before.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.action_items import prepare_action_item_for_read
from routers import action_items as action_items_router
from utils.other import endpoints as auth

VALID_ITEM = {
    'id': 'a1',
    'description': 'Send the deck',
    'completed': False,
    'shared_from': {'sender_uid': 'sender'},
}

MALFORMED_ITEMS = {
    'null_description': {**VALID_ITEM, 'description': None},
    'missing_description': {key: value for key, value in VALID_ITEM.items() if key != 'description'},
}

MUTATIONS = {
    'update': ('/v1/action-items/a1', {'completed': True}),
    'toggle_completion': ('/v1/action-items/a1/completed?completed=true', None),
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(action_items_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'owner'
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def notifications(monkeypatch):
    sent = []
    for name in ('upsert_action_item_vector', 'sync_action_item_reminder', 'record_product_event'):
        monkeypatch.setattr(action_items_router, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(action_items_router, '_wake_task_changes', lambda *args, **kwargs: None)
    monkeypatch.setattr(action_items_router, 'get_user_display_name', lambda uid: 'Owner')
    monkeypatch.setattr(action_items_router, 'send_notification', lambda *args: sent.append(args))
    return sent


def _fake_store(monkeypatch, doc):
    """Serve `doc` as action_items_db does and apply updates on top of it. Returns the stored versions."""
    versions = [dict(doc)]
    db = action_items_router.action_items_db

    def update(uid, item_id, data):
        versions.append({**versions[-1], **db._prepare_action_item_for_write(data, partial=True)})
        return True

    monkeypatch.setattr(db, 'get_action_item', lambda uid, item_id: prepare_action_item_for_read(dict(versions[-1])))
    monkeypatch.setattr(db, 'update_action_item', update)
    return versions


@pytest.mark.parametrize('path, body', MUTATIONS.values(), ids=MUTATIONS.keys())
@pytest.mark.parametrize('doc', MALFORMED_ITEMS.values(), ids=MALFORMED_ITEMS.keys())
def test_a_mutation_leaving_the_item_malformed_is_not_found_and_not_written(
    client, monkeypatch, notifications, doc, path, body
):
    versions = _fake_store(monkeypatch, doc)

    response = client.patch(path, json=body)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Action item not found'}
    assert versions == [doc]
    assert notifications == []


def test_a_patch_supplying_the_description_repairs_the_item(client, monkeypatch, notifications):
    versions = _fake_store(monkeypatch, MALFORMED_ITEMS['null_description'])

    response = client.patch('/v1/action-items/a1', json={'description': 'Fixed'})

    assert response.status_code == 200
    assert response.json()['description'] == 'Fixed'
    assert len(versions) == 2


def test_completing_a_valid_shared_item_still_writes_and_notifies_the_sender(client, monkeypatch, notifications):
    versions = _fake_store(monkeypatch, VALID_ITEM)

    response = client.patch('/v1/action-items/a1/completed?completed=true')

    assert response.status_code == 200
    assert response.json()['completed'] is True
    assert len(versions) == 2
    assert notifications == [('sender', 'Task completed', 'Owner completed: Send the deck')]
