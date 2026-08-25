"""The neutral db_client facade (ADR-0044) must present a Firestore-Client shape over the store port,
so upstream code that threads ``db_client`` runs unchanged on-prem. These cover the non-transactional
surface — document/collection reads & writes, FieldFilter/order_by/limit query translation, google
sentinel -> neutral sentinel translation, and batches — against the neutral FakeDocumentStore. The
transactional path (open Mongo session) is exercised by the live contract check, not here."""

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import BaseCompositeFilter, FieldFilter

from google.api_core.exceptions import Aborted, FailedPrecondition
from google.cloud.firestore_v1 import LastUpdateOption

from database.store import firestore_facade as ff
from database.store.firestore_facade import (
    NeutralFirestoreClient,
    _group_name_filter_value,
    _name_filter_value,
)
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

    with pytest.raises(NotImplementedError):
        list(c.collection("users/u1/goals").where("x", "STARTS_WITH", "y").stream())


def test_where_field_equals_none_maps_to_is_null():
    # The Firestore SDK rewrites ``field == None`` / ``field != None`` into the unary IS_NULL /
    # IS_NOT_NULL operator; the facade must map it back to the neutral ('==' | '!=', None) filter, or
    # any null-equality query (e.g. get_chat_session(app_id=None) -> plugin_id == None) explodes on Mongo.
    c = _client()
    c.document("users/u1/goals/g1").set({"rank": 1, "plugin_id": None})  # present + null
    c.document("users/u1/goals/g2").set({"rank": 2, "plugin_id": "x"})  # present + value
    c.document("users/u1/goals/g3").set({"rank": 3})  # plugin_id absent

    is_null = [s.id for s in c.collection("users/u1/goals").where(filter=FieldFilter("plugin_id", "==", None)).stream()]
    assert is_null == ["g1"]  # present-and-null only, NOT the absent g3

    is_not_null = {
        s.id for s in c.collection("users/u1/goals").where(filter=FieldFilter("plugin_id", "!=", None)).stream()
    }
    assert is_not_null == {"g2"}  # present-and-not-null; null g1 and absent g3 excluded


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


def test_document_id_validation_rejects_path_injection_and_reserved_ids():
    # Cubic PR 10887: the neutral store addresses docs by a '/'-delimited path, so a '/' in a single
    # client-supplied id would split into extra segments and write to the WRONG collection/key. The
    # facade mirrors Firestore's id contract centrally so every collection().document(id) is defended.

    c = _client()
    col = c.collection("users/u1/screen_activity")
    for bad in ["a/b", "", ".", "..", "__proto__"]:
        with pytest.raises(ValueError):
            col.document(bad)
    # a legitimate id still composes the expected path
    assert col.document("ok-123").path == "users/u1/screen_activity/ok-123"
    # the top-level client.document() still takes a full '/'-path (not a single id) unchanged
    assert c.document("users/u1/screen_activity/x").path == "users/u1/screen_activity/x"


def test_count_over_filters():
    # count() returns a Firestore AggregationQuery, read as .count().get()[0][0].value — the idiom
    # every source call site uses (x_posts, conversations, apps, action_items, chat, ...).
    c = _client()
    for i, s in enumerate(["a", "b", "a"]):
        c.document(f"users/u1/goals/g{i}").set({"status": s})
    assert c.collection("users/u1/goals").count().get()[0][0].value == 3
    assert c.collection("users/u1/goals").where(filter=FieldFilter("status", "==", "a")).count().get()[0][0].value == 2


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


def test_group_query_order_by_streams_ordered_and_rejects_field_order_plus_keyset():
    c = _client()
    c.document("users/u1/events/e1").set({"ts": 1})
    c.document("users/u2/events/e2").set({"ts": 2})
    q = c.collection_group("events").order_by("ts")
    # Assert the ORDERED list (a set compare would pass even if order_by did nothing).
    assert [s.id for s in q.stream()] == ["e1", "e2"]
    # An explicit field order_by combined with a document-name start_after keyset is UNSUPPORTED on both
    # real adapters (a single doc-name cursor cannot position a field-ordered set — Mongo & Firestore both
    # raise NotImplementedError; the store contract asserts this). The fake used to silently return a
    # field-ordered-but-id-keyset window, so this combo passed hermetically then broke on both backends
    # (cubic PR 10887 #5). The fake must reject it too.
    with pytest.raises(NotImplementedError):
        list(q.start_after("users/u1/events/e1").stream())


