"""Dual-backend contract for the app marketplace reads (ADR-0044 facade + ADR-0002 store port).

This surface had NO contract coverage, which is why an untranslated composite filter could 500 every
marketplace query under STORAGE_BACKEND=mongo while every suite stayed green: `database/apps.py`
expresses each multi-condition read as `where(filter=BaseCompositeFilter('AND', [...]))` (19 call
sites), a shape the facade did not translate, and neither the unit suites (which stub the filter) nor
the live E2E (which never calls /v1/apps) touched it. Reviving the users/conversations contracts was
necessary but not sufficient: neither of those modules uses a composite filter.

Runs the real chain — apps.py -> facade -> adapter -> live backend — against a Firestore emulator and
a real Mongo replica set, and asserts identical results. Skips per-backend when the service env is
absent, like the sibling contract suites.
"""

from __future__ import annotations

import os
import uuid

import pytest

from tests.store_fakes import install_fake_db_client


@pytest.fixture(params=["firestore", "mongo"])
def bind_store(request, monkeypatch):
    backend = request.param
    if backend == "firestore":
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from google.cloud import firestore as _fs

        from database.store.adapters.firestore import FirestoreDocumentStore

        # Explicit client: the adapter's default is the lazy ``db`` handle, which resolves through the
        # accessor this fixture then points at the facade -> the facade would wrap a store that asks
        # the facade for its client (RecursionError on the first read).
        store = FirestoreDocumentStore(
            client=_fs.Client(project=os.environ.get("FIREBASE_PROJECT_ID", "demo-omi-local"))
        )
    else:
        uri = os.environ.get("MONGO_URI")
        if not uri:
            pytest.skip("MONGO_URI not set")
        from database.store.adapters.mongo import MongoDocumentStore

        store = MongoDocumentStore(uri=uri, db_name="omi_contract")
    install_fake_db_client(monkeypatch, store=store)
    return store


@pytest.fixture
def seeded(bind_store):
    """One app per visibility combination, under ids unique to this run."""
    import database.apps as apps_db

    run = uuid.uuid4().hex[:8]
    ids = {
        "public_approved": f"pub-ok-{run}",
        "public_unapproved": f"pub-no-{run}",
        "private": f"priv-{run}",
    }
    owner = f"owner-{run}"
    rows = {
        ids["public_approved"]: {"approved": True, "private": False, "uid": owner},
        ids["public_unapproved"]: {"approved": False, "private": False, "uid": owner},
        ids["private"]: {"approved": True, "private": True, "uid": owner},
    }
    for app_id, row in rows.items():
        payload = dict(row)
        payload["id"] = app_id
        payload["external_integration"] = {"triggers_on": "audio_bytes"}
        bind_store.set(f"plugins_data/{app_id}", payload)
    yield apps_db, ids, owner
    for app_id in ids.values():
        bind_store.delete(f"plugins_data/{app_id}")


def test_public_approved_apps_uses_a_composite_filter(seeded):
    apps_db, ids, _owner = seeded
    found = {app["id"] for app in apps_db.get_public_approved_apps_db()}
    assert ids["public_approved"] in found
    assert ids["public_unapproved"] not in found
    assert ids["private"] not in found


def test_private_apps_are_scoped_to_their_owner(seeded):
    apps_db, ids, owner = seeded
    found = {app["id"] for app in apps_db.get_private_apps_db(owner)}
    assert found & set(ids.values()) == {ids["private"]}
    assert apps_db.get_private_apps_db("someone-else") == [] or ids["private"] not in {
        app["id"] for app in apps_db.get_private_apps_db("someone-else")
    }


def test_audio_apps_count_combines_an_in_filter_with_an_equality(seeded):
    """`in` + `==` inside one composite — the count path, which also exercises aggregation."""
    apps_db, ids, _owner = seeded
    assert apps_db.get_audio_apps_count([ids["public_approved"], ids["private"]]) == 2
    assert apps_db.get_audio_apps_count([]) == 0


def test_unapproved_public_apps_is_the_complement(seeded):
    apps_db, ids, _owner = seeded
    found = {app["id"] for app in apps_db.get_unapproved_public_apps_db()}
    assert ids["public_unapproved"] in found
    assert ids["public_approved"] not in found
