from types import SimpleNamespace

import pytest

from database.firestore_index_registry import (
    DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY,
    DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY,
    QUERY_SPECS,
    firebase_index_manifest,
)
from utils.memory import daily_memory_sweep_inventory as independent


class _Snapshot:
    def __init__(self, uid, payload=None):
        self.id = uid
        self._payload = payload or {}

    def to_dict(self):
        return self._payload


class _DocumentReference:
    def __init__(self, uid):
        self.id = uid


class _Ref:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def get(self):
        value = self.store.get(self.path)
        return SimpleNamespace(exists=value is not None, to_dict=lambda: value)

    def set(self, value, merge=False):
        current = dict(self.store.get(self.path, {})) if merge else {}
        current.update(value)
        self.store[self.path] = current

    def delete(self):
        self.store.pop(self.path, None)


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.field = None
        self.after = ""
        self.page_size = None

    def where(self, *args, **kwargs):
        field_filter = kwargs.get("filter")
        if field_filter is not None:
            self.field = (field_filter.field_path, field_filter.op_string, field_filter.value)
        elif len(args) >= 3:
            self.field = (args[0], args[1], args[2])
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self.page_size = count
        return self

    def stream(self):
        rows = list(self.rows)
        if self.field and self.field[0] in ("__name__", "uid") and self.field[1] == ">":
            boundary = getattr(self.field[2], "id", self.field[2])
            rows = [row for row in rows if row.id > boundary]
        rows.sort(key=lambda row: row.id)
        return rows[: self.page_size]


class _Users:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
        self.requested_documents = []

    def where(self, *args, **kwargs):
        query = _Query(self.rows).where(*args, **kwargs)
        self.queries.append(query)
        return query

    def document(self, uid):
        self.requested_documents.append(uid)
        return _DocumentReference(uid)


class _Db:
    def __init__(self):
        self.store = {}
        self.users = _Users([_Snapshot(uid, {"onboarding": {"completed": True}}) for uid in "abcd"])

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, path):
        if path == "users":
            return self.users
        if path == independent.DAILY_SWEEP_RETRY_COLLECTION:
            rows = [
                _Snapshot(
                    uid,
                    {
                        "uid": uid,
                        "schema_version": independent.DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION,
                    },
                )
                for key, value in self.store.items()
                if key.startswith(f"{path}/")
                for uid in [key.rsplit("/", 1)[-1]]
                if value.get("schema_version") == independent.DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION
            ]
            return _Query(rows)
        raise AssertionError(path)


def test_onboarding_queries_keep_server_cursor_without_redundant_composites():
    assert DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY in QUERY_SPECS
    assert DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY in QUERY_SPECS
    signatures = {
        (
            index["collectionGroup"],
            index["queryScope"],
            tuple((field["fieldPath"], field.get("order")) for field in index["fields"]),
        )
        for index in firebase_index_manifest()["indexes"]
    }
    assert (
        "users",
        "COLLECTION",
        (("onboarding.completed", "ASCENDING"), ("__name__", "ASCENDING")),
    ) not in signatures
    assert (
        "users",
        "COLLECTION",
        (("onboarding.device_onboarding_completed", "ASCENDING"), ("__name__", "ASCENDING")),
    ) not in signatures
    assert tuple((item.field_path, item.operator) for item in DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY.filters) == (
        ("onboarding.completed", "=="),
        ("__name__", ">"),
    )


def test_independent_inventory_executes_registered_onboarding_cursor_query(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        independent,
        "bounded_canonical_daily_sweep_uids",
        lambda *_args, **_kwargs: (),
    )
    page = independent.bounded_daily_memory_sweep_uid_inventory(db, limit=2, return_page=True)
    assert isinstance(page, independent.DailySweepUIDInventoryPage)
    assert page.onboarding_uids == ("a",)
    assert db.users.requested_documents == []
    assert all(query.field[0] != "__name__" for query in db.users.queries)


def test_independent_onboarding_cursor_is_server_side_before_page_limit(monkeypatch):
    db = _Db()
    # A provider-side limit over pre-cursor rows would starve z-user forever.
    db.users = _Users(
        [_Snapshot(f"a-{index:02d}") for index in range(12)]
        + [_Snapshot("z-user", {"onboarding": {"completed": True}})]
    )
    db.document(independent.DAILY_SWEEP_ONBOARDING_CURSOR_PATH).set(
        {
            "schema_version": independent.DAILY_SWEEP_ONBOARDING_CURSOR_SCHEMA_VERSION,
            "last_uid": "m-user",
            "generation": 0,
        }
    )
    monkeypatch.setattr(independent, "bounded_canonical_daily_sweep_uids", lambda *_args, **_kwargs: ())

    page = independent.bounded_daily_memory_sweep_uid_inventory(db, limit=2, return_page=True)

    assert page.onboarding_uids == ("z-user",)
    assert db.users.requested_documents == ["m-user", "m-user"]
    assert all(not isinstance(query.field[2], str) for query in db.users.queries)


