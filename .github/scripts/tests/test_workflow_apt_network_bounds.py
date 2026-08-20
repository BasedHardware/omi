"""Self-test: the guard must fail on the shape it exists to prevent."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "check_workflow_apt_network_bounds.py"
_spec = importlib.util.spec_from_file_location("check_workflow_apt_network_bounds", _MODULE_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)

BOUNDED = "sudo apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=10 -o Acquire::https::Timeout=10"


def _workflow(tmp_path: Path, run: str, *, timeout: bool = True) -> Path:
    step = f'      - name: deps\n{"        timeout-minutes: 5" + chr(10) if timeout else ""}        run: |\n'
    for line in run.splitlines():
        step += f"          {line}\n"
    path = tmp_path / "wf.yml"
    path.write_text(f"name: t\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n{step}")
    return path


def test_bounded_call_with_step_timeout_passes(tmp_path):
    path = _workflow(tmp_path, f"{BOUNDED} update\n{BOUNDED} install --yes redis-server")
    assert guard.check_workflow(path) == []


def test_unbounded_install_is_rejected_even_when_update_is_bounded(tmp_path):
    """The exact regression: the update line bounded, the install line forgotten."""
    path = _workflow(tmp_path, f"{BOUNDED} update\nsudo apt-get install -y xvfb")
    problems = guard.check_workflow(path)
    assert len(problems) == 1
    assert "install -y xvfb" in problems[0]
    assert "Acquire::Retries" in problems[0]


def test_missing_step_timeout_is_rejected(tmp_path):
    path = _workflow(tmp_path, f"{BOUNDED} update", timeout=False)
    problems = guard.check_workflow(path)
    assert any("timeout-minutes" in problem for problem in problems)


@pytest.mark.parametrize("subcommand", ["update", "install --yes curl", "upgrade", "build-dep foo", "download bar"])
def test_every_network_subcommand_is_covered(tmp_path, subcommand):
    path = _workflow(tmp_path, f"sudo apt-get {subcommand}")
    assert guard.check_workflow(path), f"{subcommand!r} should require acquire bounds"


def test_non_network_subcommands_are_left_alone(tmp_path):
    """`clean`/`autoremove` touch no mirror; bounding them would be noise."""
    path = _workflow(tmp_path, "sudo apt-get clean\nsudo apt-get autoremove --yes", timeout=False)
    assert guard.check_workflow(path) == []


def test_repository_workflows_are_bounded():
    root = Path(__file__).resolve().parents[2] / "workflows"
    problems: list[str] = []
    for path in sorted(root.glob("*.yml")):
        problems.extend(guard.check_workflow(path))
    assert problems == [], "\n".join(problems)
