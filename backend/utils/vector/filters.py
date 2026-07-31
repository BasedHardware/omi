"""The neutral metadata-filter contract for the vector-store port (ADR-0033).

A filter is a Pinecone/Mongo-style dict restricted to a **fixed, backend-agnostic subset** so every
adapter can translate it faithfully. Supported operators — nothing else is allowed:

  - bare equality         ``{"uid": "u1"}``                        field == value
  - ``$eq``               ``{"status": {"$eq": "open"}}``          field == value
  - ``$in``               ``{"topics": {"$in": ["a", "b"]}}``      field (or any of a list field) in values
  - ``$gte`` / ``$lte``   ``{"created_at": {"$gte": 1, "$lte": 9}}``  numeric range (inclusive)
  - ``$exists``           ``{"schema_version": {"$exists": False}}``  key present (True) / absent (False)
  - ``$and`` / ``$or``    ``{"$and": [<filter>, ...]}``             all / any sub-filter matches

``validate()`` rejects anything outside this subset (so no backend-specific semantics leak through the
port), and ``matches()`` is the in-memory interpreter used by ``FakeVectorStore`` and adapters that must
filter client-side.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

_FIELD_OPERATORS = frozenset({"$eq", "$in", "$gte", "$lte", "$exists"})
_LOGICAL_OPERATORS = frozenset({"$and", "$or"})


class UnsupportedFilterError(ValueError):
    """Raised when a filter uses an operator outside the neutral contract."""


def validate(flt: Mapping[str, Any]) -> None:
    """Raise UnsupportedFilterError if ``flt`` uses anything outside the neutral subset."""
    if not isinstance(flt, Mapping):
        raise UnsupportedFilterError(f"filter must be a dict, got {type(flt).__name__}")
    for key, value in flt.items():
        if key in _LOGICAL_OPERATORS:
            if not isinstance(value, (list, tuple)) or not value:
                raise UnsupportedFilterError(f"{key} takes a non-empty list of sub-filters")
            for sub in value:
                validate(sub)
        elif key.startswith("$"):
            raise UnsupportedFilterError(f"unsupported top-level operator {key!r}")
        elif isinstance(value, Mapping):
            for op in value:
                if op not in _FIELD_OPERATORS:
                    raise UnsupportedFilterError(f"unsupported operator {op!r} on field {key!r}")
        # else: bare-equality scalar — always allowed


def _present(metadata: Mapping[str, Any], field: str) -> bool:
    return field in metadata and metadata[field] is not None


def _match_field(field: str, condition: Any, metadata: Mapping[str, Any]) -> bool:
    if not isinstance(condition, Mapping):
        return metadata.get(field) == condition  # bare equality

    for op, operand in condition.items():
        if op == "$eq":
            if metadata.get(field) != operand:
                return False
        elif op == "$in":
            value = metadata.get(field)
            options = set(operand)
            hit = any(v in options for v in value) if isinstance(value, (list, tuple)) else value in options
            if not hit:
                return False
        elif op == "$gte":
            value = metadata.get(field)
            if value is None or value < operand:
                return False
        elif op == "$lte":
            value = metadata.get(field)
            if value is None or value > operand:
                return False
        elif op == "$exists":
            if bool(operand) != _present(metadata, field):
                return False
        else:  # defensive — validate() should have caught it
            raise UnsupportedFilterError(f"unsupported operator {op!r} on field {field!r}")
    return True


def matches(flt: Mapping[str, Any], metadata: Mapping[str, Any]) -> bool:
    """Evaluate a neutral filter against a metadata dict (AND across top-level field clauses)."""
    for key, value in flt.items():
        if key == "$and":
            if not all(matches(sub, metadata) for sub in value):
                return False
        elif key == "$or":
            if not any(matches(sub, metadata) for sub in value):
                return False
        else:
            if not _match_field(key, value, metadata):
                return False
    return True


__all__ = ["UnsupportedFilterError", "validate", "matches"]
