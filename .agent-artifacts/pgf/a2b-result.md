# A2b implementation result

Status: A2b implementation complete and committed locally. Both final repository/PR-body preflights passed all 44 checks. The historical full backend run had two failed files; both corrections pass file-isolated replays, as detailed below. No whole-suite green is claimed.

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-a2b-upstream-keep-clean`. Branch: `lane/pgf-a2b`. Base: A2a tip `c2cbe8b53c04`; stacked on A1 #24800. Local commits only; no push, PR, deployment, production access, api.omi.me calls, or GCP tier.

## What was built

- `backend/database/cells/adapters/__init__.py`: lazy public `CellSpaceStore` export; the low-level cell package still loads no domain composition or pool until explicitly requested. Conformance callers use this public entry point.
- `backend/database/cells/adapters/_base.py`: typed-adapter transaction dispatch, domain-owned result receipts and logical CAS checks. No simulator import or SDK emulation.
- `backend/database/cells/adapters/space_store.py`: explicit adapter composition through B1's registry; per-attempt identity maps; pending-write SQL overlays; one cell flush path for document/change-log writes; canonical change detection that preserves int/bool/float distinctions; partial codec normalization for related-domain task writes; native revision and mutation error mapping; task tickets held through flush and SQL commit; one post-commit task-list-version bump per changed UoW. Failed/retried attempts finish every registered fence, including when another cleanup raises.
- `backend/database/cells/adapters/{folders,people,action_items,goals,workstreams}.py`: full protocol surfaces, cross-domain task relationships, legacy document semantics, codec-before-write, mutation result replay, focus/lifecycle/history, workstream events/artifacts/checkpoints/imports, people generations and folder conversation rehoming. Bounded SQL reads for limit-bearing lists, with stable keysets and byte-order ID ties; folder keysets retain Firestore scalar ordering across null/bool/number/tagged datetime/text legacy values.
- `backend/database/cells/migrations/0002_write_fence.sql`: byte-identical B2 prerequisite, copied from the specified B2 worktree; no conflicting replacement migration.
- `backend/database/cells/migrations/0003_task_workflow_typed.sql`: expand-only generated query columns/indexes, following B2 0002. Tagged datetime extraction uses a timezone/DateStyle-fixed immutable parser; invalid legacy timestamps produce NULL. The exception handler is explicitly PARALLEL UNSAFE because Postgres forbids its subtransaction in a parallel worker. Stored-column rewrite requires an exclusive lock, explicitly before enrollment.
- `backend/testing/domain_fixtures.py`: real Postgres domain factory using the existing local discovery/migrator and a pool of two; synthetic-owner guards retained; explicit synthetic space-head enrollment; seed/read and cleanup use the cell store. All three backends are registered, with required infrastructure failing rather than silently skipping.
- `backend/tests/unit/test_port_surface_parity.py`: transaction/repository pairs for all five cell adapters plus CellSpaceStore.
- `backend/tests/unit/test_cells_task_workflow_migration.py`: numbered/expand-only schema contract and frozen checksum; fresh schema/reapply; codec timestamps; bounded lists over pending UoW changes; native replay receipts; fence-before-flush and retry cleanup; one bump per UoW; native revision-error attributes; mixed-scalar folder keysets; reserved-task no-op mutation receipts without duplicate cache bumps; scalar-type updates and codec/timestamp propagation through related-domain task patches. Redis is fixture-local/faked, preventing cached-client contamination.
- `backend/tests/support/lifecycle_writer_inventory.py`: reviewed declarations for the new cell payload builders (scope extension below).
- `backend/tests/unit/test_cell_store_conformance.py`: advance the exact migration-version expectation to 3 (scope extension below).
- `backend/tests/unit/test_executors.py`: initialize cold exception-reporting dependencies during fixture setup, preserving the existing deadlines and assertions (scope extension below).
- `backend/database/ARCHITECTURE.md`: adapter/flush/query/fence ownership and migration/admission dependencies.
- `.agent-artifacts/pgf/a2b-pr-body.md`: PR draft using the repository template headings.

Serving selection, runtime flags and production config are unchanged. CELL_STORE_MODE remains off. No edits to `cells/store.py`, `cells/feed.py`, `cells/purge.py`, `cells/__init__.py`, `jobstore/`, `.github/`, runtime env, or `testing/store_fixtures.py`. The tracked `.agent-artifacts/pgf-result.md` was not modified.

## Deviations and dependency handling

1. The explicit launch scope adds folders/people, superseding the brief's older unowned-gap exclusion. Both are implemented and tested on Postgres.
2. The own migration is 0003, reserving 0002 for B2. The migrator requires contiguous versions even for local fresh-schema tests, so the exact B2 0002 prerequisite is included byte-for-byte. B2's runtime store/purge/error files remain untouched. A temporary import overlay verified the final adapters against those exact B2 modules without editing them in this checkout.
3. The sketch casts JSON strings to timestamps, but the shared codec uses `{"$datetime": "..."}`. Direct text-to-timestamptz casts also cannot be used directly in PostgreSQL STORED generated expressions because they are not immutable. The migration reads the tagged representation through an offset-required, settings-fixed parser; schema and conformance tests exercise real Postgres.
4. Domain operations buffer edits in an attempt-local identity map, then stage only changed rows through `CellTransaction.put/delete`. Result receipts carry operation digests/results in `workflow_mutation_receipts`; their native content-free receipts are written by the same flush. Domain purge removes its native receipt metadata atomically with its result receipts so mutation IDs can be reused after purge; document/change-log writes remain on the single flush path.
5. No Firestore performance or per-UoW bump correction was made: the A2a notes are applied to the cell side only, as instructed.

## Scope extensions taken

`backend/tests/support/lifecycle_writer_inventory.py`, `backend/tests/unit/test_cell_store_conformance.py`, and `backend/tests/unit/test_executors.py` extend the A2b file list. The existing lifecycle AST guard correctly rejected the new cell payload builders. Reviewed and added only those new sites: task retirement (superseded/cancelled); goal create/delete/focus replacement/focus/lifecycle/unfocus; workstream create, draft/superseded artifact versions, accepted candidate response, and validated artifact status transitions. Existing declarations are unchanged. This is required inventory maintenance, not an assertion weakening or new allowlist bypass.

`backend/tests/unit/test_cell_store_conformance.py`: update the exact expected migration version from 1 to 3, because the expanded fresh schema correctly applies B2 0002 and A2b 0003. Both idempotent-reapply assertions are retained. The broad run exposed this stale B1 expectation; the complete cell-store file is replayed after the mechanical correction.

`backend/tests/unit/test_executors.py`: the full run timed out in the BYOK exception future; the first file-isolated replay instead timed out in the first destructive-operation exception future (25 cell-store tests passed; executor file 35 passed / 1 failed). Both retain a two-second deadline. The executor deliberately imports its gateway classifier on its first exception, and the BYOK test constructs a real SDK error with its first SDK import inside that timed future. A module-scoped setup fixture now initializes those two cold dependencies before task timing. It preserves the real classifier, the two-second deadlines and every logging/privacy assertion; no product executor code changes.

## Validation environment and reproducibility

Python: this worktree's `backend/.venv/bin/python` (3.11.15). Installed `pgserver==0.1.4` with `uv pip install --python backend/.venv/bin/python pgserver`; only this venv changed, no dependency/lock files. The fixture uses a disposable local cluster/private Unix socket. Emulator project is `demo-omi-isolated-tests`, bound to 127.0.0.1:10279; never a real customer project.

Every test/verification command runs after this scrub (saved during the run as `/tmp/a2b-run.py`):

```python
import os, sys
for key in list(os.environ):
    if key.startswith('CLOUDSDK_') or key in (
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'
    ):
        os.environ.pop(key, None)
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
```

Heavy commands use `backend/.venv/bin/python /tmp/a2b-run.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- <command>`. Backend commands below run with `cd backend`; root commands run from the repository root. Focused short Python commands use the same scrub directly. Shell commands use Homebrew Bash when preserving native Opus lookup variables.

### Terminal test outcomes

Terminal full-run evidence: 2026-11-07T03:51:21.337212+00:00. All 2,676 pytest summaries and file receipts were parsed. The full command exited 1: 2,674 files passed, 2 files failed; 65,747 tests passed, 2 failed, 104 skipped, 2,130 deselected, 75 xfailed. The stale migration assertion is corrected (25-test file replay passed). Executor cold-dependency setup is corrected (36-test file replay passed, including a managed-gate repetition). No whole-run green is claimed. Final repository and full PR-body preflights both passed: 44 checks each, 0 failures, in 1,105.24 s and 831.75 s respectively. They ran on the frozen source including the parallel-worker correction at 06938ea37f0f and the lazy public API export.

| Context | Exact command after credential scrub (heavy launcher as described above) | Result |
|---|---|---|
| backend | `export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib && BACKEND_UNIT_FILE_BUDGET_SECONDS=900 /opt/homebrew/bin/bash scripts/run-unit-ci.sh --all` | Exit 1; 2,674/2,676 files successful, 2 failed; 65,747 passed / 2 failed / 104 skipped / 2,130 deselected / 75 xfailed. Typecheck: 0 errors, 76,059 warnings. Source began at 6910f4042e78; final cell/code-inventory corrections are covered by focused final-source checks. |
| backend | `bash test-preflight.sh` (inside `scripts/run-unit-ci.sh --all`) | 17 checks passed, 9 optional warnings, 0 failures |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py` | Reserved-receipt checkpoint: 8 passed, 0 failed; later scalar/codec cases pass in the focused flush validation below |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py tests/unit/test_lifecycle_state_table_writers.py tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py` | Final flush/codec/timestamp source: 1,826 passed, 55 unavailable-emulator skips, 0 failed |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_port_surface_parity.py` | 51 passed, 0 failed |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py tests/unit/test_port_surface_parity.py` | Before final reserved-receipt case: 58 passed, 0 failed; final added cases pass in the focused flush validation below |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2b-guard-files.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=1 bash backend/test.sh` | Seven files, 2,436 passed, 1 deselected, 0 failed; file summaries: cell contracts 6, task fences 48, developer tickets 19, lifecycle inventory 1,706, surface parity 51, query contract 50, query shapes 556. New cell cases added later pass separately. |
| backend, emulator | `OMI_REQUIRE_STORE_BACKENDS=sim,emulator .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py -q` | 99 passed, 0 failed (Postgres is available and also runs) |
| backend, emulator | `OMI_REQUIRE_STORE_BACKENDS=sim,emulator,postgres .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py -q` | 99 passed, 0 failed; all three backends required |
| backend, emulator | `OMI_REQUIRE_STORE_BACKENDS=sim,emulator .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_folders_people.py -q` | 66 passed, 0 failed (includes Postgres) |
| backend, same emulator | `.venv/bin/python -m pytest -q tests/integration/test_action_items_legacy_probe_emulator.py tests/integration/test_proactivity_v2_budget_emulator.py tests/integration/test_folder_delete_concurrency_emulator.py` | 12 passed, 0 failed |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2b-extra-tests.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | Selector-only canonical memory E2E: 8 passed, 0 failed |
| backend | `.venv/bin/python -m pyright --pythonpath .venv/bin/python database/cells/adapters` | Final flush/codec helpers: 0 errors, 454 warnings |
| root | `backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils backend/database` | 0 selected blocking findings; 5 existing findings outside fail scope |
| root | `backend/.venv/bin/python backend/scripts/scan_import_time_side_effects.py` | 2,500 production files, 0 violations |
| root | `backend/.venv/bin/python backend/scripts/check_module_stub_pollution.py` | 2,860 test files, 0 violations |
| root | `backend/.venv/bin/python scripts/render_feature_flag_registry.py && backend/.venv/bin/python scripts/check_feature_flag_registry.py` | PASS; generated registry unchanged, existing advisory warnings |
| root | `make runtime-image-source-closure && make lane-backend` | 19 image contracts passed; Python 3.11 lane probe complete, no dependency install required |
| root | `backend/scripts/openapi_runner.sh scripts/export_openapi.py --app-client --write /tmp/a2b-openapi.json` | PASS |
| root | `git show origin/main:docs/api-reference/app-client-openapi.json > /tmp/a2b-openapi-base.json && backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-spec /tmp/a2b-openapi-base.json --head-spec /tmp/a2b-openapi.json && cmp /tmp/a2b-openapi-base.json /tmp/a2b-openapi.json` | PASS; byte-identical to the fetched main baseline |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cell_store_conformance.py` | After migration-version correction: 25 passed, 0 failed |
| root | `OMI_REQUIRE_STORE_BACKENDS=postgres backend/.venv/bin/python /tmp/a2b-b2-compat.py` (temporary import overlay described below) | Final source with B2 store/purge/errors at `67894e0e15cc0c9ee55d1433d8014c202772d6e9`: 120 passed, 55 unavailable-emulator skips, 0 failed |
| root | `scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/a2b-pr-body.md --metadata-only` | 4 checks passed, 0 failed; initial 28.80 s; final updated-draft metadata replay 29.52 s |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2b-executor-warm.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=1 bash backend/test.sh` (credential-scrubbed short setup check) | Executor fixture correction: 36 passed, 0 failed; 12.43 s pytest / 23 s file wall. Two-second deadlines and all assertions unchanged. Managed repetition also passed: 36 passed in 8.61 s / 15 s file wall. Both final full preflights passed all 44 checks. |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py tests/unit/test_port_surface_parity.py` | Final lazy public export: 62 passed, 0 failed; 32.79 s. Includes 11 cell contracts and 51 parity cases. |
| root | `backend/.venv/bin/python .github/scripts/check_dead_code.py --area backend` | PASS; 16 existing unreachable files at baseline/allowlist floor; no `.github` changes |
| backend | `OMI_REQUIRE_STORE_BACKENDS=postgres .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py` | Final required-Postgres parallel-safety regression replay: 12 passed, 0 failed, 0 skipped; 78.01 s. Earlier identical test selection without the required-backend env also passed 12 tests in 24.64 s. |
| root | `OMI_PR_BODY_FILE=.agent-artifacts/pgf/a2b-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | PASS: 44 checks, 0 failures; 1,105.24 s. |
| root | `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/a2b-pr-body.md` | PASS: 44 checks, 0 failures; 831.75 s. Both final preflights ran sequentially under one managed heavy admission after the queue cleared. |
| root | `scripts/pr-preflight --suggest` | PASS; INV-TASK-2 and Failure-Class: none retained |
| root | `black --line-length 120 --skip-string-normalization <changed Python files>` plus the pinned staged-file hook | PASS |

