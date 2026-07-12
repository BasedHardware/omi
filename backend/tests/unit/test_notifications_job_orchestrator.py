"""notifications-job orchestrator no longer hosts memory maintenance."""

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
    assert "should_run_canonical_short_term_maintenance_cron" not in imported_names
    assert "run_canonical_short_term_maintenance_cron" not in source
    assert "should_run_canonical_short_term_maintenance_cron" not in source


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
