# C2 round 2 implementation result

Status: implementation and corrective focused gates are green. Full selection continuation and final frozen preflight remain pending.
Updated: 2026-11-06T22:12:58.996826+00:00
Repository: BasedHardware/omi. Branch: lane/pgf-c2.
Base after the required fetch/rebase: 4b1c40b5ef03242b82013a64c1dc941728715bab.
Implementation checkpoint: 3d475d15e424bbe91514c920a96c67e42a3020d0.
GCP tier: none. No production/API/customer-data access, push, PR, deploy, or flag expansion.

## What was built

- Single transcript pointer-or-inline codec, typed read outcomes, request/context memo, upload-before-reference writes, and post-commit revision-checked swaps.
- Cold-pointer transaction preloads for processing, review, speaker/voice publication, episodes, live transcript updates, translation, sync assignment, final-pass promotion, finalization admission, privacy scrubs, and empty-recording cleanup. Cosmetic terminal helpers locally set the memo-only guard even when their parent uses the SDK directly; cold pointers preserve the existing conservative title/keep behavior without lake IO.
- Bounded retries: 32 distinct active preloads plus three content-change retries, at most 36 outer attempts. Versions read by the current attempt are retained for legacy undo; superseded unused versions are evicted.
- Deleted-blob results are filtered from list and MCP collections. Sync candidates/canonicals are checked at load before selection. Transport/key outages abort decisions; absent/shredded retain each domain's refusal policy.
- Existing branch C1 review hardening is retained: deletion/key tombstones, encrypted envelope bounds, consent stamps, and authority checks. Pusher and batch worker include KMS; batch lock adds only google-cloud-kms==3.6.0, with no existing version changed or removed.
- Hermetic cold-pointer, refusal, no-IO, retry-budget, historical-version, reader-surface, and codec regressions; listen/pusher change note.

## File list

