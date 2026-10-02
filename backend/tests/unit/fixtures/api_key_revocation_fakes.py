"""Hermetic API-key Redis and atomic Firestore batch doubles."""

from copy import deepcopy

from google.api_core.exceptions import NotFound

from database.api_key_cache import _FILL_IF_ACTIVE


class RedisStore:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))
        self.values[key] = value
        return True

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)

    def eval(self, script, key_count, *args):
        assert script == _FILL_IF_ACTIVE
        keys, values = args[:key_count], args[key_count:]
        if keys[0] in self.values:
            return 0
        for key, value in zip(keys[1:], values[1:]):
            self.set(key, value, ex=values[0])
        return 1


class AtomicKeyBatch:
    """Stage writes and enforce UPDATE's exists precondition before any SET.

    This intentionally models write-batch atomicity, not transactions or retries.
    ``before_commit`` is a deterministic seam for a revoke winning the race.
    """

    def __init__(self, before_commit=None):
        self.writes = []
        self.before_commit = before_commit

    def update(self, ref, payload):
        self.writes.append(("update", ref, deepcopy(payload), {}))

    def set(self, ref, payload, merge=False):
        self.writes.append(("set", ref, deepcopy(payload), {"merge": merge}))

    def commit(self):
        if self.before_commit:
            self.before_commit()
        for method, ref, _payload, _options in self.writes:
            if method == "update" and not ref.get().exists:
                raise NotFound("batch update requires existing key")
        for method, ref, payload, options in self.writes:
            getattr(ref, method)(payload, **options)
