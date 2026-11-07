## What changed and why

Compose conformance-only typed cell adapters for folders, people, action items, goals and workstreams over the existing cell UoW, with expand-only query columns and shared simulator/Firestore/Postgres contracts. Restore legacy IDs from document keys without rewriting payloads, use keys for retirement and replacement, and preserve UTC goal-history fallback for falsy or invalid timezones. Firestore name-match receipt replays also retain legacy document identity. No serving selectors or configuration change; enrollment remains outside this PR.

## Product invariants affected

- INV-TASK-2: relationship validation and related domain writes share one transaction.

## How it was verified

Final-source conformance passed all 186 cases on required simulator, Firestore emulator and disposable local Postgres backends. Six focused/failed-file replays passed all 206 cases, including the corrected fingerprint and timeout fixture, strict port contracts, cell migration contracts, and unchanged speaker timing tests.

The full 2,677-file unit command exited 1: 65,732 passed / 4 failed, plus one file timed out. The corrected and timing-sensitive cases passed serialized replay; the unchanged deploy-contract fixture still timed out at 900 seconds in both bulk and isolated runs. Its diagnostic stack was parsing AST import closures. No whole-suite green is claimed. The async scanner and expanded typecheck passed (0 type errors); frozen preflight passed all 43 checks. Metadata validation passed all 4 checks. Exact commands and limitations are recorded in `.agent-artifacts/pgf/a2b-fix-r1-result.md`. No production access or GCP tier was used.

## Tests

Shared regressions read ID-less documents across all five domains, check mutation-return IDs and key-based retirement/replacement, and verify projections do not add IDs to stored legacy payloads. Goal progress history covers valid, null, empty and invalid timezones through both append and update APIs. Existing migration contracts now reject destructive DDL; the import-only guard permits 120 seconds for process startup under load.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups (optional)

Cell-native creates retain redundant IDs as a documented metadata exception to payload byte parity. Before W5 enrollment, integrate the Firestore-owned profile timezone source and settle raw/typed writer lock ordering. Confirm the list query's index plan and naive legacy timestamp policy before serving those paths. No edits under `.github/`, `backend/database/jobstore/` or `backend/testing/store_fixtures.py`.

Line-Count-Exception: backend/database/action_items.py | 1751 -> 2183 | A2a brief requires typed repositories beside frozen module functions, with explicit commit hooks and atomic task budget checks.

Line-Count-Exception: backend/database/workstreams.py | 1443 -> 1964 | A2a brief requires typed repositories beside frozen module functions and guards for externally owned transactions.

Line-Count-Exception: backend/testing/domain_sim/store.py | 0 -> 1539 | Shared legacy identity and timezone conformance requires independent simulator behavior in the existing reference adapter.
