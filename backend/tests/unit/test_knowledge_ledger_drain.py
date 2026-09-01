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


def test_inventory_fails_closed_on_malformed_writer_mode():
    malformed = _Snapshot(
        "users/uid-a/memory_state/apply_control",
        {"uid": "uid-a", "writer_mode": "surprise"},
    )

    with pytest.raises(drain.LedgerDrainInventoryUnavailable, match="malformed"):
        drain.bounded_ledger_drain_inventory(_Db([malformed]))
