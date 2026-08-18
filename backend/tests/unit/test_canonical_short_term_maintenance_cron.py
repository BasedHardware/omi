import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from utils.memory import canonical_short_term_maintenance_cron as cron
from utils.memory.canonical_consolidation import ConsolidationReport

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


def test_enabled_flex_uid_routes_promotion_and_l2_with_long_leases_and_guards(monkeypatch):
    _enable(monkeypatch)
    calls = []

    def flex_invoke(_prompt):
        return "flex"

    def result_guard():
        return None

    class _FlexRouter:
        def __init__(self, *, db_client, force_enabled=False):
            assert db_client is not None
            self.force_enabled = force_enabled
            self.control = type("Control", (), {"enabled": True})()

        def llm_invoke_for_uid(self, uid):
            return flex_invoke if uid == "uid-flex" else None

        def llm_for_uid(self, uid, **_kwargs):
            return object() if uid == "uid-flex" else None

        assert_result_current = staticmethod(result_guard)

    def maintenance(uid, **kwargs):
        calls.append((uid, kwargs))
        return cron.CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, "PromotionFlexRunRouter", _FlexRouter)
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)

    cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-flex", "uid-standard"],
    )

    flex_kwargs = calls[0][1]
    assert [uid for uid, _kwargs in calls] == ["uid-flex", "uid-standard"]
    assert flex_kwargs["llm_invoke"] is flex_invoke
    assert flex_kwargs["consolidation_attempt_lease_seconds"] == cron.MEMORY_PROMOTION_FLEX_LEASE_SECONDS
    assert flex_kwargs["consolidation_result_guard"] is result_guard
    assert flex_kwargs["required_processing_limit"] == 0
    assert "required_processor" not in flex_kwargs
    standard_kwargs = calls[1][1]
    assert standard_kwargs["llm_invoke"] is None
    assert standard_kwargs["required_processing_limit"] == 0


def test_empty_and_recently_dreamed_users_are_skipped(monkeypatch):
    _enable(monkeypatch)
    calls = []

    def maintenance(uid, **_kwargs):
        calls.append(uid)
        return cron.CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    monkeypatch.setattr(
        cron,
        "count_active_short_term",
        lambda uid, db_client, cap=11: 0 if uid == "uid-empty" else 3,
    )
    monkeypatch.setattr(
        cron,
        "recently_dreamed",
        lambda uid, db_client, now: uid == "uid-recent",
    )

    summary = cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-empty", "uid-recent", "uid-ready"],
    )

    assert calls == ["uid-ready"]
    assert summary.skipped_no_short_term == 1
    assert summary.skipped_recently_dreamed == 1
    assert summary.dreamed_users == 1


def test_flex_deferral_stops_the_page_without_advancing_past_the_uid(monkeypatch):
    _enable(monkeypatch)
    calls = []

    def maintenance(uid, **_kwargs):
        calls.append(uid)
        if uid == "uid-b":
            raise cron.PromotionFlexDeferred("job_budget")
        return cron.CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    monkeypatch.setattr(cron, "count_active_short_term", lambda uid, db_client, cap=11: 3)
    monkeypatch.setattr(cron, "recently_dreamed", lambda uid, db_client, now: False)

    db = _Db(
        [
            _Snapshot("canonical_memory_maintenance_registry/uid-a"),
            _Snapshot("canonical_memory_maintenance_registry/uid-b"),
            _Snapshot("canonical_memory_maintenance_registry/uid-c"),
        ]
    )
    summary = cron.run_universal_short_term_maintenance(db_client=db, now=NOW, inventory_limit=3)

    assert calls == ["uid-a", "uid-b"]
    assert summary.flex_deferred is True
    assert summary.dreamed_users == 1
    assert db.docs[cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH]["last_uid"] == "uid-a"


def test_registry_cursor_persists_after_empty_short_term_skip(monkeypatch):
    _enable(monkeypatch)
    calls = []

    def maintenance(uid, **_kwargs):
        calls.append(uid)
        raise AssertionError("empty short-term accounts must not be dreamed")

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    monkeypatch.setattr(cron, "count_active_short_term", lambda uid, db_client, cap=11: 0)

    db = _Db(
        [
            _Snapshot("canonical_memory_maintenance_registry/uid-a"),
            _Snapshot("canonical_memory_maintenance_registry/uid-b"),
        ]
    )
    summary = cron.run_universal_short_term_maintenance(db_client=db, now=NOW, inventory_limit=2)

    assert calls == []
    assert summary.skipped_no_short_term == 2
    assert db.docs[cron.CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH]["last_uid"] == "uid-b"


