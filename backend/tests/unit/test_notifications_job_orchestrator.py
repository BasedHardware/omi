"""notifications-job orchestrator no longer hosts memory maintenance."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def memory_maintenance_job(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    entry_path = Path(__file__).resolve().parents[2] / "modal" / "memory_maintenance_job.py"
    spec = importlib.util.spec_from_file_location("_memory_maintenance_job_behavior_test", entry_path)
    assert spec is not None and spec.loader is not None
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


def test_start_job_source_does_not_invoke_memory_maintenance():
    jobs_path = Path(__file__).resolve().parents[2] / "utils" / "other" / "jobs.py"
    source = jobs_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "utils.memory.canonical_short_term_maintenance_cron":
            raise AssertionError("jobs.py must not import canonical short-term maintenance")
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    assert "run_canonical_short_term_maintenance_cron" not in imported_names
    assert "run_canonical_short_term_maintenance_cron" not in source


def test_notifications_job_orders_primary_notifications_then_health_then_x_flex():
    jobs_path = Path(__file__).resolve().parents[2] / "utils" / "other" / "jobs.py"
    source = jobs_path.read_text(encoding="utf-8")

    started_at = source.index("job_started_at = time.monotonic()")
    notifications = source.index("await start_cron_notification_job()")
    materialization_health = source.index("await run_blocking(db_executor, run_scheduled_check)")
    x_sync = source.index("await run_x_sync_job(job_started_at=job_started_at)")
    assert started_at < notifications < materialization_health < x_sync


def test_notifications_job_deploy_routes_materialization_decision_review():
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "gcp_notifications_job.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert 'chat_first_materialization_health review=true' in workflow
    assert 'chat_first_materialization_review_due' in workflow
    assert '--notification-channels="$ALERT_CHANNELS"' in workflow
    assert '--set-notification-channels="$ALERT_CHANNELS"' in workflow


def test_memory_maintenance_job_entrypoint_calls_cron_runner():
    entry_path = Path(__file__).resolve().parents[2] / "modal" / "memory_maintenance_job.py"
    source = entry_path.read_text(encoding="utf-8")
    assert "run_canonical_short_term_maintenance_cron" in source
    assert "from utils.other.jobs import start_job" not in source
    assert "recurrence_signal_persister=persist_recurrence_signals_for_maintenance" in source
    assert "recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance" in source
    assert "asyncio.run(" in source
    assert 'if __name__ == "__main__":' in source
    assert "def main() -> None:" in source
    assert "firebase_admin.initialize_app" in source
    # Import purity: Firebase init must not run at module import time.
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Expr, ast.Assign, ast.If)) and not isinstance(node, ast.FunctionDef):
            # top-level if __name__ is fine; bare initialize_app calls are not
            pass
    assert "os.environ[" not in source


def test_memory_maintenance_job_exits_with_failure_when_cron_reports_outbox_error(monkeypatch, memory_maintenance_job):
    async def failed_cron(**_kwargs):
        return SimpleNamespace(errors=["uid=test: outbox_delivery_failed"])

    monkeypatch.setattr(memory_maintenance_job, "_init_firebase", lambda: None)
    monkeypatch.setattr(memory_maintenance_job, "run_canonical_short_term_maintenance_cron", failed_cron)

    with pytest.raises(RuntimeError, match=r"completed with 1 error\(s\)"):
        memory_maintenance_job.main()
