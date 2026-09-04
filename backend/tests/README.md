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

`BACKEND_PYTEST_PARALLEL_SESSION=1` is an unfinished experiment kept behind a knob: it isolates only the files in
`tests/.module_stub_legacy_allowlist` and runs the rest in one xdist session with `--dist=loadfile`. The per-file
import and collection cost it targets is real (~2200s of summed CPU across ~930 processes), but the predicate is
not sound yet. `scripts/check_module_stub_pollution.py` only sees *direct* module-scope `sys.modules` writes, while
the common pattern here is a module-scope call to a same-file helper that writes `sys.modules`, or an import of the
deprecated `tests/unit/memory_import_isolation`. Measured on the full selection: collecting the 875 non-allowlisted
files in one process segfaults (upb re-registers an evicted `google.cloud.firestore_v1` descriptor), 11 of 35
25-file chunks fail collection on their own, and 815 files in one process is OOM-killed — and because every xdist
worker collects the whole selection, memory scales with worker count. Finishing `docs/test_isolation.md`'s
migration is the prerequisite for turning this on.
The runner also defaults the common BLAS/OpenMP thread-pool variables to `1`: process-level parallelism is
already available, while nested native pools oversubscribe the machine and make CPU attribution depend on which
test first initializes a numerical library. Explicit environment overrides remain available for native-kernel
tests outside the fast unit lane.
It also removes Git's repository-local hook variables after anchoring itself in `backend/`, so tests that create
temporary repositories cannot accidentally mutate or inspect the outer worktree during a pre-push run.
When a file fails, the runner prints a copyable command to rerun only the failed files with the same environment
and timing guard. Use that command instead of a bare `pytest` rerun when investigating a timing failure.

`scripts/run-unit-ci.sh` is the GitHub Actions entrypoint. It runs the full preflight, type-check, selector, and
isolated test contract with a 1.0-second blocking CPU-time ceiling. Pre-push intentionally does not call it: broad
selection is capped at 40 files (or reduced to changed test files), so ordinary pushes remain fast. Keep that split;
use `bash test.sh` or a focused `pytest` invocation while iterating, and let CI own full-suite validation.

### Per-test duration guard

`BACKEND_FAST_UNIT_WARN_SECONDS=<seconds>` (default `0.1`) is the per-test CPU-time target.
`BACKEND_FAST_UNIT_FAIL_SECONDS=<seconds>` (default `0.30` for direct local `test.sh` and pre-push use; `1.0` in
the CI runner) is the blocking budget. The guard measures
**CPU time of the call phase only** (`time.process_time`), not wall-clock: wall-clock inflates unpredictably
under parallel contention and makes a hard limit flake. CPU time is the better signal but still inflates
(~2x measured on a saturated host, since contention stall cycles are charged to the process), so the failure
budget keeps headroom over the warning target instead of sitting just above it. Native numerical pools are capped as described above so
aggregate process CPU remains comparable regardless of `BACKEND_PYTEST_WORKERS`. GitHub Actions keeps the same 100ms warning target but uses a higher
failure threshold so near-target CPU-accounting differences do not block unrelated PRs. The slowest wall-clock
times are still printed in the `Backend unit test durations` summary for visibility.

Under the default file-isolated runner each test file is a separate pytest process, so the first test of a
file/class amortizes that process's module import (FastAPI app / router / database graph) into its measured
time. That import cost is structural, not a per-test regression; existing over-target unit tests are
grandfathered in `tests/fast_unit_duration_allowlist.txt` (one node ID per line). To shrink that list, run a
single pytest session instead (`BACKEND_PYTEST_FILE_ISOLATION=0`, pays imports once per worker) or raise the
failure threshold.

The guard blocks under xdist too. Inside an xdist worker the controller discards `session.exitstatus`, so workers
hand their offenders back over `workeroutput` and the controller fails the session itself; without that handoff
the budget silently stopped blocking the moment the suite ran in one parallel session. Because a duration-guard
failure fails no individual test, it also prints a `BACKEND-UNIT-FAILED-FILE <path>` line that `test.sh` reads so
the rerun list still names the file.

Genuinely non-unit tests (real `asyncio` sleeps, network/Redis, stress, codebase-wide greps, full-app
wiring, per-test fresh module reload) must be marked `@pytest.mark.slow` / `@pytest.mark.integration` so they
leave the PR lane (`not integration and not slow`) rather than being allowlisted.

**`slow` is not "does not run".** Until 2026-09-04 it was: `run-unit-ci.sh` was the only backend unit lane,
so a `slow` marker took a test out of CI entirely and an exact-set guardrail that fails nothing is a comment.
#12701 added two managed `get_llm` call sites the LLM-inventory pin rejects and merged anyway, within the
hour, because nothing ran the pin. If you mark a **guardrail** `slow` — a codebase grep, a coverage ratchet,
an exact-set pin — add its file to `tests/slow_guardrail_manifest.txt` so
`scripts/run-slow-guardrails-ci.sh` runs it. That lane is unselected and unconditional by design: a check
whose job is to notice a change nobody anticipated cannot be gated on the change set that triggered the run.
Stress and network tests still belong in `slow` with no manifest entry.

## Integration Tests

Integration tests live under `tests/integration/` and are not run by `bash test.sh`. They may require Redis,
Firebase credentials, API keys, or live external services. Run them explicitly with pytest after reading
`tests/integration/README.md`.

Use `bash test-preflight.sh` before test runs. It validates dependencies and verifies that the selected Python
interpreter matches `.python-version`.