def test_positional_list_start_after_cursor_paginates():
    # cubic PR 10887 #378: enrich_historical_memory_graph pages with a Firestore POSITIONAL cursor
    #   .order_by('updated_at', DESC).order_by('__name__', DESC).start_after([updated_at, coll.document(id)])
    # The facade must align the list 1:1 with the order_by clauses (updated_at -> values, the trailing
    # DocRef -> id keyset), not treat the whole list as a single value (which mis-keyed the cursor and
    # leaked the _DocRef into the store query -> BSON encode crash on Mongo). Verified live on Mongo.
    c = _client()
    for i in range(1, 6):
        c.document(f"users/u1/memory_items/m{i}").set({"updated_at": i})

    def page(start=None):
        q = (
            c.collection("users/u1/memory_items")
            .order_by("updated_at", "DESCENDING")
            .order_by("__name__", "DESCENDING")
        )
        if start is not None:
            q = q.start_after(start)
        return [s.id for s in q.limit(2).stream()]

    p1 = page()
    assert p1 == ["m5", "m4"]
    p2 = page(start=[4, c.document("users/u1/memory_items/m4")])  # [updated_at, DocRef] positional cursor
    assert p2 == ["m3", "m2"]
    p3 = page(start=[2, c.document("users/u1/memory_items/m2")])
    assert p3 == ["m1"]


def test_group_query_name_filter_with_docref_bound_matches_full_path():
    # cubic PR 10887 #338: a collection-group __name__ filter matches _id, which IS the full document
    # path (query_group spans parents, no collection to prefix). The facade must forward a _DocRef bound
    # as its full .path, NOT the bare .id used for scoped queries (a regression from the #8 scoped fix:
    # reducing to .id made the group filter match nothing on Mongo). Verified live on Mongo.
    c = _client()
    c.document("users/u1/state/s1").set({"k": 1})
    c.document("users/u2/state/s2").set({"k": 2})
    ref = c.document("users/u1/state/s1")
    grp = c.collection_group("state").where(filter=FieldFilter("__name__", "==", ref))
    assert [s.id for s in grp.stream()] == ["s1"]  # was [] when the DocRef was reduced to bare "s1"
    # A range bound (>=) with a DocRef must also compare on the full path.
    rng = c.collection_group("state").where(filter=FieldFilter("__name__", ">=", c.document("users/u2/state/s2")))
    assert [s.id for s in rng.stream()] == ["s2"]


def test_write_option_precondition_enforced_on_batch_delete():
    # Regression: NeutralFirestoreClient.write_option was missing, so staged-task recovery and chat
    # clear (which build a precondition via write_option and pass it to batch.delete) raised
    # AttributeError on the Mongo-backed facade. It must exist AND enforce the precondition, surfacing
    # a stale revision as google FailedPrecondition (what those callers catch to re-read and retry).

    c = _client()
    ref = c.document("users/u1/staged/s1")
    ref.set({"n": 1})
    stale = ref.get().update_time
    ref.update({"n": 2})  # moves the revision past ``stale``

    batch = c.batch()
    batch.delete(ref, option=c.write_option(last_update_time=stale))
    with pytest.raises(FailedPrecondition):
        batch.commit()
    assert ref.get().exists is True  # the refused batch left the row in place

    current = ref.get().update_time
    batch = c.batch()
    batch.delete(ref, option=c.write_option(last_update_time=current))
    batch.commit()
    assert ref.get().exists is False  # a matching precondition lets the delete through


def test_last_update_option_precondition_enforced_on_reference_update():
    # review-queue self-heal passes a native LastUpdateOption to reference.update; the facade must map
    # it to the store precondition, not silently ignore it, and raise on a stale revision.

    c = _client()
    ref = c.document("users/u1/review/r1")
    ref.set({"status": "pending"})
    stale = ref.get().update_time
    ref.update({"status": "touched"})  # moves the revision

    with pytest.raises(FailedPrecondition):
        ref.update({"status": "healed"}, option=LastUpdateOption(stale))
    assert ref.get().to_dict()["status"] == "touched"

    current = ref.get().update_time
    ref.update({"status": "healed"}, option=LastUpdateOption(current))
    assert ref.get().to_dict()["status"] == "healed"


