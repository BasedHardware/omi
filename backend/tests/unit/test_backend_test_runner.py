"""Behavior tests for the backend unit-test runner's failure guidance."""

import os
import stat
import subprocess
from pathlib import Path

from testing.shell import bash_command, bash_path

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_RUNNER = BACKEND_DIR / "test.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_file_isolation_failure_prints_exact_rerun_guidance(tmp_path):
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text("tests/unit/test_example_failure.py\n", encoding="utf-8", newline="\n")

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"-m\" && \"$2\" == \"pytest\" ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
    )

    environment = os.environ | {
        "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
        "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
        "BACKEND_PYTEST_WORKERS": "1",
        "BACKEND_PYTEST_PARALLEL_SESSION": "0",
    }
    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
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
    selected_tests.write_text("tests/unit/test_example_success.py\n", encoding="utf-8", newline="\n")
    captured_environment = tmp_path / "native-thread-environment.txt"

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"-m\" && \"$2\" == \"pytest\" ]]; then\n"
        "  printf '%s\\n' \"$OMP_NUM_THREADS\" \"$OPENBLAS_NUM_THREADS\" \"$MKL_NUM_THREADS\" "
        "\"$VECLIB_MAXIMUM_THREADS\" \"$NUMEXPR_NUM_THREADS\" \"$BLIS_NUM_THREADS\" "
        "\"${GIT_DIR-unset}\" \"${GIT_WORK_TREE-unset}\" \"${GIT_INDEX_FILE-unset}\" "
        "> \"$CAPTURED_ENVIRONMENT\"\n"
        "fi\n"
        "exit 0\n",
    )

    environment = os.environ | {
        "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
        "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
        "BACKEND_PYTEST_WORKERS": "1",
        "BACKEND_PYTEST_PARALLEL_SESSION": "0",
        "CAPTURED_ENVIRONMENT": bash_path(captured_environment, cwd=BACKEND_DIR),
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
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
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
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=environment | overrides,
        text=True,
        capture_output=True,
        check=False,
    )

    assert override_result.returncode == 0
    assert captured_environment.read_text(encoding="utf-8").splitlines() == list(overrides.values()) + ["unset"] * 3


def test_file_isolation_reuses_first_worker_that_finishes(tmp_path):
    """A short later file must not wait behind an earlier blocked file.

    The fake slow test is released only by the third file. An oldest-PID wait
    stalls until the slow-test fallback timeout; completion-driven scheduling
    starts the third file as soon as the second (fast) file finishes.
    """

    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_slow.py\ntests/unit/test_fast.py\ntests/unit/test_releases_slow.py\n",
        encoding="utf-8",
        newline="\n",
    )
    control_dir = tmp_path / "control"
    control_dir.mkdir()

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'control_dir="$CONTROL_DIR"\n'
        'test_path="${!#}"\n'
        'case "$test_path" in\n'
        "  tests/unit/test_slow.py)\n"
        '    touch "$control_dir/slow-started"\n'
        "    for _ in $(seq 1 100); do\n"
        '      if [[ -f "$control_dir/release-slow" ]]; then\n'
        "        exit 0\n"
        "      fi\n"
        "      sleep 0.01\n"
        "    done\n"
        '    touch "$control_dir/slow-released-by-timeout"\n'
        "    ;;\n"
        "  tests/unit/test_fast.py)\n"
        '    touch "$control_dir/fast-finished"\n'
        "    ;;\n"
        "  tests/unit/test_releases_slow.py)\n"
        '    [[ -f "$control_dir/slow-released-by-timeout" ]] || touch "$control_dir/reused-finished-worker"\n'
        '    touch "$control_dir/release-slow"\n'
        "    ;;\n"
        "esac\n",
    )

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "2",
            "BACKEND_PYTEST_PARALLEL_SESSION": "0",
            "CONTROL_DIR": bash_path(control_dir, cwd=BACKEND_DIR),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert (control_dir / "fast-finished").is_file()
    assert (control_dir / "reused-finished-worker").is_file()
    assert not (control_dir / "slow-released-by-timeout").exists()


