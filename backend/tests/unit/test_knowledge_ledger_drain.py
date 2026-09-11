from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from models.memory_apply import WriterMode
from utils.memory import knowledge_ledger_drain as drain


class _Snapshot:
    def __init__(self, path: str, payload: dict, *, exists: bool = True):
        self.reference = SimpleNamespace(path=path)
        self._payload = payload
        self.exists = exists

    def to_dict(self):
        return self._payload


class _Query:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def order_by(self, _field):
        return self

    def start_after(self, snapshot):
        index = next(i for i, item in enumerate(self.snapshots) if item.reference.path == snapshot.reference.path)
        return _Query(self.snapshots[index + 1 :])

    def limit(self, limit):
        return _Query(self.snapshots[:limit])

    def stream(self):
        return iter(self.snapshots)


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, transaction=None):
        del transaction
        return self.db.documents.get(self.path, _Snapshot(self.path, {}, exists=False))

    def set(self, payload, merge=False):
        del merge
        self.db.documents[self.path] = _Snapshot(self.path, payload)


class _Db:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.documents = {snapshot.reference.path: snapshot for snapshot in snapshots}

    def document(self, path):
        return _Document(self, path)

    def collection_group(self, name):
        assert name == "memory_state"
        return _Query(self.snapshots)


def _control(uid: str, mode: WriterMode = WriterMode.compatibility):
    return _Snapshot(
        f"users/{uid}/memory_state/apply_control",
        {"uid": uid, "writer_mode": mode.value},
    )


def _legacy_control(uid: str):
    return _Snapshot(
        f"users/{uid}/memory_state/apply_control",
        {"uid": uid},
    )


def test_inventory_uses_an_independent_cursor_and_skips_cutover_accounts():
    db = _Db([_control("uid-a"), _control("uid-b", WriterMode.ledger)])

    page = drain.bounded_ledger_drain_inventory(db, limit=2)

    assert page.uids == ("uid-a",)
    assert page.last_path == "users/uid-b/memory_state/apply_control"
    assert drain.LEDGER_DRAIN_CURSOR_PATH != "canonical_memory_maintenance_control/uid_cursor"
    drain.commit_ledger_drain_inventory(db, page)
    cursor = db.document(drain.LEDGER_DRAIN_CURSOR_PATH).get().to_dict()
    assert cursor == {
        "schema_version": 1,
        "last_path": "users/uid-b/memory_state/apply_control",
        "generation": 1,
    }


def test_inventory_does_not_advance_before_explicit_commit():
    db = _Db([_control("uid-a")])

    page = drain.bounded_ledger_drain_inventory(db)

    assert not db.document(drain.LEDGER_DRAIN_CURSOR_PATH).get().exists
    drain.commit_ledger_drain_inventory(db, page)
    assert db.document(drain.LEDGER_DRAIN_CURSOR_PATH).get().exists


def test_inventory_resumes_after_committed_page_and_wraps_at_end():
    db = _Db([_control("uid-a"), _control("uid-b"), _control("uid-c")])

    first_page = drain.bounded_ledger_drain_inventory(db, limit=2)
    drain.commit_ledger_drain_inventory(db, first_page)
    second_page = drain.bounded_ledger_drain_inventory(db, limit=2)
    drain.commit_ledger_drain_inventory(db, second_page)
    wrapped_page = drain.bounded_ledger_drain_inventory(db, limit=2)

    assert first_page.uids == ("uid-a", "uid-b")
    assert second_page.uids == ("uid-c",)
    assert second_page.cursor_generation == 1
    assert wrapped_page.uids == ("uid-a", "uid-b")
    assert wrapped_page.cursor_generation == 2


def test_inventory_cursor_rejects_a_stale_generation():
    db = _Db([_control("uid-a")])
    page = drain.bounded_ledger_drain_inventory(db)
    db.document(drain.LEDGER_DRAIN_CURSOR_PATH).set(
        {
            "schema_version": 1,
            "last_path": "users/other/memory_state/apply_control",
            "generation": 1,
        }
    )

    with pytest.raises(drain.LedgerDrainInventoryUnavailable, match="generation conflict"):
        drain.commit_ledger_drain_inventory(db, page)


def test_inventory_treats_legacy_missing_writer_mode_as_compatibility():
    page = drain.bounded_ledger_drain_inventory(_Db([_legacy_control("uid-legacy")]))

    assert page.uids == ("uid-legacy",)


def test_scoped_inventory_reads_only_allowlisted_controls_without_global_cursor():
    db = _Db([_control("uid-a"), _control("uid-b")])

    page = drain.bounded_ledger_drain_inventory(db, uid_allowlist={"uid-a"})

    assert page.uids == ("uid-a",)
    assert page.last_path == ""
    drain.commit_ledger_drain_inventory(db, page)
    assert not db.document(drain.LEDGER_DRAIN_CURSOR_PATH).get().exists