def test_document_get_with_projection_field_paths_does_not_crash():
    # Regression (cubic PR 10887 A1): DocumentReference.get(field_paths) takes the projection as the
    # FIRST positional arg. Upstream calls `.get(['subscription'])` etc.; the facade used to bind that
    # list to `transaction` and dereference `read` on it, crashing every projection read on Mongo.
    c = _client()
    ref = c.document("users/u1")
    ref.set({"subscription": {"plan": "pro"}, "language": "it", "secret": "x"})
    snap = ref.get(["subscription", "language"])  # positional projection — must not raise
    assert snap.exists is True
    data = snap.to_dict()
    assert data.get("subscription") == {"plan": "pro"}
    assert data.get("language") == "it"
    assert "secret" not in data  # projection applied through the store's fields=
    # transaction reads still bind by keyword and keep working
    assert c.document("users/none").get(["subscription"]).exists is False


def test_collection_field_then_name_cursor_paginates_without_notimplemented():
    # Regression (cubic PR 10887 A2): a (field, __name__) order_by + start_after cursor (historical /
    # canonical memory scans) must map onto the store's {value, id} keyset instead of raising
    # NotImplementedError, so page 2+ works on the Mongo-backed facade.
    c = _client()
    for doc_id, ts in [("a", 1), ("b", 2), ("c", 3)]:
        c.document(f"users/u1/items/{doc_id}").set({"ts": ts})
    q = c.collection("users/u1/items").order_by("ts", "ASCENDING").order_by("__name__", "ASCENDING")
    page1 = [s.id for s in q.limit(2).stream()]
    assert page1 == ["a", "b"]  # real ordering, not a set
    cursor = {"ts": 2, "__name__": c.document("users/u1/items/b")}
    page2 = [s.id for s in q.start_after(cursor).stream()]
    assert page2 == ["c"]  # cursor advanced past b — no NotImplementedError, no first-page repeat


def test_group_query_name_order_with_cursor_does_not_raise():
    # cubic PR 10887 #2: canonical maintenance does collection_group(...).order_by("__name__").start_after(
    # cursor). The facade must treat the __name__ order as the implicit document-name keyset (no-op), not
    # forward it and raise on Mongo — otherwise the cron stalls at page 1.
    c = _client()
    c.document("users/u1/state/s1").set({"k": 1})
    c.document("users/u2/state/s2").set({"k": 2})
    q = c.collection_group("state").order_by("__name__")
    assert {s.id for s in q.stream()} == {"s1", "s2"}
    page = list(q.start_after("users/u1/state/s1").stream())  # resume — must page, not raise
    assert [s.id for s in page] == ["s2"]


def test_multi_field_order_composite_cursor_paginates():
    # cubic PR 10887 #4: review_queue orders by impact DESC, created_at DESC, __name__ DESC and paginates
    # via the facade. The facade must map that to the store's composite keyset, not raise on page 2.
    c = _client()
    for doc_id, d in [
        ("c1", {"impact": 3, "created_at": 20}),
        ("c2", {"impact": 3, "created_at": 10}),
        ("c3", {"impact": 2, "created_at": 50}),
    ]:
        c.document(f"users/u1/conflicts/{doc_id}").set(d)
    q = (
        c.collection("users/u1/conflicts")
        .order_by("impact", "DESCENDING")
        .order_by("created_at", "DESCENDING")
        .order_by("__name__", "DESCENDING")
    )
    assert [s.id for s in q.stream()] == ["c1", "c2", "c3"]
    cursor = {"impact": 3, "created_at": 20, "__name__": c.document("users/u1/conflicts/c1")}
    assert [s.id for s in q.start_after(cursor).stream()] == ["c2", "c3"]  # page 2, no NotImplementedError


