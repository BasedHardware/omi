"""Strict key transactions plus emulator-tested candidate key-range erasure.

Only lake_upload_candidates gains standalone deletes and single-field ranges;
all other operations retain StrictFirestore's fail-closed behavior.
"""

from types import SimpleNamespace

from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreDocument,
)


class CandidateDocument(StrictFirestoreDocument):
    def delete(self):
        self._database.rows.pop(self.path, None)


class CandidateQuery(StrictFirestoreCollection):
    def __init__(self, database, path, filters=(), limit=None):
        super().__init__(database, path)
        self.filters = filters
        self.count = limit

    def document(self, name):
        return CandidateDocument(self._database, (*self._path, name))

    def where(self, *, filter):
        assert filter.field_path == 'key' and filter.op_string in ('>=', '<')
        return CandidateQuery(self._database, self._path, (*self.filters, filter), self.count)

    def limit(self, count):
        return CandidateQuery(self._database, self._path, self.filters, count)

    def stream(self):
        matches = []
        for path, row in tuple(self._database.rows.items()):
            if path[:-1] != self._path or not isinstance(row.get('key'), str):
                continue
            if all(row['key'] >= f.value if f.op_string == '>=' else row['key'] < f.value for f in self.filters):
                matches.append(SimpleNamespace(id=path[-1]))
        return iter(matches if self.count is None else matches[: self.count])


class LakeFirestore(StrictFirestore):
    def collection(self, name):
        if name == 'lake_upload_candidates':
            return CandidateQuery(self, (name,))
        return super().collection(name)
