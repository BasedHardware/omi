"""Strict Dream-only query/batch extension, witnessed by the local emulator suite.

Document/transaction ownership and read-before-write checks come from the shared
StrictFirestore fixture. This adds only the ordered dirty query, aggregation,
atomic transforms and fenced deletion used by the Dream queue; no retry model.
"""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from google.cloud import firestore
from google.cloud.firestore_v1.transforms import Increment

from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
    StrictFirestoreTransaction,
    _assert_storable,
)


def merged(current, data, merge):
    _assert_storable(data)
    result = deepcopy(current) if merge else {}
    for key, value in data.items():
        if value is firestore.SERVER_TIMESTAMP:
            result[key] = datetime.now(timezone.utc)
        elif isinstance(value, Increment):
            result[key] = current.get(key, 0) + value.value
        else:
            result[key] = deepcopy(value)
    return result


class Document(StrictFirestoreDocument):
    def collection(self, name):
        return Query(self._database, (*self.path, name))

    def get(self, transaction=None, **kwargs):
        self._database.reads.append(self.path)
        result = super().get(transaction=transaction, **kwargs)
        result.reference = self
        result.id = self.id
        return result

    def set(self, data, merge=False):
        self._database.rows[self.path] = merged(self._database.rows.get(self.path, {}), data, merge)


class Query:
    def __init__(self, database, path, *, order=None, descending=False, bound=None):
        self.database = database
        self.path = path
        self.order = order
        self.descending = descending
        self.bound = bound

    def document(self, key):
        return Document(self.database, (*self.path, key))

    def order_by(self, field, direction='ASCENDING'):
        assert field == 'last_changed_at'
        return Query(self.database, self.path, order=field, descending=direction == 'DESCENDING', bound=self.bound)

    def limit(self, count):
        assert 0 < count <= 500
        return Query(self.database, self.path, order=self.order, descending=self.descending, bound=count)

    def _rows(self):
        return [(path, row) for path, row in self.database.rows.items() if path[:-1] == self.path]

    def count(self):
        def get(transaction=None):
            if transaction is not None:
                assert transaction._database is self.database
                transaction._assert_read_allowed()
            return [[SimpleNamespace(value=len(self._rows()))]]

        return SimpleNamespace(get=get)

    def stream(self, transaction=None):
        assert self.order and self.bound
        if transaction is not None:
            assert transaction._database is self.database
            transaction._assert_read_allowed()
        rows = sorted(self._rows(), key=lambda pair: (pair[1][self.order], pair[0]), reverse=self.descending)
        result = []
        for path, row in rows[: self.bound]:
            snapshot = StrictFirestoreSnapshot(row)
            snapshot.reference = Document(self.database, path)
            snapshot.id = path[-1]
            result.append(snapshot)
        return iter(result)


class Transaction(StrictFirestoreTransaction):
    def set(self, ref, data, merge=False):
        super().set(ref, merged(self._database.rows.get(ref.path, {}), data, merge))

    def delete(self, ref):
        self._assert_reference_belongs(ref)
        self.has_written = True
        self._database.rows.pop(ref.path, None)


class Batch:
    def __init__(self, database):
        self.database = database
        self.writes = []

    def set(self, ref, data, merge=False):
        _assert_storable(data)
        self.writes.append((ref, data, merge))

    def commit(self):
        assert len(self.writes) <= 500
        with self.database.lock:
            for ref, data, merge in self.writes:
                ref.set(data, merge=merge)


class DreamFirestore(StrictFirestore):
    def __init__(self):
        super().__init__()
        self.reads = []

    def collection(self, name):
        return Query(self, (name,))

    def transaction(self):
        tx = Transaction(self)
        self.transactions.append(tx)
        return tx

    def batch(self):
        return Batch(self)