def test_maintenance_flex_env_forces_the_router(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_FLEX_ENV, "true")
    seen = {}

    class _FlexRouter:
        def __init__(self, *, db_client, force_enabled=False):
            seen["force_enabled"] = force_enabled
            self.control = type("Control", (), {"enabled": bool(force_enabled)})()

        def llm_invoke_for_uid(self, _uid):
            return None

        def llm_for_uid(self, _uid, **_kwargs):
            return None

    monkeypatch.setattr(cron, "PromotionFlexRunRouter", _FlexRouter)
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: cron.CanonicalShortTermMaintenanceReport(uid=uid),
    )

    cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-a"],
    )
    assert seen["force_enabled"] is True


def test_overflow_queue_bypasses_recent_dream_cooldown(monkeypatch):
    _enable(monkeypatch)
    calls = []

    class _FlexRouter:
        def __init__(self, *, db_client, force_enabled=False):
            self.control = type("Control", (), {"enabled": True})()

        def llm_invoke_for_uid(self, _uid):
            return lambda prompt: "flex"

        def llm_for_uid(self, _uid, **_kwargs):
            return object()

        assert_result_current = staticmethod(lambda: None)

    def maintenance(uid, **kwargs):
        calls.append((uid, kwargs["required_processing_limit"]))
        return cron.CanonicalShortTermMaintenanceReport(uid=uid)

    monkeypatch.setattr(cron, "PromotionFlexRunRouter", _FlexRouter)
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    monkeypatch.setattr(
        cron,
        "count_active_short_term",
        lambda uid, db_client, cap=11: 11 if uid == "uid-overflow" else 3,
    )
    monkeypatch.setattr(cron, "recently_dreamed", lambda uid, db_client, now: True)

    summary = cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-daily", "uid-overflow"],
    )

    assert calls == [("uid-overflow", 0)]
    assert summary.skipped_recently_dreamed == 1
    assert summary.dreamed_users == 1


def test_failed_consolidation_does_not_start_dream_cooldown(monkeypatch):
    _enable(monkeypatch)
    persisted = []

    def persist(uid, *, db_client, now):
        persisted.append(uid)

    def maintenance(uid, **_kwargs):
        return cron.CanonicalShortTermMaintenanceReport(
            uid=uid,
            consolidation=ConsolidationReport(
                uid=uid,
                errors=["parse_failed"],
                retryable_memory_ids=["mem-a"],
            ),
        )

    monkeypatch.setattr(cron, "persist_last_dreamed_at", persist)
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)
    monkeypatch.setattr(cron, "count_active_short_term", lambda uid, db_client, cap=11: 3)
    monkeypatch.setattr(cron, "recently_dreamed", lambda uid, db_client, now: False)

    summary = cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-retry"],
    )

    assert persisted == []
    assert summary.dreamed_users == 1
    assert any("consolidation_failed" in error for error in summary.errors)


def test_successful_dream_persists_cooldown(monkeypatch):
    _enable(monkeypatch)
    persisted = []

    def persist(uid, *, db_client, now):
        persisted.append(uid)

    monkeypatch.setattr(cron, "persist_last_dreamed_at", persist)
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: cron.CanonicalShortTermMaintenanceReport(uid=uid),
    )
    monkeypatch.setattr(cron, "count_active_short_term", lambda uid, db_client, cap=11: 3)
    monkeypatch.setattr(cron, "recently_dreamed", lambda uid, db_client, now: False)

    cron.run_universal_short_term_maintenance(
        db_client=object(),
        now=NOW,
        uid_inventory=lambda _db, _limit: ["uid-ok"],
    )

    assert persisted == ["uid-ok"]


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
            db_client=object(),
            now=NOW,
            run_id="cron",
            uid_inventory=inventory,
            inventory_limit=3,
        )
    )
    assert result is expected
    assert calls[0][1]["uid_inventory"] is inventory
    assert calls[0][1]["inventory_limit"] == 3
