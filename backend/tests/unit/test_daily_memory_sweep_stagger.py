"""Per-user stagger for the daily memory sweep. Default spread is zero."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from models.memory_apply import MemoryControlState, WriterMode
from utils.memory.daily_memory_sweep import (
    DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV,
    DailySweepCursor,
    SweepAuthorityState,
    daily_memory_sweep_stagger_delay_seconds,
    daily_memory_sweep_stagger_spread_seconds,
    run_daily_memory_sweep_scheduler,
)
import utils.memory.daily_memory_sweep as sweep_mod


def _expected_delay(uid: str, spread_seconds: int) -> int:
    digest = hashlib.sha256(uid.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % spread_seconds


def test_stagger_delay_is_deterministic_and_disabled_at_zero():
    first = daily_memory_sweep_stagger_delay_seconds("user-1", 3600)
    second = daily_memory_sweep_stagger_delay_seconds("user-1", 3600)

    assert first == second == _expected_delay("user-1", 3600)
    assert daily_memory_sweep_stagger_delay_seconds("user-1", 0) == 0
    assert daily_memory_sweep_stagger_delay_seconds("user-1", -5) == 0
    assert daily_memory_sweep_stagger_delay_seconds("  user-1  ", 3600) == first


def test_stagger_spread_defaults_to_zero(monkeypatch):
    monkeypatch.delenv(DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV, raising=False)
    assert daily_memory_sweep_stagger_spread_seconds() == 0
    assert daily_memory_sweep_stagger_spread_seconds({}) == 0
    assert daily_memory_sweep_stagger_spread_seconds({DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV: "3600"}) == 3600
    assert daily_memory_sweep_stagger_spread_seconds({DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV: "0"}) == 0
    assert daily_memory_sweep_stagger_spread_seconds({DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV: "nope"}) == 0
    assert daily_memory_sweep_stagger_spread_seconds({DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV: "-1"}) == 0


def test_stagger_slot_sleeps_only_the_remaining_offset(monkeypatch):
    uid = next(
        candidate
        for candidate in ("user-1", "user-2", "user-3", "user-4")
        if daily_memory_sweep_stagger_delay_seconds(candidate, 3600) >= 5
    )
    delay = daily_memory_sweep_stagger_delay_seconds(uid, 3600)
    clock = {"t": 4.0}
    slept: list[float] = []
    monkeypatch.setattr(sweep_mod, "_sweep_monotonic", lambda: clock["t"])
    monkeypatch.setattr(sweep_mod, "_sweep_sleep", lambda seconds: slept.append(seconds))

    sweep_mod._sleep_until_sweep_stagger_slot(uid, spread_seconds=3600, started_monotonic=0.0)
    sweep_mod._sleep_until_sweep_stagger_slot(uid, spread_seconds=0, started_monotonic=0.0)
    clock["t"] = float(delay)
    sweep_mod._sleep_until_sweep_stagger_slot(uid, spread_seconds=3600, started_monotonic=0.0)

    assert slept == [delay - 4]


def _ledger_control(uid: str) -> MemoryControlState:
    return MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=4,
        source_generation=7,
        writer_mode=WriterMode.ledger,
        writer_epoch=1,
    )


def _install_quiet_scheduler(monkeypatch, seen: list[str]) -> None:
    monkeypatch.setattr(sweep_mod, "belief_model_enabled", lambda: False)
    monkeypatch.setattr(sweep_mod, "free_tier_memory_suppression_enabled", lambda _uid: False)
    monkeypatch.setattr(sweep_mod, "cleanup_expired_daily_memory_sweep_stages", lambda *args, **kwargs: None)
    monkeypatch.setattr(sweep_mod, "cleanup_expired_memory_deletion_receipts", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sweep_mod,
        "ensure_canonical_apply_control_state",
        lambda uid, db_client: seen.append(uid) or _ledger_control(uid),
    )

    def _cursor(db_client, uid, control):
        del db_client
        return DailySweepCursor(
            uid=uid,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            timezone_name="UTC",
        )

    monkeypatch.setattr(sweep_mod, "_read_cursor", _cursor)
    monkeypatch.setattr(sweep_mod, "_pending_completed_dates", lambda *args, **kwargs: ())
    monkeypatch.setattr(sweep_mod, "_sweep_monotonic", lambda: 0.0)


def test_scheduler_staggers_users_in_slot_order_and_skips_sleep_at_zero(monkeypatch):
    uids = ("user-b", "user-a")
    spread = 3600
    seen: list[str] = []
    slept: list[float] = []
    _install_quiet_scheduler(monkeypatch, seen)
    monkeypatch.setattr(sweep_mod, "_sweep_sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setenv(DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV, str(spread))

    summary = run_daily_memory_sweep_scheduler(
        db_client=object(),
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=uids,
        source_provider=lambda *_args, **_kwargs: None,
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
    )

    ordered = tuple(sorted(uids, key=lambda uid: (_expected_delay(uid, spread), uid)))
    assert tuple(seen) == ordered
    assert slept == [float(_expected_delay(uid, spread)) for uid in ordered]
    assert summary.attempted_users == 2

    seen.clear()
    slept.clear()
    monkeypatch.setenv(DAILY_MEMORY_SWEEP_STAGGER_SECONDS_ENV, "0")
    run_daily_memory_sweep_scheduler(
        db_client=object(),
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=uids,
        source_provider=lambda *_args, **_kwargs: None,
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
    )

    assert seen == ["user-a", "user-b"]
    assert slept == []
