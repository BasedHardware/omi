"""Read-only document capabilities plus discarded transaction plans.

The assignment planner gets no SDK client, writer, commit or raw reference.
Only the injected bounded reader can leave this object. Planned writes are
counted and discarded in memory, never forwarded to a customer data plane.
"""

from copy import deepcopy
import time


class ShadowBoundaryError(RuntimeError):
    pass


class Snapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return deepcopy(self._data)


class Reference:
    def __init__(self, transaction, path):
        self._transaction, self._path = transaction, tuple(path)

    @property
    def id(self):
        return self._path[-1]

    @property
    def path(self):
        return '/'.join(self._path)

    @property
    def document_path(self):
        return self._path

    def belongs_to(self, transaction):
        return self._transaction is transaction

    @property
    def parent(self):
        return Collection(self._transaction, self._path[:-1])

    def collection(self, name):
        return Collection(self._transaction, (*self._path, name))

    def get(self, transaction=None, *, field_paths=None, **kwargs):
        if transaction is not None and transaction is not self._transaction:
            raise ShadowBoundaryError('foreign_transaction')
        data = self._transaction.read(self._path, field_paths)
        return Snapshot(self, data)


class Collection:
    def __init__(self, transaction, path):
        self._transaction, self._path = transaction, tuple(path)

    @property
    def parent(self):
        return Reference(self._transaction, self._path[:-1])

    def document(self, name):
        if not isinstance(name, str) or not name or '/' in name:
            raise ShadowBoundaryError('invalid_document_name')
        return Reference(self._transaction, (*self._path, name))


class ShadowTransaction:
    def __init__(self, owner, reader, *, seconds=2, max_reads=16, clock=time.monotonic):
        self.owner, self._reader, self.clock = owner, reader, clock
        self.deadline, self.max_reads = clock() + seconds, max_reads
        self.reads = self.writes = 0
        self._cache = {}
        self._writing = False

    def user(self):
        return Reference(self, ('users', self.owner))

    def _check(self, path):
        if self.clock() >= self.deadline:
            raise ShadowBoundaryError('time_budget')
        if tuple(path[:2]) != ('users', self.owner):
            raise ShadowBoundaryError('foreign_owner')
        if (
            len(path) not in (2, 4)
            or len(path) == 4
            and path[2]
            not in {'conversations', 'deleted_conversations', 'sync_assignment', 'people', 'batch_capture_intervals'}
        ):
            raise ShadowBoundaryError('unsupported_collection')

    def read(self, path, fields=None):
        self._check(path)
        if self._writing:
            raise ShadowBoundaryError('read_after_write')
        key = (tuple(path), tuple(fields) if fields else None)
        if key not in self._cache:
            if self.reads >= self.max_reads:
                raise ShadowBoundaryError('read_budget')
            self.reads += 1
            self._cache[key] = deepcopy(self._reader(tuple(path), fields, min(1, self.deadline - self.clock())))
        return deepcopy(self._cache[key])

    def _discard_write(self, reference, payload, **kwargs):
        if not isinstance(reference, Reference) or not reference.belongs_to(self):
            raise ShadowBoundaryError('foreign_write_reference')
        self._check(reference.document_path)
        if not isinstance(payload, dict) or self.writes >= 256:
            raise ShadowBoundaryError('write_plan_budget')
        self._writing = True
        self.writes += 1
        # Deliberately retain neither transcript payloads nor write operations.

    set = _discard_write
    create = _discard_write
    update = _discard_write

    def commit(self, *args, **kwargs):
        raise ShadowBoundaryError('commit_forbidden')

    def next_part(self):
        """A fresh discarded write phase; cached reads remain the same snapshot."""
        self._writing = False

    def delete(self, *args, **kwargs):
        raise ShadowBoundaryError('delete_forbidden')

    def close(self):
        self._cache.clear()
