# PG foundation wave 1: M9 implementation result

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-m9-upstream-keep-clean`. Branch: `lane/pgf-m9`. No push or PR. No GCP tier used and no production access.

## Built

- `backend/utils/other/plane_routing.py`: `plane_for(uid)` defaults to Firestore; a ContextVar binding supports request-local resolved routes with restoration on exit. The process-configured `PLANE_LEAK_TEST_CELL_UIDS` override accepts local/offline/test stages only and rejects deployed/unspecified stages before probes install. B2 owns directory resolution.
- `backend/database/plane_leak_probe.py`: one routed-collection constant combining the W5 domain names with the canonical memory collection catalog. `plane_leak_total{op,collection,origin}` records reads and committed writes; logs contain only bounded operation/collection/origin plus `hash_log_identifier(uid)`. Descendants fold into their domain collection label. The empty-route fast path does not parse paths, resolve owners, hash, log, or create metric series.
- `backend/database/firestore_document_probe.py`: adds the observer to the existing common read-recording seam, including miss/empty-query floor observations.
- `backend/database/firestore_write_probe.py`: observes successful writes only, after Commit success or BatchWrite per-entry OK filtering. Failed/ambiguous commits do not increment the leak counter.
- `backend/tests/unit/test_plane_leak_probe.py`: hermetic SDK transports, allow/deny stages, Firestore vs cell owners, non-routed collections, nested reads, empty queries, successful/failed/partial writes, request isolation, disabled fast path, private logging, and telemetry-failure containment.

Implementation plus tests: 298 added lines, below the brief's 400-line target (excluding this handoff).

## Deviations and scope

The read probe implementation has moved out of `database/_client.py` into `database/firestore_document_probe.py`; the existing `_client` installation path is retained and the detector hooks the extracted probe. Two small shared modules keep routing separate from telemetry and avoid duplicating the domain list between probes. No callers of a retired API exist, and no compatibility wrapper was added.

Existing unrelated edits to `app/analysis_options.yaml` and `app/pubspec.lock` are preserved and excluded from commits. No edits under the prohibited directories or A1/B1/C1-owned paths.

## Verification

Status: implementation complete; broad validation BLOCKED, not green. Evidence cutoff: 2026-11-06T09:30:16.425604+00:00.

Task-start base was `82b83d3b9288b508458e3018b20ad8335c3a8cf2`. The three implementation/test commits are `8a77d8d30027`, `a77da44e8f6b`, and `8b8f66768318`; their combined diff touches exactly the five Python paths listed above. The shared `origin/main` ref advanced to `579400fdf69d3dda2a267bfa2e73ed0593604708` during this run; this lane was not rebased or published.

Tests are launched through `.agent-artifacts/pgf-tests/run-clean.py`, which removes `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*` variable, `SERVICE_ACCOUNT_JSON`, and `FIREBASE_AUTH_CREDENTIALS_PATH`, sets `OMI_ENV_STAGE=offline`, then execs the command. All pytest invocations use this worktree's `backend/.venv/bin/python`. Heavy runs use `/Users/dazheng/workspace/omi/bin/omi-heavy run --`.

Completed:

- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python -m pytest -q backend/tests/unit/test_plane_leak_probe.py`: initial and revised 30-test runs each passed; final 31 passed, 0 failed.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python -m pytest -q backend/tests/unit/test_firestore_document_probe.py backend/tests/unit/test_firestore_write_probe.py`: 155 passed, 0 failed.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/pyright --pythonpath "$PWD/backend/.venv/bin/python" backend/database/plane_leak_probe.py backend/utils/other/plane_routing.py`: 0 errors, 0 warnings. Initial invocation without `--pythonpath` reported 1 unresolved dependency because it selected the wrong environment; fixed by selecting the worktree interpreter.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- env PYTHON="$PWD/backend/.venv/bin/python" bash backend/test-preflight.sh`: 17 passed checks, 9 optional warnings, 0 failed. Initial invocation without `PYTHON` used system Python: 5 passed, 17 warnings, 4 failed; rerun above corrected the interpreter.
- `black --line-length 120 --skip-string-normalization backend/utils/other/plane_routing.py backend/database/plane_leak_probe.py backend/database/firestore_document_probe.py backend/database/firestore_write_probe.py backend/tests/unit/test_plane_leak_probe.py`: passed. The virtualenv lacks Black, so the installed formatter was used; commit hooks also ran the pinned formatter successfully.
- `git diff --check`: passed.

Selector and repository-gate commands (terminal results):

- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files /dev/stdin --output .agent-artifacts/pgf-tests/selected.txt`, stdin = the five touched Python paths above: selected 2,659 files via the database full-suite fallback plus canonical memory E2E.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf-tests/selected.txt" BACKEND_PYTEST_WORKERS=6 bash backend/test.sh`: interrupted deliberately to isolate the recurring preflight timeout. Final partial log has 227 completed file workers and 4,698 pytest-reported passes; no assertion failure was reported before interruption. Six worker-cancellation errors were generated by termination. Three subsequently discovered orphan worker groups were also stopped after confirming their cwd, inherited heavy lock, and exact selected-test commands. There are 2,432 files without recorded worker completion in `remaining.txt`. This is NOT a full-suite pass. Runner exit 137 reflects deliberate shutdown, not an assertion failure.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils`: passed; 594 sync and 168 async endpoints scanned, 0 selected blocking findings.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- make preflight`: FAILED. The Firestore index guard timed out `tests/unit/test_firestore_query_shapes.py` at its 300-second per-file budget (exit 124); other parallel checks were cancelled by the gate. This command exited 2. No index-shape assertion failure was reported before timeout.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py scripts/pr-preflight --suggest`: completed; no locked product invariants affected.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- scripts/pr-preflight --pr-body-file .agent-artifacts/pgf-pr-body.md`: FAILED on the same 300-second query-shape timeout. It additionally detected the final test-file edit made while that earlier parallel check was running; that edit was committed before the last standalone verification. Source files are stable and committed now, but this run is not a valid green metadata/preflight result.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- env OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf-pr-body.md" make preflight`: cancelled while awaiting heavy-run admission, before execution, to remove the duplicate pending preflight.
- `backend/.venv/bin/python .agent-artifacts/pgf-tests/run-clean.py /Users/dazheng/workspace/omi/bin/omi-heavy run -- timeout --signal=TERM --kill-after=30s 300s backend/.venv/bin/python -m pytest -v backend/tests/unit/test_firestore_query_shapes.py`: FAILED, exit 124, after admission and 300 seconds of execution. Collected 555 tests; eight tests visibly passed, then the runtime-driver capture fixture did not finish before the deadline. No assertion failure was reported. This used the worktree virtualenv after the broad workers were stopped, so the timeout remains unresolved. No further identical rerun was attempted.

Logs and selection are in `.agent-artifacts/pgf-tests/` locally.

## Known gaps and integration obligations

- Required broad validation is unresolved: the existing query-shape guard exceeded its fixed budget in both preflight attempts and the standalone diagnostic. The full selector run is incomplete. No budget, guard, index registry, workflow, unrelated test, or host configuration was changed to hide the failure. The cause of the timeout has not been established; this handoff does not claim it is proven baseline behavior.
- Offline-harness journey script is intentionally not in this PR; W5 integration owns it.
- Directory lookup/enrollment is B2's work. No owners are routed to a real cell by this PR. B2 must bind the resolved request route or replace the source behind `plane_for` and preserve the fast-path gate for routed owners.
- Coverage is the existing SDK probes' coverage: installing through `database._client` is required, and the write-probe kill switch must stay on for the ramp gate. Unattributable collection-group aggregates with no concrete owner path and direct transport reads are not new coverage added here. This is telemetry, not a read/write enforcement fence.
- No deployed behavior, production ramp, API endpoint acceptance, or live data was tested or changed.

## Draft PR body

## What changed and why

Add the W5 plane-leak ramp signal: routed-domain Firestore reads and known-successful writes for cell owners increment `plane_leak_total{op,collection,origin}` and emit a content-free warning with a hashed owner ID. Add a request-local routing seam, Firestore defaults, and a stage-guarded offline override; B2 will supply directory routing.

## Product invariants affected

none

## How it was verified

The 31 new M9 tests and 155 existing read/write probe tests pass using anonymous credentials and fake transports. The two new modules pass type checking; the async-blocking scan passes. Required broad validation is not green: `make preflight` and an isolated query-shape run exceed the 300-second test-file budget, and the 2,659-file selector run was interrupted during diagnosis. Exact commands and results are in `.agent-artifacts/pgf-result.md`. No production or user-facing endpoint acceptance was exercised.

## Tests

`backend/tests/unit/test_plane_leak_probe.py` covers cell and Firestore owners, routed and unrelated collections, committed/failed/partial writes, empty queries, request isolation, the disabled fast path, sanitized logs, and production override rejection. Existing read/write probe regressions also pass.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none
