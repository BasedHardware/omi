"""The neutral db_client facade (ADR-0044) must present a Firestore-Client shape over the store port,
so upstream code that threads ``db_client`` runs unchanged on-prem. These cover the non-transactional
surface — document/collection reads & writes, FieldFilter/order_by/limit query translation, google
sentinel -> neutral sentinel translation, and batches — against the neutral FakeDocumentStore. The
transactional path (open Mongo session) is exercised by the live contract check, not here."""

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database.store.firestore_facade import NeutralFirestoreClient
from tests.store_fakes import FakeDocumentStore


def _client() -> NeutralFirestoreClient:
    return NeutralFirestoreClient(FakeDocumentStore())


def test_document_set_get_roundtrip_and_id_path():
    c = _client()
    ref = c.document("users/u1/goals/g1")
    ref.set({"title": "ship", "rank": 2})
    assert ref.id == "g1"
    assert ref.path == "users/u1/goals/g1"
    snap = ref.get()
    assert snap.exists is True
    assert snap.to_dict() == {"title": "ship", "rank": 2}
    assert snap.get("title") == "ship"
    # missing doc
    assert c.document("users/u1/goals/none").get().exists is False


def test_update_with_google_delete_field_translates_to_neutral_delete():
    c = _client()
    ref = c.document("users/u1/state/s")
    ref.set({"keep": 1, "drop": 2})
    ref.update({"drop": firestore.DELETE_FIELD})
    assert ref.get().to_dict() == {"keep": 1}


def test_server_timestamp_and_array_union_translate():
    c = _client()
    ref = c.document("users/u1/state/s")
    ref.set({"tags": firestore.ArrayUnion(["a"]), "at": firestore.SERVER_TIMESTAMP})
    data = ref.get().to_dict()
    assert data["tags"] == ["a"]
    assert data["at"] is not None  # resolved to a concrete timestamp by the store


def test_collection_where_fieldfilter_order_limit():
    c = _client()
    for i, status in enumerate(["focused", "background", "focused"]):
        c.document(f"users/u1/goals/g{i}").set({"status": status, "rank": i})
    focused = list(
        c.collection("users/u1/goals").where(filter=FieldFilter("status", "==", "focused")).order_by("rank").stream()
    )
    assert [s.id for s in focused] == ["g0", "g2"]
    limited = list(c.collection("users/u1/goals").limit(1).stream())
    assert len(limited) == 1
    # snapshots carry a working reference back to the doc
    assert focused[0].reference.path == "users/u1/goals/g0"


def test_unsupported_operator_fails_loud():
    c = _client()
    import pytest

    with pytest.raises(NotImplementedError):
        list(c.collection("users/u1/goals").where("x", "STARTS_WITH", "y").stream())


def test_batch_set_and_delete():
    c = _client()
    c.document("users/u1/goals/keep").set({"v": 1})
    c.document("users/u1/goals/gone").set({"v": 2})
    batch = c.batch()
    batch.set(c.document("users/u1/goals/added"), {"v": 3})
    batch.delete(c.document("users/u1/goals/gone"))
    batch.commit()
    ids = {s.id for s in c.collection("users/u1/goals").stream()}
    assert ids == {"keep", "added"}


def test_get_all_returns_snapshots_in_order():
    c = _client()
    c.document("users/u1/goals/a").set({"v": 1})
    c.document("users/u1/goals/b").set({"v": 2})
    refs = [c.document("users/u1/goals/a"), c.document("users/u1/goals/missing"), c.document("users/u1/goals/b")]
    snaps = list(c.get_all(refs))
    assert [s.exists for s in snaps] == [True, False, True]
    assert snaps[0].to_dict() == {"v": 1}