The seven-file guard manifest contains `test_cells_task_workflow_migration.py`, `test_action_item_port_fence.py`, `test_devapi_action_item_versions.py`, `test_lifecycle_state_table_writers.py`, `test_port_surface_parity.py`, `test_firestore_query_contract.py`, and `test_firestore_query_shapes.py`, each under `tests/unit/`. The selector-extra manifest contains only `testing/e2e/test_canonical_memory_pipeline.py`.

Emulator commands above were chained with `&&` inside `GOOGLE_CLOUD_PROJECT=demo-omi-isolated-tests firebase emulators:exec --only firestore --project demo-omi-isolated-tests --config /tmp/a2b-firebase.json '<commands>'`. That disposable config points at this worktree's rules/index files, binds 127.0.0.1:10279 and disables the UI. All commands passed; the emulator stopped cleanly.

Changed-file selection: `git diff --name-only origin/main...HEAD > /tmp/a2b-changed-files.txt` followed by `backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files /tmp/a2b-changed-files.txt --output /tmp/a2b-changed-tests.txt --reason-output /tmp/a2b-selection-reason.json`. It selects 2,677 files: all 2,676 files in `--all`, plus the separately passing canonical-memory E2E file.

B2 compatibility uses a disposable package overlay under `/Volumes/Ephemeral/scratch`: copy this checkout's `database/cells`, overwrite only the overlay's `store.py`, `purge.py`, `errors.py` with the specified B2 worktree's versions, prepend the overlay parent to `database.__path__` before importing pytest, and run the cell unit and both domain conformance files with `OMI_REQUIRE_STORE_BACKENDS=postgres`. The actual loaded B2 store path is printed by the wrapper. No tracked source file is changed by this test.

