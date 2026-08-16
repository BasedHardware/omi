"""MongoDB implementation of the neutral ``DocumentStore`` port (ADR-0002/0004).

Mongo does **not** emulate Firestore — it satisfies the same neutral contract with its own
primitives. The dual-backend contract test asserts its observable behavior matches the Firestore
reference adapter.

Path model (the one non-obvious part). Firestore nests subcollections; Mongo does not. Each logical
document is stored in the Mongo collection named after its **leaf collection** (so the number of
Mongo collections stays bounded — one per logical collection name, not one per user), with metadata
that makes addressing and scoping exact:

  ``users/{uid}/people/{pid}``  ->  Mongo collection ``people``, document
      ``{ _id: "users/{uid}/people/{pid}",   # full logical path — globally unique, no cross-user id clashes
          _parent: "users/{uid}/people",     # containing collection path — scopes queries/list_ids
          _key: "{pid}",                     # the document id (StoredDocument.id)
          d: { ...user payload... } }``      # payload isolated from metadata (no _id/_parent collisions)

Neutral sentinels map to Mongo update operators; ``(field, op, value)`` filters map to a Mongo
query; transactions use a replica-set session. ``_id`` is always a string.

Known contract boundary (documented, tested around — see the dual-backend contract test): Firestore
``set(merge=True)`` deep-merges nested maps, while this adapter replaces a map value at its key
(shallow). Callers that must merge a nested map use ``update`` with dotted keys, which both backends
honor identically.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from pymongo import ASCENDING, DESCENDING, DeleteOne, InsertOne, MongoClient, ReplaceOne, UpdateOne
from pymongo.errors import DuplicateKeyError

from ..errors import AlreadyExists, NotFound, PreconditionFailed
from ..records import StoredDocument
from ..sentinels import DELETE, SERVER_TIMESTAMP, ArrayRemove, ArrayUnion, Increment
from ..ports import Filter

# ``array_contains_any`` maps to ``$in``: on an array-valued field Mongo's $in matches when ANY array
# element is in the given list (mirrors Firestore array_contains_any). ``not-in`` -> ``$nin``.
# CAVEAT (cubic review 4939247683): the plain ``in`` operator also maps to ``$in``, which matches
# Firestore ``in`` exactly for SCALAR fields (the only shape Omi uses). On an ARRAY-valued field the
# semantics diverge — Firestore ``in`` compares the whole field value, Mongo ``$in`` matches individual
# elements — so ``in`` must not be used against an array field on this port (use array_contains* instead).
_OP = {
    "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte", "in": "$in", "==": "$eq", "!=": "$ne",
    "not-in": "$nin", "array_contains_any": "$in",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rev_stamp(if_updated_at: Any = None) -> datetime:
    """The ``_updated_at`` revision to write. With no precondition it is ``now``. With a precondition it is
    ``max(now, if_updated_at + 1ms)`` so the NEW revision is strictly greater than the one the caller read.
    Mongo truncates dates to BSON millisecond, so two writes in the same ms would otherwise share a token
    and let a stale ``if_updated_at`` write slip through the optimistic-concurrency check (cubic PR 10887
    mongo.py:321; repro'd lost update). Firestore's ``update_time`` is already server-monotonic. The neutral
    revision stays a ``datetime`` — the port/facade/upstream contract is unchanged; only the Mongo adapter
    guarantees strict per-doc monotonicity for precondition writes (amends the Mongo mapping of ADR-0017)."""
    now = _now()
    if if_updated_at is None:
        return now
    return max(now, if_updated_at + timedelta(milliseconds=1))


_UPDATED_AT_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _monotonic_updated_at(now: datetime) -> Dict[str, Any]:
    """Aggregation-pipeline expression for a strictly-increasing per-document ``_updated_at``:
    ``max(now, prev + 1ms)``. Two UNCONDITIONAL writes in the same BSON millisecond otherwise share a
    revision, so a reader's stale ``if_updated_at`` token still satisfies the next conditional update — a
    silent lost update (cubic PR 10887 mongo.py:161; repro'd). ``_rev_stamp`` closed this only for
    precondition writes; this closes it for the repeatable set/merge/update paths. A brand-new doc (prev is
    null) resolves to ``now``. Cost is negligible (~+4% per write, measured) since with no contention
    ``prev + 1ms < now`` so the result is just ``now``."""
    return {"$max": [now, {"$add": [{"$ifNull": ["$_updated_at", _UPDATED_AT_EPOCH]}, 1]}]}


def _is_sentinel(value: Any) -> bool:
    return value is DELETE or value is SERVER_TIMESTAMP or isinstance(value, (ArrayUnion, ArrayRemove, Increment))


def _doc_meta(path: str) -> tuple[str, str, str]:
    """(mongo_collection_name, parent_collection_path, key) for a document path (even segments)."""
    segments = path.split("/")
    return segments[-2], "/".join(segments[:-1]), segments[-1]


def _collection_name(collection_path: str) -> str:
    """Mongo collection name for a logical collection path (odd segments)."""
    return collection_path.split("/")[-1]


def _build_update_ops(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Translate a neutral write dict (plain values + sentinels) to Mongo update operators.

    Every field is stored under the ``d`` payload subdocument, so keys are prefixed with ``d.``.
    Dotted keys (``transcription_preferences.single_language_mode``) become ``d.<dotted>`` and Mongo
    targets the nested field natively — the same semantics as a Firestore dotted-key update.
    """
    ops: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        field = "d." + key
        if value is DELETE:
            ops.setdefault("$unset", {})[field] = ""
        elif value is SERVER_TIMESTAMP:
            ops.setdefault("$currentDate", {})[field] = True
        elif isinstance(value, ArrayUnion):
            ops.setdefault("$addToSet", {})[field] = {"$each": list(value.values)}
        elif isinstance(value, ArrayRemove):
            ops.setdefault("$pull", {})[field] = {"$in": list(value.values)}
        elif isinstance(value, Increment):
            ops.setdefault("$inc", {})[field] = value.amount
        else:
            ops.setdefault("$set", {})[field] = value
    return ops


def _to_record(doc: Dict[str, Any], path: str) -> StoredDocument:
    return StoredDocument(
        id=doc.get("_key", path.split("/")[-1]),
        path=path,
        exists=True,
        data=doc.get("d", {}),
        updated_at=doc.get("_updated_at"),
        created_at=doc.get("_created_at"),
    )


class _MongoBatch:
    """Neutral batched-write accumulator; on commit, groups ops by collection and bulk-writes.

    Each queued op carries both a pymongo bulk op (the fast ``bulk_write`` path) and a ``run`` closure
    that applies the same effect individually. When no op in the batch has an ``if_updated_at``
    precondition, commit uses ``bulk_write`` unchanged. When any op does, that collection's ops run
    sequentially in queued order via ``run`` so a precondition op can be checked and raise
    ``PreconditionFailed`` — bulk_write's aggregate result cannot attribute a no-match to one op.
    Mongo batches are not atomic (see the WriteBatch port docstring), so this detects the lost race
    without rolling back; callers (staged-task recovery, chat clear) re-read and retry on the error.
    """

    def __init__(self, store: "MongoDocumentStore"):
        self._store = store
        self._ops: List[tuple] = []

    def _append(self, collection_name: str, op: Any, run: Callable[[Any], None], *, checked: bool = False) -> None:
        # ``checked`` ops need their individual result inspected (a precondition, or an update that must
        # raise NotFound on a missing doc), which forces the sequential commit path.
        self._ops.append((collection_name, op, run, checked))

    def _append_bump(self, collection_name: str, path: str, now: datetime) -> None:
        # Monotonic _updated_at for an operator-based queued write. bulk_write runs ops in order (ordered=True)
        # and the sequential fallback runs each op's closure in order, so this bump reliably reads the value
        # the preceding merge/update op wrote and lifts it to max(now, prev+1ms) (cubic 10887 mongo.py:161).
        bump = [{"$set": {"_updated_at": _monotonic_updated_at(now)}}]
        self._append(
            collection_name,
            UpdateOne({"_id": path}, bump),
            lambda coll, _b=bump: coll.update_one({"_id": path}, _b),
        )

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        collection_name, parent, key = _doc_meta(path)
        now = _now()
        if merge:
            # Operator-based merge can't compute a monotonic _updated_at inline -> stamp via a bump op.
            update: Dict[str, Any] = _build_update_ops(data)
            update.setdefault("$setOnInsert", {}).update({"_parent": parent, "_key": key, "_created_at": now})
            self._append(
                collection_name,
                UpdateOne({"_id": path}, update, upsert=True),
                lambda coll: coll.update_one({"_id": path}, update, upsert=True),
            )
            self._append_bump(collection_name, path, now)
        else:
            plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
            # Pipeline replace: whole ``d`` (non-merge), monotonic ``_updated_at``, immutable ``_created_at``
            # via ``$ifNull`` (pipelines have no ``$setOnInsert``) (cubic 10887 #1 + mongo.py:161).
            doc_update = [
                {
                    "$set": {
                        # $literal so ``d`` REPLACES rather than deep-merges (see MongoDocumentStore._set).
                        "d": {"$literal": plain},
                        "_parent": parent,
                        "_key": key,
                        "_updated_at": _monotonic_updated_at(now),
                        "_created_at": {"$ifNull": ["$_created_at", now]},
                    }
                }
            ]
            self._append(
                collection_name,
                UpdateOne({"_id": path}, doc_update, upsert=True),
                lambda coll: coll.update_one({"_id": path}, doc_update, upsert=True),
            )
            # A non-merge set can still carry neutral transforms (SERVER_TIMESTAMP/Increment/ArrayUnion).
            # Mirror MongoDocumentStore._set: apply them in a follow-up update right after the replace, or
            # the batch silently drops them (Firestore's batch translates them natively — parity).
            transforms = {k: v for k, v in data.items() if _is_sentinel(v)}
            if transforms:
                transform_ops = _build_update_ops(transforms)
                self._append(
                    collection_name,
                    UpdateOne({"_id": path}, transform_ops),
                    lambda coll, _o=transform_ops: coll.update_one({"_id": path}, _o),
                )

    def create(self, path: str, data: Dict[str, Any]) -> None:
        # Mirror MongoDocumentStore._create: insert the full document, stamping _created_at once. A
        # duplicate _id raises the neutral AlreadyExists so create-if-absent recovery (staged-task
        # restore) branches identically to the Firestore batch, which raises AlreadyExists at commit.
        collection_name, parent, key = _doc_meta(path)
        plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
        now = _now()
        document = {"_id": path, "_parent": parent, "_key": key, "_updated_at": now, "_created_at": now, "d": plain}
        transforms = {k: v for k, v in data.items() if _is_sentinel(v)}

        def run(coll: Any) -> None:
            try:
                coll.insert_one(document)
            except DuplicateKeyError as exc:
                raise AlreadyExists(path) from exc
            if transforms:
                coll.update_one({"_id": path}, _build_update_ops(transforms))

        # ``checked`` so a duplicate-key collision surfaces per-op — bulk_write's aggregate result
        # cannot attribute a DuplicateKeyError to one queued op — forcing the sequential commit path.
        self._append(collection_name, InsertOne(document), run, checked=True)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        now = _now()
        update = _build_update_ops(data)
        if if_updated_at is not None:
            # OCC: precondition + strictly-greater revision (``_rev_stamp``) in one atomic op — already
            # monotonic vs the matched token, so no bump. A no-match means the precondition can't hold
            # (revision moved OR doc missing); Firestore raises FailedPrecondition for a last-update-time
            # precondition on a MISSING doc too (emulator-verified), so map it to PreconditionFailed.
            update.setdefault("$set", {})["_updated_at"] = _rev_stamp(if_updated_at)
            query = {"_id": path, "_updated_at": if_updated_at}

            def run_occ(coll: Any) -> None:
                if coll.update_one(query, update).matched_count == 0:
                    raise PreconditionFailed(path)

            self._append(collection_name, UpdateOne(query, update), run_occ, checked=True)
            return

        # Non-OCC: apply the operator field ops (when any), then bump _updated_at monotonically. Both run in
        # queued order in the checked/sequential path; the bump also enforces existence (a missing doc no-ops
        # both) -> NotFound, matching the Firestore batch (raises at commit, not a silent drop).
        bump = [{"$set": {"_updated_at": _monotonic_updated_at(now)}}]

        def run(coll: Any) -> None:
            if update:
                coll.update_one({"_id": path}, update)
            if coll.update_one({"_id": path}, bump).matched_count == 0:
                raise NotFound(path)

        self._append(collection_name, UpdateOne({"_id": path}, bump), run, checked=True)

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        query: Dict[str, Any] = {"_id": path}
        if if_updated_at is not None:
            query["_updated_at"] = if_updated_at

        def run(coll: Any) -> None:
            result = coll.delete_one(query)
            if if_updated_at is not None and result.deleted_count == 0:
                raise PreconditionFailed(path)

        self._append(collection_name, DeleteOne(query), run, checked=if_updated_at is not None)

    def commit(self) -> None:
        by_collection: Dict[str, list] = defaultdict(list)
        for collection_name, op, run, checked in self._ops:
            by_collection[collection_name].append((op, run, checked))
        for collection_name, ops in by_collection.items():
            coll = self._store._db[collection_name]
            if any(checked for _, _, checked in ops):
                # Sequential in queued order so precondition/update ops are individually checkable.
                for _, run, _ in ops:
                    run(coll)
            else:
                # Ordered: within one collection, queued writes to the SAME document must apply in order
                # (a set then update, or set then delete) — ordered=False lets Mongo reorder and lose the
                # later write or resurrect a deleted doc.
                coll.bulk_write([op for op, _, _ in ops], ordered=True)
        self._ops = []


class _MongoTransaction:
    """Neutral transaction handle bound to a replica-set session."""

    def __init__(self, store: "MongoDocumentStore", session: Any):
        self._store = store
        self._session = session

    def get(self, path: str) -> StoredDocument:
        return self._store._get(path, session=self._session)

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._store._set(path, data, merge=merge, session=self._session)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        self._store._update(path, data, if_updated_at=if_updated_at, session=self._session)

    def create(self, path: str, data: Dict[str, Any]) -> None:
        self._store._create(path, data, session=self._session)

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._store._delete(path, if_updated_at=if_updated_at, session=self._session)


class MongoDocumentStore:
    """``DocumentStore`` backed by MongoDB (pymongo, sync)."""

    def __init__(self, uri: Optional[str] = None, db_name: str = "omi", client: Any = None):
        # tz_aware=True so BSON datetimes decode as timezone-aware UTC (PyMongo defaults to naive).
        # Stored timestamps (_now() is aware) then compare cleanly against aware values at the callers
        # (lease/admission/stale checks) instead of raising "can't compare naive and aware" TypeErrors.
        #
        # Bound server selection and connect so an unreachable/degraded Mongo fails fast (seconds)
        # instead of hanging a request worker on PyMongo's 30s default server-selection. Per-read
        # deadlines are the port's get(timeout=) -> maxTimeMS; socketTimeoutMS is deliberately left
        # UNSET so a legitimately long operation is not killed mid-flight. Tunable via env.
        if client is not None:
            self._mongo_client = client
        else:
            self._mongo_client = MongoClient(
                uri,
                tz_aware=True,
                serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")),
                connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000")),
            )
        self._db = self._mongo_client[db_name]

    def close(self) -> None:
        """Release the MongoClient (its connection pool). Called on store reset to avoid leaking
        connections across repeated test resets."""
        self._mongo_client.close()

    # --- internal ops (shared by the public surface and the transaction handle) ---
    def _get(
        self,
        path: str,
        *,
        fields: Optional[Sequence[str]] = None,
        session: Any = None,
        timeout: Optional[float] = None,
    ) -> StoredDocument:
        collection_name, _, _ = _doc_meta(path)
        projection = {"d." + field: 1 for field in fields} if fields is not None else None
        # ``timeout`` (seconds) -> Mongo ``maxTimeMS`` so a slow server-side read aborts at the
        # deadline instead of holding the worker until the (much larger) socket timeout.
        kw: Dict[str, Any] = {} if timeout is None else {"max_time_ms": int(timeout * 1000)}
        doc = self._db[collection_name].find_one({"_id": path}, projection, session=session, **kw)
        if not doc:
            return StoredDocument.missing(path)
        return _to_record(doc, path)

    def _bump_updated_at(self, collection: Any, path: str, now: datetime, session: Any) -> None:
        # Strictly-increasing per-doc revision for an operator-based write, which cannot express $max in
        # update-operator syntax. A second pipeline update reads the just-written value and bumps it to
        # max(now, prev+1ms) so repeatable merge/update writes never collide on _updated_at (cubic 10887
        # mongo.py:161). Runs in the same session, so inside a transaction it is atomic with the write.
        collection.update_one({"_id": path}, [{"$set": {"_updated_at": _monotonic_updated_at(now)}}], session=session)

    def _set(self, path: str, data: Dict[str, Any], *, merge: bool = False, session: Any = None) -> None:
        collection_name, parent, key = _doc_meta(path)
        collection = self._db[collection_name]
        now = _now()
        if merge:
            # Operator-based merge (dotted $set / $inc / array ops) cannot compute a monotonic _updated_at
            # in one update, so stamp it via a second pipeline bump (below) rather than a colliding raw now.
            update: Dict[str, Any] = _build_update_ops(data)
            update.setdefault("$setOnInsert", {}).update({"_parent": parent, "_key": key, "_created_at": now})
            collection.update_one({"_id": path}, update, upsert=True, session=session)
            self._bump_updated_at(collection, path, now, session)
            return
        # merge=False -> full payload replace via a pipeline update: ``$set`` the whole ``d`` field
        # (non-merge semantics), a monotonic ``_updated_at`` (strictly increasing per doc), and keep an
        # immutable ``_created_at`` with ``$ifNull`` (pipeline updates have no ``$setOnInsert``) (cubic
        # PR 10887 #1 + mongo.py:161). Any transforms (rare on a non-merge set) apply right after.
        plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
        collection.update_one(
            {"_id": path},
            [
                {
                    "$set": {
                        # $literal so ``d`` REPLACES (a pipeline $set of a bare object deep-MERGES into the
                        # existing d — non-merge semantics need a literal replacement); it also keeps any
                        # $-prefixed payload keys literal instead of evaluating them as field paths.
                        "d": {"$literal": plain},
                        "_parent": parent,
                        "_key": key,
                        "_updated_at": _monotonic_updated_at(now),
                        "_created_at": {"$ifNull": ["$_created_at", now]},
                    }
                }
            ],
            upsert=True,
            session=session,
        )
        transforms = {k: v for k, v in data.items() if _is_sentinel(v)}
        if transforms:
            collection.update_one({"_id": path}, _build_update_ops(transforms), session=session)

    def _update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None, session: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        collection = self._db[collection_name]
        now = _now()
        update = _build_update_ops(data)
        # ``update`` requires an existing document (the Firestore reference adapter raises NotFound
        # otherwise). Mongo's update_one silently no-ops on no match, so translate matched_count==0
        # into the neutral NotFound to preserve parity across backends.
        if if_updated_at is not None:
            # Optimistic-concurrency precondition (neutral LastUpdateOption): only apply if the stored
            # revision still matches. ``_rev_stamp`` writes a strictly-greater revision in the SAME atomic
            # update, so this path is already monotonic (the new value > the matched token) — no bump needed.
            # A no-match means the precondition cannot hold — whether the revision moved (stale) OR the
            # document is missing — and Firestore raises FailedPrecondition for a last-update-time precondition
            # on a MISSING doc too (verified against the emulator), superseding ADR-0045's existence-probe.
            update.setdefault("$set", {})["_updated_at"] = _rev_stamp(if_updated_at)
            result = collection.update_one({"_id": path, "_updated_at": if_updated_at}, update, session=session)
            if result.matched_count == 0:
                raise PreconditionFailed(path)
            return
        # Non-OCC update: the operator write can't compute a monotonic _updated_at inline, so apply the field
        # ops (when any), then bump _updated_at to max(now, prev+1ms) via a pipeline (cubic 10887 mongo.py:161).
        # The bump also enforces existence: on a missing doc both the ops and the bump no-op -> NotFound.
        if update:
            collection.update_one({"_id": path}, update, session=session)
        result = collection.update_one({"_id": path}, [{"$set": {"_updated_at": _monotonic_updated_at(now)}}], session=session)
        if result.matched_count == 0:
            raise NotFound(path)

    def _delete(self, path: str, *, if_updated_at: Any = None, session: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        if if_updated_at is not None:
            # Precondition delete: remove only the revision the caller read. A no-match means the row
            # changed or is already gone — either way the caller's read-modify-delete lost the race,
            # so surface PreconditionFailed (parity with a Firestore delete carrying LastUpdateOption).
            result = self._db[collection_name].delete_one(
                {"_id": path, "_updated_at": if_updated_at}, session=session
            )
            if result.deleted_count == 0:
                raise PreconditionFailed(path)
            return
        self._db[collection_name].delete_one({"_id": path}, session=session)

    # --- public port surface ---
    def get(
        self, path: str, *, fields: Optional[Sequence[str]] = None, timeout: Optional[float] = None
    ) -> StoredDocument:
        return self._get(path, fields=fields, timeout=timeout)

    def exists(self, path: str) -> bool:
        collection_name, _, _ = _doc_meta(path)
        return self._db[collection_name].count_documents({"_id": path}, limit=1) > 0

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._set(path, data, merge=merge)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        self._update(path, data, if_updated_at=if_updated_at)

    def create(self, path: str, data: Dict[str, Any]) -> None:
        self._create(path, data)

    def _create(self, path: str, data: Dict[str, Any], *, session: Any = None) -> None:
        collection_name, parent, key = _doc_meta(path)
        plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
        now = _now()
        document = {"_id": path, "_parent": parent, "_key": key, "_updated_at": now, "_created_at": now, "d": plain}
        try:
            self._db[collection_name].insert_one(document, session=session)
        except DuplicateKeyError as exc:
            raise AlreadyExists(path) from exc
        transforms = {k: v for k, v in data.items() if _is_sentinel(v)}
        if transforms:
            self._db[collection_name].update_one(
                {"_id": path}, _build_update_ops(transforms), session=session
            )

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._delete(path, if_updated_at=if_updated_at)

    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
        start_after: Optional[Dict[str, Any]] = None,
    ) -> List[StoredDocument]:
        mongo_filter = self._filter(collection, filters)
        # order_by is a single field name (str) or a list of (field, direction) tuples.
        specs = [(order_by, direction)] if isinstance(order_by, str) else list(order_by or [])
        # Firestore's order_by returns ONLY documents that have every ordered field; a doc missing one is
        # excluded. Mongo's sort instead includes it (a missing field sorts as null/first). Add an
        # existence predicate per ordered payload field so both backends return the same rows (cubic
        # PR 10887, mongo.py:455). ``__name__`` maps to ``_id`` which always exists. An $and keeps this
        # from colliding with any existing predicate/keyset on the same field.
        exists_clauses = [{"d." + f: {"$exists": True}} for f, _ in specs if f != "__name__"]
        if exists_clauses:
            mongo_filter = {"$and": [mongo_filter, *exists_clauses]}
        if start_after is not None:
            cursor_id = f"{collection}/{start_after['id']}"
            # Composite keyset (cubic PR 10887 #4/#5/#10/#11): ``values`` aligns with the REAL (payload)
            # order fields; a trailing ``__name__`` (Firestore's document-name token) or no order is the
            # ``_id`` tiebreak — in Mongo the document name lives in ``_id`` (the full path), never a
            # payload field. Backward-compat with the single-field ``{"value": v}`` shape.
            values = start_after.get("values")
            if values is None:
                values = [start_after["value"]] if "value" in start_after else []
            real = [(f, d) for f, d in specs if f != "__name__"]
            name_dir = next((d for f, d in specs if f == "__name__"), (real[-1][1] if real else "asc"))
            # Strictly-after, lexicographically: OR of (all prior fields equal AND this field strictly
            # after), ending with the _id tiebreak.
            ors: List[Dict[str, Any]] = []
            prefix: List[Dict[str, Any]] = []
            for i, (f, d) in enumerate(real):
                op = "$gt" if d == "asc" else "$lt"
                v = values[i] if i < len(values) else None
                step = {"d." + f: {op: v}}
                ors.append({"$and": prefix + [step]} if prefix else step)
                prefix = prefix + [{"d." + f: v}]
            id_op = "$gt" if name_dir == "asc" else "$lt"
            id_step = {"_id": {id_op: cursor_id}}
            ors.append({"$and": prefix + [id_step]} if prefix else id_step)
            keyset = ors[0] if len(ors) == 1 else {"$or": ors}
            mongo_filter = {"$and": [mongo_filter, keyset]}
        projection = {"d." + field: 1 for field in fields} if fields is not None else None
        cursor = self._db[_collection_name(collection)].find(mongo_filter, projection, session=None)
        if specs:
            # Map ``__name__`` order to _id (the document name); other fields sort by their payload key.
            # Append an _id tiebreak only when _id is not already an order key (mirrors Firestore's
            # implicit __name__ ordering) so tie order is stable across pages.
            sort_spec = [("_id" if f == "__name__" else "d." + f, ASCENDING if d == "asc" else DESCENDING) for f, d in specs]
            if not any(f == "__name__" for f, _ in specs):
                sort_spec.append(("_id", ASCENDING if specs[-1][1] == "asc" else DESCENDING))
            cursor = cursor.sort(sort_spec)
        elif start_after is not None:
            # No order field but a keyset cursor: order by _id so the document-name pagination is stable.
            cursor = cursor.sort([("_id", ASCENDING)])
        if offset is not None:
            cursor = cursor.skip(offset)
        if limit is not None:
            cursor = cursor.limit(limit)
        return [_to_record(doc, doc["_id"]) for doc in cursor]

    @staticmethod
    def _filter(collection: str, filters: Optional[Iterable[Filter]]) -> Dict[str, Any]:
        mongo_filter: Dict[str, Any] = {"_parent": collection}
        for field, op, value in filters or ():
            if field == "__name__":
                # Document-name filter: compare the full-path _id, not a payload field (cubic PR 10887 #3
                # — a d.__name__ predicate matched nothing, undercounting e.g. monthly chat usage). For
                # in/not-in the value is a LIST of ids -> a list of full-path _ids ($in/$nin need an array;
                # f"{collection}/{list}" stringified the whole list and Mongo rejected it — cubic firestore.py:276 sibling).
                if op in ("in", "not-in"):
                    mongo_filter.setdefault("_id", {})[_OP[op]] = [f"{collection}/{v}" for v in value]
                else:
                    mongo_filter.setdefault("_id", {})[_OP[op]] = f"{collection}/{value}"
            elif op == "array_contains":
                # Mongo matches an array field against a scalar by membership: {field: value}
                # selects docs whose array field contains value (mirrors Firestore array_contains).
                mongo_filter["d." + field] = value
            else:
                clause = mongo_filter.setdefault("d." + field, {})
                clause[_OP[op]] = value
                if op in ("!=", "not-in"):
                    # Firestore != / not-in exclude documents where the field is ABSENT; Mongo's
                    # $ne/$nin would otherwise MATCH a missing field, over-returning rows. Require the
                    # field to exist so the row set matches Firestore (cubic PR 10887).
                    clause["$exists"] = True
        return mongo_filter

    def count(self, collection: str, *, filters: Optional[Iterable[Filter]] = None) -> int:
        return self._db[_collection_name(collection)].count_documents(self._filter(collection, filters))

    def query_group(
        self,
        group: str,
        *,
        filters: Optional[Iterable[Filter]] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[str] = None,
    ) -> List[StoredDocument]:
        # A collection-group query is the whole Mongo collection named after the leaf (``group``),
        # with NO ``_parent`` scope — docs from every parent live there already (see the path model).
        mongo_filter: Dict[str, Any] = {}
        for field, op, value in filters or ():
            if field == "__name__":
                # In a collection group _id already IS the full document path (Firestore __name__).
                mongo_filter.setdefault("_id", {})[_OP[op]] = value
            elif op == "array_contains":
                mongo_filter["d." + field] = value
            else:
                clause = mongo_filter.setdefault("d." + field, {})
                clause[_OP[op]] = value
                if op in ("!=", "not-in"):
                    clause["$exists"] = True  # exclude missing-field docs, matching Firestore != / not-in
        specs = [(order_by, direction)] if isinstance(order_by, str) else list(order_by or [])
        # A __name__ order on a collection group is the implicit document-name (_id) keyset — strip it so
        # it doesn't count as an "explicit order" that conflicts with start_after (cubic PR 10887 #2).
        specs = [(f, d) for f, d in specs if f != "__name__"]
        if start_after is not None:
            if specs:
                # The document-name keyset supplies a single position; it cannot combine with an explicit
                # order_by (parity with the Firestore adapter, cubic PR 10887 A7).
                raise NotImplementedError(
                    "query_group start_after (document-name keyset) does not support combining with an explicit order_by"
                )
            # Document-name keyset: ``_id`` is the full logical path (mirrors Firestore __name__). MERGE
            # the ``$gt`` into any existing ``_id`` range from a __name__ filter — reassigning the whole
            # dict dropped that bound, so later pages escaped the requested name range (cubic PR 10887
            # mongo.py:541).
            mongo_filter.setdefault("_id", {})["$gt"] = start_after
        cursor = self._db[group].find(mongo_filter)
        if specs:
            sort_spec = [("d." + f, ASCENDING if d == "asc" else DESCENDING) for f, d in specs]
            sort_spec.append(("_id", ASCENDING if specs[-1][1] == "asc" else DESCENDING))
            cursor = cursor.sort(sort_spec)
        else:
            # No explicit order_by: sort by ``_id`` (full path) ascending, matching Firestore's
            # implicit __name__ order so a keyset ``start_after`` pages consistently from page one.
            cursor = cursor.sort([("_id", ASCENDING)])
        if offset is not None:
            cursor = cursor.skip(offset)
        if limit is not None:
            cursor = cursor.limit(limit)
        return [_to_record(doc, doc["_id"]) for doc in cursor]

    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]:
        if not ids:
            return []
        full_ids = [f"{collection}/{doc_id}" for doc_id in ids]
        found = {doc["_id"]: doc for doc in self._db[_collection_name(collection)].find({"_id": {"$in": full_ids}})}
        records = []
        for doc_id in ids:  # deterministic order matching the input ids (matches the reference adapter)
            doc = found.get(f"{collection}/{doc_id}")
            if doc is not None:
                records.append(_to_record(doc, doc["_id"]))
        return records

    def list_ids(self, collection: str) -> List[str]:
        cursor = self._db[_collection_name(collection)].find({"_parent": collection}, {"_key": 1})
        return [doc["_key"] for doc in cursor]

    def delete_recursive(self, path: str) -> None:
        """Delete the document at ``path`` and every descendant.

        Descendants live in other Mongo collections (one per leaf name), keyed by a full-path
        ``_id`` that starts with ``path + "/"``. So this removes ``_id == path`` plus every
        ``_id`` under that prefix, across all collections.
        """
        prefix = re.compile("^" + re.escape(path) + "/")
        for collection_name in self._db.list_collection_names():
            self._db[collection_name].delete_many({"$or": [{"_id": path}, {"_id": {"$regex": prefix}}]})

    def list_subcollections(self, doc_path: str) -> List[str]:
        """Return the immediate child collection names under a document (Firestore
        ``DocumentReference.collections()``). A subcollection ``{doc_path}/{name}`` holds docs whose
        ``_parent`` is exactly that collection path, so the distinct one-segment-deeper ``_parent``
        values name the subcollections."""
        base_depth = len(doc_path.split("/"))
        prefix = re.compile("^" + re.escape(doc_path) + "/")
        names: set[str] = set()
        for collection_name in self._db.list_collection_names():
            for parent in self._db[collection_name].distinct("_parent", {"_parent": {"$regex": prefix}}):
                segments = str(parent).split("/")
                if len(segments) == base_depth + 1:  # a direct subcollection, not a nested one
                    names.add(segments[-1])
        return sorted(names)

    def run_transaction(self, fn: Callable[[_MongoTransaction], Any], *, attempts: int = 3) -> Any:
        """Run ``fn`` inside a replica-set transaction.

        ``with_transaction`` owns commit-retry on transient/​unknown-commit errors (its own bounded
        deadline), so ``attempts`` is accepted for port symmetry but delegated to the driver.
        """
        with self._mongo_client.start_session() as session:
            return session.with_transaction(lambda s: fn(_MongoTransaction(self, s)))

    def batch(self) -> _MongoBatch:
        return _MongoBatch(self)


__all__ = ["MongoDocumentStore"]
