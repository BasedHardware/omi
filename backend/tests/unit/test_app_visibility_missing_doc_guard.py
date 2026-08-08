"""update_app_visibility_in_db must not crash when the private app document is missing.

Making a private app public deletes the `*-private` document and recreates it under a new public id.
It read the source document and immediately did `app['id'] = ...`. When the document does not exist
the read returns no data, so that line raised
`TypeError: 'NoneType' object does not support item assignment` -> a 500. The change-visibility
endpoint checks the app exists first, but that check can read a stale cache while this function does
a direct store read, so the document can be gone here (deleted, or a delete-race). The function now
skips the delete-and-recreate when the document is missing. These cover the pure getter behavior.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest  # noqa: E402

import database.apps as apps  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(apps, "_store", lambda: fake)
    return fake


def _app_ids(store):
    return {p.split("/")[-1] for p in store._docs if p.startswith(f"{apps.apps_collection}/")}


def test_missing_private_doc_skips_delete_and_recreate(store):
    # The document does not exist; the function must return without creating or recreating anything
    # instead of raising TypeError.
    result = apps.update_app_visibility_in_db("plug-private", private=False)

    assert result is None
    assert _app_ids(store) == set()  # nothing republished


def test_present_private_doc_is_republished_public(store):
    # Happy path is unchanged: an existing private app is deleted and recreated as a public app.
    store.set(f"{apps.apps_collection}/plug-private", {"name": "My App", "private": True})

    apps.update_app_visibility_in_db("plug-private", private=False)

    assert not store.exists(f"{apps.apps_collection}/plug-private")  # old private doc deleted
    new_ids = _app_ids(store)
    assert len(new_ids) == 1
    new_id = next(iter(new_ids))
    assert new_id.startswith("plug-")
    saved = store.get(f"{apps.apps_collection}/{new_id}").to_dict()
    assert saved["private"] is False
    assert saved["id"] == new_id


def test_non_private_path_updates_flag(store):
    # The simple toggle path (no private->public republish) just updates the flag in place.
    store.set(f"{apps.apps_collection}/plug", {"name": "X"})

    apps.update_app_visibility_in_db("plug", private=True)

    saved = store.get(f"{apps.apps_collection}/plug").to_dict()
    assert saved["private"] is True
    assert saved["name"] == "X"
