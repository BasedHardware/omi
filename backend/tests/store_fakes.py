"""In-memory ``DocumentStore`` fake for hermetic domain-module unit tests (WP2, ADR-0002).

Implements the neutral storage port over a dict keyed by full logical path. The backend adapters
have their own live contract test (``tests/contract/test_document_store_contract.py``); this fake
exists so ``database/*`` domain code migrated to the port can be unit-tested without any backend —
including the transactional paths that ``mongomock`` cannot run (it has no sessions).

Semantics mirror the port contract: neutral sentinels, dotted-key updates, collection scoping by
containing path. ``run_transaction`` runs the callback directly (a unit test asserts domain logic,
not real atomicity — parity/atomicity is covered by the live contract test).
"""

from __future__ import annotations

import copy
import itertools
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from database.store.errors import AlreadyExists, NotFound, PreconditionFailed
from database.store.records import StoredDocument
from database.store.sentinels import DELETE, SERVER_TIMESTAMP, ArrayRemove, ArrayUnion, Increment

_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "array_contains": lambda a, b: isinstance(a, (list, tuple)) and b in a,
    "not-in": lambda a, b: a not in b,
    "array_contains_any": lambda a, b: isinstance(a, (list, tuple)) and any(x in a for x in b),
}


def _set_path(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        data = data.setdefault(part, {})
    data[parts[-1]] = value


def _del_path(data: Dict[str, Any], dotted: str) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        if not isinstance(data.get(part), dict):
            return
        data = data[part]
    data.pop(parts[-1], None)


def _get_path(data: Dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


def _apply(data: Dict[str, Any], patch: Dict[str, Any]) -> None:
    for key, value in patch.items():
        if value is DELETE:
            _del_path(data, key)
        elif value is SERVER_TIMESTAMP:
            _set_path(data, key, datetime.now(timezone.utc))
        elif isinstance(value, ArrayUnion):
            current = list(_get_path(data, key) or [])
            current.extend(v for v in value.values if v not in current)
            _set_path(data, key, current)
        elif isinstance(value, ArrayRemove):
            current = list(_get_path(data, key) or [])
            _set_path(data, key, [v for v in current if v not in value.values])
        elif isinstance(value, Increment):
            _set_path(data, key, (_get_path(data, key) or 0) + value.amount)
        else:
            _set_path(data, key, value)


class _FakeBatch:
    def __init__(self, store: "FakeDocumentStore"):
        self._store = store
        self._ops: List[tuple] = []

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._ops.append(("set", path, data, merge))

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        self._ops.append(("update", path, data, if_updated_at))

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._ops.append(("delete", path, None, if_updated_at))

    def commit(self) -> None:
        for kind, path, data, extra in self._ops:
            if kind == "set":
                self._store.set(path, data, merge=extra)
            elif kind == "update":
                self._store.update(path, data, if_updated_at=extra)
            else:
                self._store.delete(path, if_updated_at=extra)
        self._ops = []


class _FakeTransaction:
    def __init__(self, store: "FakeDocumentStore"):
        self._store = store

    def get(self, path: str) -> StoredDocument:
        return self._store.get(path)

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        self._store.set(path, data, merge=merge)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        self._store.update(path, data, if_updated_at=if_updated_at)

    def create(self, path: str, data: Dict[str, Any]) -> None:
        self._store.create(path, data)

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        self._store.delete(path, if_updated_at=if_updated_at)


class FakeDocumentStore:
    """Backend-neutral in-memory document store for tests."""

    def __init__(self, *, backing: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        # ``backing`` lets a test share its own path->data dict (e.g. a Firestore-shaped fake's
        # ``.docs``) so ``document_store`` reads/writes and the injected ``db_client`` fake see the
        # same store during the D1 migration (ADR-0022). Absent → a fresh in-memory dict.
        self._docs: Dict[str, Dict[str, Any]] = backing if backing is not None else {}
        self._updated: Dict[str, datetime] = {}
        # Strictly-increasing stamps (base + counter) so a later write always has a greater revision.
        self._clock = itertools.count()

    def _stamp(self, path: str) -> None:
        self._updated[path] = datetime.now(timezone.utc) + timedelta(microseconds=next(self._clock))

    def get(self, path: str, *, fields: Optional[Sequence[str]] = None) -> StoredDocument:
        if path not in self._docs:
            return StoredDocument.missing(path)
        data = copy.deepcopy(self._docs[path])
        if fields is not None:
            data = {k: v for k, v in data.items() if k in set(fields)}
        return StoredDocument.present(path, data, updated_at=self._updated.get(path))

    def exists(self, path: str) -> bool:
        return path in self._docs

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None:
        # Resolve neutral sentinels (ArrayUnion/DELETE/SERVER_TIMESTAMP/...) like the real adapters,
        # merging shallowly at the top level when merge=True.
        target = self._docs[path] if (merge and path in self._docs) else {}
        _apply(target, copy.deepcopy(data))
        self._docs[path] = target
        self._stamp(path)

    def create(self, path: str, data: Dict[str, Any]) -> None:
        if path in self._docs:
            raise AlreadyExists(path)
        document: Dict[str, Any] = {}
        _apply(document, copy.deepcopy(data))
        self._docs[path] = document
        self._stamp(path)

    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None:
        # ``update`` requires an existing document — it does NOT upsert (that is ``set``). The
        # Firestore reference adapter raises NotFound on a missing doc and the Mongo adapter matches
        # via matched_count==0, so the fake raises here too to stay representative of both backends.
        if path not in self._docs:
            raise NotFound(path)
        # ``if_updated_at`` optimistic-concurrency precondition: a stale revision raises
        # PreconditionFailed, mirroring both adapters (LastUpdateOption / _updated_at conditional).
        if if_updated_at is not None and self._updated.get(path) != if_updated_at:
            raise PreconditionFailed(path)
        _apply(self._docs[path], copy.deepcopy(data))
        self._stamp(path)

    def delete(self, path: str, *, if_updated_at: Any = None) -> None:
        if if_updated_at is not None and self._updated.get(path) != if_updated_at:
            # Precondition delete on a changed/missing revision lost the race (parity with the adapters).
            raise PreconditionFailed(path)
        self._docs.pop(path, None)
        self._updated.pop(path, None)

    # Session-aware private aliases so the neutral db_client facade's transaction (which threads
    # ``session=`` to the store) can run over this fake session-less — hermetic, no real atomicity.
    def _get(self, path: str, *, fields: Optional[Sequence[str]] = None, session: Any = None) -> StoredDocument:
        return self.get(path, fields=fields)

    def _set(self, path: str, data: Dict[str, Any], *, merge: bool = False, session: Any = None) -> None:
        self.set(path, data, merge=merge)

    def _update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None, session: Any = None) -> None:
        self.update(path, data, if_updated_at=if_updated_at)

    def _create(self, path: str, data: Dict[str, Any], *, session: Any = None) -> None:
        self.create(path, data)

    def _delete(self, path: str, *, if_updated_at: Any = None, session: Any = None) -> None:
        self.delete(path, if_updated_at=if_updated_at)

    def query(
        self,
        collection: str,
        *,
        filters: Optional[Iterable] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
        start_after: Optional[Dict[str, Any]] = None,
    ) -> List[StoredDocument]:
        rows = self._matching_rows(collection, filters)
        reverse = direction == "desc"
        if order_by is None or isinstance(order_by, str):
            if order_by is not None:
                # (value, path) key so the id tiebreak matches the adapters' keyset ordering.
                rows.sort(key=lambda pd: (pd[1].get(order_by), pd[0]), reverse=reverse)
            if start_after is not None:
                cursor_key = (start_after["value"], f"{collection}/{start_after['id']}")
                rows = [
                    pd
                    for pd in rows
                    if (
                        (pd[1].get(order_by), pd[0]) < cursor_key
                        if reverse
                        else (pd[1].get(order_by), pd[0]) > cursor_key
                    )
                ]
        else:
            # Multi-field order_by: [(field, direction), ...]. ``__name__`` means the document id
            # (its full path), matching the adapters. Stable sorts applied most-significant last over
            # a composite key; the keyset ``start_after`` filters on (primary field value, id).
            def _sort_val(pd, field):
                return pd[0] if field == "__name__" else pd[1].get(field)

            rows.sort(key=lambda pd: pd[0])
            for field, fdir in reversed(list(order_by)):
                rows.sort(key=lambda pd, f=field: _sort_val(pd, f), reverse=(fdir == "desc"))
            if start_after is not None:
                primary_field, primary_dir = order_by[0]
                primary_reverse = primary_dir == "desc"
                cursor_key = (start_after["value"], f"{collection}/{start_after['id']}")
                rows = [
                    pd
                    for pd in rows
                    if (
                        (_sort_val(pd, primary_field), pd[0]) < cursor_key
                        if primary_reverse
                        else (_sort_val(pd, primary_field), pd[0]) > cursor_key
                    )
                ]
        if offset is not None:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        if fields is not None:
            keep = set(fields)
            rows = [(p, {k: v for k, v in d.items() if k in keep}) for p, d in rows]
        return [StoredDocument.present(p, copy.deepcopy(d), updated_at=self._updated.get(p)) for p, d in rows]

    def _matching_rows(self, collection: str, filters: Optional[Iterable]) -> List[tuple]:
        rows = [(p, d) for p, d in self._docs.items() if p.rsplit("/", 1)[0] == collection]
        for field, op, value in filters or ():
            if "." in field:
                # Nested (dotted) field path, e.g. ``subject.kind`` — resolve like the real
                # adapters so domain queries filtering on embedded fields are emulated.
                rows = [
                    (p, d)
                    for p, d in rows
                    if (nested := _get_path(d, field)) is not None and _OPS[op](nested, value)
                ]
            else:
                rows = [(p, d) for p, d in rows if field in d and _OPS[op](d[field], value)]
        return rows

    def count(self, collection: str, *, filters: Optional[Iterable] = None) -> int:
        return len(self._matching_rows(collection, filters))

    def query_group(
        self,
        group: str,
        *,
        filters: Optional[Iterable] = None,
        order_by: Optional[str] = None,
        direction: str = "asc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[str] = None,
    ) -> List[StoredDocument]:
        # Collection-group scope: every doc whose containing collection's leaf name == ``group``,
        # regardless of parent (e.g. ``users/{uid}/fair_use_state/current`` matches ``fair_use_state``).
        rows = [(p, d) for p, d in self._docs.items() if p.rsplit("/", 1)[0].rsplit("/", 1)[-1] == group]
        for field, op, value in filters or ():
            if "." in field:
                # Resolve dotted paths (e.g. ``subject.kind``) like the real adapters and ``query()``,
                # so collection-group filters on embedded fields are emulated faithfully (not top-level only).
                rows = [(p, d) for p, d in rows if (nested := _get_path(d, field)) is not None and _OPS[op](nested, value)]
            else:
                rows = [(p, d) for p, d in rows if field in d and _OPS[op](d[field], value)]
        reverse = direction == "desc"
        if isinstance(order_by, str):
            rows.sort(key=lambda pd: (pd[1].get(order_by), pd[0]), reverse=reverse)
        elif order_by is not None:
            rows.sort(key=lambda pd: pd[0])
            for field, fdir in reversed(list(order_by)):
                rows.sort(key=lambda pd, f=field: pd[1].get(f), reverse=(fdir == "desc"))
        else:
            # No explicit order_by: document-name (full path) ascending, matching Firestore's
            # implicit __name__ order so a keyset ``start_after`` pages consistently from page one.
            rows.sort(key=lambda pd: pd[0])
        if start_after is not None:
            # Document-name keyset (mirrors the adapters): resume strictly after the cursor path.
            rows = [pd for pd in rows if pd[0] > start_after]
        if offset is not None:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return [StoredDocument.present(p, copy.deepcopy(d), updated_at=self._updated.get(p)) for p, d in rows]

    def get_many(self, collection: str, ids: Sequence[str]) -> List[StoredDocument]:
        result = []
        for doc_id in ids:
            path = f"{collection}/{doc_id}"
            if path in self._docs:
                result.append(
                    StoredDocument.present(
                        path, copy.deepcopy(self._docs[path]), updated_at=self._updated.get(path)
                    )
                )
        return result

    def list_ids(self, collection: str) -> List[str]:
        return [
            path.rsplit("/", 1)[-1]
            for path in self._docs
            if path.rsplit("/", 1)[0] == collection
        ]

    def list_subcollections(self, doc_path: str) -> List[str]:
        base = doc_path.split("/")
        names = set()
        for key in self._docs:
            segs = key.split("/")
            if len(segs) > len(base) and segs[: len(base)] == base:
                names.add(segs[len(base)])
        return sorted(names)

    def delete_recursive(self, path: str) -> None:
        for key in [k for k in self._docs if k == path or k.startswith(path + "/")]:
            del self._docs[key]
            self._updated.pop(key, None)

    def run_transaction(self, fn: Callable[[_FakeTransaction], Any], *, attempts: int = 3) -> Any:
        return fn(_FakeTransaction(self))

    def batch(self) -> _FakeBatch:
        return _FakeBatch(self)


def install_fake_db_client(
    monkeypatch: Any,
    backing: Optional[Dict[str, Dict[str, Any]]] = None,
    store: Optional[Any] = None,
) -> Any:
    """Inject the neutral ``db_client`` facade over a document store for domain modules that thread
    the raw client (``from database._client import db``) under ADR-0044.

    The merge adopted upstream's ``db``/``db_client`` idiom wholesale, so ``database.*`` modules no
    longer expose a ``_store`` seam to monkeypatch; instead patch the client accessor so
    ``db.collection(...)`` / ``@transactional`` run through the facade against a store. ``store``
    accepts any port-conforming store — the default fresh ``FakeDocumentStore``, a subclass (e.g. one
    that races a concurrent delete), or the real ``MongoDocumentStore`` over mongomock for an
    end-to-end path-based run. Returns the store so tests seed/assert on it exactly as they did
    against the old ``_store`` seam."""
    from database import _client
    from database.store.firestore_facade import NeutralFirestoreClient

    # ``store`` lets a test supply a FakeDocumentStore subclass (e.g. one that races a concurrent
    # delete) and still drive it through the facade; otherwise a fresh fake is created.
    fake = store if store is not None else FakeDocumentStore(backing=backing)
    client = NeutralFirestoreClient(fake)
    monkeypatch.setattr(_client, "get_firestore_client", lambda: client)
    monkeypatch.setattr(_client, "_firestore_client", client, raising=False)
    return fake


__all__ = ["FakeDocumentStore", "install_fake_db_client"]
