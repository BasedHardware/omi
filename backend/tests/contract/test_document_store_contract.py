"""Dual-backend contract test for the neutral storage port (WP2, ADR-0002/0004).

The SAME assertions run against BOTH adapters — the Firestore reference adapter (against the
Firestore emulator) and the Mongo adapter (against a real single-node replica set). Parity here is
the proof that ``database.store`` abstracts the backend rather than leaking one: a domain module
written to the port behaves identically whichever ``STORAGE_BACKEND`` is configured.

Live services required (both provided by the offline harness — see docs/BACKLOG.md §Handoff):
  * ``FIRESTORE_EMULATOR_HOST`` — the emulator (image ``omi-onprem-firestore-emulator``).
  * ``MONGO_URI`` — a Mongo replica set (image ``mongo``); transactions require the replica set.
A backend whose env is absent is skipped, so the file is safe to collect anywhere. It is NOT a
hermetic unit test (it needs live services) and is not run by ``backend/test.sh``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest

from database.store.errors import AlreadyExists, NotFound
from database.store.records import StoredDocument
from database.store.sentinels import DELETE, SERVER_TIMESTAMP, ArrayRemove, ArrayUnion, Increment


@pytest.fixture(params=["firestore", "mongo"])
def store(request):
    """Yield each configured adapter in turn; skip a backend whose service isn't wired."""
    backend = request.param
    if backend == "firestore":
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from database.store.adapters.firestore import FirestoreDocumentStore

        return FirestoreDocumentStore()
    uri = os.environ.get("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI not set")
    from database.store.adapters.mongo import MongoDocumentStore

    return MongoDocumentStore(uri=uri, db_name="omi_contract")


@pytest.fixture
def uid() -> str:
    """A unique user id so tests never collide within a shared backend."""
    return f"u_{uuid.uuid4().hex}"


# --- point ops ---------------------------------------------------------------


def test_get_missing_is_absent(store, uid):
    doc = store.get(f"users/{uid}")
    assert doc.exists is False
    assert doc.to_dict() is None
    assert doc.id == uid


def test_set_and_get_roundtrip(store, uid):
    payload = {"name": "Ada", "n": 3, "ratio": 1.5, "on": True, "tags": ["a", "b"], "nested": {"k": "v"}}
    store.set(f"users/{uid}", payload)
    doc = store.get(f"users/{uid}")
    assert doc.exists is True
    assert doc.id == uid
    assert doc.to_dict() == payload


def test_set_merge_writes_and_preserves(store, uid):
    store.set(f"users/{uid}", {"a": 1, "b": 2})
    store.set(f"users/{uid}", {"b": 20, "c": 3}, merge=True)
    data = store.get(f"users/{uid}").to_dict()
    assert data == {"a": 1, "b": 20, "c": 3}


def test_set_no_merge_replaces_whole_document(store, uid):
    store.set(f"users/{uid}", {"a": 1, "b": 2})
    store.set(f"users/{uid}", {"c": 3})
    assert store.get(f"users/{uid}").to_dict() == {"c": 3}


def test_exists(store, uid):
    assert store.exists(f"users/{uid}") is False
    store.set(f"users/{uid}", {"a": 1})
    assert store.exists(f"users/{uid}") is True


def test_delete(store, uid):
    store.set(f"users/{uid}", {"a": 1})
    store.delete(f"users/{uid}")
    assert store.exists(f"users/{uid}") is False


def test_get_projection(store, uid):
    store.set(f"users/{uid}", {"language": "en", "secret": "hidden", "n": 1})
    doc = store.get(f"users/{uid}", fields=["language"])
    data = doc.to_dict()
    assert data.get("language") == "en"
    assert "secret" not in data  # projection excludes unrequested fields


# --- update: dotted keys + neutral sentinels ---------------------------------


def test_update_dotted_key_merges_nested_map(store, uid):
    store.set(f"users/{uid}", {"prefs": {"lang": "en", "keep": "me"}})
    store.update(f"users/{uid}", {"prefs.lang": "it"})
    assert store.get(f"users/{uid}").to_dict()["prefs"] == {"lang": "it", "keep": "me"}


def test_update_delete_sentinel_removes_field(store, uid):
    store.set(f"users/{uid}", {"a": 1, "b": 2})
    store.update(f"users/{uid}", {"b": DELETE})
    assert store.get(f"users/{uid}").to_dict() == {"a": 1}


