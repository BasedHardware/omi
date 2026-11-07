# A2b fix round 1 result

Status: requested fixes implemented and committed locally; verification outcomes below. No whole-suite green is claimed.
Repository: BasedHardware/omi, branch `lane/pgf-a2b`. Verification date: 2026-11-07 UTC.
Implementation baseline: `a742c2a397ff`; final source frozen at `028f2d0c5f2f` (only an explicit local dictionary annotation follows the 65ad runtime/test checkpoint).
No push, PR, production access, customer data, api.omi.me call, GCP tier, or ANX contact.
The tracked `.agent-artifacts/pgf-result.md` was not changed.

## Built / review disposition

- BLOCKING legacy IDs: `82655f9c838d`. Cell reads for folders, people, action items, goals and workstreams restore IDs from document keys, including mutation-return and receipt projections. Retirement, goal focus replacement and work-intent task lookup use keys. Projections leave legacy stored payloads unchanged. Synthetic seeds no longer inject IDs; simulator projections were corrected independently. Shared regressions read/retire ID-less rows and reject misleading payload IDs.
- BLOCKING goal history timezone: `ef472a44a652`. Cell and simulator mirror `database/goals.py`'s falsy-zone / any-exception UTC fallback and `str(zone)` conversion. Shared conformance covers valid, null, invalid and empty timezones through both append and update progress.
- NON-BLOCKING import startup flake (flash 1): `738cd9e65475`. Fresh-process import test timeout is 120 seconds; assertions unchanged.
- NON-BLOCKING expand-only contract (flash 5): `738cd9e65475`. Existing migration test rejects DROP/RENAME and non-ADD-COLUMN ALTER statements after stripping comments and strings. No migration edits or checksum changes.
- NON-BLOCKING redundant stored IDs (flash 6): `738cd9e65475`. ARCHITECTURE.md explicitly documents the metadata exception to byte parity and W6's requirement to preserve legacy payloads without requiring redundant IDs.
- Additional regression fixture/projection coverage: `dcc7fca4a480`. Complete legacy workstream payloads exercise Firestore's strict wire-shaped list/update boundary; a Postgres-specific test checks cell ID projection for list/update as well. The subsequent receipt-replay correction is separately recorded below.

- Simulator related-view projection: `25ad787a76a1`. Folder conversation reads also project document keys now that synthetic seeds preserve raw payloads. The existing offset/identity regression additionally asserts the read does not insert an ID in storage.

- Required Firestore correctness extension: `ce378672a6bf`. The first required-emulator run exposed an ID-less name-match receipt replay. The Firestore adapter now restores the receipt entity key on replay, preserving the existing nonempty-ID fallback convention and leaving payloads unchanged.

- Re-audited generation fingerprint: `076a84bfac8f`. The sole changed writer digest in `backend/docs/people-generation-writers.json` is updated after the four write/generation/receipt calls were proven AST-identical and the real emulator + strict transaction contracts ran. The enforcing test and its negative mutation assertions are unchanged.
- Qualification-test timing correction: `65ad065bc328`. The cleanup-only 10 ms timeout injection now applies only to Task waits; startup/readiness coroutines keep their production budget. This fixes the observed false connect failure without changing any production STT code, cleanup deadline, or assertions.

- Type-inference correction: `028f2d0c5f2f`. The keyed people-pin projection now has an explicit `dict[str, Any]` local before `model_construct`; its values and runtime behavior are unchanged. The expanded adapter/Firestore typecheck initially found this one inference error; final check is recorded below.

## File list

- `backend/database/ARCHITECTURE.md`
- `backend/database/cells/adapters/_base.py`
- `backend/database/cells/adapters/action_items.py`
- `backend/database/cells/adapters/folders.py`
- `backend/database/cells/adapters/goals.py`
- `backend/database/cells/adapters/people.py`
- `backend/database/cells/adapters/workstreams.py`
- `backend/database/people.py`
- `backend/docs/people-generation-writers.json`
- `backend/testing/domain_fixtures.py`
- `backend/testing/domain_sim/store.py`
- `backend/tests/integration/test_domain_conformance_action_items_goals_workstreams.py`
- `backend/tests/integration/test_domain_conformance_folders_people.py`
- `backend/tests/unit/test_cells_task_workflow_migration.py`
- `backend/tests/unit/test_qualify_parakeet_route.py`

## Scope extensions taken / deviations

