"""Neutral ``db_client`` adapter — a Firestore-Client-shaped facade over the storage port (ADR-0044).

Upstream threads ``db_client`` (a ``google.cloud.firestore.Client``) through the memory/task
subsystem (``db_client.document(path)`` / ``.collection(path)`` / ``.transaction()`` / ``.get_all``).
Our on-prem port replaces raw Firestore with the neutral store port, but hand-rewriting every injected
call site is unsustainable across merges. Instead this facade exposes the small Firestore-Client
surface upstream uses, backed by ``get_document_store()`` (Mongo on-prem), so upstream code runs
verbatim. It is installed at ``database/_client.py::get_firestore_client()`` only when
``STORAGE_BACKEND != firestore``; the Firestore backend keeps the real SDK client.

Scope: this is the ONE place the port is allowed to speak Firestore's client shape (ADR-0044 amends
ADR-0004 for this injection surface); everywhere else the rule stays "use the neutral store, don't
emulate Firestore". Paths are logical ("users/{uid}/people/{pid}"); payloads are plain dicts.
"""

from __future__ import annotations

import contextlib
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from google.api_core import exceptions as _gexc

from database.store import sentinels as _neutral
from database.store.errors import AlreadyExists as _StoreAlreadyExists
from database.store.errors import NotFound as _StoreNotFound
from database.store.errors import PreconditionFailed as _StorePreconditionFailed
from database.store.ports import missing_facade_session_ops, missing_store_session_ops
from database.store.records import StoredDocument

# Google sentinels/types are only needed to RECOGNISE values upstream passes in; importing them here
# keeps the recognition in one place. Absent SDK (stubbed test env) -> the identity checks simply
# never match, which is correct for a pure-neutral payload.
try:  # pragma: no cover - import shape depends on the installed SDK
    from google.cloud import firestore as _fs
    from google.cloud.firestore_v1.transforms import ArrayRemove as _FsArrayRemove
    from google.cloud.firestore_v1.transforms import ArrayUnion as _FsArrayUnion
    from google.cloud.firestore_v1.transforms import Increment as _FsIncrement
except Exception:  # pragma: no cover
    _fs = None
    _FsArrayUnion = _FsArrayRemove = _FsIncrement = ()  # type: ignore[assignment]

# Firestore query direction constants, resolved defensively.
_DESCENDING = getattr(getattr(_fs, "Query", None), "DESCENDING", "DESCENDING") if _fs else "DESCENDING"

_AUTO_ID_ALPHABET = string.ascii_letters + string.digits


def _auto_id() -> str:
    """A Firestore-style random 20-char document id. Must be RANDOM, not derived from the collection
    path: a deterministic id makes every no-id ``document()``/``add()`` collide and overwrite the
    previous record (fair-use events, action-item creates)."""
    return "".join(secrets.choice(_AUTO_ID_ALPHABET) for _ in range(20))


def _validate_doc_id(doc_id: str) -> str:
    """Reject document ids that Firestore itself refuses, before they compose a neutral path.

    The neutral store addresses documents by a ``/``-delimited string path, so a ``/`` inside a
    single client-supplied id would split into extra segments and silently write to the WRONG
    collection/key (path injection). This mirrors Firestore's document-id contract centrally, so
    every ``collection().document(id)`` call site is defended once: non-empty, no ``/``, not ``.``
    or ``..``, not the reserved ``__*__`` form, at most 1500 bytes (Firestore's limit)."""
    if not doc_id:
        raise ValueError("A document id must not be empty")
    if "/" in doc_id:
        raise ValueError(f"Invalid document id {doc_id!r}: a document id must not contain '/'")
    if doc_id in (".", ".."):
        raise ValueError(f"Invalid document id {doc_id!r}: a document id must not be '.' or '..'")
    if doc_id.startswith("__") and doc_id.endswith("__"):
        raise ValueError(f"Invalid document id {doc_id!r}: the '__*__' form is reserved")
    if len(doc_id.encode("utf-8")) > 1500:
        raise ValueError("Invalid document id: exceeds Firestore's 1500-byte limit")
    return doc_id


# Firestore comparison op strings -> neutral store ops (ports.Filter). The store's Mongo adapter
# accepts these directly; unsupported ops surface as a clear error rather than silently mis-querying.
_OP_MAP = {
    "==": "==",
    "!=": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "in": "in",
    "not-in": "not-in",
    "array_contains": "array_contains",
    "array_contains_any": "array_contains_any",
}


def _name_filter_value(value: Any) -> Any:
    """Normalize a ``__name__`` filter bound to the bare document id the store expects.

    Firestore's ``.where('__name__', op, ref)`` passes a ``DocumentReference`` (here a ``_DocRef``),
    while the store's ``__name__`` filter compares the document id relative to the queried collection
    (the Mongo adapter builds ``f"{collection}/{value}"``). Forwarding the ``_DocRef`` object verbatim
    stringified to its object ``repr`` and matched nothing — e.g. ``user_usage``'s monthly ``__name__``
    range (`llm_usage_ref.document(...)` bounds) returned zero rows on Mongo, undercounting chat usage
    (cubic PR 10887 #8; the contract test only exercised a bare-string bound, so the seam hid it). A
    plain string id passes through unchanged. Collection-GROUP queries need the FULL path instead —
    see ``_group_name_filter_value``. A membership filter (``in``/``not-in``) carries a LIST of references,
    each of which must be normalized element-wise — leaving the list untouched made a valid Firestore
    ``.where('__name__', 'in', [ref, ...])`` match nothing on the neutral facade (cubic PR 10887 facade:350)."""
    if isinstance(value, (list, tuple)):
        return [v.id if isinstance(v, _DocRef) else v for v in value]
    return value.id if isinstance(value, _DocRef) else value