def test_update_missing_raises_not_found(store, uid):
    # update() requires an existing document (unlike set(), which upserts). Every backend must raise
    # the neutral NotFound rather than silently no-op — otherwise a caller that updates a
    # concurrently-deleted doc "succeeds" on one backend and fails on another.
    with pytest.raises(NotFound):
        store.update(f"users/{uid}", {"a": 1})


def test_update_increment_sentinel(store, uid):
    store.set(f"users/{uid}", {"count": 10})
    store.update(f"users/{uid}", {"count": Increment(5)})
    assert store.get(f"users/{uid}").to_dict()["count"] == 15


def test_update_array_union_and_remove(store, uid):
    store.set(f"users/{uid}", {"tags": ["a"]})
    store.update(f"users/{uid}", {"tags": ArrayUnion(["a", "b"])})  # "a" already present -> not duplicated
    assert sorted(store.get(f"users/{uid}").to_dict()["tags"]) == ["a", "b"]
    store.update(f"users/{uid}", {"tags": ArrayRemove(["a"])})
    assert store.get(f"users/{uid}").to_dict()["tags"] == ["b"]


def test_update_server_timestamp_sets_a_datetime(store, uid):
    store.set(f"users/{uid}", {"a": 1})
    store.update(f"users/{uid}", {"touched_at": SERVER_TIMESTAMP})
    assert isinstance(store.get(f"users/{uid}").to_dict()["touched_at"], datetime)


# --- collection ops ----------------------------------------------------------


def test_query_equality_order_and_limit(store, uid):
    base = f"users/{uid}/people"
    store.set(f"{base}/p1", {"name": "p1", "team": "x", "rank": 3})
    store.set(f"{base}/p2", {"name": "p2", "team": "x", "rank": 1})
    store.set(f"{base}/p3", {"name": "p3", "team": "y", "rank": 2})

    team_x = store.query(base, filters=[("team", "==", "x")])
    assert {d.id for d in team_x} == {"p1", "p2"}

    ordered = store.query(base, order_by="rank", direction="asc")
    assert [d.id for d in ordered] == ["p2", "p3", "p1"]

    limited = store.query(base, order_by="rank", direction="asc", limit=1)
    assert [d.id for d in limited] == ["p2"]


def test_query_multi_field_order_by(store, uid):
    base = f"users/{uid}/people"
    # Same score for a,b (b created later); c lower score. Primary scoring desc, secondary created_at desc.
    store.set(f"{base}/a", {"score": 5, "created_at": 100})
    store.set(f"{base}/b", {"score": 5, "created_at": 200})
    store.set(f"{base}/c", {"score": 9, "created_at": 50})

    ordered = store.query(base, order_by=[("score", "desc"), ("created_at", "desc")])
    assert [d.id for d in ordered] == ["c", "b", "a"]


def test_query_group_spans_parents(store, uid):
    # collection-group: the same leaf collection under different parents, plus a different leaf excluded.
    store.set(f"users/{uid}/widgets/w1", {"kind": "a"})
    store.set(f"users/{uid}-other/widgets/w2", {"kind": "a"})
    store.set(f"users/{uid}/gadgets/g1", {"kind": "a"})  # different leaf → excluded

    hits = store.query_group("widgets", filters=[("kind", "==", "a")])
    assert {d.id for d in hits} == {"w1", "w2"}
    # results carry the full logical path so the caller can recover the parent (uid)
    assert {d.path for d in hits} == {f"users/{uid}/widgets/w1", f"users/{uid}-other/widgets/w2"}


def test_query_group_start_after_keyset(store, uid):
    # document-name keyset over a collection-group: ordered by full logical path ascending,
    # resume strictly after the cursor path — the portable form of a Firestore __name__ cursor.
    # Uses a kind marker unique to this test so the cross-parent query isolates its own docs.
    for n in ("w1", "w2", "w3"):
        store.set(f"users/{uid}/widgets/{n}", {"kind": "ks"})
    mine = [f"users/{uid}/widgets/{n}" for n in ("w1", "w2", "w3")]

    paths = sorted(d.path for d in store.query_group("widgets", filters=[("kind", "==", "ks")]))
    assert paths == mine

    after_first = store.query_group("widgets", filters=[("kind", "==", "ks")], start_after=mine[0])
    assert [d.path for d in after_first] == mine[1:]

    page = store.query_group("widgets", filters=[("kind", "==", "ks")], start_after=mine[0], limit=1)
    assert [d.path for d in page] == [mine[1]]


