"""Unit tests for stlt_lifecycle_proof dry-run / fail-closed contracts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stlt_lifecycle_proof.py"


def _load_mod() -> Any:
    import sys

    name = "stlt_lifecycle_proof_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(monkeypatch: pytest.MonkeyPatch) -> Any:
    # Isolate env mutations from the rest of the suite.
    kept = dict(os.environ)
    monkeypatch.setattr(os, "environ", kept)
    return _load_mod()


def test_default_project_is_based_hardware(mod: Any) -> None:
    args = mod._parse_args([])
    assert args.project == "based-hardware"
    assert args.apply is False


def test_dry_run_is_ok(mod: Any) -> None:
    args = mod._parse_args(["--project", "based-hardware", "--uid", "uid-test"])
    result = mod.run_proof(args)
    assert result.ok is True
    assert result.mode == "dry_run"
    assert result.batch_cap == 1
    assert result.memory_id == ""
    assert os.environ.get("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP") == "1"


def test_apply_requires_confirm_and_encryption(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    monkeypatch.setenv("OMI_LLM_GATEWAY_FEATURE_MODE", "gateway")
    args = mod._parse_args(["--apply", "--project", "based-hardware", "--uid", "uid-test"])
    result = mod.run_proof(args)
    assert result.ok is False
    assert "apply_requires_--confirm-data-plane" in result.errors
    assert "ENCRYPTION_SECRET_required" in result.errors


def test_apply_requires_gateway_unless_allow_direct(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "x" * 32)
    monkeypatch.setenv("OMI_LLM_GATEWAY_FEATURE_MODE", "direct")
    args = mod._parse_args(
        [
            "--apply",
            "--confirm-data-plane",
            "--project",
            "based-hardware",
            "--uid",
            "uid-test",
        ]
    )
    result = mod.run_proof(args)
    assert result.ok is False
    assert any("gateway" in e for e in result.errors)


def test_configure_env_forces_batch_cap_one(mod: Any) -> None:
    mod._configure_env(project="based-hardware")
    assert os.environ["MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP"] == "1"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "based-hardware"


def test_safe_error_omits_exception_args(mod: Any) -> None:
    class Boom(Exception):
        pass

    label = mod._safe_error(Boom("secret memory content should not leak"))
    assert label == "Boom"
    assert "secret" not in label