def test_drain_runs_without_waiting_for_short_term_maintenance(monkeypatch):
    page = drain.LedgerDrainInventoryPage(
        uids=("uid-enabled", "uid-disabled"),
        last_path="users/uid-disabled/memory_state/apply_control",
        cursor_generation=0,
        scanned_documents=2,
    )
    calls = []

    async def resolve(uid, *, stage, force_refresh):
        assert stage is drain.JITDecisionStage.INGRESS
        assert force_refresh is True
        return SimpleNamespace(permits_work=uid == "uid-enabled")

    async def run_blocking(_executor, function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is inventory:
            return page
        if function is drain.run_ledger_migration_sweep:
            return SimpleNamespace(
                migrated_long_term_count=3,
                adjudicated_short_term_count=1,
                remaining_live_legacy_count=0,
                authorization_revoked=False,
            )
        return None

    def inventory(_db, *, limit):
        raise AssertionError("run_blocking owns this seam")

    monkeypatch.setattr(drain, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(drain, "run_blocking", run_blocking)

    summary = asyncio.run(drain.run_knowledge_ledger_drain(db_client=object(), inventory_provider=inventory))

    functions = [call[0] for call in calls]
    assert drain.run_ledger_migration_sweep in functions
    assert drain.publish_ledger_migration_cutover in functions
    assert drain.commit_ledger_drain_inventory in functions
    assert summary.cutover_users == 1
    assert summary.migrated_rows == 3
    assert summary.rollout_blocked_users == 1


def test_revoked_row_authority_never_publishes(monkeypatch):
    page = drain.LedgerDrainInventoryPage(
        uids=("uid-a",),
        last_path="users/uid-a/memory_state/apply_control",
        cursor_generation=0,
        scanned_documents=1,
    )
    published = []

    async def resolve(_uid, *, stage, force_refresh):
        return SimpleNamespace(permits_work=True)

    async def run_blocking(_executor, function, *args, **kwargs):
        if function is inventory:
            return page
        if function is drain.run_ledger_migration_sweep:
            return SimpleNamespace(
                migrated_long_term_count=1,
                adjudicated_short_term_count=0,
                remaining_live_legacy_count=1,
                authorization_revoked=True,
            )
        if function is drain.publish_ledger_migration_cutover:
            published.append(args[0])
        return None

    def inventory(_db, *, limit):
        raise AssertionError("run_blocking owns this seam")

    monkeypatch.setattr(drain, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(drain, "run_blocking", run_blocking)

    summary = asyncio.run(drain.run_knowledge_ledger_drain(db_client=object(), inventory_provider=inventory))

    assert published == []
    assert summary.authorization_revoked_users == 1


def test_drain_allowlist_blocks_unlisted_accounts_before_rollout_or_mutation(monkeypatch):
    page = drain.LedgerDrainInventoryPage(
        uids=("uid-unlisted",),
        last_path="users/uid-unlisted/memory_state/apply_control",
        cursor_generation=0,
        scanned_documents=1,
    )
    resolved = []

    async def resolve(*args, **kwargs):
        resolved.append((args, kwargs))
        return SimpleNamespace(permits_work=True)

    async def run_blocking(_executor, function, *args, **kwargs):
        if function is inventory:
            return page
        if function is drain.commit_ledger_drain_inventory:
            return None
        raise AssertionError(f"unlisted account reached {function}")

    def inventory(_db, *, limit):
        raise AssertionError("run_blocking owns this seam")

    monkeypatch.setattr(drain, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(drain, "run_blocking", run_blocking)

    summary = asyncio.run(
        drain.run_knowledge_ledger_drain(db_client=object(), inventory_provider=inventory, uid_allowlist={"uid-owner"})
    )

    assert resolved == []
    assert summary.allowlist_blocked_users == 1
    assert summary.attempted_users == 0


def test_drain_retries_the_same_page_when_an_account_fails(monkeypatch):
    page = drain.LedgerDrainInventoryPage(
        uids=("uid-a",),
        last_path="users/uid-a/memory_state/apply_control",
        cursor_generation=0,
        scanned_documents=1,
    )
    committed = []

    async def resolve(_uid, *, stage, force_refresh):
        return SimpleNamespace(permits_work=True)

    async def run_blocking(_executor, function, *args, **kwargs):
        if function is inventory:
            return page
        if function is drain.run_ledger_migration_sweep:
            raise RuntimeError("migration failed")
        if function is drain.commit_ledger_drain_inventory:
            committed.append(page)
        return None

    def inventory(_db, *, limit):
        raise AssertionError("run_blocking owns this seam")

    monkeypatch.setattr(drain, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(drain, "run_blocking", run_blocking)

    summary = asyncio.run(drain.run_knowledge_ledger_drain(db_client=object(), inventory_provider=inventory))

    assert summary.errors == ["uid=uid-a:migration:RuntimeError"]
    assert committed == []


def test_drain_resolves_the_firestore_client_at_call_time(monkeypatch):
    client = object()
    seen_clients = []
    page = drain.LedgerDrainInventoryPage(uids=(), last_path="", cursor_generation=0, scanned_documents=0)

    def inventory(_db, *, limit):
        raise AssertionError("run_blocking owns this seam")

    async def run_blocking(_executor, function, *args, **kwargs):
        if function is inventory:
            seen_clients.append(args[0])
            return page
        # Everything else the drain offloads — including client construction — really runs.
        return function(*args, **kwargs)

    monkeypatch.setattr(drain, "get_firestore_client", lambda: client)
    monkeypatch.setattr(drain, "run_blocking", run_blocking)

    asyncio.run(drain.run_knowledge_ledger_drain(inventory_provider=inventory))

    assert seen_clients == [client]


def test_inventory_fails_closed_on_malformed_writer_mode():
    malformed = _Snapshot(
        "users/uid-a/memory_state/apply_control",
        {"uid": "uid-a", "writer_mode": "surprise"},
    )

    with pytest.raises(drain.LedgerDrainInventoryUnavailable, match="malformed"):
        drain.bounded_ledger_drain_inventory(_Db([malformed]))
