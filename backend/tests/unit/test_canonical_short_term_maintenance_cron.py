import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils.memory import canonical_short_term_maintenance_cron as cron
from utils.memory.short_term_promotion import CanonicalShortTermLifecycleReport
from utils.memory.short_term_promotion import CanonicalShortTermMaintenanceReport
from utils.memory.canonical_consolidation import RequiredIntakeCompletion
from utils.memory.promotion_flex import PromotionFlexDeferred

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_flex_router(monkeypatch):
    router = SimpleNamespace(
        control=SimpleNamespace(enabled=True),
        job_budget_fits=lambda: True,
        llm_for_uid=lambda *_, **__: object(),
        assert_result_current=lambda: None,
        require_job_budget=lambda: None,
    )
    monkeypatch.setattr(cron, 'PromotionFlexRunRouter', lambda **_: router)
    return router


def test_legacy_cron_has_no_daily_sweep_inventory_owner():
    """Daily sweep inventory has one owner in the independent job module."""

    assert not hasattr(cron, "DailySweepUIDInventoryPage")
    assert not hasattr(cron, "bounded_daily_memory_sweep_uid_inventory")
    assert not hasattr(cron, "commit_daily_memory_sweep_uid_inventory")
    assert not any(name.startswith("DAILY_MEMORY_SWEEP_") for name in vars(cron))


class _Reference:
    def __init__(self, path):
        self.path = path


class _Snapshot:
    def __init__(self, path):
        self.reference = _Reference(path)

    def to_dict(self):
        uid = self.reference.path.split("/")[-1]
        return {"uid": uid, "schema_version": 1}


class _Query:
    def __init__(self, snapshots, *, page_limit=None):
        self.snapshots = sorted(snapshots, key=lambda snapshot: snapshot.to_dict()["uid"])
        self.page_limit = page_limit

    def where(self, _field, _op, value):
        return _Query([snapshot for snapshot in self.snapshots if snapshot.to_dict()["uid"] > value])

    def order_by(self, _field):
        return self

    def limit(self, _limit):
        return _Query(self.snapshots, page_limit=_limit)

    def stream(self):
        return iter(self.snapshots[: self.page_limit] if self.page_limit is not None else self.snapshots)


class _Db:
    def __init__(self, snapshots=None):
        self.snapshots = snapshots or []
        self.docs = {}

    @property
    def cursor(self):
        return self.docs.get(cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH)

    @cursor.setter
    def cursor(self, payload):
        if payload is None:
            self.docs.pop(cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH, None)
        else:
            self.docs[cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH] = payload

    def collection(self, _collection_id):
        return _Query(self.snapshots)

    def document(self, path):
        outer = self

        class _CursorRef:
            def get(self):
                payload = outer.docs.get(path)
                return type(
                    "Snapshot",
                    (),
                    {"exists": payload is not None, "to_dict": lambda _self: payload},
                )()

            def set(self, payload, **_kwargs):
                outer.docs[path] = dict(payload)

            def create(self, payload):
                if path in outer.docs:
                    raise RuntimeError("exists")
                outer.docs[path] = dict(payload)

        return _CursorRef()


def _enable(monkeypatch):
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "true")


def test_disabled_global_switch_does_not_resolve_inventory(monkeypatch):
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    inventory = MagicMock()
    summary = asyncio.run(cron.run_canonical_short_term_maintenance_cron(uid_inventory=inventory, now=NOW))
    assert summary.user_count == 0
    inventory.assert_not_called()


def test_missing_inventory_fails_closed_with_operational_dependency(monkeypatch):
    _enable(monkeypatch)
    summary = asyncio.run(cron.run_canonical_short_term_maintenance_cron(db_client=object(), now=NOW))
    assert summary.inventory_source == "unavailable"
    assert summary.inventory_complete is False
    assert summary.errors == ["canonical_uid_inventory_unavailable"]


def test_bounded_registry_inventory_is_deterministic_and_capped():
    snapshots = [
        _Snapshot("canonical_memory_maintenance_registry/uid-b"),
        _Snapshot("canonical_memory_maintenance_registry/uid-a"),
    ]
    assert cron.bounded_canonical_memory_uid_inventory(_Db(snapshots), limit=1) == ("uid-a",)


def test_registry_cursor_progresses_and_wraps_without_starvation():
    snapshots = [
        _Snapshot("canonical_memory_maintenance_registry/uid-a"),
        _Snapshot("canonical_memory_maintenance_registry/uid-b"),
    ]
    db = _Db(snapshots)
    assert cron.bounded_canonical_memory_uid_inventory(db, limit=1) == ("uid-a",)


def test_registry_cursor_read_failure_fails_closed():
    class BrokenDb:
        def document(self, _path):
            class BrokenRef:
                def get(self):
                    raise RuntimeError("transport unavailable")

            return BrokenRef()

        def collection(self, _name):
            raise AssertionError("cursor failure should stop before registry query")

    with pytest.raises(cron.CanonicalMaintenanceInventoryUnavailable, match="cursor unavailable"):
        cron.bounded_canonical_memory_uid_inventory(BrokenDb(), limit=1)