def test_docref_get_threads_read_timeout_to_store():
    # Regression (cubic review 4909186286 #2): _DocRef.get used to ``del timeout``, so default-read
    # rollout's 2s deadline was silently dropped on the Mongo-backed facade (the Mongo adapter maps
    # timeout -> maxTimeMS). The facade must now thread the read deadline to the store.
    seen = {}

    class _RecordingStore(FakeDocumentStore):
        def get(self, path, *, fields=None, timeout=None):
            seen["timeout"] = timeout
            return super().get(path, fields=fields, timeout=timeout)

    c = NeutralFirestoreClient(_RecordingStore())
    c.document("users/u1").set({"v": 1})
    snap = c.document("users/u1").get(timeout=2)
    assert snap.to_dict() == {"v": 1}
    assert seen["timeout"] == 2


def test_get_all_batches_via_get_many_not_per_ref():
    # cubic review 4939247683: get_all must batch by collection through store.get_many (one $in per
    # collection on Mongo), not do N point reads. Spy the fake store's get_many vs get.

    store = FakeDocumentStore()
    c = NeutralFirestoreClient(store)
    c.document("users/u1/goals/a").set({"v": 1})
    c.document("users/u1/goals/b").set({"v": 2})

    calls = {"get_many": 0, "get": 0}
    real_gm, real_get = store.get_many, store.get
    store.get_many = lambda collection, ids: (
        calls.__setitem__("get_many", calls["get_many"] + 1),
        real_gm(collection, ids),
    )[1]
    store.get = lambda path, **kw: (calls.__setitem__("get", calls["get"] + 1), real_get(path, **kw))[1]

    refs = [c.document("users/u1/goals/a"), c.document("users/u1/goals/missing"), c.document("users/u1/goals/b")]
    snaps = list(c.get_all(refs))
    assert [s.exists for s in snaps] == [True, False, True]  # one snapshot per ref, order + missing kept
    assert snaps[0].to_dict() == {"v": 1}
    assert calls["get_many"] == 1  # single batched read for the one collection
    assert calls["get"] == 0  # NOT N per-ref point reads


def _conflicting_client():
    """A client whose first in-transaction write hits a Mongo write conflict."""

    class _ConflictStore(FakeDocumentStore):
        # The public op, not a private `_set(session=...)` alias: the fake declares itself session-less
        # (begin_session() -> None), so the facade runs its writes straight on the store. That used to
        # be a separate, session-swallowing method — one seam now instead of two.
        def set(self, path, data, *, merge=False):
            exc = Exception("WriteConflict")
            exc.has_error_label = lambda label: label == "TransientTransactionError"
            raise exc

    return NeutralFirestoreClient(_ConflictStore())


def test_txn_write_conflict_is_held_instead_of_escaping_the_body():
    # cubic PR 10887 goals.py:635: a MongoDB write conflict can surface at the write op (update_one /
    # insert_one on the session), not only at commit. This test used to assert that the write RAISED
    # google's Aborted, on the stated grounds that @firestore.transactional would then replay apply().
    #
    # Measured on the live rig, that never happened: google's `_pre_commit` -- which runs the decorated
    # body, and therefore the write -- sits OUTSIDE `except retryable_exceptions`, so raising here
    # produced a bare Aborted at the caller and the body ran exactly once (ADR-0091, BACKLOG L53). The
    # conflict is now HELD, and the assertion moves with it: the write returns, and the transaction
    # remembers.
    c = _conflicting_client()
    txn = c.transaction()

    txn.set(c.document("users/u1/goals/reservation"), {"version": 2})  # must not raise

    assert isinstance(txn._poisoned, Aborted), "the conflict must be remembered, translated"


def test_a_held_write_conflict_is_raised_by_the_commit():
    """Where the decorator actually retries."""
    c = _conflicting_client()
    txn = c.transaction()
    txn.set(c.document("users/u1/goals/reservation"), {"version": 2})

    with pytest.raises(Aborted):
        txn._commit()


def test_a_poisoned_transaction_writes_nothing_and_reads_absent():
    """The body runs on to the end, so it must find a transaction that answers without raising and
    without applying anything."""
    c = _conflicting_client()
    ref = c.document("users/u1/goals/reservation")
    txn = c.transaction()
    txn.set(ref, {"version": 2})

    txn.update(ref, {"version": 3})
    txn.create(c.document("users/u1/goals/new"), {"version": 1})
    txn.delete(ref)
    snapshot = txn.get(ref)

    assert snapshot.exists is False
    assert snapshot.to_dict() in (None, {})


