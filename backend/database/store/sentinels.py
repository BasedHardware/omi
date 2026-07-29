"""Neutral field-transform sentinels for the storage port.

Domain code expresses mutations in backend-agnostic terms; each adapter maps them to its own
primitive (Firestore: ``DELETE_FIELD`` / ``ArrayUnion`` / ``ArrayRemove`` / ``Increment`` /
``SERVER_TIMESTAMP``; Mongo: ``$unset`` / ``$addToSet`` / ``$pull`` / ``$inc`` / ``$currentDate``).
No SDK type leaks into the domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


class _Delete:
    """Remove the field. Adapter maps to Firestore DELETE_FIELD / Mongo $unset."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "DELETE"

    # Stateless singleton: copying must preserve identity so ``value is DELETE`` holds after a
    # (deep)copy of a write payload — adapters and fakes match this sentinel by identity.
    def __copy__(self) -> "_Delete":
        return self

    def __deepcopy__(self, memo: Any) -> "_Delete":
        return self


class _ServerTimestamp:
    """Server-side timestamp. Adapter maps to Firestore SERVER_TIMESTAMP / Mongo $currentDate."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "SERVER_TIMESTAMP"

    # Stateless singleton: copying must preserve identity (see ``_Delete``).
    def __copy__(self) -> "_ServerTimestamp":
        return self

    def __deepcopy__(self, memo: Any) -> "_ServerTimestamp":
        return self


@dataclass(frozen=True)
class ArrayUnion:
    values: List[Any]


@dataclass(frozen=True)
class ArrayRemove:
    values: List[Any]


@dataclass(frozen=True)
class Increment:
    amount: float


DELETE = _Delete()
SERVER_TIMESTAMP = _ServerTimestamp()

__all__ = ["DELETE", "SERVER_TIMESTAMP", "ArrayUnion", "ArrayRemove", "Increment"]