- `.github/scripts/dead_code/backend.allowlist.json`
- `backend/database/_client.py`
- `backend/database/conversation_finalization_jobs.py`
- `backend/database/conversation_terminal_title.py`
- `backend/database/conversations.py`
- `backend/database/episode_attach_memo.py`
- `backend/database/episode_timeline.py`
- `backend/database/episodes.py`
- `backend/database/helpers.py`
- `backend/database/owner_confirmation.py`
- `backend/database/recording_sessions.py`
- `backend/database/recurring_voice_privacy.py`
- `backend/database/review_changes.py`
- `backend/database/review_overlay_merge.py`
- `backend/database/review_transcript_changes.py`
- `backend/database/smart_merge.py`
- `backend/database/speaker_assignment_effects.py`
- `backend/database/speaker_auto_enroll.py`
- `backend/database/speaker_learning_jobs.py`
- `backend/database/speaker_profile_authority.py`
- `backend/database/speaker_resolution_updates.py`
- `backend/database/sync_assignment.py`
- `backend/database/transcript_pointer.py`
- `backend/database/users.py`
- `backend/diarizer/pylock.batch-pipeline.toml`
- `backend/diarizer/requirements-batch-pipeline.txt`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-06-transcript-lake-offload.md`
- `backend/docs/people-generation-writers.json`
- `backend/docs/runbooks/people-scan-reuse.md`
- `backend/pusher/pylock.toml`
- `backend/pusher/requirements.txt`
- `backend/tests/integration/test_recurring_voice_privacy_firestore.py`
- `backend/tests/support/dream_firestore.py`
- `backend/tests/support/firestore_query_driver_registry.py`
- `backend/tests/unit/memory_import_isolation.py`
- `backend/tests/unit/test_conversation_archive_filter_contract.py`
- `backend/tests/unit/test_conversation_terminal_family.py`
- `backend/tests/unit/test_conversation_transcript_offload.py`
- `backend/tests/unit/test_desktop_migration.py`
- `backend/tests/unit/test_episode_attach_cost.py`
- `backend/tests/unit/test_episode_attach_review.py`
- `backend/tests/unit/test_focus_sessions_adversarial_challenge.py`
- `backend/tests/unit/test_focus_sessions_read_boundary.py`
- `backend/tests/unit/test_focus_sessions_stress_harness.py`
- `backend/tests/unit/test_live_transcript_merge.py`
- `backend/tests/unit/test_live_transcript_replay.py`
- `backend/tests/unit/test_memory_product_error_sanitization.py`
- `backend/tests/unit/test_object_lake.py`
- `backend/tests/unit/test_pusher_audio_projection.py`
- `backend/tests/unit/test_space_keys.py`
- `backend/tests/unit/test_transcript_pointer.py`
- `backend/utils/other/object_lake.py`
- `backend/utils/other/space_keys.py`
- `backend/utils/person_evidence_backfill.py`
- `backend/utils/sync/assignment.py`

The tracked `.agent-artifacts/pgf-result.md` is restored to origin/main (empty branch diff). This lane's report and draft PR body are under `.agent-artifacts/pgf/`. The unrelated app/analysis_options.yaml and app/pubspec.lock edits are preserved; the temporary preflight stash was restored and its exact binary patch hash matched. The first preflight stash was dropped after restoration. The later exact-OID stash was also restored and its binary patch hash matched. Its backup is retained to avoid a race on the shared stash stack; no app edits were committed.

## Deviations and scope extensions taken

All eight corrections in fix-r1.md were implemented under the lead's explicit approval: helpers collection filtering; finalization admission; recording cleanup; sync load validation; bounded retry amendment; batch worker KMS pin/lock; speaker authority/auto-enroll/users publication; episode memo/timeline owners.

Scope extensions taken (necessary test import/caller migrations and owning inventory; existing test assertions remain unchanged):

- `test_episode_attach_cost.py`, `test_episode_attach_review.py`: inject existing operational failures through the locally imported preload runner, scoped to memo operations.
- `test_memory_product_error_sanitization.py`: preload the real import-pure codec before this legacy fixture closes SDK package paths; six setup errors are corrected.
- `backend/docs/people-generation-writers.json`, `backend/docs/runbooks/people-scan-reuse.md`: re-audit and pin the nine changed writer scopes. Generation-helper/document-write AST calls are identical, 17 strict/inventory tests and 31 loopback emulator checks pass; no guard or test was relaxed.
- `test_desktop_migration.py`: open the real local `utils.other` package path before importing user/codec code; the closed package stub caused a C2 collection failure.
- `memory_import_isolation.py`: model the generic transaction marker, and snapshot/evict the new client-binding codec/terminal modules along with their callers. A real-codec no-IO test guards the fixture's behavior.
- `test_focus_sessions_adversarial_challenge.py`, `test_focus_sessions_read_boundary.py`, `test_focus_sessions_stress_harness.py`: preload the real, import-pure codec before closing external cloud package paths. No production IO is performed by these focus-only fixtures.

Additional correction within the original brief's file list: `conversation_terminal_title.py` had direct-SDK terminal callers without the generic runner marker. Both transactional cosmetic helpers now mark their local decode scope. Four cold/warm-pointer tests reproduce the unmarked SDK boundary and verify zero in-transaction lake fetches. Queue state and terminal policy are unchanged.

No round-2 edits were made under .github/, database/jobstore/, database/cells/, database/directory/, or testing/store_fixtures.py. The pre-existing branch's dead-code allowlist removal and C1 review files are retained, as recorded in the round-1 receipt. No new C1 API changes were required.

The original no-argument run-unit-ci.sh command now requires a mode, so it is run with --changed-files. Its selector requires the full backend suite for database/_client.py. test.sh is executed by that CI runner with the selected list; there is no redundant second all-suite run.

No anx writes or messages were made, per the implementation task's escalation rule. The earlier scope ask is superseded by fix-r1.md and was not used as an approval gate.

## Verification

Every test command uses `python3 .agent-artifacts/pgf-c2-test-env.py`, which removes GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable, service-account/Firebase credential paths and inherited project bindings; it supplies only demo hints and a closed loopback metadata endpoint. Python is backend/.venv (3.11.15). Heavy commands run through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 --`.

Current wrapper: `python3 .agent-artifacts/pgf-c2-test-env.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- <payload>` (the long continuation uses `--wait 7200`).