def test_beginning_again_clears_the_held_conflict():
    """google's decorator REUSES the transaction object across attempts: a replay that started poisoned
    would run inert and re-raise until the attempt budget ran out."""
    c = _conflicting_client()
    txn = c.transaction()
    txn.set(c.document("users/u1/goals/reservation"), {"version": 2})
    assert txn._poisoned is not None

    txn._begin()

    assert txn._poisoned is None


def test_get_all_binds_positional_transaction():
    # cubic PR 10887 firestore_facade.py:658: real Firestore is get_all(references, field_paths, transaction);
    # a positional transaction must BIND (read through the session), not be swallowed by *_ (read outside it).
    c = _client()
    c.document("users/u1/goals/g1").set({"v": 1})
    txn = c.transaction()
    reads: list = []
    orig_read = txn.read
    txn.read = lambda path, **kw: (reads.append(path), orig_read(path, **kw))[1]
    snaps = list(c.get_all([c.document("users/u1/goals/g1")], None, txn))  # positional field_paths + transaction
    assert [s.to_dict() for s in snaps] == [{"v": 1}]
    assert reads == ["users/u1/goals/g1"]  # the read went THROUGH the transaction, not the batched get_many


def test_select_projects_fields_to_the_store():
    # cubic PR 10887 facade:258: .select() must propagate the projection to the store instead of fetching
    # every field. select(['f']) returns only f; select([]) is ids-only; no select returns the full doc.
    c = _client()
    c.document("users/u1/goals/g1").set({"title": "a", "rank": 1, "secret": "x"})
    c.document("users/u1/goals/g2").set({"title": "b", "rank": 2, "secret": "y"})
    coll = c.collection("users/u1/goals")
    assert {s.id: s.to_dict() for s in coll.select(["title"]).stream()} == {"g1": {"title": "a"}, "g2": {"title": "b"}}
    assert sorted(s.id for s in coll.select([]).stream()) == ["g1", "g2"]  # ids preserved
    assert all(s.to_dict() == {} for s in coll.select([]).stream())  # [] is ids-only, not "no projection"
    assert {s.id: s.to_dict() for s in coll.stream()}["g1"] == {"title": "a", "rank": 1, "secret": "x"}


def test_name_filter_normalizes_membership_list_of_refs():
    # cubic PR 10887 facade:350: a __name__ in/not-in filter carries a LIST of references; each must be
    # normalized element-wise, else a valid Firestore .where('__name__','in',[ref,...]) matches nothing.
    c = _client()
    r1, r2 = c.document("users/u1/goals/g1"), c.document("users/u1/goals/g2")
    assert _name_filter_value([r1, r2]) == ["g1", "g2"]  # scoped query -> bare ids
    assert _group_name_filter_value([r1, r2]) == ["users/u1/goals/g1", "users/u1/goals/g2"]  # group -> full paths
    assert _name_filter_value(r1) == "g1"  # scalar path still works
    assert _name_filter_value(["g1", "g2"]) == ["g1", "g2"]  # plain strings pass through


def test_get_all_in_transaction_reads_through_session():
    # With a transaction, get_all must read through the transaction (read-your-writes), NOT the
    # session-unaware get_many. Prove each ref is routed through transaction.read.

    store = FakeDocumentStore()
    store.set("users/u1/goals/x", {"v": 9})
    c = NeutralFirestoreClient(store)

    class _StubTx:
        def __init__(self):
            self.reads = []

        def read(self, path, **_kw):
            self.reads.append(path)
            return store.get(path)

    tx = _StubTx()
    snaps = list(c.get_all([c.document("users/u1/goals/x")], transaction=tx))
    assert tx.reads == ["users/u1/goals/x"]  # routed through the session, not get_many
    assert snaps[0].to_dict() == {"v": 9}