def test_independent_inventory_commits_only_its_own_fair_cursor_namespace():
    db = _Db()
    page = independent.DailySweepUIDInventoryPage(
        uids=("uid-a",),
        canonical_uids=("uid-a",),
        onboarding_uids=("uid-a",),
    )
    independent.commit_daily_memory_sweep_uid_inventory(
        db,
        page,
        completed_uids=("uid-a",),
        failed_uids=(),
    )
    assert db.store[independent.DAILY_SWEEP_CANONICAL_CURSOR_PATH]["last_uid"] == "uid-a"
    assert db.store[independent.DAILY_SWEEP_ONBOARDING_CURSOR_PATH]["last_uid"] == "uid-a"


def test_independent_retry_slice_keeps_later_source_pages_eligible(monkeypatch):
    db = _Db()
    failed = tuple(f"retry-{index:02d}" for index in range(40))
    independent.commit_daily_memory_sweep_uid_inventory(
        db,
        independent.DailySweepUIDInventoryPage(uids=failed),
        completed_uids=(),
        failed_uids=failed,
        advance_page=False,
    )
    monkeypatch.setattr(
        independent,
        "bounded_canonical_daily_sweep_uids",
        lambda *_args, **_kwargs: ("canonical-later-a", "canonical-later-b"),
    )
    page = independent.bounded_daily_memory_sweep_uid_inventory(db, limit=4, return_page=True)
    assert page.retry_uids == ("retry-00",)
    assert "canonical-later-a" in page.uids


def test_independent_retry_cursor_rotates_past_more_than_32_failing_uids(monkeypatch):
    db = _Db()
    failed = tuple(f"retry-{index:02d}" for index in range(40))
    independent.commit_daily_memory_sweep_uid_inventory(
        db,
        independent.DailySweepUIDInventoryPage(uids=failed),
        completed_uids=(),
        failed_uids=failed,
        advance_page=False,
    )
    monkeypatch.setattr(independent, "bounded_canonical_daily_sweep_uids", lambda *_args, **_kwargs: ())
    first = independent.bounded_daily_memory_sweep_uid_inventory(db, limit=400, return_page=True)
    assert len(first.retry_uids) == 32
    independent.commit_daily_memory_sweep_uid_inventory(
        db,
        first,
        completed_uids=(),
        failed_uids=first.retry_uids,
        advance_page=False,
    )
    second = independent.bounded_daily_memory_sweep_uid_inventory(db, limit=400, return_page=True)
    assert second.retry_uids[0] == "retry-32"


@pytest.mark.parametrize(
    ("channel", "path"),
    [
        ("retry_uids", independent.DAILY_SWEEP_RETRY_CURSOR_PATH),
        ("canonical_uids", independent.DAILY_SWEEP_CANONICAL_CURSOR_PATH),
        ("onboarding_uids", independent.DAILY_SWEEP_ONBOARDING_CURSOR_PATH),
    ],
)
def test_independent_overlapping_page_commits_are_generation_fenced(channel, path):
    db = _Db()
    page = independent.DailySweepUIDInventoryPage(uids=("uid-a",), **{channel: ("uid-a",)})
    stale_page = independent.DailySweepUIDInventoryPage(uids=("uid-a",), **{channel: ("uid-a",)})

    independent.commit_daily_memory_sweep_uid_inventory(db, page, completed_uids=(), failed_uids=())
    with pytest.raises(independent.DailySweepInventoryUnavailable):
        independent.commit_daily_memory_sweep_uid_inventory(db, stale_page, completed_uids=(), failed_uids=())

    assert db.store[path]["last_uid"] == "uid-a"
    assert db.store[path]["generation"] == 1


def test_explicit_jit_qa_inventory_does_not_use_firestore_or_global_cursors():
    page = independent.explicit_jit_qa_daily_sweep_uid_inventory(("qa-user", "qa-user"))
    assert page.uids == ("qa-user",)
    assert page.canonical_uids == ()
    assert page.onboarding_uids == ()
    assert page.retry_uids == ()


@pytest.mark.parametrize("uids", [(), ("qa/user",), ("",), tuple(f"uid-{n}" for n in range(5))])
def test_explicit_jit_qa_inventory_rejects_unbounded_or_malformed_allowlist(uids):
    with pytest.raises(independent.DailySweepInventoryUnavailable):
        independent.explicit_jit_qa_daily_sweep_uid_inventory(uids)
