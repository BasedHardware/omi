"""notifications-job orchestrator hosts push/daily summary only (not X sync / memory)."""

from __future__ import annotations

import ast
from pathlib import Path


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


def test_start_job_source_does_not_import_x_connector():
    jobs_path = Path(__file__).resolve().parents[2] / "utils" / "other" / "jobs.py"
    source = jobs_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "utils.x_connector":
            raise AssertionError("jobs.py must not import utils.x_connector")

    assert "run_x_sync_job" not in source
    assert "should_run_x_sync_job" not in source


def test_x_connector_sync_job_entrypoint_calls_runner_without_hour_modulo():
    entry_path = Path(__file__).resolve().parents[2] / "modal" / "x_connector_sync_job.py"
    source = entry_path.read_text(encoding="utf-8")
    assert "run_x_sync_job" in source
    assert "raise_if_x_sync_job_failed" in source
    assert "should_run_x_sync_job" not in source
    assert "from utils.other.jobs import start_job" not in source
    assert "asyncio.run(" in source
    assert 'if __name__ == "__main__":' in source
    assert "def main() -> None:" in source
    assert "firebase_admin.initialize_app" in source
    # Deploy readiness: Cloud Run must see non-zero exit on sync-contract failure.
    assert "raise_if_x_sync_job_failed(summary)" in source


def test_notifications_job_orders_primary_notifications_then_health():
    """X connector sync moved to its own Cloud Run Job (#9298), so the shared
    cron runs notifications, then the read-only Redis memory check."""
    jobs_path = Path(__file__).resolve().parents[2] / "utils" / "other" / "jobs.py"
    source = jobs_path.read_text(encoding="utf-8")

    notifications = source.index("await start_cron_notification_job()")
    assert "chat_first_materialization_health" not in source
    redis_memory = source.index("await run_blocking(db_executor, run_redis_memory_check)")
    assert notifications < redis_memory


def test_notifications_job_deploy_retires_materialization_decision_review():
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "gcp_notifications_job.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert 'chat_first_materialization_health review=true' not in workflow
    assert 'chat_first_materialization_review_due' not in workflow
    assert 'redis_memory_threshold threshold=90' in workflow
    assert 'redis_memory_90' in workflow
    assert '--notification-channels="$ALERT_CHANNELS"' in workflow
    assert '--set-notification-channels="$ALERT_CHANNELS"' in workflow


def test_notifications_job_deploy_grants_id_token_when_it_uses_wif():
    """WIF auth needs an OIDC token, and GitHub only mints one with id-token: write.

    #9298 moved the X Flex VPC probe and GKE credentials -- the steps that first
    needed the permission -- out of this workflow, and dropped it. main then added
    development WIF auth here, which needs it on its own. The two edits landed in
    different hunks, so the merge was textually clean and silently produced a
    deploy that fails at google-github-actions/auth. This pins the pairing, not
    either edit.
    """
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "gcp_notifications_job.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    if "workload_identity_provider:" in workflow:
        assert "id-token: 'write'" in workflow


def test_memory_maintenance_job_is_retired():
    """memory-maintenance-job was retired 2026-10-26: required intake runs inline
    at write time and Dream's sweep owns retries/backlog (dream-agent.md)."""
    modal_dir = Path(__file__).resolve().parents[2] / "modal"
    assert not (modal_dir / "memory_maintenance_job.py").exists()
    assert not (modal_dir / "Dockerfile.memory_maintenance_job").exists()
    workflows = Path(__file__).resolve().parents[3] / ".github" / "workflows"
    assert not (workflows / "gcp_memory_maintenance_job.yml").exists()
    assert not (workflows / "gcp_memory_maintenance_job_auto_dev.yml").exists()
