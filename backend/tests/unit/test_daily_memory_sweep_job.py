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
    ],
    ids=["disabled", "kill-switch"],
)
def test_disabled_producer_still_runs_bounded_lifecycle_cleanup(monkeypatch, daily_memory_sweep_job, authority):
    job = daily_memory_sweep_job
    db_client = object()
    page = DailySweepUIDInventoryPage(uids=("uid-cleanup",), canonical_uids=("uid-cleanup",))
    cleaned: list[tuple[str, object]] = []
    source_calls: list[str] = []
    commits: list[dict[str, object]] = []

    monkeypatch.setattr(job, "default_db_client", db_client)
    monkeypatch.setattr(job, "daily_memory_sweep_authority_from_environment", lambda: authority)
    monkeypatch.setattr(job, "bounded_daily_memory_sweep_uid_inventory", lambda *_args, **_kwargs: page)
    monkeypatch.setattr(
        sweep,
        "cleanup_expired_daily_memory_sweep_stages",
        lambda uid, *, db_client, **_kwargs: cleaned.append((uid, db_client)) or 1,
    )
    monkeypatch.setattr(
        job,
        "firestore_daily_sweep_source_provider",
        lambda *_args, **_kwargs: source_calls.append("source"),
    )
    monkeypatch.setattr(job, "commit_daily_memory_sweep_uid_inventory", lambda *_args, **kwargs: commits.append(kwargs))

    job.run_daily_memory_sweep_job()

    assert cleaned == [("uid-cleanup", db_client)]
    assert source_calls == []
    assert commits == [
        {
            "completed_uids": (),
            "failed_uids": (),
            "advance_page": False,
        }
    ]