The shared `testing/domain_sim/store.py` reference needed the same identity and timezone corrections once the harness stopped masking missing IDs. This is necessary to satisfy the brief's every-backend conformance requirement. The same requirement exposed a real Firestore receipt-replay defect (185 passed / 1 failed in the first emulator matrix), so `backend/database/people.py` receives the minimal read-projection correction; query definitions, signatures and writes are unchanged. `database/ARCHITECTURE.md` documents the small correctness exception requested by flash item 6. The static People writer fingerprint inventory and the pure qualification-test timeout stub are additional correctness extensions needed by the observed unit failures; neither is production configuration. No edits under `.github/`, `backend/database/jobstore/`, or `backend/testing/store_fixtures.py`; no pool, schema, runtime flag or enrollment changes.

## Skipped review items / known gaps

- Luna query/index expression mismatch: deferred. This is a performance/planner concern requiring representative EXPLAIN evidence or a migration/keyset redesign, not a small correctness fix. Confirm before serving the list path.
- Flash 2, raw versus typed lock ordering: deferred to B1/B2 integration. Typed transactions lock the head early; raw writers lock documents before head flush. Require a consistent writer ordering or all enrolled-space writes through the typed path before enrollment; existing retries do not prove absence of deadlocks.
- Flash 3, live timezone source: deferred to W5. Profile ownership remains Firestore per M4/C7; a cell-only profile read cannot discover a live user's timezone without enrollment mirroring or a plane-aware source. Invalid/falsy fallback is fixed; source integration is not.
- Flash 4, naive updated_at: deferred. Exclusion versus UTC coercion requires the migration/backfill policy; the current parser requires offsets and current writers stamp aware datetimes. This lane does not decide that policy.
- No deployed or user-facing cell acceptance is claimed; these are synthetic adapter contracts.
- The unchanged `test_cross_service_deploy_contract.py` timed out twice at the required 900-second budget. Its diagnostic stack was `ast.parse -> cross_service_contract._index -> import_closure -> build_readers -> build_context`, inside the module fixture before any assertion result. Both that test and `backend/scripts/cross_service_contract.py` have zero diff from `a742c2a397ff`. No timeout was raised and no check was skipped or weakened. This remains a validation gap for the lead; it does not establish that the full backend suite is green.

## Verification commands and terminal results

All test/scanner/type/preflight processes run from this worktree through the following credential scrubber before exec (no credentials printed):

```python
import os, sys
for key in list(os.environ):
    if key.startswith('CLOUDSDK_') or key in (
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'
    ):
        os.environ.pop(key, None)
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
```

Heavy launcher (the same prefix for verify.sh, post.sh, gates.sh and final-gates.sh):

```bash
backend/.venv/bin/python /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/run.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- /opt/homebrew/bin/bash /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/final-gates.sh
```