### Development failures and corrections

- A forced-parallel Postgres probe reproduced `InvalidTransactionState: cannot start subtransactions during a parallel operation` in the timestamp decoder's exception block. Corrected its declaration from PARALLEL SAFE to PARALLEL UNSAFE, pinned the new migration checksum and added a real forced-parallel regression. The entire final cell-contract file passed: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_cells_task_workflow_migration.py` after credential scrub, 12 passed / 0 failed / 0 skipped in 24.64 s. The fixture used disposable local Postgres; no migration was applied to production.

- First Postgres conformance: 5 failed / 105 passed / 55 emulator skips. Fixed inherited purge transaction dispatch, pending-write query visibility, and domain receipt purge isolation. Second: 110 passed / 55 emulator skips.
- First schema/fence addition: 1 failed / 114 passed / 55 skips because the test compared timestamp formatting in the connection's local timezone. It now compares UTC instants. Next: 115 passed / 55 skips.
- Initial parity-only run: 51 passed. A later combined new-cell-test/parity run exposed 2 Redis-network failures / 55 passes: the new PG tests had initialized real cached Redis clients before the hermetic driver. Fixture-local fake Redis removes that contamination. Final combined run passes.
- The first broad guard invocation shared one pytest session: 8 failed / 2,423 passed. Three failures were the correctly missing lifecycle declarations (now reviewed and added); five staged-task driver failures were shared-session Redis contamination from existing fence tests. File-isolated replay passes all seven files, with 2,436 total passes. No query guard or assertion was weakened.
- First full CI-runner attempt stopped at typecheck: 56 errors / 76,605 warnings, so no full-suite pass was claimed. Fixed public helper names, decorator/heterogeneous-payload typing, explicit domain attributes and optional values. An incorrectly invoked narrow pyright command initially selected system Python 3.14 and added unrelated stdlib diagnostics; final commands specify the worktree's Python explicitly. Final adapter typecheck has zero errors.
- A transient intermediate edit missed the new ParamSpec import, causing two collection errors. Corrected before the final tests/commit.
- Broad run later exposed the old B1 `current_version == 1` assertion (24 other cell-store cases passed). Updated only the exact expectation to 3; the whole 25-test file passed replay. The same broad run also encountered a 2-second future timeout in unchanged `test_executors.py::test_submit_with_context_logs_byok_quota_halt_without_traceback`; the corrected fixture passes both direct and managed file-isolated replays (36 tests).
- The first frozen-source `make preflight` stopped on `dead-code-ratchet` after 429.14 s: the conformance-only composition class had no production importer. Added a real lazy public export in the already authorized adapters package, migrated conformance imports to it, and added a no-pool/fresh-process import test. Focused backend ratchet and 62 public-API/parity tests pass; both final full gates also pass all 44 checks. Other uncompleted checks from that failed run are not claimed passed.
- Initial make preflight hit a runtime-image source-copy race: test-created `_segments`/`_speech_profiles` directories disappeared during copying. No source correction or safety bypass was made; final preflight is run after tests finish.

