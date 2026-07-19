from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check_release_rings.py")
SPEC = importlib.util.spec_from_file_location("check_release_rings", MODULE_PATH)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_checked_in_release_ring_workflows_are_guarded() -> None:
    assert checker.check() == []


def test_missing_guard_is_reported(tmp_path: Path, monkeypatch) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    scripts_dir = tmp_path / ".github" / "scripts"
    scripts_dir.mkdir(parents=True)
    (workflow_dir / "release-record.yml").write_text("workflow_run:\n", encoding="utf-8")
    (workflow_dir / "deploy-release-ring.yml").write_text("workflow_dispatch:\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    assert any("missing required release-ring guard" in error for error in checker.check())