def test_name_range_filter_with_docref_bounds_matches_documents():
    # cubic PR 10887 #8: user_usage.get_current_month_usage does
    #   llm_usage_ref.where('__name__', '>=', llm_usage_ref.document('YYYY-MM-01'))
    #                .where('__name__', '<',  <next month>)
    # i.e. the __name__ bounds are DocumentReferences (_DocRef), not bare strings. The facade must
    # normalize a _DocRef bound to its document id before the store; forwarding the object verbatim
    # stringified to its repr and matched nothing on Mongo -> monthly chat usage undercounted to zero.
    # The contract test only exercised a string bound, so the seam hid this. Verified live on Mongo.
    c = _client()
    usage = c.collection("users/u1/usage")
    for month in ("2026-06-01", "2026-07-01", "2026-08-01"):
        usage.document(month).set({"questions": 1})
    q = usage.where("__name__", ">=", usage.document("2026-07-01")).where("__name__", "<", usage.document("2026-09-01"))
    assert sorted(s.id for s in q.stream()) == ["2026-07-01", "2026-08-01"]
    # count() shares the filter path and must agree (usage aggregates via count too).
    assert q.count().get()[0][0].value == 2


def test_name_filter_string_bound_still_matches():
    # The bare-string __name__ bound (contract-test shape) must keep working after DocRef normalization.
    c = _client()
    items = c.collection("users/u1/items")
    for k in ("a", "b", "c"):
        items.document(k).set({"v": 1})
    q = items.where("__name__", ">=", "b")
    assert sorted(s.id for s in q.stream()) == ["b", "c"]


def test_commit_retries_commit_only_on_unknown_result_but_replays_body_on_transient():
    # cubic PR 10887 firestore_facade.py:508: UnknownTransactionCommitResult means the commit MAY have
    # succeeded, so _commit must retry the COMMIT (idempotent) and NEVER signal a body replay; only a
    # TransientTransactionError (body never applied) is replayed via Aborted.

    class _LabelExc(Exception):
        def __init__(self, label):
            self._label = label

        def has_error_label(self, label):
            return label == self._label

    class _UnknownThenOk:
        def __init__(self):
            self.commits = 0

        def commit_transaction(self):
            self.commits += 1
            if self.commits < 3:
                raise _LabelExc("UnknownTransactionCommitResult")

    tx = ff._FacadeTransaction.__new__(ff._FacadeTransaction)
    tx._session = _UnknownThenOk()
    tx._commit()  # must not raise: retries the commit only
    assert tx._session.commits == 3  # retried, no body replay

    class _Transient:
        def commit_transaction(self):
            raise _LabelExc("TransientTransactionError")

    tx2 = ff._FacadeTransaction.__new__(ff._FacadeTransaction)
    tx2._session = _Transient()
    with pytest.raises(Aborted):  # decorator replays the whole transaction body
        tx2._commit()


def test_group_query_order_by_field_missing_on_some_docs_does_not_crash():
    # cubic PR 10887 store_fakes.py:344: query_group ordered by a field some group docs lack must not
    # crash on a None sort key (the fake used to raise TypeError while both real adapters return rows).
    # Firestore excludes docs missing the ordered field; the fake now filters them before sorting.
    c = _client()
    c.document("users/u1/items/a").set({"rank": 2})
    c.document("users/u2/items/b").set({"rank": 1})
    c.document("users/u3/items/c").set({"other": 9})  # no ``rank`` -> excluded from the order
    ordered = [s.id for s in c.collection_group("items").order_by("rank").stream()]
    assert ordered == ["b", "a"]  # c excluded, no TypeError


# --- composite filters (ADR-0044) -------------------------------------------------------------
# database/apps.py builds every multi-condition app query as
# ``where(filter=BaseCompositeFilter('AND', [FieldFilter(...), ...]))`` — 19 call sites covering the
# whole marketplace surface (counts, private/public/popular/unapproved listings, tester apps, and
# the six persona lookups). A composite carries ``.operator``/``.filters`` and none of the
# FieldFilter attributes, so reading field_path/op_string/value off it yields None on all three and
# the operator map used to raise a misleading "unsupported query operator: None" — i.e. those
# queries 500'd on Mongo while working on Firestore.


def _seed_apps(c) -> None:
    c.document("plugins_data/a").set({"private": False, "approved": True, "category": "health"})
    c.document("plugins_data/b").set({"private": False, "approved": False, "category": "health"})
    c.document("plugins_data/c").set({"private": True, "approved": True, "category": "work"})


def test_composite_and_filter_applies_every_member():
    c = _client()
    _seed_apps(c)
    q = c.collection("plugins_data").where(
        filter=BaseCompositeFilter("AND", [FieldFilter("private", "==", False), FieldFilter("approved", "==", True)])
    )
    assert sorted(s.id for s in q.stream()) == ["a"]


