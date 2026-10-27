"""A set-merge fake validated through the real Firestore protobuf serializer."""

from copy import deepcopy
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.transforms import Increment, ArrayUnion


def merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict):
            merge(target.setdefault(key, {}), value)
        elif isinstance(value, Increment):
            target[key] = target.get(key, 0) + value._value
        elif isinstance(value, ArrayUnion):
            old = target.setdefault(key, [])
            for item in value._values:
                if item not in old:
                    old.append(deepcopy(item))
        else:
            target[key] = deepcopy(value)


class Snapshot:
    def __init__(self, path, data):
        self.id = path.split('/')[-1]
        self.exists = data is not None
        self.data = data

    def to_dict(self):
        return deepcopy(self.data)


class Doc:
    def __init__(self, store, path):
        self.store = store
        self.path = path
        self.id = path.split('/')[-1]

    def collection(self, name):
        return Collection(self.store, self.path + '/' + name)

    @property
    def parent(self):
        return Collection(self.store, self.path.rsplit('/', 1)[0])

    def get(self, field_paths=None, transaction=None):
        if transaction is not None and getattr(transaction, 'pending', []):
            raise RuntimeError('Firestore transactions must read before writing')
        self.store.reads += 1
        data = self.store.docs.get(self.path)
        if data is not None and field_paths:
            data = {k: v for k, v in data.items() if k in field_paths}
        return Snapshot(self.path, data)

    def create(self, data):
        if self.path in self.store.docs:
            raise AlreadyExists('duplicate')
        self.set(data, merge=False)

    def set(self, data, merge=True):
        self.store.wire.extend(
            _helpers.pbs_for_set_with_merge(
                'projects/test/databases/(default)/documents/' + self.path, data, merge=True
            )
        )
        self.store.writes += 1
        if not merge:
            self.store.docs[self.path] = {}
        globals()['merge'](self.store.docs.setdefault(self.path, {}), data)


class Collection:
    def __init__(self, store, path, filters=(), fields=None, cap=None):
        self.store = store
        self.path = path
        self.filters = filters
        self.fields = fields
        self.cap = cap

    def document(self, id):
        return Doc(self.store, self.path + '/' + id)

    @property
    def parent(self):
        return Doc(self.store, self.path.rsplit('/', 1)[0])

    def where(self, filter):
        return Collection(self.store, self.path, (*self.filters, filter), self.fields, self.cap)

    def select(self, fields):
        return Collection(self.store, self.path, self.filters, fields, self.cap)

    def limit(self, cap):
        return Collection(self.store, self.path, self.filters, self.fields, cap)

    def stream(self):
        result = []
        for path, data in self.store.docs.items():
            if path.rsplit('/', 1)[0] != self.path:
                continue
            matched = True
            for f in self.filters:
                value = path.rsplit('/', 1)[-1] if f.field_path == '__name__' else data.get(f.field_path)
                operand = getattr(f.value, 'id', f.value)
                if f.op_string == '==' and value != operand:
                    matched = False
                if f.op_string == '>=' and (value is None or value < operand):
                    matched = False
                if f.op_string == '<' and (value is None or value >= operand):
                    matched = False
            if matched:
                result.append(Snapshot(path, {k: v for k, v in data.items() if not self.fields or k in self.fields}))
        result = result[: self.cap] if self.cap else result
        self.store.reads += len(result)
        return iter(result)


class Store:
    def __init__(self, docs=None):
        self.docs = deepcopy(docs or {})
        self.writes = 0
        self.reads = 0
        self.wire = []

    def collection(self, name):
        return Collection(self, name)

    def get_all(self, references, field_paths=None):
        self.batch_reads = getattr(self, "batch_reads", 0) + 1
        return [ref.get(field_paths) for ref in references]

    def transaction(self):
        return Transaction()

    def batch(self):
        return Batch()


class Batch:
    """Serialize all writes before applying; transaction races use the emulator."""

    def __init__(self):
        self.pending = []

    def set(self, ref, data, merge=False):
        # Validate each payload with the SDK before staging any mutation.
        _helpers.pbs_for_set_with_merge('projects/test/databases/(default)/documents/' + ref.path, data, merge=merge)
        self.pending.append((ref, data, merge))

    def commit(self):
        for ref, data, merge in self.pending:
            ref.set(data, merge=merge)


class Transaction(Batch):
    """Single-attempt serialized writes; retry/erasure semantics use the emulator."""

    _read_only = False
    _max_attempts = 1
    _id = None

    def _clean_up(self):
        self.pending.clear()
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'shadow-usage-test'

    def _commit(self):
        self.commit()

    def _rollback(self):
        self.pending.clear()
