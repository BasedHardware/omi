## What changed and why

Add conformance-only typed cell adapters for folders, people, action items, goals and workstreams, exposed through a lazy `database.cells.adapters.CellSpaceStore` entry point and composed in one space UoW over the existing cell flush. SQL applies filters, ordering, keysets and limits before returning list rows. Task tickets span flush and commit, with one post-commit cache bump per changed UoW. Canonical change detection preserves numeric/boolean storage types, and related-domain task patches pass through the shared codec with their update timestamps.

Promote doc-mode storage with expand-only generated query columns that decode tagged datetimes. Migration 0003 follows B2's byte-identical 0002 write-fence prerequisite. These migrations must land before enrollment. No serving selectors, runtime flags or production configuration change; CELL_STORE_MODE stays off.

## Product invariants affected

- INV-TASK-2: task relationships validate goals/workstreams in the same transaction; failed bodies roll back all domains.

## How it was verified

Simulator, real disposable Postgres and Firestore emulator: 165 conformance tests passed; 12 legacy emulator regressions passed. Public API/cell contract/signature checks: 62 passed; the final 12-test cell-contract file also passes after correcting parallel-worker safety in the timestamp decoder. Task/query/lifecycle guard replay: 2,436 passed. Core adapters also passed 120 tests with B2's write-fenced store, with 55 optional emulator cases skipped in that Postgres-focused run. OpenAPI is byte-identical to the fetched main baseline.

The full 2,676-file backend command exited 1 (65,747 passed / 2 failed): a stale migration-version assertion and a two-second executor dependency-initialization timeout. Both files are corrected and pass isolated replay (25 cell-store tests; 36 executor tests). No full-run green is claimed. Both full preflights are being rerun after adding the public lazy export required by the dead-code ratchet; the focused backend ratchet passes. Exact commands and all outcomes are in `.agent-artifacts/pgf/a2b-result.md`. No production access or GCP tier was used.

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