def test_composite_and_filter_nests():
    c = _client()
    _seed_apps(c)
    inner = BaseCompositeFilter("AND", [FieldFilter("approved", "==", True), FieldFilter("category", "==", "health")])
    q = c.collection("plugins_data").where(
        filter=BaseCompositeFilter("AND", [FieldFilter("private", "==", False), inner])
    )
    assert sorted(s.id for s in q.stream()) == ["a"]


def test_composite_member_null_equality_still_translates():
    """A ``field == None`` member must get the same IS_NULL treatment as a standalone filter."""
    c = _client()
    c.document("plugins_data/x").set({"private": False, "owner": None})
    c.document("plugins_data/y").set({"private": False, "owner": "u1"})
    q = c.collection("plugins_data").where(
        filter=BaseCompositeFilter("AND", [FieldFilter("private", "==", False), FieldFilter("owner", "==", None)])
    )
    assert sorted(s.id for s in q.stream()) == ["x"]


def test_composite_and_filter_composes_with_count_and_limit():
    c = _client()
    _seed_apps(c)
    comp = BaseCompositeFilter("AND", [FieldFilter("private", "==", False), FieldFilter("category", "==", "health")])
    assert c.collection("plugins_data").where(filter=comp).count().get()[0][0].value == 2
    assert len(list(c.collection("plugins_data").where(filter=comp).limit(1).stream())) == 1


def test_composite_or_filter_is_rejected_explicitly():
    """The port's filter list is an implicit AND: OR must fail loudly, not be silently dropped."""
    c = _client()
    comp = BaseCompositeFilter("OR", [FieldFilter("private", "==", False), FieldFilter("approved", "==", True)])
    with pytest.raises(NotImplementedError, match="OR"):
        c.collection("plugins_data").where(filter=comp)


def test_composite_and_filter_on_collection_group():
    c = _client()
    c.document("users/u1/apps/a").set({"private": False, "approved": True})
    c.document("users/u2/apps/b").set({"private": False, "approved": False})
    q = c.collection_group("apps").where(
        filter=BaseCompositeFilter("AND", [FieldFilter("private", "==", False), FieldFilter("approved", "==", True)])
    )
    assert [s.id for s in q.stream()] == ["a"]


# --- add(data, document_id) --------------------------------------------------------------------
# database/apps.py:228 creates an app with ``app_ref.add(app_data, app_data['id'])``. Firestore's
# signature is add(document_data, document_id=None); the facade took only the data, so app creation
# raised TypeError on Mongo — and had it been accepted, the doc would have landed under a random
# auto-id instead of the app id.


def test_add_with_explicit_document_id_uses_it():
    c = _client()
    _write_time, ref = c.collection("plugins_data").add({"name": "omi-app"}, "app-123")
    assert ref.id == "app-123"
    assert c.document("plugins_data/app-123").get().to_dict() == {"name": "omi-app"}


def test_add_without_document_id_still_auto_ids():
    c = _client()
    _write_time, ref = c.collection("plugins_data").add({"name": "omi-app"})
    assert ref.id and ref.id != "app-123"
    assert c.document(f"plugins_data/{ref.id}").get().exists is True


# --- stream/get transport kwargs -----------------------------------------------------------------
# database/trends.py:16 and :33 read with ``stream(retry=Retry())``. The facade took only
# ``transaction``, so ``get_trends_data()`` raised TypeError on the FIRST line of its body under
# STORAGE_BACKEND=mongo and /v1/trends was a 500 for every on-prem user — the same class as the
# ``add(data, document_id)`` case above, and found the same way: by running the reader instead of
# reading it. The second call sits inside ``except Exception: continue``, so a fix reaching only the
# first line would have served every category with zero topics: an empty board, no error, nothing to
# notice. ``retry``/``timeout`` are transport policy each adapter already owns, so they are accepted
# and not forwarded; the behavioral pair is in tests/contract/test_trends_contract.py, on both legs.


