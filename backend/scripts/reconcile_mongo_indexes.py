"""Create the MongoDB secondary indexes that mirror ``firestore.indexes.json`` (ADR-0046).

The neutral store's Mongo adapter (``database/store/adapters/mongo.py``) keys every document by ``_id``
(the full logical path), scopes a collection query with ``_parent`` (the containing collection path),
and stores the payload under ``d``. Firestore auto-serves composite queries from the indexes declared
in ``firestore.indexes.json``; MongoDB does not — without matching indexes those same queries become
collection scans, so on the on-prem-default Mongo backend (ADR-0046) reads get slow at any real size.

This script reconciles that gap: for each Firestore composite index it creates the equivalent Mongo
compound index, mapping

    field ``foo`` (ASCENDING/DESCENDING)  ->  ``d.foo`` (1 / -1)
    the ``__name__`` token                ->  ``_id``   (the document name lives in _id, the full path)
    queryScope COLLECTION                 ->  prefix ``_parent: 1`` (query() always scopes by _parent)
    queryScope COLLECTION_GROUP           ->  no ``_parent`` prefix (query_group spans parents)

plus a baseline ``_parent`` index on every collection in the manifest (scoped queries that do not match
a composite still filter ``_parent``). ``create_index`` is idempotent, so the script is safe to re-run
at deploy time. Firestore stays the reference backend (ADR-0003); this only makes the Mongo path fast.

Usage:
    MONGO_URI=mongodb://mongo:27017/?replicaSet=rs0 python scripts/reconcile_mongo_indexes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


def _resolve_manifest_path() -> Path:
    """Locate ``firestore.indexes.json``. Running from the source tree it sits at the repo root
    (``parents[2]``). In the backend image the Dockerfile bundles it next to the copied ``backend/``
    tree at the WORKDIR (``parents[1]`` == ``/app``), because ``COPY backend/ .`` does not include a
    repo-root file. Without this the startup hook (main.startup_event, STORAGE_BACKEND=mongo) logged a
    manifest error and created ZERO indexes in the shipped image (cubic PR 10887 main.py:288)."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "firestore.indexes.json", here.parents[1] / "firestore.indexes.json"):
        if candidate.exists():
            return candidate
    return here.parents[2] / "firestore.indexes.json"  # canonical path; load_manifest surfaces a clear error


MANIFEST_PATH = _resolve_manifest_path()

# Indexes for scoped queries that Firestore auto-serves via single-field indexes but Mongo does not, and
# that firestore.indexes.json (composite-only) never declares — so the reconcile would otherwise leave
# them collection-scanning on the Mongo backend (cubic PR 10887 reconcile_mongo_indexes.py:92). Each
# entry is (collection, compound-keys). The hourly daily-summary / morning-notification crons query the
# top-level ``users`` collection by ``time_zone`` (get_users_for_daily_summary /
# get_users_{id,token,endpoints}_in_timezones); every doc there shares _parent="users", so a bare _parent
# index has no selectivity — the time_zone key is what turns the full scan into an index hit.
_SUPPLEMENTARY_INDEXES: List[Tuple[str, "MongoIndexKeys"]] = [
    ("users", [("_parent", 1), ("d.time_zone", 1)]),
    # get_users_endpoints_in_timezones runs a COLLECTION-GROUP query over unifiedpush_endpoints filtered
    # by time_zone (no _parent scope — the group spans users), so index d.time_zone alone; without it the
    # hourly UnifiedPush morning fan-out collection-scans every endpoint (cubic PR 10887).
    ("unifiedpush_endpoints", [("d.time_zone", 1)]),
]

# A Mongo index spec: an ordered list of (key, direction) with direction in {1, -1}.
MongoIndexKeys = List[Tuple[str, int]]

_ORDER = {"ASCENDING": 1, "DESCENDING": -1}


