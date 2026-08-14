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

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from pymongo import ASCENDING, DESCENDING, DeleteOne, MongoClient, ReplaceOne, UpdateOne
from pymongo.errors import DuplicateKeyError

from ..errors import AlreadyExists, NotFound, PreconditionFailed
from ..records import StoredDocument
from ..sentinels import DELETE, SERVER_TIMESTAMP, ArrayRemove, ArrayUnion, Increment
from ..ports import Filter

# ``array_contains_any`` maps to ``$in``: on an array-valued field Mongo's $in matches when ANY array
# element is in the given list (mirrors Firestore array_contains_any). ``not-in`` -> ``$nin``.
_OP = {
    "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte", "in": "$in", "==": "$eq", "!=": "$ne",
    "not-in": "$nin", "array_contains_any": "$in",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    def _append(self, collection_name: str, op: Any, run: Callable[[Any], None], *, precond: bool = False) -> None:
        self._ops.append((collection_name, op, run, precond))

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        collection_name, parent, key = _doc_meta(path)
        if merge:
            update: Dict[str, Any] = _build_update_ops(data)
            update.setdefault("$set", {})["_updated_at"] = _now()
            update.setdefault("$setOnInsert", {}).update({"_parent": parent, "_key": key})
            self._append(
                collection_name,
                UpdateOne({"_id": path}, update, upsert=True),
                lambda coll: coll.update_one({"_id": path}, update, upsert=True),
            )
        else:
            plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
            document = {"_id": path, "_parent": parent, "_key": key, "_updated_at": _now(), "d": plain}
            self._append(
                collection_name,
                ReplaceOne({"_id": path}, document, upsert=True),
                lambda coll: coll.replace_one({"_id": path}, document, upsert=True),
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

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        update = _build_update_ops(data)
        update.setdefault("$set", {})["_updated_at"] = _now()
        query: Dict[str, Any] = {"_id": path}
        if if_updated_at is not None:
            query["_updated_at"] = if_updated_at

        def run(coll: Any) -> None:
            result = coll.update_one(query, update)
            if if_updated_at is not None and result.matched_count == 0:
                raise PreconditionFailed(path)

        self._append(collection_name, UpdateOne(query, update), run, precond=if_updated_at is not None)

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        query: Dict[str, Any] = {"_id": path}
        if if_updated_at is not None:
            query["_updated_at"] = if_updated_at

        def run(coll: Any) -> None:
            result = coll.delete_one(query)
            if if_updated_at is not None and result.deleted_count == 0:
                raise PreconditionFailed(path)

        self._append(collection_name, DeleteOne(query), run, precond=if_updated_at is not None)

    def commit(self) -> None:
        by_collection: Dict[str, list] = defaultdict(list)
        for collection_name, op, run, precond in self._ops:
            by_collection[collection_name].append((op, run, precond))
        for collection_name, ops in by_collection.items():
            coll = self._store._db[collection_name]
            if any(precond for _, _, precond in ops):
                # Sequential in queued order so precondition ops are individually checkable.
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
        self._mongo_client = client if client is not None else MongoClient(uri, tz_aware=True)
        self._db = self._mongo_client[db_name]

    def close(self) -> None:
        """Release the MongoClient (its connection pool). Called on store reset to avoid leaking
        connections across repeated test resets."""
        self._mongo_client.close()

    # --- internal ops (shared by the public surface and the transaction handle) ---
    def _get(self, path: str, *, fields: Optional[Sequence[str]] = None, session: Any = None) -> StoredDocument:
        collection_name, _, _ = _doc_meta(path)
        projection = {"d." + field: 1 for field in fields} if fields is not None else None
        doc = self._db[collection_name].find_one({"_id": path}, projection, session=session)
        if not doc:
            return StoredDocument.missing(path)
        return _to_record(doc, path)

    def _set(self, path: str, data: Dict[str, Any], *, merge: bool = False, session: Any = None) -> None:
        collection_name, parent, key = _doc_meta(path)
        collection = self._db[collection_name]
        if merge:
            update: Dict[str, Any] = _build_update_ops(data)
            update.setdefault("$set", {})["_updated_at"] = _now()
            update.setdefault("$setOnInsert", {}).update({"_parent": parent, "_key": key})
            collection.update_one({"_id": path}, update, upsert=True, session=session)
            return
        # merge=False -> full document replace. Plain fields form the payload; any transforms
        # (rare on a non-merge set) are applied right after so their semantics still hold.
        plain = {k: v for k, v in data.items() if not _is_sentinel(v)}
        document = {"_id": path, "_parent": parent, "_key": key, "_updated_at": _now(), "d": plain}
        collection.replace_one({"_id": path}, document, upsert=True, session=session)
        transforms = {k: v for k, v in data.items() if _is_sentinel(v)}
        if transforms:
            collection.update_one({"_id": path}, _build_update_ops(transforms), session=session)

    def _update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None, session: Any = None) -> None:
        collection_name, _, _ = _doc_meta(path)
        update = _build_update_ops(data)
        update.setdefault("$set", {})["_updated_at"] = _now()
        # ``update`` requires an existing document (the Firestore reference adapter raises NotFound
        # otherwise). Mongo's update_one silently no-ops on no match, so translate matched_count==0
        # into the neutral NotFound to preserve parity across backends.
        query: Dict[str, Any] = {"_id": path}
        if if_updated_at is not None:
            # Optimistic-concurrency precondition (neutral LastUpdateOption): only apply if the stored
            # revision still matches. A no-match then means either the revision moved (PreconditionFailed)
            # or the document is gone (NotFound) — distinguish by a bare existence probe, matching
            # Firestore, which raises FailedPrecondition on a stale revision and NotFound on a missing doc.
            query["_updated_at"] = if_updated_at
        result = self._db[collection_name].update_one(query, update, session=session)
        if result.matched_count == 0:
            if if_updated_at is not None and self._db[collection_name].count_documents(
                {"_id": path}, limit=1, session=session
            ):
                raise PreconditionFailed(path)
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
    def get(self, path: str, *, fields: Optional[Sequence[str]] = None) -> StoredDocument:
        return self._get(path, fields=fields)

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
        document = {"_id": path, "_parent": parent, "_key": key, "_updated_at": _now(), "d": plain}
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
        if start_after is not None:
            cursor_id = f"{collection}/{start_after['id']}"
            if not specs:
                # No explicit order: keyset purely by document name (_id), ascending — mirrors the
                # Firestore adapter's __name__-only cursor (cubic PR 10887 A6; specs[0] used to IndexError).
                keyset = {"_id": {"$gt": cursor_id}}
            else:
                # Keyset is single-field. Full-path _id tiebreak mirrors Firestore __name__, so ties on
                # the order_by field neither skip nor duplicate a row.
                keyset_field, keyset_dir = specs[0]
                op = "$gt" if keyset_dir == "asc" else "$lt"
                field_key = "d." + keyset_field
                keyset = {
                    "$or": [
                        {field_key: {op: start_after["value"]}},
                        {"$and": [{field_key: start_after["value"]}, {"_id": {op: cursor_id}}]},
                    ]
                }
            mongo_filter = {"$and": [mongo_filter, keyset]}
        projection = {"d." + field: 1 for field in fields} if fields is not None else None
        cursor = self._db[_collection_name(collection)].find(mongo_filter, projection, session=None)
        if specs:
            # Always tiebreak by _id (mirrors Firestore's implicit __name__ ordering) so tie order is
            # stable across pages — the keyset cursor depends on that consistency for single-field.
            sort_spec = [("d." + f, ASCENDING if d == "asc" else DESCENDING) for f, d in specs]
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
            if op == "array_contains":
                # Mongo matches an array field against a scalar by membership: {field: value}
                # selects docs whose array field contains value (mirrors Firestore array_contains).
                mongo_filter["d." + field] = value
            else:
                mongo_filter.setdefault("d." + field, {})[_OP[op]] = value
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
            if op == "array_contains":
                mongo_filter["d." + field] = value
            else:
                mongo_filter.setdefault("d." + field, {})[_OP[op]] = value
        specs = [(order_by, direction)] if isinstance(order_by, str) else list(order_by or [])
        if start_after is not None:
            if specs:
                # The document-name keyset supplies a single position; it cannot combine with an explicit
                # order_by (parity with the Firestore adapter, cubic PR 10887 A7).
                raise NotImplementedError(
                    "query_group start_after (document-name keyset) does not support combining with an explicit order_by"
                )
            # Document-name keyset: ``_id`` is the full logical path (mirrors Firestore __name__).
            mongo_filter["_id"] = {"$gt": start_after}
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
