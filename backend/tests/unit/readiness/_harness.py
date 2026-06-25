"""Shared helpers for p1_3 / t2x readiness script unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]

STANDARD_SAFE_BY_DEFAULT_ASSERTIONS: dict[str, Any] = {
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "read_only": True,
    "mutation_allowed": False,
    "runtime_wiring_changed": False,
    "routers_memories_modified": False,
    "network_or_provider_calls_executed": False,
    "provider_calls_executed": False,
    "firestore_reads_executed": False,
    "firestore_writes_executed": False,
    "production_rollout_approved": False,
    "approval_claimed": False,
    "execute": False,
}


def load_readiness_script(script_filename: str, *, module_label: str | None = None):
    script_path = BACKEND_DIR / "scripts" / script_filename
    label = module_label or script_filename.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(label, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load readiness script {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_readiness_report(script_filename: str, *, execute: bool = False, module_label: str | None = None) -> dict:
    module = load_readiness_script(script_filename, module_label=module_label)
    return module.build_report(execute=execute)


def assert_readiness_safe_by_default(report: dict, *, artifact: str) -> None:
    assert report["artifact"] == artifact
    for key, expected in STANDARD_SAFE_BY_DEFAULT_ASSERTIONS.items():
        assert report[key] == expected, f"{artifact}: expected report[{key!r}] == {expected!r}"