def test_file_isolation_reaps_worker_that_dies_before_status(tmp_path):
    """A worker killed before writing its status must not hang the scheduler.

    Without a liveness check for exited-but-statusless PIDs, the final drain
    loop spins forever waiting for a file that will never arrive. The runner
    must detect the dead child, reap it, and fail the suite.
    """

    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_crash.py\ntests/unit/test_ok.py\n",
        encoding="utf-8",
        newline="\n",
    )

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'test_path="${!#}"\n'
        'case "$test_path" in\n'
        "  tests/unit/test_crash.py)\n"
        # Kill the parent subshell so NO status file is ever written.
        # This simulates an OOM/signal crash before status handoff.
        "    kill -9 $PPID\n"
        "    exit 137\n"
        "    ;;\n"
        "  tests/unit/test_ok.py)\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n",
    )

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "1",
            "BACKEND_PYTEST_PARALLEL_SESSION": "0",
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )

    # The suite must fail, not hang (timeout=10 would raise subprocess.TimeoutExpired).
    assert result.returncode == 1, result.stderr
    assert "test_crash.py" in result.stdout
    assert "worker exited before writing status" in result.stdout


def _recording_python(tmp_path: Path) -> Path:
    """Fake interpreter that records one line per ``-m pytest`` invocation."""
    fake_python = tmp_path / "recording-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n" "set -euo pipefail\n"
        # test.sh probes for xdist with `python -c 'import xdist'`; claim it is present
        # so the parallel partition really asks for -n/--dist.
        'if [[ "${1:-}" == "-c" ]]; then exit 0; fi\n'
        'if [[ "${1:-}" == "-m" && "${2:-}" == "pytest" ]]; then\n'
        "  shift 2\n"
        '  printf \'%s\\n\' "$*" >> "$INVOCATION_LOG"\n'
        "fi\n"
        'exit "${FAKE_PYTEST_STATUS:-0}"\n',
    )
    return fake_python


def test_partition_isolates_only_module_stub_offenders_and_batches_the_rest(tmp_path):
    """The per-file process cost is only owed by files that leak module stubs.

    Isolation exists to contain module-scope ``sys.modules`` mutation, and that
    population is enumerated in ``tests/.module_stub_legacy_allowlist``. Every other
    file must share one parallel pytest session, or the suite pays a fresh
    import+collection ~900 times for nothing.
    """
    allowlist = tmp_path / "allowlist"
    allowlist.write_text(
        "# comment\nbackend/tests/unit/test_legacy_stub.py\n\n",
        encoding="utf-8",
        newline="\n",
    )
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_clean_a.py\ntests/unit/test_legacy_stub.py\ntests/unit/test_clean_b.py\n",
        encoding="utf-8",
        newline="\n",
    )
    invocation_log = tmp_path / "invocations.txt"

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(_recording_python(tmp_path), cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_MODULE_STUB_ALLOWLIST": bash_path(allowlist, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "2",
            "BACKEND_PYTEST_PARALLEL_SESSION": "1",
            "INVOCATION_LOG": bash_path(invocation_log, cwd=BACKEND_DIR),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2, invocations

    isolated = [line for line in invocations if "tests/unit/test_legacy_stub.py" in line]
    batched = [line for line in invocations if "tests/unit/test_clean_a.py" in line]
    assert len(isolated) == 1 and len(batched) == 1
    # The allowlisted file gets a process to itself; the clean files share one session.
    assert "test_clean_a.py" not in isolated[0] and "test_clean_b.py" not in isolated[0]
    assert "tests/unit/test_clean_b.py" in batched[0]
    assert "test_legacy_stub.py" not in batched[0]
    assert "-n 2" in batched[0]
    assert "--dist=loadfile" in batched[0]
    assert "-n" not in isolated[0].split()
    assert "Partition: 2 file(s) in one parallel pytest session, 1 file(s) in per-file isolation." in result.stdout


def test_every_file_gets_its_own_process_unless_the_parallel_session_is_requested(tmp_path):
    """The safe default. Sharing a pytest session is opt-in, and must stay that way.

    Collecting this tree's non-allowlisted files together does not work yet: 11 of 35
    25-file chunks fail collection outright and the full set segfaults the upb protobuf
    backend or gets OOM-killed. See the partition comment in test.sh.
    """
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_clean_a.py\ntests/unit/test_clean_b.py\n",
        encoding="utf-8",
        newline="\n",
    )
    invocation_log = tmp_path / "invocations.txt"

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(_recording_python(tmp_path), cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "1",
            "BACKEND_PYTEST_PARALLEL_SESSION": "0",
            "INVOCATION_LOG": bash_path(invocation_log, cwd=BACKEND_DIR),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2, invocations
    assert all("--dist=loadfile" not in line for line in invocations)
    assert "Partition:" not in result.stdout


def test_parallel_partition_failure_names_the_failing_files_and_fails_the_suite(tmp_path):
    """One process for many files still has to report per file.

    The rerun guidance is only useful if it names the file that failed, so the
    parallel session's failures are read back out of pytest's short summary.
    """
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_clean_a.py\ntests/unit/test_clean_b.py\n",
        encoding="utf-8",
        newline="\n",
    )

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        'if [[ "${1:-}" == "-c" ]]; then exit 0; fi\n'
        'if [[ "${1:-}" == "-m" && "${2:-}" == "pytest" ]]; then\n'
        "  echo 'FAILED tests/unit/test_clean_b.py::test_thing - AssertionError: boom'\n"
        "  echo 'ERROR tests/unit/test_clean_a.py - ImportError: no such module'\n"
        # Session-level gates (the fast-unit duration guard) fail no test, so they
        # announce their files with this marker instead. See tests/conftest.py.
        "  echo 'BACKEND-UNIT-FAILED-FILE tests/unit/test_clean_c.py'\n" "  exit 1\n" "fi\n" "exit 0\n",
    )

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "2",
            "BACKEND_PYTEST_PARALLEL_SESSION": "1",
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1, result.stdout
    assert "Backend unit test file failed: tests/unit/test_clean_a.py (status 1)" in result.stdout
    assert "Backend unit test file failed: tests/unit/test_clean_b.py (status 1)" in result.stdout
    assert "Backend unit test file failed: tests/unit/test_clean_c.py (status 1)" in result.stdout
    assert "echo tests/unit/test_clean_a.py >> /tmp/omi-backend-unit-failures.txt" in result.stdout
    assert "echo tests/unit/test_clean_b.py >> /tmp/omi-backend-unit-failures.txt" in result.stdout
    assert "echo tests/unit/test_clean_c.py >> /tmp/omi-backend-unit-failures.txt" in result.stdout


