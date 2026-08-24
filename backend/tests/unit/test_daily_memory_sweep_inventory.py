from types import SimpleNamespace

import pytest

from database.firestore_index_registry import (
    DAILY_SWEEP_ONBOARDING_COMPLETED_USERS_QUERY,
    DAILY_SWEEP_ONBOARDING_DEVICE_COMPLETED_USERS_QUERY,
    QUERY_SPECS,
    firebase_index_manifest,
)
from utils.memory import canonical_short_term_maintenance_cron as cron
from utils.memory import daily_memory_sweep_inventory as independent


class _Snapshot:
    def __init__(self, uid, payload=None):
        self.id = uid
        self._payload = payload or {}

    def to_dict(self):
        return self._payload


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
            rows = [row for row in rows if row.id > self.field[2]]
        rows.sort(key=lambda row: row.id)
        return rows[: self.page_size]


class _Users:
    def __init__(self, rows):
        self.rows = rows

    def where(self, *args, **kwargs):
        return _Query(self.rows).where(*args, **kwargs)


class _Db:
    def __init__(self):
        self.store = {}
        self.users = _Users([_Snapshot(uid, {"onboarding": {"completed": True}}) for uid in "abcd"])

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, path):
        if path == "users":
            return self.users
        if path in (cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION, independent.DAILY_SWEEP_RETRY_COLLECTION):
            rows = [
                _Snapshot(
                    uid,
                    {
                        "uid": uid,
                        "schema_version": (
                            cron.DAILY_MEMORY_SWEEP_RETRY_STATE_SCHEMA_VERSION
                            if path == cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION
                            else independent.DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION
                        ),
                    },
                )
                for key, value in self.store.items()
                if key.startswith(f"{path}/")
                for uid in [key.rsplit("/", 1)[-1]]
                if value.get(
                    "schema_version",
                )
                == (
                    cron.DAILY_MEMORY_SWEEP_RETRY_STATE_SCHEMA_VERSION
                    if path == cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION
                    else independent.DAILY_SWEEP_RETRY_STATE_SCHEMA_VERSION
                )
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


def test_legacy_onboarding_cursor_is_server_side_before_page_limit(monkeypatch):
    db = _Db()
    db.users = _Users(
        [_Snapshot(f"a-{index:02d}") for index in range(12)]
        + [_Snapshot("z-user", {"onboarding": {"completed": True}})]
    )
    db.document(cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_CURSOR_PATH).set(
        {
            "schema_version": cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_SCHEMA_VERSION,
            "last_uid": "m-user",
            "generation": 0,
        }
    )
    monkeypatch.setattr(cron, "bounded_canonical_memory_uid_inventory", lambda *_args, **_kwargs: ())

    page = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=2, persist_cursor=False, return_page=True)

    assert page.onboarding_uids == ("z-user",)


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
    assert cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH not in db.store


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


def test_daily_sweep_inventory_reserves_onboarding_and_advances_separate_cursor(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-a", "canonical-b"),
    )
    first = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4)
    second = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4)

    assert first == ("canonical-a", "canonical-b", "a", "b")
    assert second == ("canonical-a", "canonical-b", "c", "d")
    assert db.store[cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_CURSOR_PATH]["last_uid"] == "d"


def test_daily_sweep_inventory_advances_page_and_requeues_failed_uids(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-a", "canonical-b"),
    )
    page = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4, persist_cursor=False, return_page=True)

    assert isinstance(page, cron.DailySweepUIDInventoryPage)
    assert db.store == {}
    cron.commit_daily_memory_sweep_uid_inventory(
        db,
        page,
        completed_uids=("canonical-b", "a"),
        failed_uids=("canonical-a",),
    )

    assert db.store[cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH]["last_uid"] == "canonical-b"
    assert db.store[cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_CURSOR_PATH]["last_uid"] == "b"
    assert db.store[f"{cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION}/canonical-a"] == {
        "schema_version": cron.DAILY_MEMORY_SWEEP_RETRY_STATE_SCHEMA_VERSION,
        "uid": "canonical-a",
    }


def test_daily_sweep_retry_queue_does_not_starve_later_pages(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-a", "canonical-b"),
    )
    first = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4, persist_cursor=False, return_page=True)
    cron.commit_daily_memory_sweep_uid_inventory(
        db,
        first,
        completed_uids=("canonical-b",),
        failed_uids=("canonical-a",),
    )

    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-c", "canonical-d"),
    )
    second = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4, persist_cursor=False, return_page=True)
    assert second.uids[0] == "canonical-a"
    assert "canonical-c" in second.uids


def test_retry_page_slice_does_not_starve_sources_when_many_retries_are_failing(monkeypatch):
    db = _Db()
    failed = tuple(f"retry-{index:02d}" for index in range(40))
    cron.commit_daily_memory_sweep_uid_inventory(
        db,
        cron.DailySweepUIDInventoryPage(uids=failed),
        completed_uids=(),
        failed_uids=failed,
        advance_page=False,
    )
    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-later-a", "canonical-later-b"),
    )
    page = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4, persist_cursor=False, return_page=True)
    assert page.retry_uids == ("retry-00",)
    assert "canonical-later-a" in page.uids


@pytest.mark.parametrize(
    ("channel", "path"),
    [
        ("retry_uids", cron.DAILY_MEMORY_SWEEP_RETRY_CURSOR_PATH),
        ("canonical_uids", cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH),
        ("onboarding_uids", cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_CURSOR_PATH),
    ],
)
def test_legacy_overlapping_page_commits_are_generation_fenced(channel, path):
    db = _Db()
    page = cron.DailySweepUIDInventoryPage(uids=("uid-a",), **{channel: ("uid-a",)})
    stale_page = cron.DailySweepUIDInventoryPage(uids=("uid-a",), **{channel: ("uid-a",)})

    cron.commit_daily_memory_sweep_uid_inventory(db, page, completed_uids=(), failed_uids=())
    with pytest.raises(cron.CanonicalMaintenanceInventoryUnavailable):
        cron.commit_daily_memory_sweep_uid_inventory(db, stale_page, completed_uids=(), failed_uids=())

    assert db.store[path]["last_uid"] == "uid-a"
    assert db.store[path]["generation"] == 1


def test_retry_write_failure_precedes_cursor_advance(monkeypatch):
    class BrokenRetryDb(_Db):
        def document(self, path):
            ref = super().document(path)
            if path.startswith(cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION):
                ref.set = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("retry write down"))
            return ref

    db = BrokenRetryDb()
    page = cron.DailySweepUIDInventoryPage(uids=("uid-a",), canonical_uids=("uid-a",))
    with pytest.raises(cron.CanonicalMaintenanceInventoryUnavailable, match="retry state unavailable"):
        cron.commit_daily_memory_sweep_uid_inventory(db, page, completed_uids=(), failed_uids=("uid-a",))
    assert cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH not in db.store


def test_retry_documents_do_not_truncate_large_outage_set():
    db = _Db()
    failed = tuple(f"uid-{index}" for index in range(2_000))
    cron.commit_daily_memory_sweep_uid_inventory(
        db,
        cron.DailySweepUIDInventoryPage(uids=failed),
        completed_uids=(),
        failed_uids=failed,
        advance_page=False,
    )
    retry_docs = [path for path in db.store if path.startswith(f"{cron.DAILY_MEMORY_SWEEP_RETRY_COLLECTION}/")]
    assert len(retry_docs) == len(failed)
