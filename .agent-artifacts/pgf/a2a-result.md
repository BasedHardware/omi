# A2a implementation and validation record

Status: validation in progress; this is not a completion receipt.

Repository: BasedHardware/omi. Branch: `lane/pgf-a2a`. Implementation base: A1 tip `73d5a4a01ccd225083e998c99157e98e5b4c524c` (PR #24800). No push or PR creation is authorized. No GCP tier was used; no production service or data was accessed.

## Built

- Pure typed action-item, goal and workstream ports, storage entities and domain errors. Point reads, controls and writes compose in `SpaceStore`; standalone aggregate read views and purges are repository operations.
- Firestore adapters beside the original module entry points. All 121 module function parameter lists are unchanged, and every existing module read function body is unchanged. Write bodies now live in concrete adapter document methods; module Dream-dirty decorators remain in place.
- Per-attempt commit fences and post-commit callbacks in `FirestoreSpaceStore`. Tickets begin immediately before an owned UoW commits, span retries, and finish on every exit, including another fence's cleanup failure; effects run only for the final committed attempt. Standalone writers retain their prior transaction/retry shapes and explicitly fence the commits they own.
- Task writer migration for candidates, refresh, completion backfill, legacy staged recovery, integration outbox, review journal/inverse, chat edits, unlock and workflow resolution/import. The audit also covered goal lifecycle detaches and refresh delivery claims, which write task documents.
- Revision CAS and mutation receipts on typed task/goal operations; portable list and sync keysets; per-domain purges including owned receipts. The sync cursor preserves the Firestore timestamp precision and lookahead row.
- An independent simulator, synthetic sim/emulator harness coverage, protocol signature/purity checks, commit-ticket tests and workflow conformance. No cell adapters or migrations were implemented.
- Re-homed query owners, fixed literal body pins, retained module caller recipes and audited lifecycle writer scopes. The existing version-cache flag's mechanism wording was regenerated; no new flag or deployment configuration was added. The dormant SpaceStore allowlist entry was removed after refresh became its product caller.

## File list

- `A .agent-artifacts/pgf/a2a-result.md` (this evidence record)
- `M .github/scripts/dead_code/backend.allowlist.json`
- `M backend/database/ARCHITECTURE.md`
- `M backend/database/_client.py`
- `M backend/database/action_item_completion_backfill.py`
- `A backend/database/action_item_fence.py`
- `M backend/database/action_item_refresh.py`
- `D backend/database/action_item_write_fence.py`
- `M backend/database/action_items.py`
- `M backend/database/candidate_integration_outbox.py`
- `M backend/database/candidates.py`
- `M backend/database/chat_edits.py`
- `M backend/database/goals.py`
- `M backend/database/ports/__init__.py`
- `A backend/database/ports/action_items.py`
- `M backend/database/ports/base.py`
- `A backend/database/ports/goals.py`
- `A backend/database/ports/workstreams.py`
- `M backend/database/review_changes.py`
- `M backend/database/space_store.py`
- `M backend/database/staged_tasks.py`
- `M backend/database/workstreams.py`
- `M backend/docs/feature-flag-registry.md`
- `M backend/testing/domain_fixtures.py`
- `M backend/testing/domain_sim/store.py`
- `A backend/tests/integration/test_domain_conformance_action_items_goals_workstreams.py`
- `M backend/tests/support/firestore_query_driver_registry.py`
- `M backend/tests/support/lifecycle_writer_inventory.py`
- `A backend/tests/unit/test_action_item_port_fence.py`
- `M backend/tests/unit/test_action_item_refresh.py`
- `M backend/tests/unit/test_candidate_lifecycle.py`
- `M backend/tests/unit/test_client_processing_trust_boundary.py`
- `M backend/tests/unit/test_devapi_action_item_versions.py`
- `M backend/tests/unit/test_port_surface_parity.py`
- `M config/feature-flags.yaml`

Implementation commits:

- `b7b501ad58c` feat(database): define task workflow ports and explicit commit fences
- `47358b05431` feat(database): port task workflow writers and move task commit fencing
- `7c037339989` test(database): prove workflow and task fence conformance on sim and firestore
- `04abbe10e64` test(database): register workflow query delegation and isolate ticket redis
- `ba37956f236` feat(database): finalize typed workflow adapter boundaries and sync cursors
- `bdd20ad1bfa` test(database): cover reserved workflow identities and purge isolation
- `e10f4fcd6ad` test(database): complete task batch and refresh fence coverage
- `3c2b01ce26b` test(database): verify workflow domain rollback through the space unit of work
- `cc4a227f649` test(database): preserve the workflow import request contract
- `e76dc2d43f0` feat(database): validate workflow port inputs through the read boundary
- `d4a2699224d` feat(database): finish every commit fence after cleanup failures
- `79d2403cc5e` test(database): repin workflow entity serialization at the trust boundary
- `99b7ec2eed5` feat(database): retain goal identity at the typed point-read boundary
- `3c76364d91e` feat(database): load workflow transaction dependencies at their call sites

## Caller and fixture audit

The current grep census found 228 importing/caller/fixture files and 102 matching lines in the specifically named witness/router/DumpSite/plugin-structure files. Parameter, return-annotation and decorator parity was checked against A1's exact tip for all module functions: action_items 41, goals 40, workstreams 40; zero mismatches. The only module bodies that changed are the prescribed writers, task relationship seam and unlock fence. Module return contracts do not change, so dict mocks and released response fixtures require no retyping. The exact-set `test_client_processing_trust_boundary.py` DumpSite registry was separately updated for one renamed goal writer and six new typed-entity serialization sites; each was reviewed as task/goal data, not Conversation content. The assertion and its negative proofs remain intact. `test_llm_provider_plugin_structure.py` retains A1's FolderEntity fixture unchanged.

Read-only raw collection consumers were checked in action_item_dedup, action_item_sync, task_recommendations, locked_content's probe, entity_pages, review, dream_prescan, dream_state_pass and summary_tasks. The Chat-first E2E fixture does write a task document, but its admission gate only permits isolated local/offline accounts. It remains unchanged as the brief explicitly directs; it is not an additional serving writer. No scope extension is required for the listed production writer coverage.

## Writer scope migration

The moved lifecycle payloads retain their keys and values; only their owning scopes change. The static inventory was re-reviewed and re-pinned to these concrete methods.

| Retained module entry point | Adapter body |
|---|---|
| `action_items.create_action_item` | `FirestoreActionItems.create_document` |
| `action_items.create_action_items_batch` | `FirestoreActionItems.create_documents` |
| `action_items.update_action_item` | `FirestoreActionItems.update_document` |
| `action_items.restore_channel_write` | `FirestoreActionItems.restore_channel_document` |
| `action_items.batch_update_action_items` | `FirestoreActionItems.update_documents` |
| `action_items.delete_action_item` | `FirestoreActionItems.delete_document` |
| `action_items.delete_action_items_batch` | `FirestoreActionItems.delete_documents` |
| `action_items.delete_action_items_for_conversation` | `FirestoreActionItems.delete_conversation_documents` |
| `action_items.retire_action_items_for_conversation` | `FirestoreActionItems.retire_conversation_documents` |
| `action_items.batch_set_sync_requested` | `FirestoreActionItems.request_sync_documents` |
| `action_items.batch_sync_update_action_items` | `FirestoreActionItems.sync_update_documents` |
| `goals.create_goal` | `FirestoreGoals.create_document` |
| `goals.create_goal_idempotent` | `FirestoreGoals.create_idempotent_document` |
| `goals.update_goal` | `FirestoreGoals.update_document` |
| `goals.focus_goal` | `FirestoreGoals.focus_document` |
| `goals.unfocus_goal` | `FirestoreGoals.unfocus_document` |
| `goals.transition_goal_lifecycle` | `FirestoreGoals.transition_lifecycle_document` |
| `goals._append_goal_progress_event` | `FirestoreGoals.append_progress_document` |
| `goals.update_goal_progress` | `FirestoreGoals.update_progress_document` |
| `goals.delete_goal` | `FirestoreGoals.delete_document` |
| `workstreams.update_workstream` | `FirestoreWorkstreams.update_document` |
| `workstreams.append_workstream_event` | `FirestoreWorkstreams.append_event_document` |
| `workstreams.create_artifact_descriptor` | `FirestoreWorkstreams.create_artifact_document` |
| `workstreams.transition_artifact_status` | `FirestoreWorkstreams.transition_artifact_document` |
| `workstreams.upsert_continuation_checkpoint` | `FirestoreWorkstreams.upsert_checkpoint_document` |
| `workstreams.resolve_workstream_candidate` | `FirestoreWorkstreams.resolve_candidate_document` |
| `workstreams.resolve_work_intent` | `FirestoreWorkstreams.resolve_intent_document` |
| `workstreams.import_task_goal_links` | `FirestoreWorkstreams.import_links_documents` |

## Interpretations and deviations

- The original Redis ticket API does not poison on a rejected Firestore commit with a confirmed Redis ticket. Such a failure invalidates the prior cache version, matching the removed SDK wrapper's `finally`. Poison is reserved for an uncertain Redis begin/finish reply. Tests distinguish these cases. Treating every retry's `committed=False` as poison would permanently disable the cache after ordinary contention, contrary to the brief's requirement to preserve the existing Lua/ticket semantics.
- The typed UoW import operation pre-reads all links before staging writes. The retained module import preserves its existing resumable per-link transactions and its request limit. The UoW form is atomic and subject to the backend transaction bounds; it adds no arbitrary 200-link restriction.
- The local emulator uses a disposable configuration on loopback port 10279 and project `demo-omi-isolated-tests`. Product Firebase configuration is unchanged.
- Concrete adapter document methods are public because retained module functions and external Firestore coordinators call them. Typed consumers see the narrower protocol surfaces; no retired API or compatibility adapter is introduced.

## Validation

Every test process is launched after removing `GOOGLE_APPLICATION_CREDENTIALS`, all `CLOUDSDK_*` variables, `SERVICE_ACCOUNT_JSON` and `FIREBASE_AUTH_CREDENTIALS_PATH`. Python is this worktree's `backend/.venv` (3.11.15). Heavy commands use `/Users/dazheng/workspace/omi/bin/omi-heavy`. Full unit runs use four file-isolated workers and a 900-second per-file wall budget.

All commands below use the credential-scrubbing launcher. From the repository root it is `backend/.venv/bin/python /tmp/a2a-run.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- <command>`; commands marked backend run through `bash -c 'cd backend && <command>'`. `/tmp/a2a-run.py` contains exactly:

```python
import os, sys
for key in list(os.environ):
    if key.startswith('CLOUDSDK_') or key in (
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'
    ):
        os.environ.pop(key, None)
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
```

### Completed final validation

| Context | Exact command after the launcher | Result |
|---|---|---|
| backend | `PYTHON=.venv/bin/python bash test-preflight.sh` | 17 passed, 9 optional warnings, 0 failed |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_lifecycle_state_table_writers.py tests/unit/test_port_surface_parity.py tests/unit/test_firestore_query_contract.py tests/unit/test_firestore_query_shapes.py tests/unit/test_firestore_runtime_witnesses.py` | 2,369 passed, 9 warnings; zero serving query debt |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_action_item_refresh.py tests/unit/test_workstream_core.py tests/unit/test_goal_progress_history_atomic.py` | 72 passed, 9 warnings |
| backend | `FIRESTORE_EMULATOR_HOST=127.0.0.1:10279 PYTHONPATH=. .venv/bin/python -m pytest -q tests/integration/test_action_items_legacy_probe_emulator.py tests/integration/test_proactivity_v2_budget_emulator.py tests/integration/test_folder_delete_concurrency_emulator.py` | 12 passed, 1 warning; local emulator only |
| backend | `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python database/action_items.py database/goals.py database/workstreams.py database/space_store.py database/ports` | 0 errors, 806 warnings on final source; full-tree typecheck also passed with 0 errors |
| backend | `.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils database` | 0 selected high-network-I/O blockers; 5 existing findings of other kinds |
| backend | `.venv/bin/python scripts/scan_import_time_side_effects.py` | 2,493 production files, 0 violations |
| backend | `.venv/bin/python scripts/check_module_stub_pollution.py` | 2,859 test files, 0 violations |
| root | `backend/.venv/bin/python scripts/render_feature_flag_registry.py && backend/.venv/bin/python scripts/check_feature_flag_registry.py` | PASS; generated documentation consistent; existing registry warnings retained |
| root | `backend/scripts/openapi_runner.sh scripts/export_openapi.py --app-client --write /tmp/a2-openapi.json` | PASS |
| root | `backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-spec /tmp/a2-openapi-base.json --head-spec /tmp/a2-openapi.json` | PASS; baseline is `git show origin/main:docs/api-reference/app-client-openapi.json` |
| root | `cmp /tmp/a2-openapi-base.json /tmp/a2-openapi.json` | PASS; byte-identical |
| root | `make runtime-image-source-closure` | 19 image contracts passed |
| root | `make lane-backend` | PASS; complete worktree-local Python environment |
| root | `scripts/pr-preflight --suggest` | PASS; suggestions reviewed; INV-TASK-2 applies to candidate acceptance; no semantic fix class |
| root | `scripts/backend-python-format --check backend/database/_client.py backend/database/action_item_completion_backfill.py backend/database/action_item_fence.py backend/database/action_item_refresh.py backend/database/action_items.py backend/database/candidate_integration_outbox.py backend/database/candidates.py backend/database/chat_edits.py backend/database/goals.py backend/database/ports/__init__.py backend/database/ports/action_items.py backend/database/ports/base.py backend/database/ports/goals.py backend/database/ports/workstreams.py backend/database/review_changes.py backend/database/space_store.py backend/database/staged_tasks.py backend/database/workstreams.py backend/testing/domain_fixtures.py backend/testing/domain_sim/store.py backend/tests/integration/test_domain_conformance_action_items_goals_workstreams.py backend/tests/support/firestore_query_driver_registry.py backend/tests/support/lifecycle_writer_inventory.py backend/tests/unit/test_action_item_port_fence.py backend/tests/unit/test_action_item_refresh.py backend/tests/unit/test_client_processing_trust_boundary.py backend/tests/unit/test_devapi_action_item_versions.py backend/tests/unit/test_port_surface_parity.py` | 28 files unchanged on final source; PASS |

### Latest validation and outstanding gates

- Root: `env BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/scripts/run-unit-ci.sh --all` (includes `test-preflight.sh`, full pyright and `test.sh` with all 2,675 selected files). Preflight passed (17 required checks); full-tree pyright passed with 0 errors and 75,627 warnings; all 2,675 selected files are now executing.
- The pre-cleanup-extension fence suite passed 38 in 18.52 seconds. The two new cleanup/retry regressions passed (`.venv/bin/python -m pytest -q tests/unit/test_action_item_port_fence.py -k failing_cleanup`: 2 passed, 19 deselected in 8.63 seconds; a lightweight direct scrubbed run). The full expanded suite passed 40 tests in 14.65 seconds through the heavy gate.
- Backend: `firebase emulators:exec --only firestore --project demo-omi-isolated-tests --config /tmp/a2a-firebase.json "OMI_REQUIRE_STORE_BACKENDS=sim,emulator GOOGLE_CLOUD_PROJECT=demo-omi-isolated-tests .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py -q"` (110 passed in 16.86 seconds on final source). Temporary configuration names this worktree's rules/index files, binds Firestore to `127.0.0.1:10279`, disables UI and enables single-project mode. The most recent completed suite before the two import-limit and four cleanup-failure cases passed 104/104.
- Root local preflight passed all 44 checks in 587.56 seconds before the final DumpSite-only fixture adjustment. After the DumpSite fixture adjustment, the required local preflight passed all 44 checks in 383.10 seconds and unqualified CI-lane PR preflight passed all 44 in 636.33 seconds. A subsequent candidate-lifecycle regression exposed a typed goal point-read assumption, corrected in `99b7ec2eed5`; the complete candidate lifecycle rerun passed 80/80 in 11.85 seconds after that repair; conformance passed 110 in 15.21 seconds, legacy emulator regressions passed 12 in 9.96 seconds, focused pyright had 0 errors / 806 warnings, local preflight passed 44 in 425.48 seconds, and CI-lane preflight passed 44 in 603.81 seconds. Final heavy gate job: two named fixture files via `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-final-fixtures.txt BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash test.sh`, then `OMI_PR_BODY_FILE=/tmp/a2a-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight`, then unqualified `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 scripts/pr-preflight --pr-body-file /tmp/a2a-pr-body.md`. The list contains `tests/unit/test_client_processing_trust_boundary.py` (55 passed, 9 warnings in 28.91 seconds) and `tests/unit/test_llm_provider_plugin_structure.py` (7 passed in 4.35 seconds); both passed through the isolated runner before the gates.
- Completed: root `scripts/pr-preflight --pr-body-file /tmp/a2a-pr-body.md --metadata-only` passed all 4 checks in 24.48 seconds. This lightweight metadata validation ran without the heavy gate after its unstarted queue waiter was cancelled; the full local preflight remains gated separately.

The completed final heavy regression job ran the changed-selector-only hermetic E2E file through `test.sh`, then the fence suite (40 passed), emulator matrix (110 passed) and focused pyright (0 errors, 806 warnings) sequentially, stopping on the first failure; it exited 0. The E2E file passed 8 tests with 17 warnings in 84.81 seconds. The changed-file selector chooses 2,676 files because `_client.py` requires the full suite and adds `testing/e2e/test_canonical_memory_pipeline.py`; `--all` chooses 2,675. Their union is covered by the full contract plus `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-extra-unit-files.txt BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash test.sh` (the list contains only that E2E path). The selector comparison initially asserted an exact subset and exposed this extra file; no selected file is being skipped. Preflight and conformance waiters that had not started were cancelled before the final cleanup code changed; neither executed tests or consumed a heavy slot.

Latest source repair: the full unit run found 35 failed / 45 passed in `test_candidate_lifecycle.py`, all failing because the narrow snapshot fixture lacks `snapshot.id`. The typed goal point read now uses its already-known lookup ID, preserving the same `goal_id` alias default and lenient fields; existing module readers and the shared strict fixture remain unchanged. The candidate fixture also supplies fake Redis for explicit tickets. The isolated `test.sh` rerun passed all 80 cases in 11.85 seconds on repaired source (17-second file wall). A lightweight direct smoke also passed 1 case / 79 deselected in 12.70 seconds. The same heavy job continues through the 110-case conformance matrix, 12 emulator regressions, focused pyright, required `make preflight`, and unqualified `scripts/pr-preflight` sequentially.

Subsequent import-only repair (`3c76364d91e`): the full run found one collection error in `test_desktop_migration.py` because newly eager workflow imports pulled A1 folder transaction helpers into `action_items` imports. The three adapters now load those helpers only in their typed transaction methods, and task relationship validation loads the related domains only when a link is supplied. The unrelated legacy import surface no longer requires the additional client stub API. The unchanged desktop fixture collects all 114 tests. A heavy job is rerunning desktop migration, candidate lifecycle, protocol parity and both named fixture suites, followed by conformance, emulator regressions, focused typecheck, local preflight and full PR preflight. OpenAPI is being freshly exported and byte-compared after the import-graph repair.

Native test environment: seven `test_empty_capture_recovery.py` cases failed because `ctypes.util.find_library('opus')` returned `None`, despite `/opt/homebrew/opt/opus/lib/libopus.dylib` already being installed. A test-process-only `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib` resolves the library and imports `opuslib`. The failed file is queued through the unchanged `test.sh` runner with that environment. No host configuration, dependency installation, audio source or audio assertion changed.

### Corrected intermediate failures

- Initial conformance: 8 failed / 86 passed; after fixes 94 passed, then 96 passed, then 104 passed as coverage expanded.
- Initial fence suite: 1 failed / 34 passed (review-journal fake commit did not execute its supplied writer); corrected fixture yielded 36 passed before two new real refresh-commit cases were added.
- Lifecycle/query/parity runs exposed moved-owner and digest registrations, a Redis fixture isolation issue and a newly discovered sync-page owner. These were corrected without assertion weakening; the final combined 2,369-test suite passed. Intermediate combined results included 2 failed / 1,695 passed; 1 failed / 92 passed / 115 setup errors; 1 failed / 16 passed; and 1 failed / 90 passed.
- Initial affected-domain run: 31 failed / 60 passed / 16 deselected, exposing circular import assumptions, bound SDK callback unwrapping and a refresh Redis fixture; corrected focused run passed 72.
- Initial `run-unit-ci.sh --all` failed typecheck with 91 errors before executing unit tests. Typed adapter access and transaction seams were corrected; focused pyright passed with 0 errors. A fresh full contract is in flight.
- An unqualified `bash test-preflight.sh` selected the system Python and had 4 failed / 5 passed / 17 warnings. Setting `PYTHON=.venv/bin/python` passed all 17 required checks.
- Initial `make preflight` exposed query owner/fixture failures; the next run reached the read-boundary ratchet and rejected nine new direct wire-model constructions in port input parsing. These inputs now use `parse_payload_strict`; the read-boundary ratchet passes without a baseline or guard edit.
- Two heavy commands exceeded the gate's 900-second queue wait before any tests ran. Final jobs use a 3,600-second queue wait; no capacity was added and no other agent's processes were stopped.
- One accidental bare `scripts/pr-preflight --pr-body-file ...` invocation began a duplicate full CI-lane run; its owned process group was stopped and the supported `--metadata-only` command replaced it. The required local `make preflight` remains mandatory.
- The first metadata-only check passed 3 of 4 gates and found the missing INV-TASK-2 declaration on `candidates.py`; the draft now cites that invariant and explains the unchanged explicit-gesture admission.
- One OpenAPI check invocation used the wrong root-relative script path and did not run; the corrected backend script and byte comparison both passed.

No assertion was weakened. No workflow or test guard was modified.

## Active validation checkpoint

This checkpoint is not a completion receipt. Source revision: `3c76364d91e`. Recorded at 2026-11-06T20:37:44.681301+00:00.

- Full backend contract: PID `98653`, log `/tmp/a2a-unit-all-final.log`, tool waiter `26576`. The initial candidate failures have an 80/80 passing rerun; the desktop cold-import issue has a passing 114-test collection and awaits its full rerun. Native Opus failures have a verified process-only library-path repair and await rerun.
- Final import/conformance/type/preflight chain: log `/tmp/a2a-import-final.log`, waiter `18579`.
- Fresh OpenAPI export/compatibility/byte comparison: log `/tmp/a2a-openapi-final.log`, waiter `15445`.
- Opus-dependent failed-file rerun: log `/tmp/a2a-opus-rerun.log`, waiter `22349`.
- Heartbeat is armed and touched during monitoring. No production access or publication is authorized.

## Known gaps and ownership

- A2b cell adapters, typed cell migration and Postgres registration/conformance are intentionally out of scope.
- Folders/people cell adapters remain the unowned follow-up identified by the brief. Their Firestore behavior and `bump_people_generation` are unchanged.
- Account-wipe registry wiring and serving plane routing remain B2's work.
- Nonfunctional references to the retired SDK fence module remain in `action_item_versions.py`'s docstring and the write-probe frame exclusion list. Those files are outside the brief's edit boundary; there is no remaining installer or import of the removed module.
- The explicitly excluded local/offline E2E fixture does not acquire task tickets. Its isolated fixture-only cache behavior is outside A2a's serving writer contract.

## Draft PR body

## What changed and why

Add typed action-item, goal and workstream repository ports and Firestore adapters while retaining existing module function signatures and dict/wire-model results. Move Redis task-writer tickets from the SDK patch into explicit per-space commit hooks and standalone commit boundaries, including goal lifecycle detaches and refresh delivery claims.

A2a only: cell adapters and migrations belong to A2b. No new feature flags or routing changes.

## Product invariants affected

- INV-TASK-2: candidate acceptance keeps its explicit user-gesture gate; task and relationship writes remain in its existing transaction.

## How it was verified

Validation is in progress. Final commands, counts and limits are recorded in `.agent-artifacts/pgf/a2a-result.md` before handoff.

## Tests

Adds sim/emulator workflow conformance, protocol/adapter signature parity, and explicit commit-ticket parity. Existing module readers remain unchanged; moved query owners and lifecycle scopes are re-registered.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups (optional)

Remove the dormant SpaceStore allowlist entry now that refresh uses the product UoW.

Line-Count-Exception: backend/database/action_items.py | 1751 -> 2165 | A2a brief requires typed repositories beside frozen module functions and independent workflow reference adapters in the existing simulator.

Line-Count-Exception: backend/database/workstreams.py | 1443 -> 1960 | A2a brief requires typed repositories beside frozen module functions and independent workflow reference adapters in the existing simulator.

Line-Count-Exception: backend/testing/domain_sim/store.py | 0 -> 1511 | A2a brief requires typed repositories beside frozen module functions and independent workflow reference adapters in the existing simulator.