| Exact payload / command | Result |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py -q` | Initial 186 passed / 3 failed; corrected 190 passed. The later HTTP/wire guard expansion passed 194. |
| Same two files plus `backend/tests/unit/test_conversation_terminal_family.py -q` | Terminal correction: 279 passed. Final shared-fixture guard expansion: **280 passed, 0 failed**. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_episode_attach_cost.py backend/tests/unit/test_episode_attach_review.py -q` | **66 passed, 0 failed**. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_desktop_migration.py -q` | **114 passed, 0 failed** after the collection-boundary correction. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-memory-fixture-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Two isolated files: feedback speaker roles **46 passed**, memory replacement policy **24 passed** (70 total). |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-focus-fixture-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Focus read-boundary **7 passed**; adversarial/stress **12 deselected** by `not integration and not slow`; all three files collected successfully, exit 0. |
| `env PYTHONPATH="$PWD/backend" backend/.venv/bin/python -m pytest -p tests.conftest -p tests.unit.conftest -c backend/pyproject.toml --confcutdir=backend .agent-artifacts/pgf/test_c2_http_acceptance.py -q` | Manual real-router ASGI probe: initial 1 failed / 3 passed (sparse fixture omitted required is_user), corrected **4 passed**. The four cases are now committed in the 280-test run. |
| `env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/scripts/run-unit-ci.sh --changed-files "$PWD/.agent-artifacts/pgf/c2-changed-files.txt"` | Environment: 18 passed, 8 optional warnings, 0 failed. Full type check: **0 errors**, 75,445 warnings. Intentionally stopped with exit 137 after **1,332 atomic file results**, to free this task's admission slot for corrective gates. It is not a green full-CI claim. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-remaining-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Pending continuation: **1,386 files**, including 41 intentional reruns. All unconfirmed files, every failure, changed tests, shared-fixture consumers and recent files are included. Union with the atomic checkpoint is exactly **2,677 selected files**, with no omission. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-memory-product-fixture-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | **6 passed**, exit 0 after the fixture correction. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-people-generation-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Initial 13 strict writer tests passed / inventory 1 failed, 3 passed (run before refresh). After audit/refresh: **17 passed**, exit 0. |
| `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH="$PWD/backend" firebase emulators:exec --only firestore --project demo-wq20-people --config "$PWD/.agent-artifacts/pgf/c2-people-firebase.json" 'backend/.venv/bin/python backend/scripts/fsr_people_generation_emulator_test.py'` | **31 checks passed**, exit 0; only owned loopback/demo resources; emulator stopped and ports closed. |
| `.venv/bin/python -m pyright --pythonpath .venv/bin/python database/conversation_terminal_title.py` (backend/) | **0 errors**, 20 warnings. |
| `bash test-preflight.sh` (backend/) | **18 passed, 8 optional warnings, 0 failed**. |
| `.venv/bin/python scripts/scan_import_time_side_effects.py` (backend/) | Exit 0. |
| `.venv/bin/python scripts/check_module_stub_pollution.py` (backend/) | Exit 0 before the final fixture-only edits; final preflight rechecks it. |
| `.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils` (backend/) | Exit 0. |
| `make runtime-image-source-closure` | Exit 0, **19 registered images**. |
| `backend/.venv/bin/python backend/scripts/runtime_image_contracts.py check-third-party` | Exit 0; worker KMS gap resolved. Existing open dependency-set exemptions are unchanged. |
| `.venv/bin/python -m pytest tests/integration/test_recurring_voice_privacy_firestore.py -q` (backend/) | **14 skipped** without an emulator/credentials, not counted as passing. |
| `uv pip compile backend/diarizer/requirements-batch-pipeline.txt --format pylock.toml --python 3.11.15 --python-platform x86_64-unknown-linux-gnu --output-file backend/diarizer/pylock.batch-pipeline.toml` | Exit 0. Only google-cloud-kms==3.6.0 added; no existing version changed or was removed. |
| `bash backend/scripts/update-python-lock.sh` | Exit 0; all six managed locks regenerated with **no Git changes**; no upgrade flag. |
| `env OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf/c2-pr-body.md" BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | Four frozen runs each passed **41 checks**. Latest: **41 passed in 258.78s** on 0bfe7a13cf1, including memory/focus fixture corrections. Memory-product fixture/inventory corrections require a final run. |
| `scripts/pr-preflight --suggest` | Ran; required invariant citation: none. |
| `scripts/pr-preflight --lane local --pr-body-file .agent-artifacts/pgf/c2-pr-body.md --metadata-only` | Latest completed body validation: **4 passed**; final receipt body will be revalidated. |
| Pinned Black 26.5.1, `--check --line-length 120 --skip-string-normalization`, all 41 then-changed backend Python files; pinned pre-commit hook on later edits | Passed. The venv lacks a Black entry point, so uvx/pinned hook was used. |
| `git diff --check` | Passed. |

