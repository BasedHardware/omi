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


def test_file_isolation_caps_native_pools_and_scrubs_hook_git_environment(tmp_path):
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text("tests/unit/test_example_success.py\n", encoding="utf-8")
    captured_environment = tmp_path / "native-thread-environment.txt"

    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"-m\" && \"$2\" == \"pytest\" ]]; then\n"
        f"  printf '%s\\n' \"$OMP_NUM_THREADS\" \"$OPENBLAS_NUM_THREADS\" \"$MKL_NUM_THREADS\" "
        f"\"$VECLIB_MAXIMUM_THREADS\" \"$NUMEXPR_NUM_THREADS\" \"$BLIS_NUM_THREADS\" "
        f"\"${{GIT_DIR-unset}}\" \"${{GIT_WORK_TREE-unset}}\" \"${{GIT_INDEX_FILE-unset}}\" "
        f"> {captured_environment}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    environment = os.environ | {
        "PYTHON": str(fake_python),
        "BACKEND_UNIT_TEST_FILE_LIST": str(selected_tests),
        "BACKEND_PYTEST_WORKERS": "1",
        "GIT_DIR": subprocess.check_output(["git", "rev-parse", "--git-dir"], cwd=BACKEND_DIR, text=True).strip(),
        "GIT_WORK_TREE": str(BACKEND_DIR.parent),
        "GIT_INDEX_FILE": str(tmp_path / "outer-index"),
    }
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        environment.pop(variable, None)

    result = subprocess.run(
        ["bash", str(TEST_RUNNER)],
        cwd=BACKEND_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert captured_environment.read_text(encoding="utf-8").splitlines() == ["1"] * 6 + ["unset"] * 3

    overrides = {
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "3",
        "MKL_NUM_THREADS": "4",
        "VECLIB_MAXIMUM_THREADS": "5",
        "NUMEXPR_NUM_THREADS": "6",
        "BLIS_NUM_THREADS": "7",
    }
    override_result = subprocess.run(
        ["bash", str(TEST_RUNNER)],
        cwd=BACKEND_DIR,
        env=environment | overrides,
        text=True,
        capture_output=True,
        check=False,
    )

    assert override_result.returncode == 0
    assert captured_environment.read_text(encoding="utf-8").splitlines() == list(overrides.values()) + ["unset"] * 3
