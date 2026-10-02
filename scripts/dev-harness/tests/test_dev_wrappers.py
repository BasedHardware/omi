from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
SHARED_SOURCES = ("_resolve_python.sh", "_source_local_dev_env.sh")
# Every wrapper that hands control to the Python CLI, with the subcommand it runs.
CLI_WRAPPERS = (
    ("dev-up.sh", "up"),
    ("dev-down.sh", "down"),
    ("dev-status.sh", "status"),
    ("dev-summary.sh", "summary"),
    ("dev-reset.sh", "reset"),
    ("dev-logs.sh", "logs"),
    ("dev-check.sh", "check"),
)

PROVISIONED_CLI = "import sys\nprint('cli', *sys.argv[1:])\n"
# python-dotenv and friends live in backend/requirements.txt, so an unprovisioned
# interpreter fails at import time exactly like this.
UNPROVISIONED_CLI = "import omi_missing_third_party_dep\n" + PROVISIONED_CLI


def _bash() -> str:
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required for dev-harness wrapper tests")
    return bash


def _fixture_repo(root: Path, wrapper: str, cli_body: str, extra_modules: dict[str, str] | None = None) -> Path:
    """A checkout carrying one wrapper plus a stand-in dev_harness package."""
    repo = root / "repo"
    harness = repo / "scripts/dev-harness"
    harness.mkdir(parents=True)
    for name in (wrapper, *SHARED_SOURCES):
        shutil.copy2(HARNESS_ROOT / name, harness / name)

    package = harness / "dev_harness"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(cli_body, encoding="utf-8")
    for module, body in (extra_modules or {}).items():
        (package / module).write_text(body, encoding="utf-8")
    return repo


def _run_wrapper(repo: Path, wrapper: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # The resolver appends an inherited PYTHONPATH, and the fixture package must
    # be the only importable dev_harness.
    env.pop("PYTHONPATH", None)
    env["PYTHON"] = sys.executable
    return subprocess.run(
        [_bash(), f"scripts/dev-harness/{wrapper}", *args],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("wrapper,subcommand", CLI_WRAPPERS)
def test_wrapper_names_lane_bootstrap_when_the_harness_is_unprovisioned(
    tmp_path: Path, wrapper: str, subcommand: str
) -> None:
    """The harness's own prerequisite check lives inside the Python CLI, so an
    unprovisioned venv used to die at `import dev_harness.cli` first — the
    contributor saw `ModuleNotFoundError: No module named 'dotenv'` and a
    traceback naming neither the venv nor the bootstrap command (issue #11533).
    """
    repo = _fixture_repo(tmp_path, wrapper, UNPROVISIONED_CLI)

    result = _run_wrapper(repo, wrapper)

    assert result.returncode != 0, result.stdout
    assert "make lane-bootstrap" in result.stdout, result.stdout
    assert "omi_missing_third_party_dep" in result.stdout, result.stdout
    assert "Traceback" not in result.stdout, result.stdout
    assert f"cli {subcommand}" not in result.stdout, result.stdout


@pytest.mark.parametrize("wrapper,subcommand", CLI_WRAPPERS)
def test_wrapper_runs_the_cli_when_the_harness_imports(tmp_path: Path, wrapper: str, subcommand: str) -> None:
    repo = _fixture_repo(tmp_path, wrapper, PROVISIONED_CLI)

    result = _run_wrapper(repo, wrapper)

    assert result.returncode == 0, result.stdout
    assert f"cli {subcommand}" in result.stdout, result.stdout
    assert "make lane-bootstrap" not in result.stdout, result.stdout


MOBILE_SESSION_MODULE = "import sys\nprint('cli', *sys.argv[1:])\n\nif __name__ == '__main__':\n    pass\n"


def test_mobile_session_wrapper_forwards_arguments_to_the_cli(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path, "mobile-session.sh", PROVISIONED_CLI, {"mobile_session.py": MOBILE_SESSION_MODULE})

    result = _run_wrapper(repo, "mobile-session.sh", "doctor", "--json")

    assert result.returncode == 0, result.stdout
    assert "cli doctor --json" in result.stdout, result.stdout


def test_mobile_session_wrapper_names_lane_bootstrap_when_unprovisioned(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path, "mobile-session.sh", UNPROVISIONED_CLI, {"mobile_session.py": MOBILE_SESSION_MODULE})

    result = _run_wrapper(repo, "mobile-session.sh", "list")

    assert result.returncode != 0, result.stdout
    assert "make lane-bootstrap" in result.stdout, result.stdout
    assert "Traceback" not in result.stdout, result.stdout
