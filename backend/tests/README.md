# Backend Tests

## Unit Tests

`bash test.sh` is the CI source of truth for backend unit tests. It gets its file list from
`scripts/select_backend_unit_tests.py --all`, which covers:

- `tests/unit/test_*.py`
- `tests/services/**/test_*.py`
- `tests/routers/**/test_*.py`
- top-level `tests/test_*.py` files that are still part of the unit suite

For changed-file runs, use:

```bash
python scripts/select_backend_unit_tests.py --changed-files /tmp/changed-files --output /tmp/backend-tests
BACKEND_UNIT_TEST_FILE_LIST=/tmp/backend-tests bash test.sh
```

`BACKEND_PYTEST_MARK_EXPR` defaults to `not integration and not slow`, which is the PR unit-test lane.
Use markers for tests that need live services, credentials, long waits, native stress paths, or broader
component coverage.

`BACKEND_PYTEST_TIMING_SUMMARY=1` is enabled by default and prints the slowest unit tests and files.
`test.sh` runs selected files in isolated pytest processes by default and parallelizes them with
`BACKEND_PYTEST_WORKERS`. This keeps legacy module-stubbing tests from polluting each other while still avoiding
the old serial file-by-file run. Set `BACKEND_PYTEST_FILE_ISOLATION=0` to try one pytest session with xdist.
The runner also defaults the common BLAS/OpenMP thread-pool variables to `1`: process-level parallelism is
already available, while nested native pools oversubscribe the machine and make CPU attribution depend on which
test first initializes a numerical library. Explicit environment overrides remain available for native-kernel
tests outside the fast unit lane.
It also removes Git's repository-local hook variables after anchoring itself in `backend/`, so tests that create
temporary repositories cannot accidentally mutate or inspect the outer worktree during a pre-push run.
When a file fails, the runner prints a copyable command to rerun only the failed files with the same environment
and timing guard. Use that command instead of a bare `pytest` rerun when investigating a timing failure.

`scripts/run-unit-ci.sh` is the authoritative pre-push and GitHub Actions entrypoint. It runs the same preflight,
type-check, selector, and isolated test runner with the same 1.0-second blocking CPU-time ceiling. Use `bash test.sh`
or a focused `pytest` invocation while iterating; the push hook is the full selected acceptance gate.

### Per-test duration guard

`BACKEND_FAST_UNIT_WARN_SECONDS=<seconds>` (default `0.1`) is the per-test CPU-time target.
`BACKEND_FAST_UNIT_FAIL_SECONDS=<seconds>` (default `0.12` for direct local `test.sh` use; `1.0` in the shared
pre-push/CI contract) is the blocking budget. The guard measures
**CPU time of the call phase only** (`time.process_time`), not wall-clock: wall-clock inflates unpredictably
under parallel contention and makes a hard limit flake. Native numerical pools are capped as described above so
aggregate process CPU remains comparable regardless of `BACKEND_PYTEST_WORKERS`. GitHub Actions keeps the same 100ms warning target but uses a higher
failure threshold so near-target CPU-accounting differences do not block unrelated PRs. The slowest wall-clock
times are still printed in the `Backend unit test durations` summary for visibility.

Under the default file-isolated runner each test file is a separate pytest process, so the first test of a
file/class amortizes that process's module import (FastAPI app / router / database graph) into its measured
time. That import cost is structural, not a per-test regression; existing over-target unit tests are
grandfathered in `tests/fast_unit_duration_allowlist.txt` (one node ID per line). To shrink that list, run a
single pytest session instead (`BACKEND_PYTEST_FILE_ISOLATION=0`, pays imports once per worker) or raise the
failure threshold.

Genuinely non-unit tests (real `asyncio` sleeps, network/Redis, stress, codebase-wide greps, full-app
wiring, per-test fresh module reload) must be marked `@pytest.mark.slow` / `@pytest.mark.integration` so they
leave the PR lane (`not integration and not slow`) rather than being allowlisted.

## Integration Tests

Integration tests live under `tests/integration/` and are not run by `bash test.sh`. They may require Redis,
Firebase credentials, API keys, or live external services. Run them explicitly with pytest after reading
`tests/integration/README.md`.

Use `bash test-preflight.sh` before test runs. It validates dependencies and verifies that the selected Python
interpreter matches `.python-version`.