Direct verification uses this worktree's Python 3.11 `backend/.venv`. The unmodified preflight Firestore-index guard manages its own isolated `.agent-brief/firestore-index-guard/venv-3.11.15` as prescribed by that guard; no environment/dependency configuration was changed. Every run exports:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib
export BACKEND_UNIT_FILE_BUDGET_SECONDS=900
export PYTHON="$PWD/backend/.venv/bin/python"
```

No remote Postgres DSN or allow-remote flag is set. Firebase config uses this worktree's rules/index files, loopback `127.0.0.1:10289`, UI disabled and project `demo-omi-isolated-tests`; Postgres is the fixture's disposable local pgserver. Required backends fail rather than skip. Each emulator run shut down cleanly.

### Required conformance matrix

```bash
firebase emulators:exec --only firestore --project demo-omi-isolated-tests --config /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/firebase.json 'cd backend && OMI_REQUIRE_STORE_BACKENDS=sim,emulator,postgres .venv/bin/python -m pytest -m integration -q tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py'
```

- `25ad787a76a1`: 185 passed / 1 failed / 0 skipped, 35.58 seconds. The new emulator regression exposed the legacy People receipt-replay defect; fixed in `ce378672a6bf` with assertions retained.
- `ce378672a6bf`: 186 passed / 0 failed / 0 skipped, 51.95 seconds.
- `65ad065bc328`: 186 passed / 0 failed / 0 skipped, 26.09 seconds.
- `028f2d0c5f2f`: 186 passed / 0 failed / 0 skipped, 35.07 seconds.

### Changed-file unit selector and full execution

```bash
git diff --name-only a742c2a397ff HEAD > /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/changed-files.txt
backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/changed-files.txt --output /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/selected-tests.txt --reason-output /Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/selection-reason.txt
BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/selected-tests.txt /opt/homebrew/bin/bash backend/test.sh
```

Selector: 2,677 files; `backend/database/cells/adapters/_base.py requires the full backend unit suite`. The frozen bulk source was `ce378672a6bf`. Exit 1: **2,672 successful files / 5 failed files**. Reconciled all 2,677 unique file receipts and 2,676 pytest summaries, with zero missing/unexpected files: **65,732 passed / 4 failed / 101 skipped / 2,130 deselected / 75 xfailed**, plus the timed-out file without a summary.

Failed-file dispositions:

| File under tests/unit | Bulk result | Final replay / correction |
|---|---|---|
| test_people_generation_inventory.py | 3 passed / 1 failed | 4 passed; sole audited writer fingerprint repinned in 076a84bfac8f |
| test_qualify_parakeet_route.py | 33 passed / 1 failed | 34 passed; startup timeout injection corrected in 65ad065bc328 |
| test_speaker_tag_prompts_service.py | 57 passed / 1 failed | 58 passed unchanged; short worker-start wall budget failed under bulk load |
| test_speaker_voice_matches.py | 45 passed / 1 failed | 46 passed unchanged; short worker-start wall budget failed under bulk load |
| test_cross_service_deploy_contract.py | exit 124 at 900 seconds | exit 124 again at 900 seconds; unchanged fixture, gap above |

The bulk suite's passing strict People read/write-order and generation tests ran before the fingerprint repin. Re-audit also compared all four write/generation/receipt call ASTs before/after the projection change; they were identical. Negative mutation assertions remain unchanged.

### Serialized replay and final type-only-change check

`retry-tests.txt` contains these exact seven paths, in order:

```text
tests/unit/test_people_generation_inventory.py
tests/unit/test_port_surface_parity.py
tests/unit/test_cells_task_workflow_migration.py
tests/unit/test_qualify_parakeet_route.py
tests/unit/test_speaker_tag_prompts_service.py
tests/unit/test_speaker_voice_matches.py
tests/unit/test_cross_service_deploy_contract.py
```

```bash
BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/retry-tests.txt BACKEND_PYTEST_WORKERS=1 PYTEST_ADDOPTS='-o faulthandler_timeout=120' /opt/homebrew/bin/bash backend/test.sh
```

At `65ad065bc328`: exit 1 solely for the final unchanged cross-service file's 900-second timeout. First six files: **206 passed / 0 failed / 0 skipped** (4 + 51 + 13 + 34 + 58 + 46); all seven selected file receipts reconciled.

After the explicit dictionary annotation at `028f2d0c5f2f`, `typed-tests.txt` contains only `tests/unit/test_cells_task_workflow_migration.py`:

```bash
BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/pgf-a2b-fix-r1/typed-tests.txt BACKEND_PYTEST_WORKERS=1 /opt/homebrew/bin/bash backend/test.sh
```

Result: PASS, **13 passed / 0 failed / 0 skipped**, 34.58 seconds (47-second file wall receipt). Conformance is rerun on this exact checkpoint as above; the full 2,677-file command is not claimed as rerun after the annotation or the two unit corrections.

### Source, preflight and metadata gates

```bash
"$PYTHON" backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils backend/database
(cd backend && .venv/bin/python -m pyright --pythonpath .venv/bin/python database/cells/adapters database/people.py)
OMI_PR_BODY_FILE=.agent-artifacts/pgf/a2b-fix-r1-pr-body.md make preflight
scripts/pr-preflight --metadata-only --pr-body-file .agent-artifacts/pgf/a2b-fix-r1-pr-body.md
scripts/pr-preflight --suggest
git diff a742c2a397ff --check
```

- Async scanner: PASS, 594 def + 171 async endpoints, zero selected blocking findings (five known outside fail scope).
- Expanded typecheck initially found one inference error at the new keyed Person projection; fixed in 028f2d0c5f2f. Final typecheck: PASS, **0 errors / 484 warnings**.
- Frozen `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight`: PASS, **43 checks / 0 failed**, 609.46 seconds, frozen at `028f2d0c5f2f`.
- Metadata gate: PASS, **4 checks / 0 failed**, 35.31 seconds.
- `pr-preflight --suggest`: PASS, INV-TASK-2 and Failure-Class none.
- Pinned staged-file formatter and whitespace checks: PASS.

The requested fallback is the targeted all-backend contracts and backend unit evidence above if baseline preflight/suite issues prevent a global green. No whole-suite green is claimed. Two preliminary pytest probes were cancelled while still queued for heavy admission; zero tests started, no results claimed. Only this run's verified PIDs were signalled.

## Draft PR body

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