def firestore_index_to_mongo_keys(index: Mapping[str, Any]) -> Tuple[str, MongoIndexKeys]:
    """Map one Firestore composite index to (mongo_collection, compound_index_keys).

    ``collectionGroup`` is already the leaf collection name the Mongo adapter uses. A ``COLLECTION``
    scope prefixes ``_parent`` because ``query()`` filters ``_parent == <path>``; a ``COLLECTION_GROUP``
    scope does not. ``__name__`` maps to ``_id``; every other field to ``d.<fieldPath>``.
    """
    collection = index["collectionGroup"]
    keys: MongoIndexKeys = []
    if index.get("queryScope") == "COLLECTION":
        keys.append(("_parent", 1))
    for field in index.get("fields", []):
        path = field["fieldPath"]
        if path == "__name__":
            key = "_id"
        else:
            key = f"d.{path}"
        order = field.get("order")
        if order is None:
            # arrayConfig (CONTAINS) fields are multikey membership, not ordered; index ascending.
            direction = 1
        else:
            direction = _ORDER[order]
        keys.append((key, direction))
    return collection, keys


def _index_name(keys: MongoIndexKeys) -> str:
    """Deterministic, length-safe index name (Mongo caps generated names; compounds can be long)."""
    digest = hashlib.sha1(json.dumps(keys).encode()).hexdigest()[:12]
    return f"fsidx_{digest}"


def load_manifest(path: Path = MANIFEST_PATH) -> Mapping[str, Any]:
    return json.loads(path.read_text())


def planned_indexes(manifest: Mapping[str, Any]) -> List[Tuple[str, MongoIndexKeys, str]]:
    """Return (collection, keys, name) for every composite + a baseline ``_parent`` per collection."""
    plan: List[Tuple[str, MongoIndexKeys, str]] = []
    seen = set()
    collections = set()
    for index in manifest.get("indexes", []):
        collection, keys = firestore_index_to_mongo_keys(index)
        collections.add(collection)
        signature = (collection, tuple(keys))
        if signature in seen:
            continue
        seen.add(signature)
        plan.append((collection, keys, _index_name(keys)))
    for collection in sorted(collections):
        keys = [("_parent", 1)]
        signature = (collection, tuple(keys))
        if signature not in seen:
            seen.add(signature)
            plan.append((collection, keys, _index_name(keys)))
    # Supplementary scoped-query indexes not derivable from the composite manifest (e.g. users by
    # time_zone), plus a _parent baseline for each such collection when the manifest didn't already add one.
    for collection, keys in _SUPPLEMENTARY_INDEXES:
        for spec in (keys, [("_parent", 1)]):
            signature = (collection, tuple(spec))
            if signature not in seen:
                seen.add(signature)
                plan.append((collection, spec, _index_name(spec)))
    return plan


# Unique indexes: not a performance mirror of firestore.indexes.json but an INVARIANT the database
# enforces, so they are declared separately and created separately (ADR-0085).
#
# Measured on both backends: the create path for an action item reads by idempotency key inside a
# transaction and then writes. Firestore LOCKS what a transaction reads, so a concurrent writer gets
# 409 Aborted and only one row is created. Mongo takes no read lock: both transactions commit and the
# user ends up with two identical tasks. The read being inside the transaction was never what protected
# the invariant — the lock was — so on our default backend it has to be the index.
#
# The filter is where the care is. It CANNOT simply be ``completed == false``: the retire path marks
# ``deleted: true, completed: false`` and the create path deliberately makes a NEW item with the same
# key once a row is retired, so a retired row still holding the key would collide with a create the
# product makes on purpose. Mongo's partialFilterExpression admits equality, $exists, the ordering
# comparators, $type, $and/$or/$in — but NOT $exists:false and NOT $ne — so "and not deleted" is not
# expressible. It is handled in the data instead: the retire path now clears the key, and the filter
# requires the key to be a string, which a cleared (null) one is not.
_UNIQUE_INDEXES: List[Tuple[str, "MongoIndexKeys", Dict[str, Any]]] = [
    (
        "action_items",
        [("_parent", 1), ("d.idempotency_key", 1)],
        {"d.completed": False, "d.idempotency_key": {"$exists": True, "$type": "string"}},
    ),
]


