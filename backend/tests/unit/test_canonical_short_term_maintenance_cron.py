import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from utils.memory import canonical_short_term_maintenance_cron as cron

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


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
        self.cursor = None

    def collection(self, _collection_id):
        return _Query(self.snapshots)

    def document(self, _path):
        outer = self

        class _CursorRef:
            def get(self):
                payload = outer.cursor
                return type("Snapshot", (), {"exists": payload is not None, "to_dict": lambda _self: payload})()

            def set(self, payload, **_kwargs):
                outer.cursor = dict(payload)

            def create(self, payload):
                if outer.cursor is not None:
                    raise RuntimeError("exists")
                outer.cursor = dict(payload)

        return _CursorRef()


def _enable(monkeypatch):
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "true")


def test_disabled_global_switch_does_not_resolve_inventory(monkeypatch):
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    inventory = MagicMock()
    summary = cron.run_universal_short_term_maintenance(uid_inventory=inventory, now=NOW)
    assert summary.user_count == 0
    inventory.assert_not_called()


def test_missing_inventory_fails_closed_with_operational_dependency(monkeypatch):
    _enable(monkeypatch)
    summary = cron.run_universal_short_term_maintenance(db_client=object(), now=NOW)
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
                    raise RuntimeError('transport unavailable')

            return BrokenRef()

        def collection(self, _name):
            raise AssertionError('cursor failure should stop before registry query')

    with pytest.raises(cron.CanonicalMaintenanceInventoryUnavailable, match='cursor unavailable'):
        cron.bounded_canonical_memory_uid_inventory(BrokenDb(), limit=1)


def test_seed_existing_apply_control_accounts_is_bounded_and_resumable():
    class ApplySnapshot:
        def __init__(self, uid):
            self.reference = _Reference(f'users/{uid}/memory_state/apply_control')

        def to_dict(self):
            return {'uid': self.reference.path.split('/')[1]}

    class SeedQuery:
        def __init__(self, snapshots):
            self.snapshots = snapshots
            self.page_limit = None

        def order_by(self, _field):
            return self

        def where(self, _field, _operator, value):
            self.snapshots = [item for item in self.snapshots if item.to_dict().get('uid', '') > value]
            return self

        def start_after(self, snapshot):
            path = getattr(getattr(snapshot, 'reference', None), 'path', '')
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
                'Snapshot',
                (),
                {
                    'exists': payload is not None,
                    'reference': _Reference(self.path),
                    'to_dict': lambda _self: payload,
                },
            )()

        def set(self, payload, **_kwargs):
            self.state[self.path] = payload

    class SeedDb:
        def __init__(self):
            self.state = {
                'users/uid-a/memory_state/apply_control': {'uid': 'uid-a'},
                'users/uid-b/memory_state/apply_control': {'uid': 'uid-b'},
            }
            self.snapshots = [ApplySnapshot('uid-a'), ApplySnapshot('uid-b')]

        def collection_group(self, _name):
            return SeedQuery(self.snapshots)

        def collection(self, name):
            snapshots = [
                type(
                    'RegistrySnapshot',
                    (),
                    {
                        'to_dict': lambda _self, payload=payload: payload,
                    },
                )()
                for path, payload in self.state.items()
                if path.startswith(f'{name}/')
            ]
            return SeedQuery(snapshots)

        def document(self, path):
            return SeedRef(path, self.state)

    db = SeedDb()
    cron._seed_registry_from_existing_memory_states(db, limit=1)

    assert db.state['canonical_memory_maintenance_registry/uid-a'] == {'uid': 'uid-a', 'schema_version': 1}
    assert db.state[cron.CANONICAL_MEMORY_MAINTENANCE_SEED_CURSOR_PATH] == {
        'schema_version': 1,
        'last_path': 'users/uid-a/memory_state/apply_control',
    }
    assert cron.bounded_canonical_memory_uid_inventory(db, limit=1) == ("uid-a",)
    assert cron.bounded_canonical_memory_uid_inventory(db, limit=1) == ("uid-b",)


def test_injected_inventory_runs_arbitrary_uids(monkeypatch):
    _enable(monkeypatch)
    calls = []

    def maintenance(uid, **_kwargs):
        calls.append(uid)
        return cron.CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    summary = cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-z", "uid-a", "uid-z"],
    )
    assert calls == ["uid-a", "uid-z"]
    assert summary.user_count == 2
    assert summary.inventory_source == "injected"
    assert summary.inventory_complete is True


def test_inventory_candidates_come_from_the_injected_universal_inventory(monkeypatch):
    _enable(monkeypatch)
    summary = cron.run_universal_short_term_maintenance(
        db_client=_Db([_Snapshot("users/uid-any/memory_items/m1")]),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-any"],
    )
    assert summary.user_count == 1


def test_async_entrypoint_forwards_inventory_seam(monkeypatch):
    expected = cron.CanonicalShortTermMaintenanceCronSummary(run_id="cron", user_count=1)
    calls = []

    async def run_blocking(_executor, _function, *args, **kwargs):
        calls.append((args, kwargs))
        return expected

    monkeypatch.setattr(cron, "run_blocking", run_blocking)
    inventory = lambda _db, _limit: ["uid-a"]
    result = asyncio.run(
        cron.run_canonical_short_term_maintenance_cron(
            db_client=object(), now=NOW, run_id="cron", uid_inventory=inventory, inventory_limit=3
        )
    )
    assert result is expected
    assert calls[0][1]["uid_inventory"] is inventory
    assert calls[0][1]["inventory_limit"] == 3
