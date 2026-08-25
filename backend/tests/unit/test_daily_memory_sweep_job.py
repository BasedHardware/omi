"""Deployed daily-memory-sweep entrypoint lifecycle behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from utils.memory import daily_memory_sweep as sweep
from utils.memory.daily_memory_sweep_inventory import DailySweepUIDInventoryPage


@pytest.fixture
def daily_memory_sweep_job(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    entry_path = Path(__file__).resolve().parents[2] / "modal" / "daily_memory_sweep_job.py"
    spec = importlib.util.spec_from_file_location("_daily_memory_sweep_job_behavior_test", entry_path)
    assert spec is not None and spec.loader is not None
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


@pytest.mark.parametrize(
    "authority",
    [
        sweep.SweepAuthorityState(enabled=False),
        sweep.SweepAuthorityState(enabled=True, kill_switch_active=True),
        None,
    ],
    ids=["disabled", "kill-switch", "unavailable"],
)
def test_closed_authority_exits_before_inventory_cleanup_or_scheduler_work(
    monkeypatch, daily_memory_sweep_job, authority
):
    job = daily_memory_sweep_job
    inventory_calls: list[bool] = []
    scheduler_calls: list[bool] = []
    commit_calls: list[bool] = []

    monkeypatch.setattr(job, "daily_memory_sweep_authority_from_environment", lambda: authority)
    monkeypatch.setattr(
        job,
        "bounded_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: inventory_calls.append(True),
    )
    monkeypatch.setattr(
        job,
        "run_daily_memory_sweep_scheduler",
        lambda *_args, **_kwargs: scheduler_calls.append(True),
    )
    monkeypatch.setattr(
        job,
        "commit_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: commit_calls.append(True),
    )

    job.run_daily_memory_sweep_job()

    assert inventory_calls == []
    assert scheduler_calls == []
    assert commit_calls == []


def test_truthy_malformed_authority_fails_closed(monkeypatch, daily_memory_sweep_job):
    job = daily_memory_sweep_job
    inventory_calls: list[bool] = []

    class MalformedAuthority:
        may_write = "false"

    monkeypatch.setattr(job, "daily_memory_sweep_authority_from_environment", MalformedAuthority)
    monkeypatch.setattr(
        job,
        "bounded_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: inventory_calls.append(True),
    )

    job.run_daily_memory_sweep_job()

    assert inventory_calls == []


def test_authority_property_failure_exits_before_inventory(monkeypatch, daily_memory_sweep_job):
    job = daily_memory_sweep_job
    inventory_calls: list[bool] = []

    class UnreadableAuthority:
        @property
        def may_write(self):
            raise RuntimeError("authority unreadable")

    monkeypatch.setattr(job, "daily_memory_sweep_authority_from_environment", UnreadableAuthority)
    monkeypatch.setattr(
        job,
        "bounded_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: inventory_calls.append(True),
    )

    job.run_daily_memory_sweep_job()

    assert inventory_calls == []


def test_authority_resolution_failure_exits_before_inventory(monkeypatch, daily_memory_sweep_job):
    job = daily_memory_sweep_job
    inventory_calls: list[bool] = []

    def unavailable_authority():
        raise RuntimeError("authority unavailable")

    monkeypatch.setattr(job, "daily_memory_sweep_authority_from_environment", unavailable_authority)
    monkeypatch.setattr(
        job,
        "bounded_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: inventory_calls.append(True),
    )

    job.run_daily_memory_sweep_job()

    assert inventory_calls == []


def test_open_authority_preserves_inventory_scheduler_and_commit_flow(monkeypatch, daily_memory_sweep_job):
    job = daily_memory_sweep_job
    db_client = object()
    page = DailySweepUIDInventoryPage(uids=("uid-open",), canonical_uids=("uid-open",))
    summary = sweep.DailySweepSchedulerSummary(
        attempted_users=1,
        committed_users=1,
        completed_uids=("uid-open",),
    )
    inventory_calls: list[bool] = []
    scheduler_uids: list[tuple[str, ...]] = []
    commits: list[dict[str, object]] = []

    monkeypatch.setattr(job, "default_db_client", db_client)
    monkeypatch.setattr(
        job,
        "daily_memory_sweep_authority_from_environment",
        lambda: sweep.SweepAuthorityState(enabled=True),
    )
    monkeypatch.setattr(
        job,
        "bounded_daily_memory_sweep_uid_inventory",
        lambda *_args, **_kwargs: inventory_calls.append(True) or page,
    )
    monkeypatch.setattr(
        job,
        "run_daily_memory_sweep_scheduler",
        lambda **kwargs: scheduler_uids.append(tuple(kwargs["uid_inventory"])) or summary,
    )
    monkeypatch.setattr(job, "commit_daily_memory_sweep_uid_inventory", lambda *_args, **kwargs: commits.append(kwargs))

    job.run_daily_memory_sweep_job()

    assert inventory_calls == [True]
    assert scheduler_uids == [("uid-open",)]
    assert commits == [
        {
            "completed_uids": ("uid-open",),
            "failed_uids": (),
            "advance_page": True,
        }
    ]
