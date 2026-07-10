"""Behavior tests for the backend unit-test runner's failure guidance."""

import os
import stat
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_RUNNER = BACKEND_DIR / "test.sh"


def test_file_isolation_failure_prints_exact_rerun_guidance(tmp_path):
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text("tests/unit/test_example_failure.py\n", encoding="utf-8")

    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"-m\" && \"$2\" == \"pytest\" ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    environment = os.environ | {
        "PYTHON": str(fake_python),
        "BACKEND_UNIT_TEST_FILE_LIST": str(selected_tests),
        "BACKEND_PYTEST_WORKERS": "1",
    }
    result = subprocess.run(
        ["bash", str(TEST_RUNNER)],
        cwd=BACKEND_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Backend unit test file failed: tests/unit/test_example_failure.py (status 1)" in result.stdout
    assert "Backend unit suite failed." in result.stdout
    assert "Reproduce only the failed file(s) with the same test.sh runner and timing guard:" in result.stdout
    assert "echo tests/unit/test_example_failure.py >> /tmp/omi-backend-unit-failures.txt" in result.stdout
    assert "BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-backend-unit-failures.txt bash test.sh" in result.stdout
    assert "Do not use bare pytest for fast-unit timing failures" in result.stdout