## Known gaps / integration gates

- A1 #24800 and B2 #24805 remain OPEN at the final fresh check against main `eb7d5eb2df2bb30907be8325fcdda214d3cba99f`; no conditional rebase is warranted. Re-fetch and rebase the stack when its prerequisites merge; do not integrate A2b before A2a/A1. B2 is required for live write admission, tombstones and wipe integration.
- This is conformance-only validation. There is no deployed/runtime/user-facing cell acceptance claim and no enrollment. Stored columns must be applied before enrollment. Pooler/capacity/rollout decisions remain outside A2b.
- The full command was non-green (two failed files). The final report records the corrected migration test and executor replay separately; it does not relabel that historical command as green. Both final full preflights pass all 44 checks.

## Final state and hygiene

All A2b implementation and test corrections are in small conventional local commits; source correction tip is `06938ea37f0f` (parallel safety), followed by evidence-only updates. No push or PR was made. Final boundary comparison against the A2a base shows no forbidden-path changes. B2 0002 is still byte-identical to its specified worktree. The emulator and disposable Postgres test processes exited; the final managed preflight pipeline exited 0. The owned heartbeat is stopped during final cleanup; no other lane's process was signalled. No production data, production API, GCP identity or tier was used.

## Draft PR body

The same draft is saved as `.agent-artifacts/pgf/a2b-pr-body.md`.

