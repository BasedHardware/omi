"""Strict key transactions plus emulator-tested candidate key-range erasure.

Only lake_upload_candidates gains standalone deletes and single-field ranges;
all other operations retain StrictFirestore's fail-closed behavior.
"""

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreSnapshot, StrictFirestoreTransaction

from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
)


class CandidateSnapshot(StrictFirestoreSnapshot):
    def __init__(self, data, name):
        super().__init__(data)
        self.id = name


class CandidateDocument(StrictFirestoreDocument):
    def delete(self):
        self._database.rows.pop(self.path, None)


class CandidateQuery:
    def __init__(self, database, path, filters=(), limit=None):
        self._database = database
        self._path = path
        self.filters = filters
        self.count = limit

    def document(self, name):
        return CandidateDocument(self._database, (*self._path, name))

    def where(self, *, filter):
        if filter.field_path != 'key' or filter.op_string not in ('>=', '<'):
            raise NotImplementedError('Candidate queries support only key >= and < filters')
        return CandidateQuery(self._database, self._path, (*self.filters, filter), self.count)

    def limit(self, count):
        return CandidateQuery(self._database, self._path, self.filters, count)

    def stream(self):
        matches = []
        for path, row in tuple(self._database.rows.items()):
            if path[:-1] != self._path or not isinstance(row.get('key'), str):
                continue
            if all(self._matches(row['key'], f) for f in self.filters):
                snapshot = CandidateSnapshot(row, path[-1])
                matches.append(snapshot)
        return iter(matches if self.count is None else matches[: self.count])

    @staticmethod
    def _matches(key, filter):
        if filter.field_path != 'key':
            raise NotImplementedError('Candidate queries support only key filters')
        if filter.op_string == '>=':
            return key >= filter.value
        if filter.op_string == '<':
            return key < filter.value
        raise NotImplementedError('Candidate queries support only >= and < filters')


def _server_times(value: Any, *, now: datetime | None = None) -> Any:
    now = now if now is not None else datetime.now(timezone.utc)
    if value is firestore.SERVER_TIMESTAMP:
        return now
    if isinstance(value, dict):
        return {key: _server_times(item, now=now) for key, item in value.items()}
    return value


class CandidateTransaction(StrictFirestoreTransaction):
    def __init__(self, database, *, allow_reads_after_writes=False, max_attempts=None):
        super().__init__(database, allow_reads_after_writes=allow_reads_after_writes)
        if max_attempts is not None:
            self._max_attempts = max_attempts

    # Limited to candidate timestamp transforms, proven on loopback Firestore.
    def create(self, ref, data):
        super().create(ref, _server_times(data))

    def update(self, ref, patch):
        super().update(ref, _server_times(patch))


class LakeFirestore(StrictFirestore):
    def transaction(self, max_attempts=None):
        transaction = CandidateTransaction(
            self, allow_reads_after_writes=self._allow_reads_after_writes, max_attempts=max_attempts
        )
        self.transactions.append(transaction)
        return transaction

    def collection(self, name) -> Any:
        if name == 'lake_upload_candidates':
            return CandidateQuery(self, (name,))
        return super().collection(name)
