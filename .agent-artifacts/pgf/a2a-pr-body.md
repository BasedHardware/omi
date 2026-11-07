## What changed and why

Add typed action-item, goal and workstream ports and Firestore adapters while retaining existing module signatures and dict/wire results. Move task writer tickets into explicit unit-of-work commit hooks and standalone writers, including account erasure and operator scripts. Outbox-only claims retain their cache version; atomic bulk deletes reject before staging when the transaction would exceed 500 writes.

A2a only: cell adapters and migrations follow in A2b. No routing, deployment or flag changes.

## Product invariants affected

- INV-TASK-2: candidate acceptance retains its user-gesture gate and atomic task/relationship writes.

## How it was verified

Credential-scrubbed backend Python 3.11; no production access or GCP tier. Focused task fences: 67 passed; sim/emulator conformance: 110 passed; legacy emulator regressions: 12 passed; workflow/query/lifecycle guards: 2,344 passed; People inventory: 4 passed; selector E2E: 8 passed. OpenAPI is byte-identical to the measured main baseline. Both 44-check repository preflights passed on frozen source.

The full 2,675-file backend run exited 1: 2,672 files passed, 3 failed/timed out (65,636 tests passed, 8 failed, one file timed out). All three files passed isolated replays: prefetch 18 passed; Opus-dependent empty capture 68 passed after restoring the installed native-library lookup path; cross-service deployment audit 26 passed and 3 optional historical replays skipped. No whole-run green is claimed. Exact commands, outcomes and integration baseline are in `.agent-artifacts/pgf/a2a-result.md`.

## Tests

Regression coverage checks outbox-only claims versus task writes at commit, wipe purge tickets, transaction bulk limits including other-domain writes, standalone chunking, raw external transaction errors, goal detach and workstream resolve/import fences, and UoW task commit-context forwarding. Operator tests cover multi-owner migration batches and task unlocks.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups (optional)

The port fence is synchronous; future async task writers must fence their own commits. The A1 dead-code allowlist addition and A2a removal are net-zero versus main; this fix round makes no `.github/` edits. FirestoreActionItems.list() still reads the whole collection and must be bounded before A2b/W5 serving migration. Redundant post-commit bumps within one UoW are deferred to A2b.

Scope extensions: fence the historical task migration and soft-cap operator unlock after the complete writer census found their direct batch commits.

Line-Count-Exception: backend/database/action_items.py | 1751 -> 2183 | A2a brief requires typed repositories beside frozen module functions, with explicit commit hooks and atomic task budget checks.

Line-Count-Exception: backend/database/workstreams.py | 1443 -> 1964 | A2a brief requires typed repositories beside frozen module functions and guards for externally owned transactions.

Line-Count-Exception: backend/testing/domain_sim/store.py | 0 -> 1511 | A2a brief requires independent workflow reference adapters in the existing simulator.
