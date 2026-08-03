"""Unit tests for stlt_lifecycle_proof dry-run contract."""

from __future__ import annotations

import os
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stlt_lifecycle_proof.py"
mod = SourceFileLoader("stlt_lifecycle_proof", str(SCRIPT)).load_module()


def test_dry_run_is_default_and_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP", raising=False)
    args = mod._parse_args(["--project", "based-hardware", "--uid", "uid-test"])
    assert args.apply is False
    result = mod.run_proof(args)
    assert result.ok is True
    assert result.mode == "dry_run"
    assert result.project == "based-hardware"
    assert result.batch_cap == 1
    assert result.memory_id == ""
    assert any("based-hardware" in n for n in result.notes)


def test_configure_env_sets_batch_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP", raising=False)
    mod._configure_env(project="based-hardware", batch_cap=1)
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "based-hardware"
    assert os.environ["MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP"] == "1"


def test_apply_without_encryption_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    args = mod._parse_args(["--apply", "--project", "based-hardware"])
    result = mod.run_proof(args)
    assert result.ok is False
    assert any("ENCRYPTION_SECRET" in e for e in result.errors)
