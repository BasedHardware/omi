# Backend Tests

## Unit Tests

`test.sh` is the runner for backend unit tests, locally and in CI. Pick the narrowest selection:

```bash
bash test.sh tests/unit/test_x.py tests/unit/test_y.py   # exactly these files; start here
bash test.sh test_x.py                                   # a bare name that is unique under tests/
bash test.sh tests/unit/test_x.py::test_case             # one test, same runner and guards
bash test.sh --changed                                   # what CI's PR selector picks for this branch
bash test.sh --all                                       # the full suite: CI's job, opt-in locally
bash test.sh --list --changed                            # print a selection without running it
```

A path that does not resolve, a directory, an ambiguous bare name, or an unknown option is an error
that names the argument; nothing falls back to the full suite. Named files and `--changed`/`--all`
selections must also stay inside `backend/` after symlinks are resolved (a symlinked test file or
directory pointing elsewhere is an error); an explicit `BACKEND_UNIT_TEST_FILE_LIST` may name any file. With no selection, a local run uses
`--changed` and CI (`CI` or `GITHUB_ACTIONS` set to `true`) uses `--all`. Every automated caller
(the CI runner, pre-push, the ratchet preflight, the Firestore index guard) passes an explicit
`BACKEND_UNIT_TEST_FILE_LIST`, so that default only changes what a person or agent typing
`bash test.sh` gets. That list variable is still accepted; combining it with file arguments,
`--changed` or `--all` is an error rather than a guess about which one wins.

`--changed` diffs the merge-base with `origin/main` (`--base REF` to change it) against `HEAD`, the
working tree and untracked files, then runs `scripts/select_backend_unit_tests.py --changed-files`
on that list: the same selector, and the same diff, that CI's PR job uses, so a local run can select
more than CI for a change but not less. A stale local `origin/main` only widens the diff. Like CI,
it keeps the hermetic E2E files the selector's contracts name. An empty diff selects nothing; the selector itself
treats an empty path list as "run everything", which a clean local checkout must not inherit. When the diff touches a full-run
input (for example `test.sh` or a lockfile) the selector picks the whole suite, as it does in CI.

The full selection, `scripts/select_backend_unit_tests.py --all`, covers:

- `tests/unit/test_*.py`
- `tests/services/**/test_*.py`
- `tests/routers/**/test_*.py`
- top-level `tests/test_*.py` files that are still part of the unit suite
- `scripts/jobstore_operator/tests/test_*.py` (portable offline controls)

Any source, test or fixture change under `scripts/jobstore_operator/` selects
the portable operator files through the existing CI runner, one pytest process
per file. These fake-based tests do not execute Docker, Kubernetes or SQL and
do not establish native-image qualification, production readiness or serving.

For a changed-file run over an arbitrary path list (`bash test.sh --changed` builds that list from
Git for you):

```bash
python scripts/select_backend_unit_tests.py --changed-files /tmp/changed-files --output /tmp/backend-tests
BACKEND_UNIT_TEST_FILE_LIST=/tmp/backend-tests bash test.sh
```

How changed-file selection decides (in order): explicit full-run inputs (lockfiles, `conftest.py`,
`test.sh`, `main.py`, the selector itself) run everything; workflow contracts and area mappings add their
tests; any other present, parseable Python module, including `database/`, `models/` and `tests/support/`
helpers, selects the tests that can import it (`scripts/backend_import_graph.py`: module-level import
closure, one lazy-import hop, `conftest.py` ancestors, literal `importlib` names); an unmapped data file
selects tests reaching a module that names it. Deleted or unparseable modules, data files nothing names,
and modules with no dependents still run the full suite. Every selection writes its reason.

Controls, all on unless set to `0`/`false`/`off`:

- `BACKEND_UNIT_GRAPH_SELECTION` (repository variable and local env): off restores the pre-graph
  full-suite fallbacks.
- `BACKEND_UNIT_MAIN_SELECTION` (repository variable): off makes every main push run `--all` again. When on,
  a main push selects from the diff since the last green main push run plus a rotating 1/8 slice of the
  suite (slice = green main run count mod 8); the nightly full run (`main_nightly_full.yml`) still runs all.
- The `ci:full` PR label forces the full unit suite on that PR (add it, then re-run).

Before changing selection rules, replay them over recent main history and quote the output:

```bash
python scripts/backtest_backend_unit_selection.py --limit 300 --json /tmp/selection-backtest.json
```

It exits nonzero if graph selection drops any test the legacy narrow selection picked.

`BACKEND_PYTEST_MARK_EXPR` defaults to `not integration and not slow`, which is the PR unit-test lane.
Use markers for tests that need live services, credentials, long waits, native stress paths, or broader
component coverage.

