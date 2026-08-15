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
from typing import Any, List, Mapping, Optional, Tuple

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
        return create_planned_indexes(client[db_name or os.getenv("MONGO_DB", "omi")])
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
