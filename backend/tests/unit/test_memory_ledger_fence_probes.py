"""The legacy-commit privacy fences must not pay phantom per-memory lookups.

Every legacy ledger commit reads ``memory_items/{id}`` and
``memory_historical_overrides/{id}`` per mutation id inside the transaction.
Users without suppression history have no override documents and no tombstoned
items, so those reads come back NOT_FOUND — the 1:1 phantom pair that
dominated Firestore ``NOT_FOUND`` read volume (cost card C015, measured
~4.4M/day per collection on 2026-10-18).

The fence pre-screens with two transactional limit-1 probes (any override
document; any tombstoned item). When both probes come back empty the exact
per-memory reads are skipped — two billed empty queries instead of two
NOT_FOUND lookups per id. When a probe matches (or cannot run), the exact
reads run unchanged, so every fence outcome is preserved.

Fence contract that must keep holding (2026-09-08 KB card section):
both docs absent -> historical admitted; override present -> suppressed,
never 503; item or override present but unreadable -> fenced.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


class _ProbeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _ProbeDocument:
    """DocumentReference fake that records exact (phantom) lookups."""

    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        self._db.gets.append(self.path)
        return _ProbeSnapshot(self._db.docs.get(self.path))


class _ProbeQuery:
    """limit/where chain fake the fence probes run through transaction.get."""

    def __init__(self, db, path):
        self._db = db
        self._path = path
        self._status = None

    def limit(self, _count):
        return self

    def where(self, *, filter):
        self._status = getattr(filter, "value", None)
        return self

    def _matches(self, key, payload):
        if not key.startswith(f"{self._path}/"):
            return False
        if self._status is None:
            return True
        return isinstance(payload, dict) and payload.get("status") == self._status


class _ProbeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []

    def set(self, ref, payload):
        self.sets.append((getattr(ref, "path", str(ref)), payload))

    def get(self, query_or_ref):
        if isinstance(query_or_ref, _ProbeQuery):
            return [
                _ProbeSnapshot(self._db.docs[key])
                for key, payload in sorted(self._db.docs.items())
                if query_or_ref._matches(key, payload)
            ]
        return query_or_ref.get(transaction=self)


class _ProbeDb:
    """Db fake supporting both document gets and the fence's probe queries."""

    def __init__(self, docs):
        self.docs = dict(docs)
        self.gets = []

    def collection(self, name):
        return _ProbeQuery(self, name)

    def document(self, path):
        return _ProbeDocument(self, path)


@pytest.fixture(scope="module")
def memory_ledger():
    """Load fresh database.memory_ledger against stubbed clients.

    Mirrors the sanctioned fake-must-precede-import setup in
    tests/unit/test_memory_ledger.py, plus a FieldFilter stub so the fence's
    probe executes its real filter-building code path.
    """
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")
    client_stub.data_plane_db = client_stub.db
    client_stub.document_id_from_seed = lambda seed: "id-" + str(abs(hash(seed)) % (10**12))

    legal_holds_stub = ModuleType("database.legal_holds")

    class _LegalHoldAuthorityUnavailable(RuntimeError):
        pass

    legal_holds_stub.LegalHoldAuthorityUnavailable = _LegalHoldAuthorityUnavailable
    legal_holds_stub.assert_no_destructive_operation_transaction = lambda *_args, **_kwargs: None
    legal_holds_stub.assert_destructive_gate_still_ours = lambda *_args, **_kwargs: None
    legal_holds_stub.assert_destructive_operation_transaction = lambda *_args, **_kwargs: None
    legal_holds_stub.current_destructive_operation_token = lambda *_args, **_kwargs: "test-token"

    class _StubFieldFilter:
        def __init__(self, field_path, op_string, value):
            self.field_path = field_path
            self.op_string = op_string
            self.value = value

    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_v1_stub = ModuleType("google.cloud.firestore_v1")
    firestore_v1_stub.transactional = lambda func: func
    firestore_v1_stub.FieldFilter = _StubFieldFilter

    fakes = {
        "database._client": client_stub,
        "database.legal_holds": legal_holds_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore_v1": firestore_v1_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.memory_ledger",
            os.path.join(str(_BACKEND), "database", "memory_ledger.py"),
        )
        globals()["memory_ledger"] = module
        yield module


