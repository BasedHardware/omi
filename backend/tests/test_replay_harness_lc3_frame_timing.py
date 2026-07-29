"""Regression coverage for the package-free LC3 replay-oracle runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / "backend" / "testing" / "replay_harness_lc3_frame_timing"
RUNNER = HARNESS_DIR / "run.sh"


def _unsupported_uname(tmp_path: Path) -> Path:
    """Provide a deterministic unsupported-host response for the shell runner."""

    uname = tmp_path / "uname"
    uname.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == \"-s\" ]]; then\n"
        "  printf '%s\\n' Darwin\n"
        "elif [[ \"${1:-}\" == \"-m\" ]]; then\n"
        "  printf '%s\\n' arm64\n"
        "else\n"
        "  exit 64\n"
        "fi\n",
        encoding="utf-8",
    )
    uname.chmod(0o755)
    return tmp_path


def test_lc3_replay_runner_fails_closed_on_an_unsupported_host(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["PATH"] = f"{_unsupported_uname(tmp_path)}:{environment['PATH']}"

    completed = subprocess.run(
        ["bash", str(RUNNER)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "requires Linux x86_64" in completed.stderr
    assert "unsupported" in completed.stderr


def test_lc3_replay_oracle_is_registered_without_a_private_package_init() -> None:
    """Static repository contract for the dedicated, package-free test runner."""

    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["test:replay-lc3-frame-timing"] == (
        "backend/testing/replay_harness_lc3_frame_timing/run.sh"
    )
    assert RUNNER.is_file()
    assert not (HARNESS_DIR / "__init__.py").exists()