def create_unique_indexes(db: Any) -> List[str]:
    """Create the unique partial indexes. Idempotent; reports a blocking duplicate instead of dying.

    ``create_index`` raises ``DuplicateKeyError`` when the data ALREADY violates the constraint, and the
    raw pymongo message names one offending value with no context. A boot that fails that way tells an
    operator nothing about what to fix, so the duplicates are looked up and named. Creation is skipped,
    not retried: the index cannot exist until somebody resolves them, and the boot must not be blocked
    by a data problem it cannot fix itself.
    """
    from pymongo.errors import DuplicateKeyError

    ensured: List[str] = []
    for collection, keys, partial in _UNIQUE_INDEXES:
        name = f"uniq_{_index_name(keys)[6:]}"
        try:
            db[collection].create_index(keys, name=name, unique=True, partialFilterExpression=partial)
            ensured.append(f"{collection}.{name}")
        except DuplicateKeyError:
            offenders = _duplicate_groups(db, collection, keys, partial)
            print(
                f"SKIPPED unique index {collection}.{name}: the data already violates it. "
                f"Resolve these first, then restart:"
            )
            for group, count in offenders:
                print(f"  {group} -> {count} live rows")
            if not offenders:
                print("  (the duplicates were resolved between the failure and the lookup)")
    return ensured


def _duplicate_groups(
    db: Any, collection: str, keys: "MongoIndexKeys", partial: Mapping[str, Any], limit: int = 20
) -> List[Tuple[str, int]]:
    """The key groups that already have more than one matching document, so the failure can name them."""
    group_id = {key.replace(".", "_"): f"${key}" for key, _ in keys}
    pipeline = [
        {"$match": dict(partial)},
        {"$group": {"_id": group_id, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$limit": limit},
    ]
    try:
        return [
            (json.dumps(row["_id"], default=str, sort_keys=True), row["n"])
            for row in db[collection].aggregate(pipeline)
        ]
    except Exception:  # pragma: no cover - the report must never be the thing that fails
        return []


def create_planned_indexes(db: Any, plan: Optional[List[Tuple[str, MongoIndexKeys, str]]] = None) -> List[str]:
    """Create every planned index on ``db`` (a pymongo Database). Idempotent — ``create_index`` is a
    no-op when the index already exists — so this is safe to re-run every deploy/boot. Returns the
    ``collection.name`` of each index ensured."""
    plan = plan if plan is not None else planned_indexes(load_manifest())
    ensured: List[str] = []
    for collection, keys, name in plan:
        db[collection].create_index(keys, name=name, background=True)
        ensured.append(f"{collection}.{name}")
    return ensured


def reconcile_mongo_indexes(db_name: Optional[str] = None) -> List[str]:
    """Open a short-lived client from ``MONGO_URI`` and ensure every planned index. This is the entry
    the backend calls at startup (STORAGE_BACKEND=mongo) so a self-hosted Mongo deployment provisions
    its indexes without a manual step. Raises if ``MONGO_URI`` is unset."""
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise RuntimeError("MONGO_URI must be set")
    from pymongo import MongoClient  # local import so callers/--dry-run need no pymongo

    client = MongoClient(uri)
    try:
        db = client[db_name or os.getenv("MONGO_DB", "omi")]
        return create_planned_indexes(db) + create_unique_indexes(db)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Mongo indexes mirroring firestore.indexes.json")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without creating indexes")
    parser.add_argument("--db", default=os.getenv("MONGO_DB", "omi"), help="Mongo database name")
    args = parser.parse_args()

    plan = planned_indexes(load_manifest())
    print(f"{len(plan)} indexes planned from {MANIFEST_PATH.name} (db={args.db}):")
    for collection, keys, name in plan:
        print(f"  {collection}.{name}: {keys}")

    if args.dry_run:
        print("--dry-run: no indexes created")
        return

    for ensured in reconcile_mongo_indexes(db_name=args.db):
        print(f"  ensured {ensured}")
    print("done")


if __name__ == "__main__":
    main()
