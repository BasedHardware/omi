"""In-memory Firestore double for the shadow slot conditional-write lane.

The strict transaction fixture certifies the transactional slot ring; this
double certifies its replacement lane. It models exactly the surface that lane
uses — plain point reads with ``update_time`` fences, ``create`` existence
refusal, ``LastUpdateOption``-fenced merges with ``DELETE_FIELD`` semantics —
and raises Firestore precondition errors when a write loses a fence race.
Every fence value doubles as a generation: two writers that read the same
fence cannot both commit, which is the production lane's entire arbiter.

Transactions remain single-attempt and read-before-write, mirroring
``FirestoreStore.run``. Operations can be injected per ``shadow_operation``
label so tests can prove the CAS path never opens the transactional ring
read set that aborts concurrent workers in production, and fence races can
be staged at exact write boundaries through ``race_hooks``.
"""

from copy import deepcopy
from threading import RLock

from database.batch_pipeline_transaction_labels import current_operation
from database.firestore_transaction_retry import FirestoreContentionExhausted
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from google.cloud.firestore import DELETE_FIELD


class CASDoubleSnapshot:
    def __init__(self, data, update_time):
        self._data = deepcopy(data)
        self.update_time = update_time
        self.id = None

    def to_dict(self):
        return deepcopy(self._data)


class _CASDoubleDocument:
    def __init__(self, database, key):
        self._database = database
        self._key = key

    def get(self, *args, **kwargs):
        with self._database.lock:
            self._database.reads.append(self._key)
            data, fence = self._database.rows.get(self._key, ({}, None))
            return CASDoubleSnapshot(data, fence)

    def create(self, value, **kwargs):
        with self._database.lock:
            self._database.creates.append(self._key)
            hook = self._database.race_hooks.get(self._key)
            if hook is not None:
                hook()
            if self._key in self._database.rows:
                raise AlreadyExists('document already exists')
            self._database.rows[self._key] = (deepcopy(value), self._database.generation())

    def update(self, value, option=None, retry=None, **kwargs):
        with self._database.lock:
            self._database.updates.append((self._key, deepcopy(value), retry))
            current = self._database.rows.get(self._key)
            fence = getattr(option, '_last_update_time', None)
            # One-shot: the concurrent winner commits exactly once, then the
            # race is gone (subsequent writes see its generation normally).
            hook = self._database.race_hooks.pop(self._key, None)
            if hook is not None:
                hook()
            current = self._database.rows.get(self._key)
            if current is None or current[1] != fence:
                raise FailedPrecondition('document updated since its read')
            merged = dict(current[0])
            for key, val in value.items():
                if val is DELETE_FIELD:
                    merged.pop(key, None)  # A sentinel deletes the field outright.
                else:
                    merged[key] = deepcopy(val)
            self._database.rows[self._key] = (merged, self._database.generation())


class _CASDoubleCollection:
    def __init__(self, database, prefix):
        self._database = database
        self._prefix = prefix
        self._filter = None
        self._limit = None

    def document(self, name):
        return _CASDoubleDocument(self._database, (self._prefix, name))

    def where(self, field, op, value):
        if op != '<=':
            raise NotImplementedError('the CAS double models only bounded created_at windows')
        self._filter = (field, value)
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        if self._filter is None or self._limit is None:
            raise NotImplementedError('unbounded scans are not modeled')
        field, before = self._filter
        rows = []
        for (prefix, name), (data, _fence) in sorted(self._database.rows.items()):
            if prefix != self._prefix:
                continue
            created = data.get(field)
            if not isinstance(created, (int, float)) or created > before:
                continue
            snapshot = CASDoubleSnapshot(data, None)
            snapshot.id = name
            rows.append(snapshot)
            if len(rows) >= self._limit:
                break
        return iter(rows)


class _CASDoubleClient:
    def __init__(self):
        self.rows = {}
        self.created = []
        self.reads = []
        self.creates = []
        self.updates = []
        self.race_hooks = {}
        self._generations = 0
        self.lock = RLock()

    def generation(self):
        with self.lock:
            self._generations += 1
            return f'gen-{self._generations}'

    def collection(self, name):
        return _CASDoubleCollection(self, name)


class _CASDoubleTransaction:
    """Read-before-write transaction view over the shared rows."""

    def __init__(self, database):
        self._database = database
        self.reads = []
        self._writes = {}

    def get(self, table, key):
        self.reads.append((table, key))
        data, _ = self._database.client.rows.get((f'{self._database.namespace}_{table}', key), ({}, None))
        return deepcopy(data)

    def put(self, table, key, value):
        self._writes[(table, key)] = deepcopy(value)

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        if self._database.privacy is not None:
            self._database.privacy(uid)
        return 0

    def flush(self):
        with self._database.client.lock:
            for (table, key), value in self._writes.items():
                address = (f'{self._database.namespace}_{table}', key)
                current = self._database.client.rows.get(address, ({}, None))
                merged = dict(current[0])
                for field, val in value.items():
                    if val is DELETE_FIELD:
                        merged.pop(field, None)
                    else:
                        merged[field] = deepcopy(val)
                self._database.client.rows[address] = (merged, self._database.client.generation())


class ShadowStoreDouble:
    """Store double for ``ShadowStore`` on the conditional-write lane."""

    def __init__(self, *, clock=None, busy=False, refuse=(), privacy=None):
        self.client = _CASDoubleClient()
        self.namespace = 'batch_pipeline_dev'
        # One shared mutable instant: every replica constructed over this
        # double reads the same ``now`` through the same closure, so a test
        # moves the whole fleet's clock in one assignment.
        self.now = 7200.0
        self.clock = clock or (lambda: self.now)
        self._busy = busy
        self._refuse = set(refuse)
        self.privacy = privacy
        self.transactions = []

    def refuse(self, operation):
        """Inject one failed transaction attempt (contention exhaustion)."""
        self._refuse.add(operation)

    def race(self, table, key, hook):
        """Stage a concurrent writer that commits inside one fenced write.

        The hook runs while the production write is in flight, before the
        fence is compared — exactly the interleaving a real concurrent
        writer produces when it wins between this reader's read and write.
        """
        self.client.race_hooks[(f'{self.namespace}_{table}', key)] = hook

    def clear_race(self, table, key):
        self.client.race_hooks.pop((f'{self.namespace}_{table}', key), None)

    def row(self, table, key):
        """Direct test read of one stored document (arrange/assert only)."""
        return deepcopy(self.client.rows.get((f'{self.namespace}_{table}', key), ({}, None))[0])

    def slot(self, index):
        return self.row('shadow_slots', str(index))

    def job(self, segment):
        return self.row('shadow_jobs', segment)

    def fence(self, table, key):
        return self.client.rows.get((f'{self.namespace}_{table}', key), ({}, None))[1]

    def labels(self):
        return [operation for operation, _transaction in self.transactions]

    def rewrite(self, table, key, value):
        """Unfenced arrange helper: force one row without a fence race."""
        address = (f'{self.namespace}_{table}', key)
        self.client.rows[address] = (deepcopy(value), self.client.generation())

    def run(self, body):
        # ``shadow_operation`` labels are prefixed; refuse on the bare
        # operation name the store API uses. The injection lands after the
        # bounded retry budget, exactly what callers observe in production.
        operation = current_operation().removeprefix('batch_shadow_')
        if operation in self._refuse:
            raise FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {operation}')
        transaction = _CASDoubleTransaction(self)
        self.transactions.append((operation, transaction))
        result = body(transaction)
        transaction.flush()
        return result