def test_query_array_contains(store, uid):
    base = f"users/{uid}/people"
    store.set(f"{base}/p1", {"name": "p1", "tags": ["persona", "audio"]})
    store.set(f"{base}/p2", {"name": "p2", "tags": ["chat"]})
    store.set(f"{base}/p3", {"name": "p3", "tags": ["persona"]})

    hits = store.query(base, filters=[("tags", "array_contains", "persona")])
    assert {d.id for d in hits} == {"p1", "p3"}
    assert store.count(base, filters=[("tags", "array_contains", "persona")]) == 2


def test_query_offset_and_count(store, uid):
    base = f"users/{uid}/people"
    for i in range(5):
        store.set(f"{base}/p{i}", {"name": f"p{i}", "n": i})
    assert store.count(base) == 5
    assert store.count(base, filters=[("n", ">=", 3)]) == 2
    page = store.query(base, order_by="n", direction="asc", offset=1, limit=2)
    assert [d.to_dict()["n"] for d in page] == [1, 2]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_query_keyset_start_after_is_tie_safe(store, uid, direction):
    base = f"users/{uid}/people"
    # All share the same order_by value (a tie) so only the id tiebreak keeps paging correct.
    for pid in ("p1", "p2", "p3", "p4", "p5"):
        store.set(f"{base}/{pid}", {"rank": 7, "name": pid})

    seen = []
    cursor = None
    for _ in range(10):  # bounded; a broken keyset would loop or skip
        page = store.query(base, order_by="rank", direction=direction, limit=2, start_after=cursor)
        if not page:
            break
        seen.extend(d.id for d in page)
        last = page[-1]
        cursor = {"value": last.to_dict()["rank"], "id": last.id}

    assert sorted(seen) == ["p1", "p2", "p3", "p4", "p5"]  # every row visited
    assert len(seen) == len(set(seen))  # none duplicated across pages


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_query_explicit_name_tiebreak_pages_consistently(store, uid, direction):
    # The canonical-graph read pattern: an explicit ``__name__`` (document id) tiebreak field so the
    # FIRST page shares the paginated pages' total order. Firestore's implicit __name__ is ASC only,
    # so the adapter must honour the explicit id order (and not double it under start_after). All
    # rows tie on ``rank``, so the id direction alone determines the sequence — both backends must agree.
    base = f"users/{uid}/people"
    for pid in ("p1", "p2", "p3", "p4", "p5"):
        store.set(f"{base}/{pid}", {"rank": 7, "name": pid})

    order = [("rank", direction), ("__name__", direction)]
    seen = []
    cursor = None
    for _ in range(10):  # bounded; a broken keyset would loop or skip
        page = store.query(base, order_by=order, limit=2, start_after=cursor)
        if not page:
            break
        seen.extend(d.id for d in page)
        last = page[-1]
        cursor = {"value": last.to_dict()["rank"], "id": last.id}

    # First page + cursor pages form one total order (rank tie -> id in the chosen direction).
    assert seen == sorted(["p1", "p2", "p3", "p4", "p5"], reverse=(direction == "desc"))


def test_query_is_scoped_to_the_collection(store, uid):
    other = f"u_{uuid.uuid4().hex}"
    store.set(f"users/{uid}/people/p1", {"name": "mine"})
    store.set(f"users/{other}/people/p1", {"name": "theirs"})
    result = store.query(f"users/{uid}/people")
    assert [d.to_dict()["name"] for d in result] == ["mine"]  # never leaks the other user's subcollection


def test_get_many_returns_existing_in_id_order(store, uid):
    base = f"users/{uid}/people"
    store.set(f"{base}/p1", {"name": "p1"})
    store.set(f"{base}/p3", {"name": "p3"})
    result = store.get_many(base, ["p1", "p2", "p3"])  # p2 missing
    assert [d.id for d in result] == ["p1", "p3"]
    assert all(isinstance(d, StoredDocument) and d.exists for d in result)


def test_list_ids(store, uid):
    base = f"users/{uid}/people"
    store.set(f"{base}/p1", {"name": "p1"})
    store.set(f"{base}/p2", {"name": "p2"})
    assert sorted(store.list_ids(base)) == ["p1", "p2"]


def test_delete_recursive_removes_document_and_subtree(store, uid):
    store.set(f"users/{uid}", {"root": True})
    store.set(f"users/{uid}/people/p1", {"name": "p1"})
    store.set(f"users/{uid}/people/p2", {"name": "p2"})
    store.set(f"users/{uid}/integrations/asana", {"token": "t"})

    store.delete_recursive(f"users/{uid}")

    assert store.exists(f"users/{uid}") is False
    assert store.list_ids(f"users/{uid}/people") == []
    assert store.list_ids(f"users/{uid}/integrations") == []


