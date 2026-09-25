"""A `__name__` filter takes a Key, not a string — otherwise the query raises on every call.

`get_usage_summary` and `get_plan_usage_report` bound their scan with
`where("__name__", ">=", cutoff_id)` where `cutoff_id` is a date string like `2026-01-01`. Firestore
requires a Key (a DocumentReference) there and rejects anything else:

    google.api_core.exceptions.InvalidArgument: 400 __key__ filter value must be a Key

Measured against the Firestore emulator: both functions raised on every call, for every user.

The document ids ARE the dates, so the reference is simply `usage_collection.document(cutoff_id)` — the
intent and the bound are unchanged, only the type is.
"""

from __future__ import annotations

from typing import Any, List, Tuple

import database.llm_usage as llm_usage


class _Doc:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _Query:
    def __init__(self, collection: "_Collection") -> None:
        self._collection = collection

    def stream(self) -> List[_Doc]:
        return self._collection.docs


class _Collection:
    """Records what `where` was called with, and hands back the documents regardless."""

    def __init__(self, docs: List[_Doc]) -> None:
        self.docs = docs
        self.filters: List[Tuple[str, str, Any]] = []
        self.requested_documents: List[str] = []
        self.references: dict = {}

    def where(self, field: str, op: str, value: Any) -> _Query:
        self.filters.append((field, op, value))
        return _Query(self)

    def document(self, doc_id: str) -> Any:
        # A stand-in for the DocumentReference the real collection returns. Constructing a real one here
        # would reach for ambient credentials; what this pins is that the caller RESOLVES the cutoff
        # through the collection instead of handing the query a bare string. That the resolved value must
        # be a Key is Firestore's rule, measured against the emulator and quoted in the module docstring.
        self.requested_documents.append(doc_id)
        reference = object()
        self.references[doc_id] = reference
        return reference


class _UserRef:
    def __init__(self, collection: _Collection) -> None:
        self._collection = collection

    def collection(self, _name: str) -> _Collection:
        return self._collection


class _Db:
    def __init__(self, collection: _Collection) -> None:
        self._collection = collection

    def collection(self, _name: str) -> Any:
        return type('C', (), {'document': lambda _self, _uid: _UserRef(self._collection)})()


def _run(monkeypatch, function, collection: _Collection):
    # setattr rather than mock.patch: patching the module's `db` INTROSPECTS the lazy client proxy
    # (`_is_async_obj`), which resolves a real Firestore client and reaches for ambient credentials.
    monkeypatch.setattr(llm_usage, 'db', _Db(collection))
    return function('test-user')


def test_the_usage_summary_bounds_its_scan_with_a_key(monkeypatch):
    collection = _Collection([_Doc('2026-01-02', {'chat': {'m': {'input_tokens': 1}}})])

    _run(monkeypatch, llm_usage.get_usage_summary, collection)

    field, op, value = collection.filters[0]
    assert (field, op) == ('__name__', '>=')
    assert not isinstance(
        value, str
    ), 'a string here is rejected by Firestore with 400 __key__ filter value must be a Key'
    assert collection.requested_documents, 'the cutoff must be resolved to a reference on this collection'
    assert value is collection.references[collection.requested_documents[0]]


def test_the_plan_usage_report_bounds_its_scan_with_a_key(monkeypatch):
    collection = _Collection([_Doc('2026-01-02', {'plan_usage': {}})])

    _run(monkeypatch, llm_usage.get_plan_usage_report, collection)

    field, op, value = collection.filters[0]
    assert (field, op) == ('__name__', '>=')
    assert not isinstance(value, str)
    assert value is collection.references[collection.requested_documents[0]]


def test_the_cutoff_reference_still_names_a_date(monkeypatch):
    """The bound is unchanged — only its type is. A reference to some other id would silently widen or
    narrow the window."""
    import re

    collection = _Collection([])
    _run(monkeypatch, llm_usage.get_usage_summary, collection)

    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', collection.requested_documents[0])
