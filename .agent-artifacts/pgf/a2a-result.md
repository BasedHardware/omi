# A2a implementation and validation record

Status: implementation and scoped verification complete; full backend unit contract remains in flight. This is not the final completion receipt.

Evidence recorded at 2026-11-06T21:48:53.820433+00:00. Repository: BasedHardware/omi. Branch: `lane/pgf-a2a`. Source revision: `78446f1214f`. Base: A1 tip `73d5a4a01ccd225083e998c99157e98e5b4c524c` (PR #24800, still open at the latest live check). No push or PR creation was performed. GCP tier: none; no production service or data was used.

## Built

- Pure typed action-item, goal and workstream ports, storage entities and domain errors. Point reads, controls and writes compose in `SpaceStore`; standalone aggregate read views and purges are repository operations.
- Firestore adapters beside the original module entry points. All 121 module function parameter lists are unchanged, and every existing module read function body is unchanged. Write bodies now live in concrete adapter document methods; module Dream-dirty decorators remain in place.
- Per-attempt commit fences and post-commit callbacks in `FirestoreSpaceStore`. Tickets begin immediately before an owned UoW commits, span retries, and finish on every exit, including another fence's cleanup failure; effects run only for the final committed attempt. Standalone writers retain their prior transaction/retry shapes and explicitly fence the commits they own.
- Task writer migration for candidates, refresh, completion backfill, legacy staged recovery, integration outbox, review journal/inverse, chat edits, unlock and workflow resolution/import. The audit also covered goal lifecycle detaches and refresh delivery claims, which write task documents.
- Revision CAS and mutation receipts on typed task/goal operations; portable list and sync keysets; per-domain purges including owned receipts. The sync cursor preserves the Firestore timestamp precision and lookahead row.
- An independent simulator, synthetic sim/emulator harness coverage, protocol signature/purity checks, commit-ticket tests and workflow conformance. No cell adapters or migrations were implemented.
- Re-homed query owners, fixed literal body pins, retained module caller recipes and audited lifecycle writer scopes. The existing version-cache flag's mechanism wording was regenerated; no new flag or deployment configuration was added. The dormant SpaceStore allowlist entry was removed after refresh became its product caller.

## File list

- `A .agent-artifacts/pgf/a2a-result.md`
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
- `M backend/tests/unit/test_goals_extract_progress_advice_and_patch_nulls.py`
- `M backend/tests/unit/test_port_surface_parity.py`
- `M config/feature-flags.yaml`

Implementation/evidence commits:

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
- `0c3269fea3c` test(database): checkpoint A2a implementation and validation evidence
- `78446f1214f` feat(database): keep goal reader imports independent of task writers

## Caller and fixture audit

The current grep census found 228 importing/caller/fixture files and 102 matching lines in the specifically named witness/router/DumpSite/plugin-structure files. Parameter, return-annotation and decorator parity was checked against A1's exact tip for all module functions: action_items 41, goals 40, workstreams 40; zero mismatches. The only module function bodies that changed are the prescribed writers, task relationship seam and unlock fence. Transaction-only dependencies load inside the repository methods that need them; the original goal/action-item reader import surface remains usable with narrow clients. Module return contracts do not change, so dict mocks and released response fixtures require no retyping. The exact-set `test_client_processing_trust_boundary.py` DumpSite registry was separately updated for one renamed goal writer and six new typed-entity serialization sites; each was reviewed as task/goal data, not Conversation content. The assertion and its negative proofs remain intact. `test_llm_provider_plugin_structure.py` retains A1's FolderEntity fixture unchanged.

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

The constructor-seam audit also checked every `_goal_ref` mock and `_get_db` override. One goal-update test now supplies its fake client through `_get_db`; no assertion changed. Goal-only cold-import fixtures and the desktop migration fixture remain unchanged and pass.

## Interpretations and deviations

- The original Redis ticket API does not poison on a rejected Firestore commit with a confirmed Redis ticket. Such a failure invalidates the prior cache version, matching the removed SDK wrapper's `finally`. Poison is reserved for an uncertain Redis begin/finish reply. Tests distinguish these cases. Treating every retry's `committed=False` as poison would permanently disable the cache after ordinary contention, contrary to the brief's requirement to preserve the existing Lua/ticket semantics.
- The typed UoW import operation pre-reads all links before staging writes. The retained module import preserves its existing resumable per-link transactions and its request limit. The UoW form is atomic and subject to the backend transaction bounds; it adds no arbitrary 200-link restriction.
- The local emulator uses a disposable configuration on loopback port 10279 and project `demo-omi-isolated-tests`. Product Firebase configuration is unchanged.
- Concrete adapter document methods are public because retained module functions and external Firestore coordinators call them. Typed consumers see the narrower protocol surfaces; no retired API or compatibility adapter is introduced.

## Validation

All test commands use this worktree's Python 3.11.15 and remove `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*` variable, `SERVICE_ACCOUNT_JSON`, and `FIREBASE_AUTH_CREDENTIALS_PATH` before execution. Heavy commands run through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- ...` (the final broad retry permits a 7200-second queue wait). The exact scrub launcher `/tmp/a2a-run.py` is reproducible from:

```python
import os, sys
for key in list(os.environ):
    if key.startswith('CLOUDSDK_') or key in (
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'
    ):
        os.environ.pop(key, None)
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
```

The root prefix is `backend/.venv/bin/python /tmp/a2a-run.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- <command>`. Backend-context commands run through `bash -c 'cd backend && <command>'`. Lightweight collection, resolver, metadata and smoke checks use the same scrub launcher without acquiring a heavy slot.

### Completed scoped proofs on final source

| Context | Exact command after the launcher | Pass/fail result |
|---|---|---|
| backend | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-goal-final-files.txt BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash test.sh` | 29/29 files successful; 2,831 tests passed, 1 marked-slow test deselected; 0 failures |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_firestore_query_shapes.py::test_digest_pinned_entries_unchanged` | 1 passed, 9 warnings, 0 failed; 10.97 seconds |
| backend | `OMI_REQUIRE_STORE_BACKENDS=sim,emulator .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py -q` | 110 passed, 0 failed; 19.61 seconds |
| backend | `.venv/bin/python -m pytest -q tests/integration/test_action_items_legacy_probe_emulator.py tests/integration/test_proactivity_v2_budget_emulator.py tests/integration/test_folder_delete_concurrency_emulator.py` | 12 passed, 1 warning, 0 failed; 37.94 seconds |
| backend | `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python database/action_items.py database/goals.py database/workstreams.py database/space_store.py database/ports` | 0 errors, 806 warnings |
| root | `OMI_PR_BODY_FILE=/tmp/a2a-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | 44 checks passed, 0 failed; 754.73 seconds |
| root | `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 scripts/pr-preflight --pr-body-file /tmp/a2a-pr-body.md` | 44 checks passed, 0 failed; 359.87 seconds |
| root | `backend/scripts/openapi_runner.sh scripts/export_openapi.py --app-client --write /tmp/a2a-openapi-final.json` | PASS |
| root | `backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-spec /tmp/a2-openapi-base.json --head-spec /tmp/a2a-openapi-final.json` | PASS |
| root | `cmp /tmp/a2-openapi-base.json /tmp/a2a-openapi-final.json` | PASS; byte-identical; baseline is `git show origin/main:docs/api-reference/app-client-openapi.json` |
| root | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-opus-files.txt BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | `test_empty_capture_recovery.py`: 68 passed, 1 warning, 0 failed; 11.45 seconds |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-executor-files.txt BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | `test_executors.py`: 36 passed, 0 failed; 3.43 seconds |

The 29-file focused manifest is reproduced exactly below (backend-relative paths):

```text
tests/unit/test_action_item_port_fence.py
tests/unit/test_candidate_lifecycle.py
tests/unit/test_client_processing_trust_boundary.py
tests/unit/test_desktop_migration.py
tests/unit/test_devapi_action_item_versions.py
tests/unit/test_firestore_query_contract.py
tests/unit/test_firestore_query_shapes.py
tests/unit/test_firestore_runtime_witnesses.py
tests/unit/test_goal_context_null_message_text.py
tests/unit/test_goal_extraction_batch.py
tests/unit/test_goal_get_by_id.py
tests/unit/test_goal_history_local_day.py
tests/unit/test_goal_progress_events_skip_malformed.py
tests/unit/test_goal_progress_history_atomic.py
tests/unit/test_goal_source_compatibility.py
tests/unit/test_goal_storage_coerce_guard.py
tests/unit/test_goal_update_alias_validation_422.py
tests/unit/test_goals_advice_arg_and_clear_metric.py
tests/unit/test_goals_any_active_goal.py
tests/unit/test_goals_defensive.py
tests/unit/test_goals_extract_progress_advice_and_patch_nulls.py
tests/unit/test_goals_id_fallback.py
tests/unit/test_goals_reject_non_finite.py
tests/unit/test_goals_response_int_guard.py
tests/unit/test_goals_sort_missing_created_at.py
tests/unit/test_goals_wrapped_firmware_hardening.py
tests/unit/test_lifecycle_state_table_writers.py
tests/unit/test_llm_provider_plugin_structure.py
tests/unit/test_port_surface_parity.py
```

The conformance and legacy emulator commands execute in one disposable emulator session using:

```bash
export GOOGLE_CLOUD_PROJECT=demo-omi-isolated-tests
firebase emulators:exec --only firestore --project demo-omi-isolated-tests --config /tmp/a2a-firebase.json   'OMI_REQUIRE_STORE_BACKENDS=sim,emulator .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py -q && .venv/bin/python -m pytest -q tests/integration/test_action_items_legacy_probe_emulator.py tests/integration/test_proactivity_v2_budget_emulator.py tests/integration/test_folder_delete_concurrency_emulator.py'
```

The temporary configuration references this worktree's rules/index files, binds Firestore to `127.0.0.1:10279`, disables UI, and enables single-project mode. The emulator exited cleanly after every session. The Opus repair is process-only: the library was installed already, but Python's default search returned `None`; no host setting or dependency installation changed.

### Other required completed commands

| Context | Command | Result |
|---|---|---|
| backend | `PYTHON=.venv/bin/python bash test-preflight.sh` | 17 required checks passed, 9 optional warnings, 0 failed |
| backend | `.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils database` | 0 selected high-network-I/O blockers; 5 existing findings of other kinds |
| backend | `.venv/bin/python scripts/scan_import_time_side_effects.py` | 2,493 production files, 0 violations; final preflight also passes this guard |
| backend | `.venv/bin/python scripts/check_module_stub_pollution.py` | 2,859 test files, 0 violations; final preflight also passes this guard |
| root | `backend/.venv/bin/python scripts/render_feature_flag_registry.py && backend/.venv/bin/python scripts/check_feature_flag_registry.py` | PASS; generated doc consistent; existing warnings retained |
| root | `make runtime-image-source-closure` | 19 image contracts passed; final preflights repeat the proof |
| root | `make lane-backend` | PASS; worktree-local environment complete |
| root | `scripts/pr-preflight --suggest` | PASS; final draft cites INV-TASK-2 and declares Failure-Class: none |
| root | `scripts/pr-preflight --pr-body-file /tmp/a2a-pr-body.md --metadata-only` | 4 checks passed; full unqualified commands above also passed |

Every implementation commit passed the pinned staged Black formatter. A whole-change formatter check passed 29 files before the final goal fixture/import adjustment; those two changed files also passed the same formatter. A final 30-file check is pending before handoff.

### Full contract still in flight

Root command: `BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/scripts/run-unit-ci.sh --all`. It includes `test-preflight.sh` (17 required passes), full-tree pyright (0 errors / 75,627 warnings), and `test.sh` over all 2,675 selected files. The command started before the corrective commits, so its initial failures remain in its log even after passing isolated reruns.

The changed-file selector additionally selects `testing/e2e/test_canonical_memory_pipeline.py`; the explicit isolated `test.sh` run for that file passed 8 tests with 17 warnings in 84.81 seconds. Thus the union covers all 2,676 changed-selector files. No selected file is intentionally omitted.

The following initial full-run failures have passing reruns (a subsequent People audit-pin mismatch is described below): candidate lifecycle (35 failed / 45 passed initially; 80 passed on rerun), desktop migration (1 collection error initially; 114 passed), goal ID fallback (11 fixture errors; 11 passed), goal sorting (5 fixture errors; 5 passed), goal null-patch update (1 failed / 2 passed; 3 passed), empty capture recovery (7 native-library failures; 68 passed with the process library path), and executors (1 known two-second future timeout; all 36 passed alone). Final counts and any additional failures will be recorded when the run terminates, followed by a replay of its final failed-file list.

### Corrected development failures and command corrections

- Initial conformance: 8 failed / 86 passed; after fixes, successive expanded suites passed 94, 96, 104 and finally 110 cases.
- Initial fence suite: 1 failed / 34 passed because the review-journal fake did not execute its writer callback. Corrected fixture and expanded suites passed 36, 38 and finally 40 cases; current focused batch includes all 40.
- Registry/lifecycle iterations exposed moved owners, body pins, Redis fixture isolation and sync-page ownership. Intermediate results included 2 failed / 1,695 passed; 1 failed / 92 passed / 115 setup errors; 1 failed / 16 passed; and 1 failed / 90 passed. The completed combined guard suite passed 2,369 before the final import repairs; the final focused suite and explicit digest check repeat the relevant proofs on current source.
- Initial affected-domain run: 31 failed / 60 passed / 16 deselected; corrected bound SDK callback handling, circular import assumptions and refresh Redis fixture yielded 72 passes. Current scoped verification is broader.
- Initial full-contract typecheck had 91 errors and ran no unit tests. Corrected typed adapter access and transaction seams produced a passing full-tree typecheck and passing final modified-boundary checks.
- An unqualified environment preflight chose system Python (4 failed / 5 passed / 17 warnings); explicit `PYTHON=.venv/bin/python` passed all 17 required checks.
- Initial root preflights exposed query recipe failures, then direct wire-model construction in new port input parsing. New input mappings now use the approved `parse_payload_strict` boundary. Neither guard nor baseline changed.
- The first metadata-only validation missed INV-TASK-2 (3 of 4 passed); the corrected draft passes all four and both full preflight commands.
- Two heavy commands exceeded a 900-second admission wait without executing tests. Later commands permit longer queue waits. Superseded validation trees were stopped only by their verified owned PIDs/process groups before source corrections; no other agent's work was stopped.
- One early bare PR-preflight invocation duplicated the full lane and was cancelled. The required unqualified invocation was subsequently run to completion and is green. An initial wrong OpenAPI checker path was corrected; both compatibility and byte comparison now pass on final source.

No assertion was weakened, no test was skipped to hide a failure, and no workflow or guard was modified.

## Active validation checkpoint

Recorded at 2026-11-06T21:48:53.820433+00:00. Code is at `78446f1214f`; all scoped proofs above are complete. Only the full backend run and its final failed-file replay remain. Its PID is `98653`, log `/tmp/a2a-unit-all-final.log`, tool waiter `26576`. The heartbeat remains armed and is touched during monitoring. This section will be replaced by the terminal receipt before handoff.

## Approval required: shared People writer audit metadata

The full run found `test_people_generation_inventory.py` failing 1 test / passing 3 tests. Its golden inventory detects whole-function body changes in four shared writers that A2a wraps with task-only fences:

- `backend/database/chat_edits.py:apply_update`
- `backend/database/chat_edits.py:restore`
- `backend/database/review_changes.py:record_agent_change`
- `backend/database/review_changes.py:set_undone`

The concrete proposed change is only four hash values in `backend/docs/people-generation-writers.json`. No People code, generation bump, guard, negative proof or inventory entry changes. An AST comparison against the A1 base proves each complete function is identical after removing only the new conditional task-fence/nullcontext wrapper. Every inner People writer fingerprint is already unchanged. The strict People-generation suite passed in the full run, and A1's People emulator conformance passed in the latest 110-case matrix. A candidate copy of the four-hash update produces an empty inventory delta.

This JSON file is outside the brief's section-2 edit list. The user's instruction to stay strictly inside those boundaries requires explicit scope authorization before applying it. The proposed patch is prepared but has not been applied:

```diff
--- a/backend/docs/people-generation-writers.json
+++ b/backend/docs/people-generation-writers.json
@@ -1,8 +1,8 @@
 {
   "backend/database/_client.py:delete_collection_recursive": "020f43fc0e4d148051db3469545adc5b04a13653c4daa3a0acf57f3501f6f0b9",
-  "backend/database/chat_edits.py:apply_update": "f2f307cfbf62e2659abf3e553ec2de1558795a82300b1b197291f56daab58c22",
+  "backend/database/chat_edits.py:apply_update": "bca47670489842cd09a545553630f2587a39c3ac8776ec9642d186af797857c7",
   "backend/database/chat_edits.py:apply_update.apply": "171d40fbe346a445bbc179bf6457c61921c8c8fa434574e26c8cd0e3838e5c05",
-  "backend/database/chat_edits.py:restore": "3d29685851e3593a39ab72464329655b39b8eeb546b067897ebb384ad4fadeb8",
+  "backend/database/chat_edits.py:restore": "176e0486e5f7c21a3cc105b41cd3e5c369b59817d579ca029898dd12525a2856",
   "backend/database/chat_edits.py:restore.apply": "5fdf32961bb04b56021e0565a3657205cc2fd2baad47e78e8dc578900f5814e9",
   "backend/database/notes_identity.py:stage_notes_identity": "afe1b3e1fa7752d35fe15630d66d05a727194cb27031f952b787171b3fdc9d13",
   "backend/database/people.py:FirestorePeople.__init__": "79d88b21d261b62849fa84089fcb3c84156b6b0c54cc5f4576db7599ffc941cd",
@@ -26,10 +26,10 @@
   "backend/database/recurring_voices.py:learn.commit": "ee2305e7552f7fbdc3046cd5f2e0aa512c4455ebe4ae73e00f87c608d9d83c54",
   "backend/database/review_changes.py:merge_review_entities": "b18b815d852db49a460ad9464be99f3aca9bbd36f21df30bf1331924b3abf84a",
   "backend/database/review_changes.py:merge_review_entities.ensure_nodes": "c2760571ee024aef8ff58335773e79b33249203f967f03ed92fcb83975658407",
-  "backend/database/review_changes.py:record_agent_change": "a0a1717e5cfb3045adb4d3b6e2d390ca9026d539b3d1d4cc8510c7051567deaf",
+  "backend/database/review_changes.py:record_agent_change": "9a437dcb0254a24edf0e4ead842d0876517096c57b84aeea480fab68200fef2b",
   "backend/database/review_changes.py:record_agent_change.build": "7801046e76b83b8ba368de09517c3a19cbb7ce7bc512263ac1e7fb8f899e50c6",
   "backend/database/review_changes.py:record_agent_change.build.write": "297319e3fda808b05b1538cff02d187bc7f67cf989b065df660d49fad6b83780",
-  "backend/database/review_changes.py:set_undone": "2cbd8a4c361ebcefd77afc4823754c3efe3c31b86d73f014328f3a709955500a",
+  "backend/database/review_changes.py:set_undone": "c8beb648f329d57e37041816f13f751333a4dfc6e5b2f67bea203ac01f78c969",
   "backend/database/review_changes.py:set_undone.build": "cf730f7d22c4e7b25e80acefba5598f760181fd0d56e4bf0814b7aade1198088",
   "backend/database/review_changes.py:set_undone.build.write": "4b4b1e9d555005735d19ed3f72483672aa65744c5bece0e02467bd85d4b196ec",
   "backend/database/speaker_assignment_effects.py:persist_assignment_effects": "4c47a1ea63c563c148fe884fac4be7dfa4839d5127a02a09cedf9626c1223951",
```

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

Scoped verification is green: 2,831 tests across 29 isolated files, the explicit slow body-digest check, 110 sim/emulator conformance cases, 12 legacy emulator regressions, modified-boundary pyright with zero errors, and both 44-check preflight commands. OpenAPI is byte-identical to origin/main. The full 2,675-file backend run is still in progress; its final counts and failure replay will be recorded before handoff. Exact commands and outputs are in `.agent-artifacts/pgf/a2a-result.md`.

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