def _group_name_filter_value(value: Any) -> Any:
    """Normalize a ``__name__`` filter bound for a collection-GROUP query to the full document path.

    Unlike a scoped collection query (which the store rebuilds as ``f"{collection}/{value}"`` from a
    bare id — see ``_name_filter_value``), a collection-group query matches the document name against
    ``_id`` directly, which IS the full logical path (query_group spans parents, so there is no single
    collection to prefix). Reducing a ``_DocRef`` to its bare ``.id`` here made the group ``__name__``
    filter match nothing on Mongo (cubic PR 10887 #338, a regression from the #8 scoped-query fix). Keep
    the ``_DocRef``'s full ``.path``; a plain string path passes through unchanged."""
    if isinstance(value, (list, tuple)):
        return [v.path if isinstance(v, _DocRef) else v for v in value]
    return value.path if isinstance(value, _DocRef) else value


def _field_filter_triple(
    field_path: Any, op_string: Any, value: Any, *, name_value: Callable[[Any], Any]
) -> Tuple[Any, str, Any]:
    """Translate one Firestore field filter into the store's neutral ``(field, op, value)``."""
    op = _OP_MAP.get(op_string)
    if op is None:
        # A ``field == None`` / ``field != None`` filter: the Firestore SDK rewrites the equality
        # into the unary IS_NULL / IS_NOT_NULL operator (``op_string`` becomes a
        # ``StructuredQuery.UnaryFilter.Operator`` enum, not a string). The store adapters express
        # null matching as the neutral ``('==' | '!=', None)`` filter, so map it back — this is what
        # makes a null-equality query run on Mongo exactly as it does natively on Firestore
        # (e.g. ``get_chat_session(app_id=None)`` queries ``plugin_id == None``).
        unary = getattr(op_string, "name", None)
        if unary == "IS_NULL":
            op, value = "==", None
        elif unary == "IS_NOT_NULL":
            op, value = "!=", None
        else:
            raise NotImplementedError(f"unsupported query operator: {op_string!r}")
    if field_path == "__name__":
        value = name_value(value)
    return (field_path, op, value)


def _filter_triples(filter_obj: Any, *, name_value: Callable[[Any], Any]) -> List[Tuple[Any, str, Any]]:
    """Translate a Firestore ``FieldFilter`` **or** an AND ``BaseCompositeFilter`` into neutral triples.

    A composite carries ``.operator`` + ``.filters`` and none of the FieldFilter attributes, so reading
    ``field_path``/``op_string``/``value`` off it yields None on all three — which is how a composite
    used to reach the operator map as ``None`` and raise a misleading "unsupported query operator:
    None". Every multi-condition app query is built this way (``database/apps.py``, 19 call sites), so
    the whole marketplace surface answered 500 on Mongo while working on Firestore.

    The port's ``filters`` argument is an implicit AND, so an AND composite flattens into it —
    recursively, because Firestore allows nesting. OR has no equivalent on the port (it would need a
    disjunctive query the adapters do not express), so it is rejected explicitly: a silently dropped
    OR would widen a query instead of narrowing it, which on an ownership/visibility filter means
    returning data the caller must not see.
    """
    members = getattr(filter_obj, "filters", None)
    if members is None:
        return [
            _field_filter_triple(
                getattr(filter_obj, "field_path", None),
                getattr(filter_obj, "op_string", None),
                getattr(filter_obj, "value", None),
                name_value=name_value,
            )
        ]
    operator = getattr(filter_obj, "operator", None)
    op_name = str(getattr(operator, "name", None) or operator).upper()
    if not op_name.endswith("AND"):
        raise NotImplementedError(
            f"composite {op_name} filters are not supported by the document-store port "
            "(its filter list is an implicit AND); express the query as separate reads instead"
        )
    triples: List[Tuple[Any, str, Any]] = []
    for member in members:
        triples.extend(_filter_triples(member, name_value=name_value))
    return triples