def test_seed_existing_apply_control_accounts_is_bounded_and_resumable():
    class ApplySnapshot:
        def __init__(self, uid):
            self.reference = _Reference(f"users/{uid}/memory_state/apply_control")

        def to_dict(self):
            return {"uid": self.reference.path.split("/")[1]}

    class SeedQuery:
        def __init__(self, snapshots):
            self.snapshots = snapshots
            self.page_limit = None

        def order_by(self, _field):
            return self

        def where(self, _field, _operator, value):
            self.snapshots = [item for item in self.snapshots if item.to_dict().get("uid", "") > value]
            return self

        def start_after(self, snapshot):
            path = getattr(getattr(snapshot, "reference", None), "path", "")
            self.snapshots = [item for item in self.snapshots if item.reference.path > path]
            return self

        def limit(self, limit):
            self.page_limit = limit
            return self

        def stream(self):
            return iter(self.snapshots[: self.page_limit])

    class SeedRef:
        def __init__(self, path, state):
            self.path = path
            self.state = state

        def get(self):
            payload = self.state.get(self.path)
            return type(
                "Snapshot",
                (),
                {
                    "exists": payload is not None,
                    "reference": _Reference(self.path),
                    "to_dict": lambda _self: payload,
                },
            )()

        def set(self, payload, **_kwargs):
            self.state[self.path] = payload

    class SeedDb:
        def __init__(self):
            self.state = {
                "users/uid-a/memory_state/apply_control": {"uid": "uid-a"},
                "users/uid-b/memory_state/apply_control": {"uid": "uid-b"},
            }
            self.snapshots = [ApplySnapshot("uid-a"), ApplySnapshot("uid-b")]

        def collection_group(self, _name):
            return SeedQuery(self.snapshots)

        def collection(self, name):
            snapshots = [
                type(
                    "RegistrySnapshot",
                    (),
                    {
                        "to_dict": lambda _self, payload=payload: payload,
                    },
                )()
                for path, payload in self.state.items()
                if path.startswith(f"{name}/")
            ]
            return SeedQuery(snapshots)

        def document(self, path):
            return SeedRef(path, self.state)

    db = SeedDb()
    cron._seed_registry_from_existing_memory_states(db, limit=1)

    assert db.state["canonical_memory_maintenance_registry/uid-a"] == {
        "uid": "uid-a",
        "schema_version": 1,
    }
    assert db.state[cron.CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH] == {
        "schema_version": 1,
        "last_path": "users/uid-a/memory_state/apply_control",
    }
    assert cron.bounded_canonical_memory_uid_inventory(db, limit=1) == ("uid-a",)
    assert cron.bounded_canonical_memory_uid_inventory(db, limit=1) == ("uid-b",)


def test_every_selected_account_runs_outbox_even_without_stm_or_in_ledger_mode(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def maintain(uid, **kwargs):
        called.append((uid, kwargs))
        return CanonicalShortTermMaintenanceReport(
            uid=uid, required_intake=RequiredIntakeCompletion(uid=uid), outbox={'delivered_count': 2}
        )

    monkeypatch.setattr(cron, 'run_canonical_short_term_maintenance_async', maintain)
    summary = asyncio.run(
        cron.run_canonical_short_term_maintenance_cron(
            db_client=object(), now=NOW, uid_inventory=lambda *_: ['empty-account', 'ledger-account']
        )
    )
    assert [uid for uid, _ in called] == ['empty-account', 'ledger-account']
    assert summary.maintained_users == 2 and summary.outbox_delivered_total == 4
    assert called[0][1]['required_processing_limit'] == 25
    assert callable(called[0][1]['required_processor'])
    assert 'llm_invoke' not in called[0][1]
    assert not any('dreamed' in name for name in vars(cron))


def test_flex_stop_does_not_mark_the_current_or_later_account_completed(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def maintain(uid, **kwargs):
        called.append(uid)
        if uid == 'b':
            raise PromotionFlexDeferred('provider deferred')
        return CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, 'run_canonical_short_term_maintenance_async', maintain)
    summary = asyncio.run(
        cron.run_canonical_short_term_maintenance_cron(
            db_client=object(), now=NOW, uid_inventory=lambda *_: ['a', 'b', 'c']
        )
    )
    assert called == ['a', 'b']
    assert summary.flex_deferred and summary.completed_uids == ('a',)


def test_outbox_error_is_reported_even_without_intake(monkeypatch):
    _enable(monkeypatch)

    async def maintain(uid, **kwargs):
        return CanonicalShortTermMaintenanceReport(uid=uid, outbox={'dead_letter_count': 1})

    monkeypatch.setattr(cron, 'run_canonical_short_term_maintenance_async', maintain)
    summary = asyncio.run(
        cron.run_canonical_short_term_maintenance_cron(db_client=object(), now=NOW, uid_inventory=lambda *_: ['a'])
    )
    assert summary.outbox_dead_letters_total == 1
    assert any('outbox_delivery_failed' in error for error in summary.errors)
