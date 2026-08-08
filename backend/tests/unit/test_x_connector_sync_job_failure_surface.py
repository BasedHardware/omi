"""x-connector-sync-job must fail Cloud Run on sync-contract breakage (#11183)."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Dict

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
X_CONNECTOR_PATH = BACKEND_DIR / "utils" / "x_connector.py"
ENTRY_PATH = BACKEND_DIR / "modal" / "x_connector_sync_job.py"


def _load_raise_if_x_sync_job_failed():
    source = X_CONNECTOR_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "raise_if_x_sync_job_failed":
            fn_node = node
            break
    assert fn_node is not None, "raise_if_x_sync_job_failed missing from utils/x_connector.py"
    module = ast.Module(body=[fn_node], type_ignores=[])
    ast.fix_missing_locations(module)
    ns: dict = {"Dict": Dict}
    exec(compile(module, str(X_CONNECTOR_PATH), "exec"), ns, ns)
    return ns["raise_if_x_sync_job_failed"]


raise_if_x_sync_job_failed = _load_raise_if_x_sync_job_failed()


@pytest.fixture
def x_connector_sync_job(monkeypatch):
    monkeypatch.setenv(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    spec = importlib.util.spec_from_file_location("_x_connector_sync_job_behavior_test", ENTRY_PATH)
    assert spec is not None and spec.loader is not None
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


def test_raise_if_x_sync_job_failed_on_listing_errors():
    with pytest.raises(RuntimeError, match="list_users"):
        raise_if_x_sync_job_failed(
            {
                "users": 0,
                "synced": 0,
                "new_posts": 0,
                "failed": 0,
                "errors": ["list_users: RuntimeError: boom"],
            }
        )


def test_raise_if_x_sync_job_failed_when_every_user_fails():
    with pytest.raises(RuntimeError, match="synced 0/2"):
        raise_if_x_sync_job_failed(
            {"users": 2, "synced": 0, "new_posts": 0, "failed": 2, "errors": []}
        )


def test_raise_if_x_sync_job_failed_allows_partial_and_empty_success():
    raise_if_x_sync_job_failed(
        {"users": 0, "synced": 0, "new_posts": 0, "failed": 0, "errors": []}
    )
    raise_if_x_sync_job_failed(
        {"users": 3, "synced": 2, "new_posts": 1, "failed": 1, "errors": []}
    )


def test_entrypoint_wires_raise_after_asyncio_run():
    entry = ENTRY_PATH.read_text(encoding="utf-8")
    assert "summary = asyncio.run(run_x_sync_job())" in entry
    assert "raise_if_x_sync_job_failed(summary)" in entry


def test_run_x_sync_job_listing_failure_summary_contract_in_source():
    """Listing failures must populate ``errors`` (not a healthy zero summary)."""
    source = X_CONNECTOR_PATH.read_text(encoding="utf-8")
    assert "'errors': [f'list_users:" in source or '"errors": [f"list_users:' in source
    assert "'failed': failed" in source


def test_x_connector_sync_job_exits_nonzero_on_listing_errors(monkeypatch, x_connector_sync_job):
    async def failed_run():
        return {
            "users": 0,
            "synced": 0,
            "new_posts": 0,
            "failed": 0,
            "errors": ["list_users: RuntimeError: firestore down"],
        }

    monkeypatch.setattr(x_connector_sync_job, "_init_firebase", lambda: None)
    monkeypatch.setattr(x_connector_sync_job, "run_x_sync_job", failed_run)

    with pytest.raises(RuntimeError, match="list_users"):
        x_connector_sync_job.main()


def test_x_connector_sync_job_exits_nonzero_when_all_users_fail(monkeypatch, x_connector_sync_job):
    async def failed_run():
        return {"users": 2, "synced": 0, "new_posts": 0, "failed": 2, "errors": []}

    monkeypatch.setattr(x_connector_sync_job, "_init_firebase", lambda: None)
    monkeypatch.setattr(x_connector_sync_job, "run_x_sync_job", failed_run)

    with pytest.raises(RuntimeError, match="synced 0/2"):
        x_connector_sync_job.main()


def test_x_connector_sync_job_allows_partial_success(monkeypatch, x_connector_sync_job):
    async def ok_run():
        return {"users": 2, "synced": 1, "new_posts": 3, "failed": 1, "errors": []}

    monkeypatch.setattr(x_connector_sync_job, "_init_firebase", lambda: None)
    monkeypatch.setattr(x_connector_sync_job, "run_x_sync_job", ok_run)

    x_connector_sync_job.main()
