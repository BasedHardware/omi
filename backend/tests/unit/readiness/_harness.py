"""Shared helpers for p1_3 / t2x readiness script unit tests.

These readiness scripts all follow the same shape: a ``build_report`` (or
``build_readiness_artifact``) entry point that emits a JSON-able dict which is
``BLOCKED`` / safe-by-default until explicitly executed. The helpers here remove
the duplicated ``importlib`` module-loading boilerplate and the identical
"safe by default" assertion loop, while each test file keeps its own unique
requirement-id / proof-chain / fail-closed inventories as explicit assertions.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]

# Keys that every readiness report exposes with a fixed safe-by-default value.
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


def load_readiness_script(script_filename: str, *, module_label: str | None = None, register: bool = False):
    """Import a ``backend/scripts/<script_filename>`` readiness module in isolation.

    ``register`` controls whether the module is inserted into ``sys.modules`` before
    execution. Most readiness scripts must NOT be registered (some run controlled
    subprocess/TestClient probes whose behavior changes if the parent process has the
    module pre-registered). Scripts that self-reference at import time opt in.
    """
    script_path = BACKEND_DIR / "scripts" / script_filename
    label = module_label or script_filename.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(label, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load readiness script {script_path}")
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_readiness_report(script_filename: str, *, execute: bool = False, module_label: str | None = None) -> dict:
    module = load_readiness_script(script_filename, module_label=module_label)
    return module.build_report(execute=execute)


def assert_readiness_safe_by_default(report: dict, *, artifact: str, expected: dict[str, Any] | None = None) -> None:
    """Assert a readiness report's safe-by-default invariants.

    ``expected`` defaults to :data:`STANDARD_SAFE_BY_DEFAULT_ASSERTIONS`. A set/frozenset
    value is treated as an "in" membership check (e.g. ``{"NOT_RUN", "BLOCKED"}``); any
    other value is an equality check. Each test file passes the exact key/value set it
    wants checked so no per-script assertion is silently dropped.
    """
    checks = STANDARD_SAFE_BY_DEFAULT_ASSERTIONS if expected is None else expected
    assert report["artifact"] == artifact, f"expected artifact {artifact!r}, got {report['artifact']!r}"
    for key, value in checks.items():
        actual = report[key]
        if isinstance(value, (set, frozenset)):
            assert actual in value, f"{artifact}: report[{key!r}]={actual!r} not in {set(value)!r}"
        else:
            assert actual == value, f"{artifact}: report[{key!r}]={actual!r} != {value!r}"
