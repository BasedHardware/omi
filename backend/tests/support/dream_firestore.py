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
        result = super().get(transaction=transaction)
        result.reference = self
        result.id = self.id
        return result

    def set(self, data, merge=False):
        self._database.rows[self.path] = merged(self._database.rows.get(self.path, {}), data, merge)

    def delete(self):
        self._database.rows.pop(self.path, None)


class Query:
    def __init__(self, database, path, *, order=None, descending=False, bound=None, after=None, projection=None):
        self.database = database
        self.path = path
        self.order = order
        self.descending = descending
        self.bound = bound
        self.after = after
        self.projection = projection

    def document(self, key):
        return Document(self.database, (*self.path, key))

    def order_by(self, field, direction='ASCENDING'):
        return Query(
            self.database,
            self.path,
            order=field,
            descending=direction == 'DESCENDING',
            bound=self.bound,
            after=self.after,
            projection=self.projection,
        )

    def select(self, fields):
        return Query(
            self.database,
            self.path,
            order=self.order,
            descending=self.descending,
            bound=self.bound,
            after=self.after,
            projection=fields,
        )

    def start_after(self, cursor):
        assert self.order == '__name__' and set(cursor) == {'__name__'}
        return Query(
            self.database,
            self.path,
            order=self.order,
            descending=self.descending,
            bound=self.bound,
            after=cursor['__name__'].id,
            projection=self.projection,
        )

    def limit(self, count):
        assert 0 < count <= 500
        return Query(
            self.database,
            self.path,
            order=self.order,
            descending=self.descending,
            bound=count,
            after=self.after,
            projection=self.projection,
        )

    def _rows(self):
        return [(path, row) for path, row in self.database.rows.items() if path[:-1] == self.path]

    def count(self):
        def get(transaction=None):
            if transaction is not None:
                assert transaction._database is self.database
                transaction._assert_read_allowed()
            return [[SimpleNamespace(value=len(self._rows()))]]

        return SimpleNamespace(get=get)

    def stream(self, transaction=None, timeout=None, retry=None):
        if timeout is not None:
            assert 0 < timeout <= 3
        assert self.order and self.bound
        if transaction is not None:
            assert transaction._database is self.database
            transaction._assert_read_allowed()

        def order_value(path, row):
            if self.order == '__name__':
                return path[-1]
            value = row
            for field in self.order.split('.'):
                if not isinstance(value, dict) or field not in value:
                    return None
                value = value[field]
            return value

        ordered = [(order_value(path, row), path, row) for path, row in self._rows()]
        rows = sorted(
            ((value, path, row) for value, path, row in ordered if value is not None),
            key=lambda entry: (entry[0], entry[1]),
            reverse=self.descending,
        )
        if self.after is not None:
            rows = [entry for entry in rows if entry[1][-1] > self.after]
        result = []
        for _, path, row in rows[: self.bound]:
            projected = (
                row if self.projection is None else {field: row[field] for field in self.projection if field in row}
            )
            snapshot = StrictFirestoreSnapshot(projected)
            snapshot.reference = Document(self.database, path)
            snapshot.id = path[-1]
            result.append(snapshot)
        return iter(result)


class Transaction(StrictFirestoreTransaction):
    def update(self, ref, data):
        # Dotted paths and DELETE_FIELD are witnessed by the real local SDK
        # overlay/invalidation/Undo test, rather than guessed in this fixture.
        super().update(ref, data)
        row = self._database.rows[ref.path]
        for field, value in data.items():
            if '.' not in field:
                if value is firestore.DELETE_FIELD:
                    row.pop(field, None)
                continue
            row.pop(field, None)
            parent = row
            parts = field.split('.')
            for part in parts[:-1]:
                if value is firestore.DELETE_FIELD and part not in parent:
                    parent = None
                    break
                parent = parent.setdefault(part, {})
            if parent is not None:
                if value is firestore.DELETE_FIELD:
                    parent.pop(parts[-1], None)
                else:
                    parent[parts[-1]] = deepcopy(value)

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

    def get_all(self, references, *, transaction=None, timeout=None, field_paths=None):
        assert len(references) <= 100
        if field_paths is not None:
            return super().get_all(references, transaction=transaction, field_paths=field_paths)
        if timeout is not None:
            assert 0 < timeout <= 3
        return [reference.get(transaction=transaction) for reference in references]
