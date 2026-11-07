## What changed and why

Add conformance-only typed cell adapters for folders, people, action items, goals and workstreams, composed in one space UoW over the existing cell flush. SQL applies filters, ordering, keysets and limits before returning list rows. Task tickets span flush and commit, with one post-commit cache bump per changed UoW. Canonical change detection preserves numeric/boolean storage types, and related-domain task patches pass through the shared codec with their update timestamps.

Promote doc-mode storage with expand-only generated query columns that decode tagged datetimes. Migration 0003 follows B2's byte-identical 0002 write-fence prerequisite. These migrations must land before enrollment. No serving selectors, runtime flags or production configuration change; CELL_STORE_MODE stays off.

## Product invariants affected

- INV-TASK-2: task relationships validate goals/workstreams in the same transaction; failed bodies roll back all domains.

## How it was verified

Real disposable Postgres, Firestore emulator and simulator: 165 conformance tests passed. Legacy emulator regressions: 12 passed. Signature parity: 51 passed. Additional local Postgres tests cover migration application/reapplication, codec timestamps, bounded list materialization, native replay receipts (including reserved-ID no-ops), scalar types, related-domain task codecs/timestamps, fence ordering, retry cleanup and one cache bump per UoW.

Full backend and repository gates are being run; final counts and exact credential-scrubbed commands will be recorded in `.agent-artifacts/pgf/a2b-result.md`. No production access or GCP tier was used.

## Tests

Run the shared domain suites with OMI_REQUIRE_STORE_BACKENDS=all. New `test_cells_task_workflow_migration.py` exercises a fresh schema, idempotent migration replay, SQL paging over pending UoW writes, task commit fences and native replay records. Protocol/adapter signature pairs cover all five cell adapters and CellSpaceStore.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups (optional)

Stacked on A2a and A1 #24800; B2 #24805 remains the write-admission dependency. The copied 0002 migration is byte-identical to B2, avoiding migration-number/checksum conflicts. No edits to cells/store.py, feed.py, purge.py, jobstore, workflows, runtime env or testing/store_fixtures.py. The pgserver wheel was installed only in this worktree's venv, without lock changes. Required scope extensions: declare the new cell lifecycle payload sites in the existing inventory, and advance B1's exact migration-version assertion from 1 to 3.

The following exact size declarations cover the inherited A2a diff while this stack is validated against main; remove them when A2a is the merged target base.

Line-Count-Exception: backend/database/action_items.py | 1751 -> 2183 | A2a brief requires typed repositories beside frozen module functions, with explicit commit hooks and atomic task budget checks.

Line-Count-Exception: backend/database/workstreams.py | 1443 -> 1964 | A2a brief requires typed repositories beside frozen module functions and guards for externally owned transactions.

Line-Count-Exception: backend/testing/domain_sim/store.py | 0 -> 1511 | A2a brief requires independent workflow reference adapters in the existing simulator.
