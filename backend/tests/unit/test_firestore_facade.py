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


def test_no_id_document_and_add_get_unique_random_ids():
    # Cubic PR 10887 A1/A4: a no-id document()/add() must generate a RANDOM id (else every call
    # collides and overwrites); add() returns Firestore's (write_time, DocumentReference).
    c = _client()
    col = c.collection("users/u1/fair_use_events")
    ids = {col.document().id for _ in range(50)}
    assert len(ids) == 50  # all distinct
    write_time, ref = col.add({"n": 1})
    assert isinstance(ref.id, str) and len(ref.id) == 20
    assert col.add({"n": 2})[1].id != ref.id  # a second add creates a new doc, not an overwrite
    assert ref.get().to_dict() == {"n": 1}


def test_count_over_filters():
    c = _client()
    for i, s in enumerate(["a", "b", "a"]):
        c.document(f"users/u1/goals/g{i}").set({"status": s})
    assert c.collection("users/u1/goals").count() == 3
    assert c.collection("users/u1/goals").where(filter=FieldFilter("status", "==", "a")).count() == 2


def test_collections_enumerates_subcollections_for_recursive_delete():
    # Cubic PR 10887 A2: collections() must expose real subcollections so account/conversation
    # deletion descends into them instead of orphaning descendant data.
    c = _client()
    c.document("users/u1").set({"name": "x"})
    c.document("users/u1/conversations/c1").set({"t": 1})
    c.document("users/u1/memories/m1").set({"t": 2})
    subs = {ref.id for ref in c.document("users/u1").collections()}
    assert subs == {"conversations", "memories"}


def test_start_after_advances_pagination():
    # Cubic PR 10887 A5: _Query must forward start_after or paginated reads loop / duplicate page one.
    c = _client()
    for i in range(5):
        c.document(f"users/u1/goals/g{i}").set({"rank": i})
    first_two = list(c.collection("users/u1/goals").order_by("rank").limit(2).stream())
    assert [s.id for s in first_two] == ["g0", "g1"]
    after = c.collection("users/u1/goals").order_by("rank").start_after(first_two[-1]).limit(2)
    assert [s.id for s in after.stream()] == ["g2", "g3"]  # advances, does not repeat


def test_group_query_supports_order_by_and_start_after():
    c = _client()
    c.document("users/u1/events/e1").set({"ts": 1})
    c.document("users/u2/events/e2").set({"ts": 2})
    q = c.collection_group("events").order_by("ts")
    ids = {s.id for s in q.stream()}
    assert ids == {"e1", "e2"}  # cross-parent sweep with order_by + start_after wired (no crash)
    assert list(q.start_after("users/u1/events/e1").stream())  # start_after accepted
