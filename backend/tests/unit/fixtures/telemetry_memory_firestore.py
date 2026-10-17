"""Optimistic in-memory Firestore double for client-telemetry transactions."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from database.client_telemetry import RetryableTransaction


class MemorySnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = deepcopy(data)
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class MemoryDocument:
    def __init__(self, database: TelemetryMemoryFirestore, path: tuple[str, str]):
        self._database = database
        self.path = path

    def get(self, transaction: MemoryTransaction | None = None) -> MemorySnapshot:
        if transaction is not None:
            return transaction.read(self)
        return MemorySnapshot(self._database.read_committed(self.path))

    def delete(self) -> None:
        self._database.delete(self.path)


class MemoryCollection:
    def __init__(self, database: TelemetryMemoryFirestore, name: str):
        self._database = database
        self._name = name

    def document(self, name: str) -> MemoryDocument:
        return MemoryDocument(self._database, (self._name, name))

    def stream(self) -> list["MemoryStreamSnapshot"]:
        out: list[MemoryStreamSnapshot] = []
        for (collection, document_id), (_, data) in sorted(self._database.items().items()):
            if collection != self._name:
                continue
            out.append(MemoryStreamSnapshot(self._database, (collection, document_id), deepcopy(data)))
        return out


class MemoryStreamSnapshot:
    def __init__(self, database: TelemetryMemoryFirestore, path: tuple[str, str], data: dict[str, Any]):
        self._database = database
        self.path = path
        self._data = data

    @property
    def reference(self) -> MemoryDocument:
        return MemoryDocument(self._database, self.path)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)


class MemoryTransaction:
    def __init__(self, database: TelemetryMemoryFirestore):
        self._database = database
        self._reads: dict[tuple[str, str], int] = {}
        self._writes: dict[tuple[str, str], dict[str, Any]] = {}

    def read(self, ref: MemoryDocument) -> MemorySnapshot:
        version, data = self._database.peek(ref.path)
        self._reads[ref.path] = version
        return MemorySnapshot(data)

    def set(self, ref: MemoryDocument, data: dict[str, Any]) -> None:
        self._writes[ref.path] = deepcopy(data)

    def commit(self) -> None:
        self._database.commit(self._reads, self._writes)

    def discard(self) -> None:
        self._writes.clear()
        self._reads.clear()


class TelemetryMemoryFirestore:
    """Commits only when every read version still matches."""

    manual_telemetry_transaction = True

    def __init__(self) -> None:
        self._lock = RLock()
        self._rows: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}

    def collection(self, name: str) -> MemoryCollection:
        return MemoryCollection(self, name)

    def transaction(self) -> MemoryTransaction:
        return MemoryTransaction(self)

    def peek(self, path: tuple[str, str]) -> tuple[int, dict[str, Any] | None]:
        with self._lock:
            version, data = self._rows.get(path, (0, None))
            return version, deepcopy(data)

    def items(self) -> dict[tuple[str, str], tuple[int, dict[str, Any]]]:
        with self._lock:
            return deepcopy(self._rows)

    def read_committed(self, path: tuple[str, str]) -> dict[str, Any] | None:
        with self._lock:
            row = self._rows.get(path)
            if row is None:
                return None
            return deepcopy(row[1])

    def commit(
        self,
        reads: dict[tuple[str, str], int],
        writes: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        with self._lock:
            for path, version in reads.items():
                current = self._rows.get(path, (0, None))[0]
                if current != version:
                    raise RetryableTransaction()
            for path, data in writes.items():
                current = self._rows.get(path, (0, None))[0]
                self._rows[path] = (current + 1, deepcopy(data))

    def delete(self, path: tuple[str, str]) -> None:
        with self._lock:
            self._rows.pop(path, None)

    def plant(self, collection: str, document_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            path = (collection, document_id)
            current = self._rows.get(path, (0, None))[0]
            self._rows[path] = (current + 1, deepcopy(data))