def test_stream_accepts_the_sdk_transport_kwargs():
    from google.api_core.retry import Retry

    c = _client()
    c.document("trends/ceo-best").set({"id": "ceo-best", "category": "ceo"})

    assert [s.id for s in c.collection("trends").stream(retry=Retry())] == ["ceo-best"]
    assert [s.id for s in c.collection("trends").stream(retry=Retry(), timeout=30.0)] == ["ceo-best"]


def test_get_accepts_the_sdk_transport_kwargs():
    from google.api_core.retry import Retry

    c = _client()
    c.document("trends/ceo-best").set({"id": "ceo-best", "category": "ceo"})

    assert [s.id for s in c.collection("trends").get(retry=Retry(), timeout=30.0)] == ["ceo-best"]


def test_collection_group_stream_accepts_them_too():
    from google.api_core.retry import Retry

    c = _client()
    c.document("users/u1/topics/t1").set({"topic": "Elon Musk"})

    assert [s.id for s in c.collection_group("topics").stream(retry=Retry())] == ["t1"]


# --- transport-kwarg parity with the SDK ----------------------------------------------------------
# The /v1/trends outage was one method missing `retry`. The instance is fixed above; this closes the
# CLASS, because the same shape is one keyword away on every other method: `doc_ref.delete(retry=...)`
# or `batch.commit(timeout=...)` is ordinary SDK usage that upstream may add at any time, and it would
# fail the same way -- TypeError under STORAGE_BACKEND=mongo only, on a line that looks fine.
#
# The rule is narrow on purpose. It is NOT full signature parity (the SDK's positional parameter names
# differ from ours by design, and mirroring them would be noise): only `retry` and `timeout`, only on
# methods the facade already claims to mirror. Whether they are honored is a separate question --
# `_DocRef.get` threads `timeout` to the store as a real read deadline, everything else drops both,
# which the code says at each site.


_SDK_PAIRS = [
    ('_DocRef', 'DocumentReference'),
    ('_Query', 'BaseQuery'),
    ('_CollRef', 'BaseCollectionReference'),
    ('_GroupQuery', 'CollectionGroup'),
    ('NeutralFirestoreClient', 'Client'),
    ('_FacadeTransaction', 'Transaction'),
    ('_FacadeBatch', 'WriteBatch'),
]


def _keywords(cls, name):
    """(accepted keyword names, whether it absorbs **kwargs), or None if there is no such method."""
    import inspect

    attribute = getattr(cls, name, None)
    if attribute is None or not callable(attribute):
        return None
    try:
        signature = inspect.signature(attribute)
    except (TypeError, ValueError):
        return None
    named = {p.name for p in signature.parameters.values() if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)} - {
        'self'
    }
    absorbs = any(p.kind is p.VAR_KEYWORD for p in signature.parameters.values())
    return named, absorbs


def test_every_mirrored_method_accepts_the_sdk_transport_kwargs():
    from google.cloud import firestore_v1 as sdk
    from google.cloud.firestore_v1.base_collection import BaseCollectionReference
    from google.cloud.firestore_v1.base_query import BaseQuery

    sdk_classes = {
        'DocumentReference': sdk.DocumentReference,
        'BaseQuery': BaseQuery,
        'BaseCollectionReference': BaseCollectionReference,
        'CollectionGroup': sdk.CollectionGroup,
        'Client': sdk.Client,
        'Transaction': sdk.Transaction,
        'WriteBatch': sdk.WriteBatch,
    }

    gaps = []
    checked = 0
    for facade_name, sdk_name in _SDK_PAIRS:
        facade_cls = getattr(ff, facade_name)
        sdk_cls = sdk_classes[sdk_name]
        for method in sorted(n for n in dir(facade_cls) if not n.startswith('__')):
            facade = _keywords(facade_cls, method)
            counterpart = _keywords(sdk_cls, method)
            if facade is None or counterpart is None:
                continue
            facade_kws, absorbs = facade
            if absorbs:
                continue
            checked += 1
            missing = ({'retry', 'timeout'} & counterpart[0]) - facade_kws
            if missing:
                gaps.append(f'{facade_name}.{method} does not accept {sorted(missing)}')

    assert checked > 20, f'the pairing found only {checked} mirrored methods — the facade or the SDK moved'
    assert gaps == [], 'a caller passing these would get TypeError on the Mongo posture only:\n  ' + '\n  '.join(gaps)