The exact checkpoint, atomic per-file exit statuses, continuation selection and stopped owned process groups are in c2-run-partition-checkpoint.json. No other agent's process was stopped. The continuation repeats every first-phase failure, including already-corrected fixtures; it does not hide the earlier failures. Static commands, working directories, timestamps and exit codes are in c2-static-receipts.jsonl. Logs are c2-*.log.

First-phase baseline failures: the daily-summary monitoring contract is a pure JSON check; its test and alert-rule blob are byte-identical to origin/main, and the main JSON reproduces two forbidden PromQL rules. Executor failures match fix-r1.md's known future.result(timeout=2) main/load failures; both owning files are unchanged. Evidence: c2-main-baseline-failures.json. C2 fixture failures (desktop, feedback and focus imports) are corrected and their isolated reruns pass. These are not represented as baseline failures.

## Decode-site classification after rebase

Fresh production decoder and runner greps are retained in `c2-decode-site-audit.txt` and `c2-runner-site-audit.txt` at the frozen source checkpoint. No decode site is intentionally left with unguarded lake IO inside a transaction.

- Brief §6a rows 1–9: processing upsert/persist, data-protection migration, projection bind, speaker assignment, live segment merge, translation, sync assignment and final-pass promotion use the shared preload owner. Migration retains pointer transcripts unchanged; sync validates availability at `load(cid)` before canonical/candidate decisions.
- Rows 10–16: owner confirmation, overlay merge, legacy review undo, transcript correction apply/undo, smart merge, learning jobs and speaker resolution use the preload owner. Historical undo versions remain content-addressed. Freshly prepared payload reads use the same memo; in-transaction writes defer offload.
- Rows 17–19: episode retained-bound decisions, recurring-voice privacy scrubs and person-evidence backfill use the preload owner. Privacy filtering of a freshly prepared payload is memo-backed.
- Row 20: finalization admission's existing contention-retry/direct-SDK owner is wrapped in `run_preloaded_operation`, per fix-r1; queue-state logic is retained.
- Corrected §6b classifications: empty-recording cleanup, episode memo/timeline attach and speaker authority/auto-enroll/users publication are transactional and now have preload owners. Terminal kept-row/dead-letter cosmetic decodes locally set the transaction guard; a cold pointer keeps the conservative terminal behavior, without IO. Non-transactional terminal calendar probes may resolve normally.
- Read/portability seams (`_decrypt_conversation_data`, `prepare_conversation_for_read`) resolve pointers before existing list handling. Collection helpers filter absent/deleted results. The raw-content predicate retains absent/shredded False, corruption True and transport-failure raise behavior; each transactional owner above guards it.
- Remaining non-transactional verified readers need no runner edits: recovery decode-status inspection, self-heal, agent-capability reads/transcript fingerprints, batch projection, shadow projection, and `scripts/stuck_backfill.py`. The fingerprint re-read within overlay merge is protected by that owner's memo. Emulator-script direct decodes are setup/assertion reads outside domain transactions.
- The two strict decoder adapters only delegate to the codec. The codec's own post-commit swap decodes outside a transaction. Its pointer decoder enforces memo-only access whenever the generic marker is set.
- Public chat uses its existing bounded inline decoder and excludes pointer docs; there is no lake fetch. List/detail/MCP/export/search-hydration/notification readers flow through the shared conversation preparation seams and need no per-surface implementation edits.
- Pre-transaction decorator writes upload before publication. Sync/speaker/live transaction encodes return inline and defer a revision-checked swap; live `in_progress` docs are skipped by the swap. Open-loop sibling-field encoding remains inline.

## Known gaps

- Docker image smoke is waived by fix-r1.md because Docker is unavailable. Runtime source and third-party closure remain required.
- The optional listen/privacy Firestore emulator suite was not rerun in round 2; the separate People writer contract passed 31 checks on a fresh owned loopback emulator. The offline HTTP harness was not started because local Docker is unavailable. Hermetic reader/domain tests are not a provider-backed or deployed round trip.
- No deployment, real-provider round trip, production write admission, or C4 wipe qualification is claimed. O1 keeps writing off/0 until C4 is green; the dev-first ramp follows C1's registry metadata.
- C3 owns backfill, orphan cleanup and registry/receipt; C4 owns wipe/prefix purge and keys last; B/W2 logs pointer field changes; A6 ports the seam after C2.

