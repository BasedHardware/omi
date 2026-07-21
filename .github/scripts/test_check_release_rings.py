from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_release_rings.py")
SPEC = importlib.util.spec_from_file_location("check_release_rings", MODULE_PATH)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_checked_in_production_release_vector_is_guarded() -> None:
    assert checker.check() == []


def test_beta_backend_dispatch_is_rejected(tmp_path: Path, monkeypatch) -> None:
    for relative in checker.BACKEND_RELEASE_SOURCES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checker.ROOT / relative, destination)
    deploy_path = tmp_path / ".github/workflows/deploy-release-ring.yml"
    deploy_path.write_text(deploy_path.read_text(encoding="utf-8") + "\n# beta\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    assert any("backend beta-ring logic is forbidden" in error for error in checker.check())


def test_dispatch_release_id_cannot_be_interpolated_into_shell(tmp_path: Path, monkeypatch) -> None:
    for relative in checker.BACKEND_RELEASE_SOURCES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checker.ROOT / relative, destination)
    deploy_path = tmp_path / ".github/workflows/deploy-release-ring.yml"
    deploy_path.write_text(
        deploy_path.read_text(encoding="utf-8").replace(
            "records/${RELEASE_ID}.json", "records/${{ inputs.release_id }}.json"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    assert any("must enter shell only through the job environment" in error for error in checker.check())