## What changed and why

Add conformance-only typed cell adapters for folders, people, action items, goals and workstreams, exposed through a lazy `database.cells.adapters.CellSpaceStore` entry point and composed in one space UoW over the existing cell flush. SQL applies filters, ordering, keysets and limits before returning list rows. Task tickets span flush and commit, with one post-commit cache bump per changed UoW. Canonical change detection preserves numeric/boolean storage types, and related-domain task patches pass through the shared codec with their update timestamps.

Promote doc-mode storage with expand-only generated query columns that decode tagged datetimes. Migration 0003 follows B2's byte-identical 0002 write-fence prerequisite. These migrations must land before enrollment. No serving selectors, runtime flags or production configuration change; CELL_STORE_MODE stays off.

## Product invariants affected

- INV-TASK-2: task relationships validate goals/workstreams in the same transaction; failed bodies roll back all domains.

## How it was verified

Simulator, real disposable Postgres and Firestore emulator: 165 conformance tests passed; 12 legacy emulator regressions passed. Public API/cell contract/signature checks: 62 passed; the final 12-test cell-contract file also passes after correcting parallel-worker safety in the timestamp decoder. Task/query/lifecycle guard replay: 2,436 passed. Core adapters also passed 120 tests with B2's write-fenced store, with 55 optional emulator cases skipped in that Postgres-focused run. OpenAPI is byte-identical to the fetched main baseline.