def _fact(fact_id, content="Lives in NYC"):
    return {
        "id": fact_id,
        "content": content,
        "predicate": "resides_in",
        "arguments": {"location": content.removeprefix("Lives in ")},
        "subject_entity_id": "user",
        "qualifiers": {},
    }


def _assert_fences(memory_ledger, database, uid, mutations):
    return memory_ledger._assert_legacy_commit_privacy_fences(
        transaction=_ProbeTransaction(database),
        database=database,
        uid=uid,
        mutations=mutations,
    )


def test_clean_user_skips_phantom_per_memory_lookups(memory_ledger):
    """No overrides, no tombstoned items: zero per-id reads, fence passes."""
    uid = "u1"
    database = _ProbeDb(
        {
            f"users/{uid}/memory_items/m1": {"status": "active"},
            f"users/{uid}/memory_items/m2": {"status": "active"},
        }
    )

    _assert_fences(
        memory_ledger,
        database,
        uid,
        [memory_ledger.add_fact(_fact("m1")), memory_ledger.add_fact(_fact("m2", "Works in Lisbon"))],
    )

    # The deletion-marker read stays (it hits); no memory_* lookups happen.
    assert [p for p in database.gets if "memory_" in p] == []


def test_any_override_document_selects_exact_reads(memory_ledger):
    """A suppression history for ANY id re-enables the exact reads."""
    uid = "u2"
    database = _ProbeDb(
        {
            f"users/{uid}/memory_items/m1": {"status": "active"},
            # Override for an id unrelated to this commit's mutations.
            f"users/{uid}/memory_historical_overrides/mX": {"status": "tombstoned"},
        }
    )

    _assert_fences(
        memory_ledger,
        database,
        uid,
        [memory_ledger.add_fact(_fact("m1"))],
    )

    assert f"users/{uid}/memory_items/m1" in database.gets
    assert f"users/{uid}/memory_historical_overrides/m1" in database.gets


def test_tombstoned_item_probe_selects_exact_reads_and_fences(memory_ledger):
    uid = "u3"
    database = _ProbeDb(
        {
            f"users/{uid}/memory_items/m1": {"status": "tombstoned"},
        }
    )

    with pytest.raises(memory_ledger.LegacyCommitPrivacyFence):
        _assert_fences(
            memory_ledger,
            database,
            uid,
            [memory_ledger.add_fact(_fact("m1"))],
        )

    assert f"users/{uid}/memory_items/m1" in database.gets


def test_tombstoned_override_still_fences_through_exact_reads(memory_ledger):
    """The suppression triad: a tombstoned override for a mutation id fences."""
    uid = "u4"
    database = _ProbeDb(
        {
            f"users/{uid}/memory_items/m1": {"status": "active"},
            f"users/{uid}/memory_historical_overrides/m1": {"status": "tombstoned"},
        }
    )

    with pytest.raises(memory_ledger.LegacyCommitPrivacyFence):
        _assert_fences(
            memory_ledger,
            database,
            uid,
            [memory_ledger.add_fact(_fact("m1"))],
        )


def test_probe_without_query_support_falls_back_conservatively(memory_ledger):
    """A db fake without a query surface must not silently skip the fences."""

    class _LegacyDb:
        def __init__(self, docs):
            self.docs = dict(docs)
            self.gets = []

        def collection(self, name):
            class _Coll:
                """Emulate the pre-probe fakes: no limit/where support."""

                def __init__(self, db, path):
                    self._db = db
                    self._path = path

                def document(self, document_id):
                    return _ProbeDocument(self._db, f"{self._path}/{document_id}")

            return _Coll(self, name)

    uid = "u5"
    database = _LegacyDb(
        {
            f"users/{uid}/memory_historical_overrides/m1": {"status": "tombstoned"},
        }
    )

    with pytest.raises(memory_ledger.LegacyCommitPrivacyFence):
        _assert_fences(
            memory_ledger,
            database,
            uid,
            [memory_ledger.add_fact(_fact("m1"))],
        )

    assert f"users/{uid}/memory_historical_overrides/m1" in database.gets
