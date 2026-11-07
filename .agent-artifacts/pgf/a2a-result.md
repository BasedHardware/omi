# A2a fix round 1 validation record

Status: all five fix-r1 requirements implemented and committed. Scoped verification and both repository preflights pass. The full backend command completed nonzero; all three failed/timed-out files passed isolated replays. No whole-run green is claimed. No push or PR.

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-a2a-upstream-keep-clean`. Branch: `lane/pgf-a2a`. Runtime/source head: `47f89cdd893`. Start head: `2c6017a3337`. GCP tier: none. No production service, API or data was accessed.

Final validation evidence: 2026-11-07T00:06:13.612683+00:00. Implementation commits: `8ebc150c732`, `07a4d80f71d`, `47f89cdd893`; evidence checkpoint `06caab68b1c`. The final source is `47f89cdd893`; subsequent commits update evidence/PR text only. All launched validation commands and the disposable emulator have terminated. Final integration check fetched `origin/main` at `ebd12975fe6b0baef217313f27ddff6d625b60b7`; A1 `73d5a4a01ccd` is still not an ancestor, so fix-r1's conditional rebase was not triggered. The frozen preflights measured source 47f89cdd893 against main 34125ccd5fbd6c47885d23abe70e9a1448b7515e. A1 must land before A2a integration.

## Built in this round

- Outbox-only claims acquire no task ticket and preserve the cache version. The task-update branch begins its fence after all writes are staged, immediately before commit, and releases it on every exit across SDK retries.
- Transaction-bound task ID and conversation bulk deletes reject before staging with `ActionItemTransactionLimitError` when their writes plus the existing SDK transaction buffer exceed 500. Standalone paths retain 499-write chunking.
- Account-wipe action_items recursive purge holds a task writer ticket through the entire purge. Writer census also found the historical task migration and soft-cap unlock operator; both now fence their actual commits, including every owner in a migration batch.
- Raw externally owned repositories raise a programming error rather than dropping task effects/fences. Internally owned task mutation/CAS runners explicitly collect and drain their own effects.
- Regression tests pin goal detach/workstream resolve-candidate, resolve-intent, import task fences and `_task_write` UoW context forwarding. Operator CLI help is tested from an unrelated working directory.

## Fix-round file list

- `.agent-artifacts/pgf/a2a-result.md`
- `.agent-artifacts/pgf/a2a-pr-body.md`
- `backend/database/action_items.py`
- `backend/database/candidate_integration_outbox.py`
- `backend/database/goals.py`
- `backend/database/ports/__init__.py`
- `backend/database/ports/action_items.py`
- `backend/database/user_data_deletion.py`
- `backend/database/workstreams.py`
- `backend/docs/people-generation-writers.json`
- `backend/migrations/004_migrate_action_items_to_collection.py`
- `backend/scripts/unlock_soft_cap_locked.py`
- `backend/tests/unit/test_action_item_port_fence.py`

## Scope extensions taken

- `backend/database/user_data_deletion.py`: explicitly required by fix-r1 account-wipe ruling.
- `backend/migrations/004_migrate_action_items_to_collection.py` and `backend/scripts/unlock_soft_cap_locked.py`: direct task batch commits discovered by the mandated full writer census. Multi-owner tickets and task-only unlock fencing preserve their existing transaction/write shape. No operator was run against data.
- `backend/docs/people-generation-writers.json`: re-pin only `purge_user_subtree` after reviewing its new task-only context manager. The People branch and final generation erase are unchanged. The other 79 fingerprints are byte-identical. The lead's four previously approved pins remain intact.

## Complete task writer census

Audited all backend Python files for literal/constant collection references, document paths, task reference helpers and generic/recursive deletion and batch/transaction commit surfaces. The report distinguishes direct task writers from callers of already fenced entry points.

| Direct writer | Ticket boundary |
|---|---|
| `database/action_items.py` create/create-batch/update/restore/delete/delete-batch/conversation-delete/retire/sync-request/sync-update, typed mutation/CAS and purge | Repo commit hook in SpaceTx, explicit standalone document/batch/transaction fence; owned effects drain after commit |
| `database/action_items.py::unlock_all_action_items` | Fence around locked-content query unlock |
| `database/candidates.py::resolve_task_candidate` | Fence around full contention-retry runner; task writes through bound repository |
| `database/action_item_refresh.py::reconcile` | SpaceStore registered task fence |
| `database/action_item_refresh.py::claim_delivery` | Fence around owned transaction |
| `database/action_item_completion_backfill.py::backfill_completion_page` | Fence around each CAS update |
| `database/staged_tasks.py::restore_legacy_conversation_items` | Fence around atomic recovery batch commit |
| `database/candidate_integration_outbox.py::claim_candidate_integration_dispatch` | Begin only after the task-marker and outbox updates are staged; finish after runner exits |
| `database/review_changes.py::record_agent_change` / `set_undone` | Conditional fence around ledger commit for task edits/inverses |
| `database/chat_edits.py::apply_update` / `restore` | Conditional task fence around contention-retry runner |
| `database/goals.py::FirestoreGoals.transition_lifecycle_document` | Standalone task_writes detach fence or UoW forwarded task fence |
| `database/workstreams.py::FirestoreWorkstreams.resolve_candidate_document` / `resolve_intent_document` / `import_links_documents` and atomic UoW import | Standalone task_writes fence or UoW forwarded task fence |
| `database/user_data_deletion.py::purge_user_subtree` called by users.delete_user_data | Fence around action_items recursive subcollection purge |
| `migrations/004_migrate_action_items_to_collection.py::process_conversation_batch` | Per-batch helper fences every staged owner via ExitStack, including retry and final partial batch |
| `scripts/unlock_soft_cap_locked.py::unlock_collection` | Task-only fence around each full/partial batch commit |

Indirect writers retain the above authority: messaging undo -> chat_edits.restore; extraction, task-sync, router, MCP and recovery paths -> action_items module entry points; review cleanup/inverse services -> review_changes. `restore_channel_write` is covered by the action-item repository.

Read-only direct consumers checked: action_item_dedup, action_item_sync, task_recommendations, conversation_task_links, locked_content's recoverability probe, entity_pages, review_queries, dream_history, dream_prescan, dream_state_pass, summary_tasks and vector backfill migration 007. Conversation structured.action_items is a different embedded field. `database/tasks.py` writes a top-level tasks collection. Messaging recursive erasure deletes channel identities/sessions. Conversation recursive erasure deletes conversation descendants. Generic `_client.delete_collection_recursive` reaches the task collection through the now fenced account wipe; other call sites target other collections.

The explicitly excluded local/offline `utils/task_intelligence/chat_first_e2e_fixture.py::prepare_fixture` still seeds/deletes a synthetic task in its isolated fixture batch; unchanged by the brief. `advance_fixture_clock` writes intent/state only. Emulator cleanup scripts recursively erase isolated demo owners but do not seed task documents; no serving/operator task writer remains uncovered in the census.

## Known gaps / PR notes

- A1 tip `73d5a4a01ccd` is not an ancestor of final fetched main `ebd12975fe6b0baef217313f27ddff6d625b60b7`. The conditional rebase did not apply. Do not integrate A2a ahead of A1.
- Port task fence is sync-only; future async task writers must explicitly fence their commits.
- A1's added `.github` dead-code entry and A2a's removal are net-zero versus main. No `.github` edit in this fix round.
- FirestoreActionItems.list() still reads the whole collection. Bounded reads are a gate before A2b/W5 serving migration.
- Redundant action-item post-commit bumps per UoW are deferred to A2b.
- The full backend command is non-green despite all isolated failed-file replays passing. Its 18-worker default run had one prefetch assertion, seven local Opus-loader assertions and one cross-service file timeout. No unrelated product/test assertion was weakened to force a green run.
- Folders/people cell adapters remain an unowned follow-up from the A2 brief (A1 supplied Firestore adapters only); assign separately before serving those domains on cells.
- Cell adapters, typed migrations, routing/enrollment and production deployment are outside A2a. No changes under jobstore, runtime env, testing/store_fixtures.py or .github in this round.

## Validation

All commands remove GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable, SERVICE_ACCOUNT_JSON and FIREBASE_AUTH_CREDENTIALS_PATH using `/tmp/a2a-run.py` before execution. Heavy commands use `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --`. Backend Python is this worktree's `backend/.venv/bin/python` (3.11.15). The full backend runner itself executes test-preflight, typecheck, and file-isolated test.sh.

Terminal evidence: 2026-11-07T00:06:13.612683+00:00. The full runner launched exactly 2,675 files and exited 1 after reporting three failed files. All 2,674 completed pytest summaries were parsed: 65,636 passed, 8 failed, 151 skipped, 2,130 deselected, 75 xfailed; the remaining file hit the 900-second timeout. File-level outcome: 2,672 successful / 3 failed. All three failed files subsequently passed isolated replays, with 112 total passed and 3 optional historical-replay skips. The changed-file selector requests 2,676 files: the full set plus `testing/e2e/test_canonical_memory_pipeline.py`, which passed all 8 tests separately. No validation remains in flight. The owned heartbeat was stopped by PID after all long runs terminated; no server, emulator or watcher remains from this task.

| Context | Exact command after credential scrub / heavy launcher | Result |
|---|---|---|
| backend | `PYTHON=.venv/bin/python bash test-preflight.sh` (inside the full CI runner) | 17 checks passed, 9 optional warnings, 0 failed |
| backend | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib BACKEND_UNIT_FILE_BUDGET_SECONDS=900 scripts/run-unit-ci.sh --all` | Exit 1; 2,672/2,675 files successful, 3 failed/timed out; 65,636 passed / 8 failed tests and one file timeout. Typecheck 0 errors, 75,630 warnings. Full runner invokes file-isolated `bash test.sh` for 2,675 files. Started at source 07a4d80f71d; final CLI/audit correction 47f89cdd893 landed during the broad run; focused final-source checks below cover those changes. |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_action_item_port_fence.py tests/unit/test_devapi_action_item_versions.py` | Final source: 67 passed, 0 failed; 16.41 s |
| backend, disposable emulator | `OMI_REQUIRE_STORE_BACKENDS=sim,emulator .venv/bin/python -m pytest -m integration tests/integration/test_domain_conformance_action_items_goals_workstreams.py tests/integration/test_domain_conformance_folders_people.py -q` | 110 passed, 0 failed; 4.74 s |
| backend, same emulator | `.venv/bin/python -m pytest -q tests/integration/test_action_items_legacy_probe_emulator.py tests/integration/test_proactivity_v2_budget_emulator.py tests/integration/test_folder_delete_concurrency_emulator.py` | 12 passed, 0 failed; 3.74 s; emulator stopped cleanly |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_lifecycle_state_table_writers.py tests/unit/test_port_surface_parity.py tests/unit/test_firestore_query_contract.py tests/unit/test_firestore_query_shapes.py` | 2,344 passed, 0 failed (includes slow pinned-body check); 469.46 s |
| backend | `.venv/bin/python -m pytest -q tests/unit/test_people_generation_inventory.py` | 4 passed, 0 failed; 4.67 s |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-r1-extra-tests.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | Changed-selector extra `testing/e2e/test_canonical_memory_pipeline.py`: 8 passed, 0 failed; 57.23 s |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-r1-replay-worker.txt BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | Previously failing prefetch file: 18 passed, 0 failed; 21.62 s |
| root | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/opus/lib:/opt/homebrew/lib:/usr/local/lib:/usr/lib BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-r1-opus-replay.txt BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | Empty capture file: 68 passed, 0 failed; 6.36 s (path assigned through `env` argument after the heavy launcher, Homebrew Bash invoked directly) |
| root | `BACKEND_UNIT_TEST_FILE_LIST=/tmp/a2a-r1-cross-service-replay.txt BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 bash backend/test.sh` | Cross-service deployment file: 26 passed, 3 optional historical-replay cases skipped, 0 failed; 489.62 s pytest / 552 s file wall |
| root | `OMI_PR_BODY_FILE=.agent-artifacts/pgf/a2a-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | Frozen source 47f89cdd893: 44 checks passed, 0 failed; 780.17 s |
| root | `BACKEND_UNIT_FILE_BUDGET_SECONDS=900 scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/a2a-pr-body.md` | 44 checks passed, 0 failed; 765.90 s |
| root | `scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/a2a-pr-body.md --metadata-only` | Final draft: 4 checks passed, 0 failed; 33.98 s; merge-base unchanged at f4929a909841 after final main fetch |
| root | `scripts/pr-preflight --suggest` | PASS; INV-TASK-2 citation and Failure-Class: none retained |
| root | `backend/.venv/bin/python scripts/render_feature_flag_registry.py && backend/.venv/bin/python scripts/check_feature_flag_registry.py` | PASS; generated registry unchanged; existing advisory warnings |
| root | `make runtime-image-source-closure && make lane-backend` | 19 registered image contracts passed; lane environment probe complete, no install needed |
| root | `backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils backend/database` | 0 selected blocking findings; 5 existing findings outside scope |
| root | `backend/.venv/bin/python backend/scripts/scan_import_time_side_effects.py` | 2,493 production files; 0 violations |
| root | `backend/.venv/bin/python backend/scripts/check_module_stub_pollution.py` | 2,859 test files; 0 violations |
| root | `backend/scripts/openapi_runner.sh scripts/export_openapi.py --app-client --write /tmp/a2a-r1-openapi.json` | PASS |
| root | `git show origin/main:docs/api-reference/app-client-openapi.json > /tmp/a2a-r1-openapi-base.json && backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-spec /tmp/a2a-r1-openapi-base.json --head-spec /tmp/a2a-r1-openapi.json && cmp /tmp/a2a-r1-openapi-base.json /tmp/a2a-r1-openapi.json` | PASS; byte-identical to main 34125ccd5fbd6c47885d23abe70e9a1448b7515e |

The emulator command was wrapped in `GOOGLE_CLOUD_PROJECT=demo-omi-isolated-tests firebase emulators:exec --only firestore --project demo-omi-isolated-tests --config /tmp/a2a-firebase.json '<conformance command> && <legacy command>'`. The disposable config binds 127.0.0.1:10279 and references this worktree's rules/index files. No emulator is left running. Postgres commands/migrations are A2b only and were not run.

Formatting ran through `black --line-length 120 --skip-string-normalization` and the pinned staged-file hook; no formatting diff remains.

### Reproducible credential scrub and manifests

```python
import os, sys
for key in list(os.environ):
    if key.startswith('CLOUDSDK_') or key in (
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'
    ):
        os.environ.pop(key, None)
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
```

The launcher is run with `backend/.venv/bin/python /tmp/a2a-run.py <heavy launcher> <command>`. Initial focused commands used `omi-heavy run --wait 3600 --`; remaining commands used `--wait 7200`. Backend-context commands use `bash -c 'cd backend && <command>'`; root-context commands run directly. Replay manifests each contain exactly their named backend-relative file. The extra manifest contains only `testing/e2e/test_canonical_memory_pipeline.py`.

### Development / non-green attempts

- The same focused fence command first hit two test-collection import errors (model modules corrected), then 1 failed / 62 passed when the new raw-transaction guard exposed an internally owned mutation runner's effect collector. Both owned mutation/CAS runners now explicitly opt into their drained collector; focused tests passed 66/66, then 67/67 after adding direct-script help coverage.
- Initial preflight completed all 44 check bodies but rejected three files edited while it was running (490.01 s; exit 2). This was my concurrent editing, not a check that mutates files. The final frozen-source make preflight and independent PR-body command above both passed.
- Broad run observed `test_batch_pipeline_worker_io.py::test_prefetch_is_bounded_by_count[2]` decoded peak 3 versus limit 2; 17 other tests passed. The unchanged file passed all 18 on isolated replay. No root cause or whole-run green is inferred from that replay.
- Broad run observed 7 Opus-loader failures in `test_empty_capture_recovery.py`. A credential-scrubbed subprocess probe with the same DYLD path finds `/opt/homebrew/opt/opus/lib/libopus.dylib` in direct Python, but returns None through `/usr/bin/env bash`; the protected launcher drops the lookup environment. Replaying with the path assigned after the protected launcher and direct Homebrew Bash passes all 68. The installed library and repository code were unchanged.


- Broad run additionally timed out `test_cross_service_deploy_contract.py` after 900 seconds. The unchanged file passed its one-worker replay (26 passed / 3 optional skips); the timeout remains recorded in the broad run's nonzero outcome.

## Draft PR body

The same draft is saved separately as `a2a-pr-body.md`.

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