The full 2,676-file backend command exited 1 (65,747 passed / 2 failed): a stale migration-version assertion and a two-second executor dependency-initialization timeout. Both files are corrected and pass isolated replay (25 cell-store tests; 36 executor tests). No full-run green is claimed. `make preflight` and the full PR-body preflight both passed all 44 checks after the final source corrections. Exact commands and all outcomes are in `.agent-artifacts/pgf/a2b-result.md`. No production access or GCP tier was used.

## Tests

Run the shared domain suites with OMI_REQUIRE_STORE_BACKENDS=all. New `test_cells_task_workflow_migration.py` exercises a fresh schema, idempotent migration replay, SQL paging over pending UoW writes, task commit fences and native replay records. Protocol/adapter signature pairs cover all five cell adapters and CellSpaceStore. A forced-parallel Postgres regression protects the timestamp decoder exception handler. A fresh-process import test rejects pool construction and verifies the low-level package does not load domain composition until requested.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups (optional)

Stacked on A2a and A1 #24800; B2 #24805 remains the write-admission dependency. The copied 0002 migration is byte-identical to B2, avoiding migration-number/checksum conflicts. No edits to cells/store.py, feed.py, purge.py, jobstore, workflows, runtime env or testing/store_fixtures.py. The pgserver wheel was installed only in this worktree's venv, without lock changes. Required scope extensions: declare the new cell lifecycle payload sites in the existing inventory, and advance B1's exact migration-version assertion from 1 to 3; initialize the executor tests' lazy error-classification and SDK dependencies during setup while preserving their deadlines and assertions.

The following exact size declarations cover the inherited A2a diff while this stack is validated against main; remove them when A2a is the merged target base.

Line-Count-Exception: backend/database/action_items.py | 1751 -> 2183 | A2a brief requires typed repositories beside frozen module functions, with explicit commit hooks and atomic task budget checks.

Line-Count-Exception: backend/database/workstreams.py | 1443 -> 1964 | A2a brief requires typed repositories beside frozen module functions and guards for externally owned transactions.

Line-Count-Exception: backend/testing/domain_sim/store.py | 0 -> 1511 | A2a brief requires independent workflow reference adapters in the existing simulator.