def test_parallel_partition_failure_without_a_named_file_points_back_at_per_file_isolation(tmp_path):
    """A crash with no short summary must still fail loudly and stay actionable."""
    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text("tests/unit/test_clean_a.py\n", encoding="utf-8", newline="\n")

    fake_python = tmp_path / "fake-python"
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        'if [[ "${1:-}" == "-c" ]]; then exit 0; fi\n'
        'if [[ "${1:-}" == "-m" && "${2:-}" == "pytest" ]]; then exit 134; fi\n'
        "exit 0\n",
    )

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(fake_python, cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "1",
            "BACKEND_PYTEST_PARALLEL_SESSION": "1",
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1, result.stdout
    assert "Backend unit parallel session failed (status 134) without naming a file." in result.stdout
    assert "BACKEND_PYTEST_PARALLEL_SESSION" in result.stdout


def test_shipped_allowlist_entries_are_partitioned_into_per_file_isolation(tmp_path):
    """Binds the runner's partition to the artifact the static checker maintains.

    A normalization slip (repo-relative ``backend/tests/...`` vs the selector's
    backend-relative ``tests/...``) would silently send every known offender into the
    shared session, which is the exact cross-file leak isolation exists to prevent.
    """
    shipped = BACKEND_DIR / "tests" / ".module_stub_legacy_allowlist"
    entries = [
        line.strip().removeprefix("backend/")
        for line in shipped.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert entries, "the shipped module-stub allowlist is empty; this test proves nothing"

    selected_tests = tmp_path / "selected-tests.txt"
    selected_tests.write_text(
        "tests/unit/test_clean_a.py\n" + f"{entries[0]}\n",
        encoding="utf-8",
        newline="\n",
    )
    invocation_log = tmp_path / "invocations.txt"

    result = subprocess.run(
        bash_command(TEST_RUNNER, cwd=BACKEND_DIR),
        cwd=BACKEND_DIR,
        env=os.environ
        | {
            "PYTHON": bash_path(_recording_python(tmp_path), cwd=BACKEND_DIR),
            "BACKEND_UNIT_TEST_FILE_LIST": bash_path(selected_tests, cwd=BACKEND_DIR),
            "BACKEND_PYTEST_WORKERS": "1",
            "BACKEND_PYTEST_PARALLEL_SESSION": "1",
            "INVOCATION_LOG": bash_path(invocation_log, cwd=BACKEND_DIR),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    isolated = [line for line in invocations if entries[0] in line]
    assert len(isolated) == 1
    assert "--dist=loadfile" not in isolated[0]
    assert "tests/unit/test_clean_a.py" not in isolated[0]