`BACKEND_PYTEST_TIMING_SUMMARY=1` is enabled by default and prints the slowest unit tests and files.
`test.sh` runs selected files in isolated pytest processes by default and parallelizes them with
`BACKEND_PYTEST_WORKERS`. This keeps legacy module-stubbing tests from polluting each other while still avoiding
the old serial file-by-file run. Set `BACKEND_PYTEST_FILE_ISOLATION=0` to try one pytest session with xdist.

`BACKEND_PYTEST_WORKERS` accepts a positive integer or `auto` (the default). In CI, `auto` is every core. Anywhere
else it is half the cores, at least 2 and at most 8, because a developer machine is shared: ten agent lanes on one
18-core host each starting 18 workers produced 48 concurrent pytest processes and a load average near 380
(2026-11-19). The worker count does not change the work, only how much of the host one run claims. Measured the same
day on a 10-core laptop (4 performance + 6 efficiency cores, with roughly 6 cores already busy from other work),
running a 40-file stride sample of the full selection through `test.sh` (four rounds; two at 5 workers):

| Workers | Wall (s) | User + sys CPU (s) |
| --- | --- | --- |
| 4 | 34-48 | 117-145 |
| 5 | 31-33 | 128-133 |
| 8 | 26-30 | 136-143 |
| 18 | 30-36 | 140-148 |

CPU stays within one band and rises a little with oversubscription. 18 workers on 10 cores was slower than 8, and the sample's slowest file (26 s) bounds its wall
time from 8 workers up. A host-wide admission gate, or a developer, can set `BACKEND_PYTEST_WORKERS` explicitly; an
explicit value always wins.

Each isolated file pays a fixed process start-up before its own imports: about 0.4 s wall (0.35 s CPU) for a
trivial file through `test.sh` with warm bytecode, and about 1.0 s with cold bytecode, on the same laptop. The
sample's files average about 3 CPU-seconds each, so most of a file's cost is importing the production modules it
tests, which is what the import-purity work in `docs/test_isolation.md` removes.

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
use `bash test.sh <files>` or `bash test.sh --changed` while iterating, and let CI own full-suite validation.

### Per-test duration guard

`BACKEND_FAST_UNIT_WARN_SECONDS=<seconds>` (default `0.1`) is the per-test CPU-time target.
`BACKEND_FAST_UNIT_FAIL_SECONDS=<seconds>` (default `1.0` for direct local `test.sh`, pre-push, and
the CI runner) is the blocking budget. The guard measures
**CPU time of the call phase only** (`time.process_time`), not wall-clock: wall-clock inflates unpredictably
under parallel contention and makes a hard limit flake. CPU time is the better signal but still inflates
(~2x measured on a saturated host, since contention stall cycles are charged to the process), so the failure
budget keeps headroom over the warning target instead of sitting just above it. Native numerical pools are capped as described above so
aggregate process CPU remains comparable regardless of `BACKEND_PYTEST_WORKERS`. GitHub Actions and local runs share the same 100ms warning target and 1.0s
failure threshold, so near-target CPU-accounting differences under load do not block unrelated pushes or PRs. The slowest wall-clock
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

The timing-sensitive `test_soniox_recovery_retry.py` and
`test_live_replay_provider_pairs.py` files use that same `slow` marker while
SCA-1998 and SCA-1999 track deterministic rewrites. `Backend slow timing tests`
executes both files in separate jobs on every main push, without path filtering
or concurrency coalescing. Its failures are visible as red checks with JUnit
artifacts; it is independent of the required `Backend unit suite` PR check.
Keep these files out of the blocking slow-guardrail manifest. When restoring
their PR coverage, remove each marker and its workflow matrix entry together.

## Asana project chooser regression

From the repository root, with the locked backend environment installed:

```bash
backend/.venv/bin/python -m pytest backend/tests/unit/test_asana_project_pagination.py backend/tests/unit/test_asana_project_pagination_http.py -q
```

These hermetic unit tests cover project continuation offsets, preserved query
filters, OAuth retry across pages, and propagation of later-page errors. The HTTP
cases mount the production router with fake provider/database boundaries and
check response serialization; they do not contact Asana or exercise live OAuth.
Both files are discovered by the existing backend unit runner.

## Integration Tests

Integration tests live under `tests/integration/` and are not run by `bash test.sh`. They may require Redis,
Firebase credentials, API keys, or live external services. Run them explicitly with pytest after reading
`tests/integration/README.md`.

Use `bash test-preflight.sh` before test runs. It validates dependencies and verifies that the selected Python
interpreter matches `.python-version`.