def _to_neutral(value: Any) -> Any:
    """Translate google Firestore sentinels/transforms in a payload into neutral store sentinels."""
    if _fs is not None:
        if value is _fs.SERVER_TIMESTAMP:
            return _neutral.SERVER_TIMESTAMP
        if value is _fs.DELETE_FIELD:
            return _neutral.DELETE
    if _FsArrayUnion and isinstance(value, _FsArrayUnion):
        return _neutral.ArrayUnion(list(value.values))
    if _FsArrayRemove and isinstance(value, _FsArrayRemove):
        return _neutral.ArrayRemove(list(value.values))
    if _FsIncrement and isinstance(value, _FsIncrement):
        return _neutral.Increment(value.value)
    if isinstance(value, dict):
        return {k: _to_neutral(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_neutral(v) for v in value]
    return value


def _neutral_data(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _to_neutral(v) for k, v in data.items()}


_UNKNOWN_COMMIT_RETRIES = 100  # backstop bound on the idempotent commit-retry loop (never a real limit)


def _has_txn_label(exc: Exception, label: str) -> bool:
    fn = getattr(exc, "has_error_label", None)
    return bool(callable(fn) and fn(label))


@contextlib.contextmanager
def _firestore_errors():
    """Re-raise neutral store errors as the ``google.api_core`` errors upstream code catches, so
    ``except NotFound`` / ``except AlreadyExists`` around a ``db_client`` write behave identically on
    the Mongo-backed facade as on real Firestore (ADR-0044). Without this an ``update`` on a missing
    doc raises the neutral ``NotFound`` and escapes an upstream ``except FirestoreNotFound``."""
    try:
        yield
    except _StoreNotFound as exc:
        raise _gexc.NotFound(str(exc)) from exc
    except _StoreAlreadyExists as exc:
        raise _gexc.AlreadyExists(str(exc)) from exc
    except _StorePreconditionFailed as exc:
        raise _gexc.FailedPrecondition(str(exc)) from exc


@contextlib.contextmanager
def _txn_write_errors():
    """Like ``_firestore_errors()`` for writes issued INSIDE a transaction, but ALSO maps a write-time
    MongoDB write conflict to google's ``Aborted``. A conflict can surface at operation time (the
    ``update_one``/``insert_one`` on the session), not only at commit — e.g. the goals ``reservation_ref``
    write is DESIGNED to conflict with a concurrent focus transaction. Without this the raw pymongo error
    escapes as itself; only ``_commit`` translated conflicts before (cubic PR 10887 goals.py:635).

    **This does NOT make ``@firestore.transactional`` replay the body, and the comment here used to claim
    it did.** Measured on the live rig: google's ``_Transactional.__call__`` puts only
    ``transaction._commit()`` inside ``except retryable_exceptions``; ``_pre_commit`` — which runs the
    decorated body, and therefore every ``transaction.set/update/create`` — sits outside it. So:

        conflict raised at COMMIT       -> replayed. The body runs again and the facade transaction
                                           survives the replay (verified: body ran twice, then committed).
        conflict raised INSIDE the body -> NOT replayed. The ``Aborted`` propagates to the caller after a
                                           rollback (verified: body ran once).

    What the translation still buys is the right exception TYPE, so a caller can recognise contention
    instead of catching a pymongo error. What it does not buy is transparency: under
    STORAGE_BACKEND=mongo a caller of a contended transaction can see a bare ``Aborted`` where the
    Firestore posture would have retried and surfaced the module's own domain error. Callers that catch
    only their domain error are exposed. Making write-time conflicts replay would mean buffering
    in-transaction writes until commit — a design change with a wide blast radius, not a fix, so it is
    written down here and tracked rather than done in passing."""
    try:
        yield
    except _StoreNotFound as exc:
        raise _gexc.NotFound(str(exc)) from exc
    except _StoreAlreadyExists as exc:
        raise _gexc.AlreadyExists(str(exc)) from exc
    except _StorePreconditionFailed as exc:
        raise _gexc.FailedPrecondition(str(exc)) from exc
    except Exception as exc:
        if _has_txn_label(exc, "TransientTransactionError"):
            raise _gexc.Aborted(str(exc)) from exc
        raise


class _Precondition:
    """Neutral write precondition returned by ``NeutralFirestoreClient.write_option`` — the facade's
    stand-in for a Firestore ``LastUpdateOption`` ("apply this write only if the doc's revision is
    unchanged since ``updated_at``"). The store port enforces it via ``if_updated_at``."""

    __slots__ = ("updated_at",)

    def __init__(self, updated_at: Any) -> None:
        self.updated_at = updated_at


def _precondition_time(option: Any) -> Any:
    """Extract the revision timestamp from a write ``option``, accepting either the facade's own
    ``_Precondition`` (from ``write_option``) or a native Firestore ``LastUpdateOption`` (which
    upstream constructs directly, e.g. review-queue self-heal). ``None`` -> no precondition."""
    if option is None:
        return None
    if isinstance(option, _Precondition):
        return option.updated_at
    return getattr(option, "_last_update_time", None)


class _AggregationResult:
    """One Firestore aggregation cell. Upstream reads ``.value`` (the count) off it."""

    __slots__ = ("value", "alias")

    def __init__(self, value: int, alias: str = "field_1") -> None:
        self.value = value
        self.alias = alias


class _AggregationQuery:
    """Firestore ``AggregationQuery`` shape. ``count()`` returns this, not a bare int: every source
    call site reads the total as ``q.count().get()[0][0].value`` (x_posts, conversations, folders,
    apps, action_items, daily_summaries, chat), so ``get()`` yields a nested ``[[AggregationResult]]``."""

    def __init__(self, value: int) -> None:
        self._value = value

    def get(self, transaction: Any = None, **kwargs: Any) -> List[List["_AggregationResult"]]:
        if transaction is not None:
            # Same rule as _GroupQuery.stream: refused, not ignored (BACKLOG L24). The count already ran
            # when `.count()` built this object, so honouring a transaction here would be a lie — and the
            # neutral port's `count` has no session-aware form. No caller counts inside a transaction
            # (checked), so this documents the boundary instead of pretending to hold it.
            raise NotImplementedError(
                'count().get(transaction=...) is not supported: the aggregation already ran, and the '
                'neutral port has no transactional count. Count outside the transaction, or read the '
                'documents inside it.'
            )
        return [[_AggregationResult(self._value)]]


class _Snapshot:
    """Firestore ``DocumentSnapshot`` shape over a neutral :class:`StoredDocument`."""

    def __init__(self, doc_ref: "_DocRef", stored: StoredDocument) -> None:
        self.reference = doc_ref
        self.id = doc_ref.id
        self._stored = stored

    @property
    def exists(self) -> bool:
        return self._stored.exists

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return self._stored.to_dict()

    def get(self, field_path: str) -> Any:
        data = self._stored.to_dict() or {}
        # Firestore supports dotted field paths; walk them.
        cur: Any = data
        for part in field_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    @property
    def create_time(self) -> Any:
        # The immutable document creation time (cubic PR 10887 #1). Fall back to updated_at for a legacy
        # Mongo doc written before _created_at was stamped, so create_time is never None for an existing doc.
        return self._stored.created_at or self._stored.updated_at

    @property
    def update_time(self) -> Any:
        return self._stored.updated_at


class _DocRef:
    """Firestore ``DocumentReference`` shape. Addressed by full logical path."""

    def __init__(self, client: "NeutralFirestoreClient", path: str) -> None:
        self._client = client
        self.path = path.strip("/")
        self.id = self.path.rsplit("/", 1)[-1]

    @property
    def reference(self) -> "_DocRef":
        return self

    def collection(self, sub: str) -> "_CollRef":
        return _CollRef(self._client, f"{self.path}/{sub}")

    def collections(self, *, retry: Any = None, timeout: Any = None) -> Iterable["_CollRef"]:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        # Enumerate real subcollections so recursive-delete helpers (account / conversation deletion)
        # descend into them on Mongo instead of silently leaving orphaned descendant data.
        return [
            _CollRef(self._client, f"{self.path}/{name}") for name in self._client.store.list_subcollections(self.path)
        ]

    def get(
        self,
        field_paths: Any = None,
        transaction: Optional["_FacadeTransaction"] = None,
        *,
        timeout: Any = None,
        **_: Any,
    ) -> _Snapshot:
        # Firestore's DocumentReference.get(field_paths=None, transaction=None, ...) takes field_paths
        # as the FIRST positional arg (a projection). Upstream calls ``.get(['subscription'])`` etc.;
        # binding that list to ``transaction`` crashed on the Mongo-backed facade. Route the projection
        # through the store's ``fields=`` instead. ``timeout`` (seconds) is a real read deadline on the
        # Mongo/Firestore adapters — thread it to the store (a slow read must fail closed, not hang a
        # worker: e.g. default-read rollout's 2s deadline). A transaction read carries no separate RPC
        # timeout, so it is not threaded there.
        fields = list(field_paths) if field_paths else None
        if transaction is not None:
            return _Snapshot(self, transaction.read(self.path, fields=fields))
        return _Snapshot(self, self._client.store.get(self.path, fields=fields, timeout=timeout))

    def set(self, data: Dict[str, Any], merge: bool = False, *, retry: Any = None, timeout: Any = None) -> None:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        self._client.store.set(self.path, _neutral_data(data), merge=merge)

    def update(self, data: Dict[str, Any], option: Any = None, *, retry: Any = None, timeout: Any = None) -> None:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        # ``option`` (Firestore LastUpdateOption, or the facade's own write_option token) is an
        # optimistic-concurrency precondition ("only write if the doc's revision is unchanged"). It maps
        # to the store port's ``if_updated_at``; the Mongo adapter enforces it against the stored
        # ``_updated_at`` and raises FailedPrecondition (via _firestore_errors) on a stale revision.
        with _firestore_errors():
            self._client.store.update(self.path, _neutral_data(data), if_updated_at=_precondition_time(option))

    def create(self, data: Dict[str, Any], *, retry: Any = None, timeout: Any = None) -> None:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        with _firestore_errors():
            self._client.store.create(self.path, _neutral_data(data))

    def delete(self, *, retry: Any = None, timeout: Any = None) -> None:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        with _firestore_errors():
            self._client.store.delete(self.path)


class _Query:
    """Firestore ``Query`` shape: immutable builder that materialises via the neutral store."""

    def __init__(
        self,
        client: "NeutralFirestoreClient",
        collection: str,
        *,
        filters: Optional[List[Any]] = None,
        order_by: Optional[List[Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        start_after: Optional[Any] = None,
        fields: Optional[List[str]] = None,
    ) -> None:
        self._client = client
        self._collection = collection.strip("/")
        self._filters = list(filters or [])
        self._order_by = list(order_by or [])
        self._limit = limit
        self._offset = offset
        self._start_after = start_after
        # ``select()`` projection: None = no projection (full doc); [] = ids only; ['f', …] = those payload
        # fields. Preserve the empty list (it is NOT "no projection") — that is Firestore's ids-only select.
        self._fields = list(fields) if fields is not None else None

    def _clone(self, **kw: Any) -> "_Query":
        # A kwargs bag, not a homogeneous mapping: without the annotation the inferred value type is
        # the union of everything in it (`list[Any] | int | None`), which then fails against each
        # typed parameter of _Query when it is unpacked.
        base: Dict[str, Any] = dict(
            filters=self._filters,
            order_by=self._order_by,
            limit=self._limit,
            offset=self._offset,
            start_after=self._start_after,
            fields=self._fields,
        )
        base.update(kw)
        return _Query(self._client, self._collection, **base)

    def where(
        self, field_path: Any = None, op_string: Any = None, value: Any = None, *, filter: Any = None
    ) -> "_Query":
        if filter is not None:  # modern FieldFilter / composite form
            return self._clone(filters=self._filters + _filter_triples(filter, name_value=_name_filter_value))
        return self._clone(
            filters=self._filters + [_field_filter_triple(field_path, op_string, value, name_value=_name_filter_value)]
        )

    def order_by(self, field_path: str, direction: Any = "ASCENDING") -> "_Query":
        d = "desc" if direction == _DESCENDING or str(direction).lower().startswith("desc") else "asc"
        return self._clone(order_by=self._order_by + [(field_path, d)])

    def limit(self, count: int) -> "_Query":
        return self._clone(limit=count)

    def offset(self, count: int) -> "_Query":
        return self._clone(offset=count)

    def start_after(self, snapshot_or_values: Any) -> "_Query":
        return self._clone(start_after=snapshot_or_values)

    def select(self, field_paths: Any) -> "_Query":
        # Propagate the projection to the store (which builds a Mongo ``find`` projection / a Firestore
        # ``select``) instead of fetching every field — bulk migration reads (e.g. select(['data_protection_
        # level']) over a whole collection) otherwise over-fetch and expose every document field (cubic
        # 10887 firestore_facade.py:258). ``select([])`` stays ids-only (list preserved, not treated as None).
        return self._clone(fields=list(field_paths))

    def _resolve_start_after(self) -> Optional[Dict[str, Any]]:
        """Translate a Firestore ``start_after`` cursor into the store's composite keyset
        ``{"values": [<one per REAL order field>], "id": <document id>}``. A trailing ``__name__`` order
        is the document-id tiebreak (it maps to ``id``, not a ``values`` entry). Accepts a DocumentSnapshot
        (reads each order field off it) or a Firestore-style ``{field: value, __name__: ref}`` dict."""
        cur = self._start_after
        if cur is None:
            return None
        real = [f for f, _ in self._order_by if f != "__name__"]  # payload order fields, in order
        if hasattr(cur, "to_dict"):  # a DocumentSnapshot
            data = cur.to_dict() or {}
            return {"values": [data.get(f) for f in real], "id": getattr(cur, "id", None)}
        if isinstance(cur, dict):
            ref = cur.get("__name__")
            if ref is not None:
                doc_id = getattr(ref, "id", None) or str(ref).rsplit("/", 1)[-1]
            else:
                doc_id = cur.get("id", "")
            return {"values": [cur.get(f) for f in real], "id": doc_id}
        if isinstance(cur, (list, tuple)):
            # Firestore positional cursor: values align 1:1 with the order_by clauses. A value at a
            # ``__name__`` position (or a trailing DocumentReference for the implicit document-name
            # tiebreak) is the id keyset; the rest are the payload order values. e.g.
            # enrich_historical_memory_graph pages with ``start_after([updated_at, coll.document(id)])``
            # over ``order_by('updated_at').order_by('__name__')``. Treating the whole list as one value
            # (the old bare-value fallback) mis-keyed the cursor and broke pagination past page 1 (cubic
            # PR 10887 #378).
            order_fields = [f for f, _ in self._order_by]
            values: List[Any] = []
            doc_id: Any = ""
            for i, v in enumerate(cur):
                field = order_fields[i] if i < len(order_fields) else None
                if field == "__name__" or (field is None and isinstance(v, _DocRef)):
                    doc_id = v.id if isinstance(v, _DocRef) else (getattr(v, "id", None) or str(v).rsplit("/", 1)[-1])
                else:
                    values.append(v)
            return {"values": values, "id": doc_id}
        # a bare cursor value (single-field): pair it with an empty id lower bound
        return {"values": [cur], "id": ""}

    def _run(self, transaction: Optional["_FacadeTransaction"] = None) -> List[StoredDocument]:
        order: Any = None
        direction = "asc"
        if len(self._order_by) == 1:
            order, direction = self._order_by[0]
        elif self._order_by:
            # Multi-field (incl. a trailing __name__): pass the pairs through; the store maps __name__ to
            # its _id tiebreak and builds a composite keyset for the cursor.
            order = self._order_by
        kwargs: Dict[str, Any] = {
            "filters": self._filters or None,
            "order_by": order,
            "direction": direction,
            "limit": self._limit,
            "offset": self._offset,
            "start_after": self._resolve_start_after(),
            "fields": self._fields,
        }
        if transaction is not None:
            # Inside the caller's transaction, via the same session every other op on this handle uses.
            # This parameter used to be accepted and DROPPED (BACKLOG L24): upstream reads collections
            # inside `@firestore.transactional` bodies — the idempotency-key de-dup in
            # database/action_items.py, the relationship detach in goals.py, the photo probe in
            # conversation_finalization_jobs.py — and every one of those reads ran outside the session.
            return transaction.run_query(self._collection, **kwargs)
        return self._client.store.query(self._collection, **kwargs)

    def count(self) -> "_AggregationQuery":
        # Firestore's count() returns an AggregationQuery; callers do .count().get()[0][0].value.
        return _AggregationQuery(self._client.store.count(self._collection, filters=self._filters or None))

    def stream(
        self,
        transaction: Optional["_FacadeTransaction"] = None,
        *,
        retry: Any = None,
        timeout: Any = None,
    ) -> Iterable[_Snapshot]:
        # ``retry`` / ``timeout`` are accepted and not forwarded, which needs saying because the
        # opposite choice is BACKLOG L24's defect. They are TRANSPORT policy -- how often to re-attempt
        # a failed RPC, and how long to wait -- and every adapter already owns one: the Firestore SDK
        # applies its default retry to a stream, pymongo retries reads by default. The neutral port
        # deliberately does not model them, and a ``google.api_core.retry.Retry`` object has no
        # translation into the Mongo driver's equivalent.
        #
        # Not academic: ``database/trends.py`` calls ``stream(retry=Retry())`` twice, so before this
        # signature accepted the argument ``get_trends_data()`` raised TypeError on the first line of
        # its body under STORAGE_BACKEND=mongo and /v1/trends was dead on-prem. The second call sits
        # inside ``except Exception: continue``, so fixing only the first would have returned every
        # category with zero topics -- an empty page instead of an error.
        del retry, timeout
        for stored in self._run(transaction):
            yield _Snapshot(_DocRef(self._client, stored.path), stored)

    def get(
        self,
        transaction: Optional["_FacadeTransaction"] = None,
        *,
        retry: Any = None,
        timeout: Any = None,
    ) -> List[_Snapshot]:
        return list(self.stream(transaction, retry=retry, timeout=timeout))


class _CollRef(_Query):
    """Firestore ``CollectionReference``: a query plus document addressing."""

    @property
    def id(self) -> str:
        return self._collection.rsplit("/", 1)[-1]

    @property
    def path(self) -> str:
        return self._collection

    def document(self, doc_id: Optional[str] = None) -> _DocRef:
        # No id -> a fresh random auto-id (Firestore semantics), never a deterministic derivation.
        # A client-supplied id is validated so a '/' can't split the composed path (path injection).
        doc_id = _auto_id() if doc_id is None else _validate_doc_id(doc_id)
        return _DocRef(self._client, f"{self._collection}/{doc_id}")

    def list_documents(self, *, retry: Any = None, timeout: Any = None) -> List[_DocRef]:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        return [_DocRef(self._client, s.path) for s in self._run()]

    def add(
        self,
        data: Dict[str, Any],
        document_id: Optional[str] = None,
        *,
        retry: Any = None,
        timeout: Any = None,
    ) -> Tuple[datetime, _DocRef]:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        # Firestore's signature is add(document_data, document_id=None): omitting the id here made
        # ``app_ref.add(app_data, app_data['id'])`` (database/apps.py, app creation) a TypeError on
        # Mongo — and had the argument been swallowed, the app would have landed under a random
        # auto-id, which is worse than the crash. Returns ``(write_time, DocumentReference)``;
        # callers index ``[1]`` for the ref (e.g. desktop release publishing), so keep that shape.
        ref = self.document(document_id) if document_id else self.document()
        ref.create(data)
        return datetime.now(timezone.utc), ref


class _FacadeTransaction:
    """A Firestore ``Transaction`` shape over one open Mongo session transaction.

    Satisfies both upstream's ``transactional`` fallback (``_begin``/``_commit``/``_rollback``/
    ``_clean_up``) and google's real decorator (which calls the same lifecycle plus reads ``_id``).
    Reads and writes share one session so read-modify-write stays atomic (optimistic concurrency).
    """

    _max_attempts = 5
    _read_only = False  # google's @transactional reads this to decide whether Aborted is retryable
    # Class-level default as well as an instance one: a transaction is sometimes built with ``__new__``
    # to drive ``_commit`` in isolation, and an attribute that only exists after ``__init__`` turns that
    # into an AttributeError three frames from the reason.
    _poisoned: Optional[BaseException] = None

    def __init__(self, client: "NeutralFirestoreClient") -> None:
        self._client = client
        self._session: Any = None
        self._id: Any = None
        # Set when a write hits a Mongo write conflict. See _poison() for why the conflict is HELD here
        # instead of being raised out of the body (ADR-0091, BACKLOG L53).
        self._poisoned: Optional[BaseException] = None

    # --- lifecycle (driven by the decorator/wrapper) ---
    def _begin(self, retry_id: Any = None) -> None:
        # The store opens its own session (ports.FacadeSessionStore): the Mongo adapter returns a
        # replica-set session with an active transaction, the neutral FakeDocumentStore returns None to
        # DECLARE session-less — writes apply directly, no atomicity, which is what a hermetic unit
        # test asserting domain logic needs.
        #
        # This used to sniff ``store._mongo_client`` and treat its absence as "session-less". That
        # inference is why a store implementing the documented port in full would have run every
        # transaction in the product WITHOUT ATOMICITY AND WITHOUT AN ERROR: the loud half
        # (AttributeError from _read) invited a fix, and the silent half shipped behind it. Asking the
        # store makes "no session" a declaration instead of a guess (BACKLOG L31).
        self._session = self._client.store.begin_session()
        if self._session is not None:
            # Moving the ops onto the session opened a NEW way to fail in silence, and it is closed
            # here rather than left for a body to trip over: a store that returns a half-built handle
            # would raise AttributeError from whichever op the body happened to reach first, three
            # frames deep, with the same "loud half invites a fix" shape L31 already cost us once.
            missing = missing_store_session_ops(self._session)
            if missing:
                raise TypeError(
                    f"{type(self._client.store).__name__}.begin_session() returned a "
                    f"{type(self._session).__name__}, which does not implement {', '.join(missing)}. "
                    "The facade runs every read and write of an upstream @transactional body on this "
                    "handle; see database/store/ports.py:StoreSession. Return None to declare the store "
                    "session-less on purpose (no atomicity) — never a session that cannot be used."
                )
        self._id = id(self)
        # Clear the held conflict: google's decorator REUSES this object across attempts, so a replay
        # that started still poisoned would run inert and re-raise the same conflict until the attempt
        # budget ran out. Measured that way first -- the body ran twice and still failed.
        self._poisoned = None

    @property
    def _ops(self) -> Any:
        """Where reads and writes go: the open session, or the store itself when it declared
        session-less by returning ``None`` from ``begin_session()``.

        The two carry the SAME six operations by design — ``ports.StoreSession`` mirrors the
        domain-facing ``DocumentStore`` — so "no session" costs one fallback here instead of a branch
        at every call site, and a session-less store simply loses atomicity, which is precisely what
        returning ``None`` declares.
        """
        return self._session if self._session is not None else self._client.store

    def run_query(self, collection: str, **kwargs: Any) -> List[StoredDocument]:
        """A collection read INSIDE this transaction, for ``_Query.stream(transaction=...)``.

        A method rather than the query reaching in for the handle: the transaction owns where its reads
        go, and ``_Query`` only needs to say that this read belongs to it.
        """
        return self._ops.query(collection, **kwargs)

    def _commit(self) -> Any:
        if self._poisoned is not None:
            # A write conflicted earlier in the body. Raise it HERE, which is the one place google's
            # decorator retries, and roll the session back first so the replay starts clean.
            #
            # Measured: removing these four lines still retries today, because committing an already
            # aborted session fails with a TransientTransactionError label and the handler below turns
            # THAT into Aborted. So this is redundant with pymongo's current reporting, and the mutation
            # survives — said here rather than left as an unexplained survivor. It stays because the
            # retry should be a decision of ours, not a side effect of how a driver happens to label a
            # commit on a dead session, and because the caller then sees the ORIGINAL conflict.
            self._rollback()
            raise self._poisoned
        if self._session is None:
            return []
        # A commit that fails with UnknownTransactionCommitResult MAY already have succeeded on the server,
        # so the transaction BODY must NOT be replayed (duplicate side effects). Retry the COMMIT itself —
        # committing is idempotent — per MongoDB's driver guidance. Only a TransientTransactionError (write
        # conflict, body never applied) is safe to replay via the decorator's Aborted retry (cubic PR 10887
        # firestore_facade.py:508). Bound the commit-retry loop as a backstop against a pathological hang.
        for _ in range(_UNKNOWN_COMMIT_RETRIES):
            try:
                self._session.commit_transaction()
                return []
            except Exception as exc:
                if _has_txn_label(exc, "UnknownTransactionCommitResult"):
                    continue  # retry the commit only — do NOT re-run the callback body
                if _has_txn_label(exc, "TransientTransactionError"):
                    from google.api_core.exceptions import Aborted

                    raise Aborted(str(exc)) from exc  # decorator replays the whole transaction
                raise
        # Exhausted commit retries on repeated UnknownTransactionCommitResult: surface it, don't replay.
        raise RuntimeError("transaction commit did not resolve after repeated UnknownTransactionCommitResult")

    def _rollback(self) -> None:
        if self._session is not None:
            try:
                self._session.abort_transaction()
            except Exception:  # already terminated
                pass

    def _clean_up(self) -> None:
        if self._session is not None:
            self._session.end_session()
        self._session = None
        self._id = None

    # --- the write conflict is HELD, not raised (ADR-0091) --------------------------------------------
    #
    # google's ``_Transactional.__call__`` puts only ``transaction._commit()`` inside
    # ``except retryable_exceptions``; ``_pre_commit`` -- which runs the decorated body, and therefore
    # every write below -- sits OUTSIDE it. Measured on the live rig: a conflict raised from a write
    # propagated to the caller after a rollback and the body ran exactly once, while a conflict raised
    # from the commit replayed the body and then committed. So raising a write conflict here can never
    # produce the retry the translation was added for -- it only produces a bare ``Aborted`` where the
    # Firestore posture would have retried and returned the module's own domain error.
    #
    # So the conflict is recorded and the transaction goes INERT: every later read reports "not there",
    # every later write does nothing, and ``_commit`` raises the ``Aborted`` from the place the decorator
    # actually watches. The body runs to the end on a transaction that will land nothing.
    #
    # What makes that safe is a property of this tree, measured rather than assumed: of the 155
    # transactional bodies, NONE performs a side effect outside the store. A body that sent an email or
    # enqueued a vector write would do it on a run whose writes are all discarded, and would then do it
    # again on the replay. That measurement is a precondition of this design -- if it ever stops holding,
    # this stops being correct, which is why the check lives in the unit suite and not only in a comment.

    def _poison(self, exc: BaseException) -> None:
        """Hold a write conflict until ``_commit``, where the decorator's retry can see it."""
        if self._poisoned is None:
            self._poisoned = exc

    # --- read/write within the transaction (upstream calls these with a _DocRef) ---
    def read(self, path: str, *, fields: Any = None) -> StoredDocument:
        if self._poisoned is not None:
            # The Mongo session is already aborted; asking it anything raises. Report "absent" so the
            # body can finish and reach the commit, where the conflict is re-raised for the retry.
            return StoredDocument(id=path.rsplit("/", 1)[-1], path=path, exists=False, data=None)
        return self._ops.get(path, fields=fields)

    def get(self, ref: _DocRef, **_: Any) -> _Snapshot:
        return _Snapshot(ref, self.read(ref.path))

    def set(self, ref: _DocRef, data: Dict[str, Any], merge: bool = False) -> None:
        if self._poisoned is not None:
            return
        with self._holding_conflicts():
            self._ops.set(ref.path, _neutral_data(data), merge=merge)

    def update(self, ref: _DocRef, data: Dict[str, Any], option: Any = None) -> None:
        if self._poisoned is not None:
            return
        with self._holding_conflicts():
            self._ops.update(ref.path, _neutral_data(data), if_updated_at=_precondition_time(option))

    def create(self, ref: _DocRef, data: Dict[str, Any]) -> None:
        if self._poisoned is not None:
            return
        with self._holding_conflicts():
            self._ops.create(ref.path, _neutral_data(data))

    def delete(self, ref: _DocRef, option: Any = None) -> None:
        if self._poisoned is not None:
            return
        with self._holding_conflicts():
            self._ops.delete(ref.path, if_updated_at=_precondition_time(option))

    @contextlib.contextmanager
    def _holding_conflicts(self):
        """``_txn_write_errors`` for a write issued inside THIS transaction: a transient write conflict
        poisons instead of raising. Every other error is translated and raised as before -- a missing
        document or a failed precondition is the body's business and must reach it."""
        try:
            with _txn_write_errors():
                yield
        except _gexc.Aborted as exc:
            self._poison(exc)


class _FacadeBatch:
    """Firestore ``WriteBatch`` shape over the neutral store batch (ref -> path)."""

    def __init__(self, client: "NeutralFirestoreClient") -> None:
        self._batch = client.store.batch()

    def set(self, ref: _DocRef, data: Dict[str, Any], merge: bool = False, option: Any = None) -> None:
        # No caller passes a precondition to batch.set; Firestore's set carries none either. Accept and
        # ignore ``option`` for signature parity.
        del option
        self._batch.set(ref.path, _neutral_data(data), merge=merge)

    def create(self, ref: _DocRef, data: Dict[str, Any]) -> None:
        # Firestore ``WriteBatch.create`` (staged-task recovery). A collision raises AlreadyExists at
        # commit, which _firestore_errors() maps to the google AlreadyExists upstream catches.
        self._batch.create(ref.path, _neutral_data(data))

    def update(self, ref: _DocRef, data: Dict[str, Any], option: Any = None) -> None:
        self._batch.update(ref.path, _neutral_data(data), if_updated_at=_precondition_time(option))

    def delete(self, ref: _DocRef, option: Any = None) -> None:
        self._batch.delete(ref.path, if_updated_at=_precondition_time(option))

    def commit(self, *, retry: Any = None, timeout: Any = None) -> None:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        with _firestore_errors():
            self._batch.commit()


class NeutralFirestoreClient:
    """The ``db_client`` upstream threads, backed by the neutral store port (ADR-0044).

    Only the surface upstream actually calls is implemented: ``document`` / ``collection`` /
    ``transaction`` / ``get_all`` / ``batch``. Extend here (and the boundary guard) if a merge starts
    using a new client method — that is the one maintenance point instead of hundreds of call sites.
    """

    def __init__(self, store: Any) -> None:
        # Fail here, at construction, rather than at the first transaction: the facade needs more than
        # the domain-facing DocumentStore (session-scoped ops + a session opener — ports.FacadeSessionStore),
        # and a store missing them cannot be used behind it. Naming every missing method beats surfacing
        # whichever attribute a transaction happened to touch first, three layers down (BACKLOG L31).
        missing = missing_facade_session_ops(store)
        if missing:
            raise TypeError(
                f"{type(store).__name__} cannot back NeutralFirestoreClient: it does not implement "
                f"{', '.join(missing)}. The facade runs upstream's @transactional bodies inside one "
                "session, which the domain-facing DocumentStore port does not express; see "
                "database/store/ports.py:FacadeSessionStore. Return None from begin_session() to "
                "declare a store session-less on purpose (no atomicity) — never leave it unimplemented, "
                "or transactions apply without atomicity and without an error."
            )
        self._store = store

    @property
    def store(self) -> Any:
        """The backing store, for this module's own companion classes.

        `_DocRef`, `_CollRef`, `_Query` and the transaction/batch types are one implementation split
        across several classes for readability; every one of them needs the store. Reaching for
        `client._store` from a sibling class is private access as far as a type checker is concerned
        (and upstream's pyright lane rejects it), so the module's internal API is stated once here
        rather than suppressed at each of the seventeen call sites."""
        return self._store

    def document(self, path: str) -> _DocRef:
        return _DocRef(self, path)

    def collection(self, path: str) -> _CollRef:
        return _CollRef(self, path)

    def transaction(self, *_: Any, **__: Any) -> _FacadeTransaction:
        return _FacadeTransaction(self)

    def batch(self) -> _FacadeBatch:
        return _FacadeBatch(self)

    def write_option(self, *, last_update_time: Any) -> _Precondition:
        # Firestore ``Client.write_option(last_update_time=...)`` builds a LastUpdateOption an upstream
        # write then carries (batch.delete/update precondition — staged-task recovery, chat clear).
        # Return the neutral equivalent so those paths work on the Mongo-backed facade instead of
        # raising AttributeError; the write path maps it to the store port's ``if_updated_at``.
        return _Precondition(last_update_time)

    def get_all(
        self,
        references: Iterable[_DocRef],
        field_paths: Any = None,  # mirror Firestore's positional (references, field_paths, transaction) order
        transaction: Optional["_FacadeTransaction"] = None,
        **_: Any,
    ) -> Iterable[_Snapshot]:
        # Real Firestore get_all is get_all(references, field_paths=None, transaction=None, ...). A prior
        # ``*_`` swallowed a POSITIONAL transaction, so `get_all(refs, field_paths, txn)` read OUTSIDE the
        # transaction (lost read-your-writes/atomicity). Name the params so a positional transaction binds
        # (cubic PR 10887 firestore_facade.py:658). ``field_paths`` (projection) is accepted for signature
        # parity; the batched get_many is not projection-aware, so it is not applied (over-fetch, as before).
        del field_paths
        refs = list(references)
        if transaction is not None:
            # Inside a transaction, get_all must read through the session for read-your-writes; the
            # neutral get_many is not session-aware, so route each ref through the transaction like the
            # single-doc reads do (real Firestore get_all also honors the transaction).
            for ref in refs:
                yield _Snapshot(ref, transaction.read(ref.path))
            return
        # Non-transactional: batch by collection via store.get_many (one $in per collection on Mongo)
        # instead of N point reads (many hot callers: conversations/chat/memories/review_queue/…), then
        # yield ONE snapshot per input ref (a missing ref stays exists=False), preserving order
        # (cubic review PR 10887, review 4939247683).
        by_collection: Dict[str, list] = {}
        for ref in refs:
            # `_sep`, not `_`: this method takes **_ for the kwargs it ignores, so the usual throwaway
            # name is already bound to that dict and unpacking into it rebinds a str over it.
            collection, _sep, doc_id = ref.path.rpartition("/")
            by_collection.setdefault(collection, []).append(doc_id)
        found: Dict[str, StoredDocument] = {}
        for collection, ids in by_collection.items():
            for record in self._store.get_many(collection, ids):
                found[record.path] = record
        for ref in refs:
            record = found.get(ref.path)
            yield _Snapshot(ref, record if record is not None else StoredDocument.missing(ref.path))

    def collection_group(self, group_id: str) -> "_GroupQuery":
        return _GroupQuery(self, group_id)


class _GroupQuery:
    """Firestore ``collection_group`` shape over the neutral ``query_group`` (cross-parent sweep).

    ``query_group``'s cursor is a document-name keyset (a full logical path), so ``order_by`` here
    tracks the requested single field + direction and ``start_after`` a document-name; on-prem
    cross-parent jobs (memory vector repair, projection sync) use both."""

    def __init__(self, client: "NeutralFirestoreClient", group: str, **kw: Any) -> None:
        self._client = client
        self._group = group
        self._filters: List[Any] = kw.get("filters", [])
        self._limit = kw.get("limit")
        self._order_by = kw.get("order_by")
        self._direction = kw.get("direction", "asc")
        self._start_after = kw.get("start_after")

    def _clone(self, **kw: Any) -> "_GroupQuery":
        base = dict(
            filters=self._filters,
            limit=self._limit,
            order_by=self._order_by,
            direction=self._direction,
            start_after=self._start_after,
        )
        base.update(kw)
        return _GroupQuery(self._client, self._group, **base)

    def where(
        self, field_path: Any = None, op_string: Any = None, value: Any = None, *, filter: Any = None
    ) -> "_GroupQuery":
        # group: ``__name__`` compares against the full path, not the scoped bare id.
        if filter is not None:
            return self._clone(filters=self._filters + _filter_triples(filter, name_value=_group_name_filter_value))
        return self._clone(
            filters=self._filters
            + [_field_filter_triple(field_path, op_string, value, name_value=_group_name_filter_value)]
        )

    def order_by(self, field_path: str, direction: Any = "ASCENDING") -> "_GroupQuery":
        if field_path == "__name__":
            # A collection-group query already resumes by its document-name (_id) keyset; forwarding an
            # explicit __name__ order is redundant and, combined with start_after, the store rejects it
            # (cubic PR 10887 #2 — canonical maintenance cron stalled at page 1 on Mongo). Treat the
            # ascending document-name order as the implicit keyset ordering: no-op.
            return self
        d = "desc" if direction == _DESCENDING or str(direction).lower().startswith("desc") else "asc"
        return self._clone(order_by=field_path, direction=d)

    def limit(self, count: int) -> "_GroupQuery":
        return self._clone(limit=count)

    def start_after(self, cursor: Any) -> "_GroupQuery":
        # query_group's cursor is a full document path (name keyset); accept a snapshot or a path.
        path = getattr(getattr(cursor, "reference", None), "path", None) or getattr(cursor, "path", None) or cursor
        return self._clone(start_after=path)

    def stream(
        self,
        transaction: Optional[_FacadeTransaction] = None,
        *,
        retry: Any = None,
        timeout: Any = None,
    ) -> Iterable[_Snapshot]:
        del retry, timeout  # transport policy, adapter-owned -- see the note on _Query.stream
        if transaction is not None:
            # Refused rather than ignored. A cross-parent sweep inside a transaction is not something the
            # neutral port expresses (``query_group`` has no session-aware twin) and no caller asks for it
            # — the on-prem group queries are background jobs (memory vector repair, projection sync),
            # which run outside any transaction. Accepting-and-dropping the argument is the exact defect
            # BACKLOG L24 was about, so the honest answer here is to say so instead of repeating it.
            raise NotImplementedError(
                'collection_group().stream(transaction=...) is not supported: query_group has no '
                'transactional form in the neutral port. Read the parents individually inside the '
                'transaction, or do the sweep outside it.'
            )
        for stored in self._client.store.query_group(
            self._group,
            filters=self._filters or None,
            order_by=self._order_by,
            direction=self._direction,
            limit=self._limit,
            start_after=self._start_after,
        ):
            yield _Snapshot(_DocRef(self._client, stored.path), stored)


__all__ = ["NeutralFirestoreClient"]