## Draft PR body

## What changed and why

Oversized transcript_segments can be stored as an encrypted object-lake pointer inside the existing field. The shared codec resolves pointers for backend, listen, pusher, MCP, export and search; migrated transaction owners use a content-addressed preload/retry boundary and revision-checked post-commit swaps. Deleted-owner key tombstones prevent rekeying, malformed key rows remain retryable, transcript decompression is bounded to 32 MiB, and key-document authority reads are budgeted (one per unwrap, two per put).

Writes remain default-off/0 admission. O1: OBJECT_LAKE_WRITE_ENABLED stays off in prod until C4's wipe-coverage test is green. Ramp is dev-first via OBJECT_LAKE_WRITE_PERCENT; C1's registry retains ramp metadata and ownership. No new env binding, dependency upgrade, schema migration or index is introduced; space_keys already exists and retains content-free destruction tombstones.

C3 reuses offload_inline_transcript for backfill and owns legacy re-encryption, orphan janitor and registry/receipt. C4 owns account-wipe integration, quiescing in-flight puts, prefix purge and key destruction last (preserving tombstones). B/W2 syncs pointer field changes as content-free doc changes. A6 ports the seam unchanged. Public-chat's bounded decoder excludes pointer docs; existing long shared conversations need a later product decision before backfill.

C2 also covers finalization admission, empty-recording cleanup, sync canonical/candidate admission, voice publication, and episode memo/timeline transactions. Preloads allow up to 32 distinct documents plus three content-change retries (36 total attempts). The batch worker pins KMS to match the backend runtime; existing locked versions are preserved.

## Product invariants affected

none

## How it was verified

Hermetic local tests only. GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before each command. No production access, API calls or customer data. Exact commands and final counts are recorded in .agent-artifacts/pgf/c2-result.md. Docker is unavailable locally; image smoke is waived by the lead. Runtime source and third-party closure guards are required. The current codec/domain and terminal-family run passed 280 tests; episode caller tests passed 66, desktop migration 114, memory/feedback 70, and focus read-boundary 7 (12 slow cases deselected by the standard fast-unit filter). Full type checking reported 0 errors; the later terminal module check also reported 0 errors. Source and third-party runtime closure passed. The latest frozen-tree preflight passed all 41 checks on 0bfe7a13cf1 in 258.78s; the later memory-product fixture and People inventory corrections require one final frozen run. The memory-product fixture rerun passed 6 tests. People writer re-audit passed 17 strict/inventory tests and 31 owned loopback emulator checks; the emulator stopped.

The full CI-shaped unit selection is being completed in two local phases to free the admission slot for corrective gates: 1,332 atomic file results are checkpointed, and a 1,386-file continuation includes 41 intentional reruns. Their union is exactly all 2,677 selected files. Initial main/load failures and corrected fixture failures remain recorded; the interrupted first command is not claimed green. 14 privacy integration tests skipped without an emulator. This is separate from the completed 31-check People writer emulator contract.

## Tests

backend/tests/unit/test_transcript_pointer.py: codec round trips, flag-off golden encodings, compressed-byte threshold, no-IO transaction guard, preload retries, decode taxonomy, memo hygiene, consent and deferred CAS.
backend/tests/unit/test_conversation_transcript_offload.py: pointer reader surfaces, actual HTTP detail 200/404/500 outcomes, domain refusals, direct-SDK terminal no-IO guards, oversized transcripts, tombstone races, malformed keys and authority read budgets.


Reader-site audit after rebase: brief §6a rows 1–19 use preload owners; row 20 finalization admission uses the approved contention-runner wrapper. Empty-recording cleanup, voice publication and episode memo/timeline attach are also transactional and migrated. Terminal cosmetic helpers enforce a local memo-only guard. No runner change is needed for non-transactional recovery status, self-heal, agent-capability reads/fingerprints, batch/shadow projections or stuck-backfill; overlay fingerprint reads inherit their owning transaction guard. Shared preparation covers list/detail/MCP/export/search/notifications. The bounded public-chat decoder intentionally excludes pointer docs. Emulator-script direct decodes are setup/assertion reads. Fresh-prepared transaction encodes defer offload; protection migration retains existing pointers.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4892 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.
