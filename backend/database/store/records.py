"""Neutral document record returned by the storage port.

Independent of the backend: carries no Firestore ``DocumentSnapshot`` type. It mirrors the read
surface the codebase already depends on — ``.exists`` / ``.to_dict()`` / ``.id`` / ``.path`` — so
``database.read_boundary`` and existing callers keep working, but a Mongo/ArcadeDB adapter produces
the exact same record. This is what makes the implementations interchangeable rather than
Firestore-emulating.

``updated_at`` is the backend-neutral **last-write revision** (ADR-0017): the Firestore adapter
fills it from the snapshot ``update_time`` (DB commit time); the Mongo adapter stamps ``_updated_at``
on every write. ``None`` when the backend did not report one (e.g. a projection that excluded it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StoredDocument:
    """One document read result, backend-agnostic.

    ``data`` is ``None`` exactly when ``exists`` is ``False``. ``path`` is the full logical path
    (e.g. ``users/{uid}/people/{pid}``); ``id`` is its last segment. ``updated_at`` is the neutral
    last-write revision (see module docstring), or ``None`` if the backend did not report one.
    """

    id: str
    path: str
    exists: bool
    data: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        """Return the document body, or ``None`` if it does not exist (snapshot-compatible)."""
        return self.data

    @classmethod
    def present(cls, path: str, data: Dict[str, Any], *, updated_at: Optional[datetime] = None) -> "StoredDocument":
        return cls(id=path.rsplit("/", 1)[-1], path=path, exists=True, data=data, updated_at=updated_at)

    @classmethod
    def missing(cls, path: str) -> "StoredDocument":
        return cls(id=path.rsplit("/", 1)[-1], path=path, exists=False, data=None)