# --- transactions ------------------------------------------------------------


def test_run_transaction_commits_read_modify_write(store, uid):
    store.set(f"users/{uid}", {"samples": ["s1"]})

    def append_sample(tx):
        doc = tx.get(f"users/{uid}")
        samples = list(doc.to_dict()["samples"])
        samples.append("s2")
        tx.update(f"users/{uid}", {"samples": samples})
        return len(samples)

    result = store.run_transaction(append_sample)
    assert result == 2
    assert store.get(f"users/{uid}").to_dict()["samples"] == ["s1", "s2"]


def test_updated_at_revision_is_populated_and_advances(store, uid):
    store.set(f"users/{uid}", {"n": 1})
    first = store.get(f"users/{uid}").updated_at
    assert isinstance(first, datetime)
    store.update(f"users/{uid}", {"n": 2})
    second = store.get(f"users/{uid}").updated_at
    assert isinstance(second, datetime)
    assert second >= first  # a later write reports a not-earlier revision


def test_create_succeeds_then_conflicts(store, uid):
    store.create(f"users/{uid}", {"name": "Ada"})
    assert store.get(f"users/{uid}").to_dict() == {"name": "Ada"}
    with pytest.raises(AlreadyExists):
        store.create(f"users/{uid}", {"name": "someone else"})
    assert store.get(f"users/{uid}").to_dict() == {"name": "Ada"}  # first write is preserved


def test_run_transaction_create_succeeds_then_conflicts(store, uid):
    # tx.create is part of the neutral Transaction contract. A create-if-absent restore path called
    # it and crashed with AttributeError because the adapters' transaction handles lacked create
    # (cubic review PR 10887). Both backends must support it with create-if-absent semantics.
    path = f"users/{uid}/action_items/a1"

    def create_one(tx):
        tx.create(path, {"description": "restored"})

    store.run_transaction(create_one)
    assert store.get(path).to_dict() == {"description": "restored"}

    with pytest.raises(AlreadyExists):
        store.run_transaction(create_one)  # the second create-if-absent conflicts
    assert store.get(path).to_dict() == {"description": "restored"}  # first write preserved


def test_query_not_equal_filter_on_present_field(store, uid):
    # `!=` on a present field must work on every backend: migration 004 discovers conversations with
    # non-empty action_items via ('structured.action_items', '!=', []), and Mongo lacked the operator
    # so the on-prem migration found nothing (cubic review PR 10887). (`!=` on a MISSING field diverges
    # across backends — Firestore excludes it, Mongo $ne includes it — so this only covers present fields.)
    base = f"users/{uid}/conversations"
    store.set(f"{base}/c1", {"structured": {"action_items": []}})
    store.set(f"{base}/c2", {"structured": {"action_items": ["do-x"]}})
    rows = store.query(base, filters=[("structured.action_items", "!=", [])])
    assert {doc.id for doc in rows} == {"c2"}


def test_query_projection_returns_only_requested_fields(store, uid):
    store.set(f"users/{uid}/people/p1", {"name": "Ada", "secret": "hidden", "n": 1})
    (doc,) = store.query(f"users/{uid}/people", fields=["name"])
    data = doc.to_dict()
    assert data.get("name") == "Ada"
    assert "secret" not in data and "n" not in data


def test_batch_set_update_delete_commit(store, uid):
    base = f"users/{uid}/people"
    store.set(f"{base}/p3", {"name": "to-remove"})
    batch = store.batch()
    batch.set(f"{base}/p1", {"name": "Ada", "team": "x"})
    batch.set(f"{base}/p2", {"name": "Bob", "team": "x"})
    batch.update(f"{base}/p1", {"team": "y"})
    batch.delete(f"{base}/p3")
    batch.commit()

    assert store.get(f"{base}/p1").to_dict() == {"name": "Ada", "team": "y"}
    assert store.get(f"{base}/p2").to_dict() == {"name": "Bob", "team": "x"}
    assert store.exists(f"{base}/p3") is False


def test_run_transaction_aborts_on_exception(store, uid):
    store.set(f"users/{uid}", {"samples": ["s1"]})

    def failing(tx):
        tx.update(f"users/{uid}", {"samples": ["s1", "s2"]})
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        store.run_transaction(failing)

    # The aborted write must not have been committed.
    assert store.get(f"users/{uid}").to_dict()["samples"] == ["s1"]
