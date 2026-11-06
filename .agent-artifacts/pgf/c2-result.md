# C2 round 2 implementation result

Status: implementation complete. All selected files are covered; one repeatable failure remains in unchanged main Parakeet code. Final frozen preflight passed all 43 checks on the rebased tree.
Updated: 2026-11-06T22:53:58.189926+00:00
Repository: BasedHardware/omi. Branch: lane/pgf-c2.
Initial tested base: 4b1c40b5ef03242b82013a64c1dc941728715bab. Final fetched/rebased base: 34125ccd5fbd6c47885d23abe70e9a1448b7515e.
Implementation checkpoint: d486b48fbdd58938499a9ffc023f8a4a650274f1.
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
- `backend/tests/unit/test_users_add_sample_transaction.py`
- `backend/utils/other/object_lake.py`
- `backend/utils/other/space_keys.py`
- `backend/utils/person_evidence_backfill.py`
- `backend/utils/sync/assignment.py`

The tracked `.agent-artifacts/pgf-result.md` is restored to origin/main (empty branch diff). This lane's report and draft PR body are under `.agent-artifacts/pgf/`. The unrelated app/analysis_options.yaml and app/pubspec.lock edits are preserved; the temporary preflight stash was restored and its exact binary patch hash matched. The first preflight stash was dropped after restoration. The earlier exact-OID stash was restored and its binary patch hash matched. The final exact-OID backup (eb0b876a43459be22cbc5e45da82b64200433908) was restored after preflight and its binary patch SHA-256 matched the pre-stash value. Backup objects are retained to avoid a race on the shared stash stack; no app edits were committed.

## Deviations and scope extensions taken

All eight corrections in fix-r1.md were implemented under the lead's explicit approval: helpers collection filtering; finalization admission; recording cleanup; sync load validation; bounded retry amendment; batch worker KMS pin/lock; speaker authority/auto-enroll/users publication; episode memo/timeline owners.

Scope extensions taken (necessary test import/caller migrations and owning inventory; existing test assertions remain unchanged):

- `test_episode_attach_cost.py`, `test_episode_attach_review.py`: inject existing operational failures through the locally imported preload runner, scoped to memo operations.
- `test_users_add_sample_transaction.py`: preload the real codec before closing SDK package paths and retain that module in the fixture map; five setup errors are corrected without changing assertions.
- `test_memory_product_error_sanitization.py`: preload the real import-pure codec before this legacy fixture closes SDK package paths; six setup errors are corrected.
- `backend/docs/people-generation-writers.json`, `backend/docs/runbooks/people-scan-reuse.md`: re-audit and pin the nine changed writer scopes. Generation-helper/document-write AST calls are identical, 17 strict/inventory tests and 31 loopback emulator checks pass; no guard or test was relaxed.
- `test_desktop_migration.py`: open the real local `utils.other` package path before importing user/codec code; the closed package stub caused a C2 collection failure.
- `memory_import_isolation.py`: model the generic transaction marker, and snapshot/evict the new client-binding codec/terminal modules along with their callers. A real-codec no-IO test guards the fixture's behavior.
- `test_focus_sessions_adversarial_challenge.py`, `test_focus_sessions_read_boundary.py`, `test_focus_sessions_stress_harness.py`: preload the real, import-pure codec before closing external cloud package paths. No production IO is performed by these focus-only fixtures.

Additional correction within the original brief's file list: `conversation_terminal_title.py` had direct-SDK terminal callers without the generic runner marker. Both transactional cosmetic helpers now mark their local decode scope. Four cold/warm-pointer tests reproduce the unmarked SDK boundary and verify zero in-transaction lake fetches. Queue state and terminal policy are unchanged.

No round-2 edits were made under .github/, database/jobstore/, database/cells/, database/directory/, or testing/store_fixtures.py. The pre-existing branch's dead-code allowlist removal and C1 review files are retained, as recorded in the round-1 receipt. No new C1 API changes were required.

The final fetch also brought upstream episode F-join and pusher admission work. Rebase preserved their code. The only conflict was the People inventory: main's new previous_transcript fingerprint and C2's nine audited hashes are both retained. The nine scopes were re-audited against the final base; generation/document-write calls remain identical. The 14-file post-rebase run covers all four newly selected upstream files and the two modified upstream test files, plus the overlapping C2 tests. No new upstream feature policy was changed.

The original no-argument run-unit-ci.sh command now requires a mode, so it is run with --changed-files. Its selector requires the full backend suite for database/_client.py. test.sh executes the exact CI-selected files across the checkpointed phases; no selected file is omitted. The final same-mode selector adds four upstream tests; all are covered in the post-rebase run.

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
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-remaining-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Completed continuation: **1,386 files**, including 41 intentional reruns; **1,380 files exit 0 / 6 exit 1**, terminal exit 1. Union with the 1,332 atomic checkpoint is exactly **2,677 selected files**, with no omission. Corrective reruns and the upstream monitoring fix leave one unresolved file. These are file exit counts, including marker-only skips, not test-case counts. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-memory-product-fixture-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | **6 passed**, exit 0 after the fixture correction. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-people-generation-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Initial 13 strict writer tests passed / inventory 1 failed, 3 passed (run before refresh). After audit/refresh: **17 passed**, exit 0. |
| `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH="$PWD/backend" firebase emulators:exec --only firestore --project demo-wq20-people --config "$PWD/.agent-artifacts/pgf/c2-people-firebase.json" 'backend/.venv/bin/python backend/scripts/fsr_people_generation_emulator_test.py'` | **31 checks passed**, exit 0; only owned loopback/demo resources; emulator stopped and ports closed. |
| `.venv/bin/python -m pyright --pythonpath .venv/bin/python database/episodes.py` (backend/) | Post-rebase: **0 errors**, 381 warnings, exit 0. |
| `.venv/bin/python -m pyright --pythonpath .venv/bin/python database/conversation_terminal_title.py` (backend/) | **0 errors**, 20 warnings. |
| `bash test-preflight.sh` (backend/) | **18 passed, 8 optional warnings, 0 failed**. |
| `.venv/bin/python scripts/scan_import_time_side_effects.py` (backend/) | Exit 0. |
| `.venv/bin/python scripts/check_module_stub_pollution.py` (backend/) | Exit 0; the final 43-check preflight rechecked it after all fixture changes. |
| `.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils` (backend/) | Exit 0. |
| `make runtime-image-source-closure` | Exit 0, **19 registered images**. |
| `backend/.venv/bin/python backend/scripts/runtime_image_contracts.py check-third-party` | Exit 0; worker KMS gap resolved. Existing open dependency-set exemptions are unchanged. |
| `.venv/bin/python -m pytest tests/integration/test_recurring_voice_privacy_firestore.py -q` (backend/) | **14 skipped** without an emulator/credentials. A later owned loopback rerun passed **14 tests**, exit 0; emulator stopped. |
| `uv pip compile backend/diarizer/requirements-batch-pipeline.txt --format pylock.toml --python 3.11.15 --python-platform x86_64-unknown-linux-gnu --output-file backend/diarizer/pylock.batch-pipeline.toml` | Exit 0. Only google-cloud-kms==3.6.0 added; no existing version changed or was removed. |
| `bash backend/scripts/update-python-lock.sh` | Exit 0; all six managed locks regenerated with **no Git changes**; no upgrade flag. |
| `env OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf/c2-pr-body.md" BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | Four earlier frozen runs each passed **41 checks**. Final rebased frozen run: **43 passed in 196.87s**, exit 0 on cac0edb73e7a55d1e2b0d640d5b6753d84dc7995. Only receipt text changes follow this gate. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-users-sample-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | **5 passed**, exit 0 after the sample fixture correction. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-soniox-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Original full-selection result: 15 passed / 1 timing failure. Unchanged isolated rerun: **16 passed**, exit 0. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-parakeet-route-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | **33 passed / 1 failed**, exit 1, same as the continuation. Test, receipt helper and streaming implementation are byte-identical to tested main. Unresolved, not attributed to C2. |
| `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-post-rebase-tests.txt" DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh` | Final-base regression: **625 passed across 14 files**, exit 0. All four newly selected upstream files and both modified upstream tests are covered; C2 core, terminal, episode callers and People invariants are rerun. |
| `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH="$PWD/backend" npm run test:listen-lifecycle:emulator -- --config "$PWD/.agent-artifacts/pgf/c2-people-firebase.json"` | **PASS**, exit 0: fenced cleanup races and fresh-generation listen replay; emulator stopped. |
| `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH="$PWD/backend" firebase emulators:exec --only firestore --project demo-batch-pipeline-d --config "$PWD/.agent-artifacts/pgf/c2-people-firebase.json" 'backend/.venv/bin/python -m pytest backend/tests/integration/test_recurring_voice_privacy_firestore.py -q'` | **14 passed**, exit 0; emulator stopped. |
| `scripts/pr-preflight --suggest` | Ran; required invariant citation: none. |
| `scripts/pr-preflight --lane local --pr-body-file .agent-artifacts/pgf/c2-pr-body.md --metadata-only` | Final metadata-only body validation: **4 passed in 18.27s**, exit 0. |
| Pinned Black 26.5.1, `--check --line-length 120 --skip-string-normalization`, all **48 current changed backend Python files**; pinned pre-commit hooks | Passed, exit 0. The venv lacks a Black entry point, so uvx/pinned hook was used. |
| `git diff --check` | Passed. |

The exact checkpoint, atomic per-file exit statuses, continuation selection and stopped owned process groups are in c2-run-partition-checkpoint.json. No other agent's process was stopped. The continuation repeats every first-phase failure, including already-corrected fixtures; it does not hide the earlier failures. Static commands, working directories, timestamps and exit codes are in c2-static-receipts.jsonl. Logs are c2-*.log.

First-phase baseline failures: the daily-summary monitoring contract is a pure JSON check; its test and alert-rule blob are byte-identical to origin/main, and the main JSON reproduces two forbidden PromQL rules. Executor failures match fix-r1.md's known future.result(timeout=2) main/load failures; both owning files are unchanged. Evidence: c2-main-baseline-failures.json. C2 fixture failures (desktop, feedback, focus, memory-product and sample imports) and the audited People inventory are corrected; isolated reruns pass. These are not represented as baseline failures. The final rebase includes main's monitoring fix and its contract now passes. Executors passed their continuation rerun. Soniox's unchanged keepalive test had one 80ms scheduling failure, then passed all 16 tests in isolation. Parakeet's unchanged timeout test fails both in the continuation and isolated rerun (33 passed / 1 failed each); c2-parakeet-baseline-evidence.json pins source identity. No cause in C2 was found; no unrelated STT policy/test was modified.

Coverage after the final rebase: the same CI selector requires **2,681 files**, adding four and removing none. The two-phase 2,677-file run plus the 14-file post-rebase run covers that exact set. Corrective reruns leave **2,680 files exit 0 (includes marker-only skips), one file exit 1**. Neither interrupted nor nonzero phase is described as a green CI command.

## Decode-site classification after rebase

Fresh production decoder and runner greps are retained in `c2-decode-site-audit.txt` and `c2-runner-site-audit.txt` at the frozen source checkpoint. No decode site is intentionally left with unguarded lake IO inside a transaction.

- Brief §6a rows 1–9: processing upsert/persist, data-protection migration, projection bind, speaker assignment, live segment merge, translation, sync assignment and final-pass promotion use the shared preload owner. Migration retains pointer transcripts unchanged; sync validates availability at `load(cid)` before canonical/candidate decisions.
- Rows 10–16: owner confirmation, overlay merge, legacy review undo, transcript correction apply/undo, smart merge, learning jobs and speaker resolution use the preload owner. Historical undo versions remain content-addressed. Freshly prepared payload reads use the same memo; in-transaction writes defer offload.
- Rows 17–19: episode retained-bound decisions, recurring-voice privacy scrubs and person-evidence backfill use the preload owner. Privacy filtering of a freshly prepared payload is memo-backed.
- Row 20: finalization admission's existing contention-retry/direct-SDK owner is wrapped in `run_preloaded_operation`, per fix-r1; queue-state logic is retained.
- Corrected §6b classifications: empty-recording cleanup, episode memo/timeline attach and speaker authority/auto-enroll/users publication are transactional and now have preload owners. Terminal kept-row/dead-letter cosmetic decodes locally set the transaction guard; a cold pointer keeps the conservative terminal behavior, without IO. Non-transactional terminal calendar probes may resolve normally.
- Read/portability seams (`_decrypt_conversation_data`, `prepare_conversation_for_read`) resolve pointers before existing list handling. Collection helpers filter absent/deleted results. The raw-content predicate retains absent/shredded False, corruption True and transport-failure raise behavior; each transactional owner above guards it.
- Remaining non-transactional verified readers need no runner edits: recovery decode-status inspection, self-heal, agent-capability reads/transcript fingerprints, batch projection, shadow projection, and `scripts/stuck_backfill.py`. The fingerprint re-read within overlay merge is protected by that owner's memo. Emulator-script direct decodes are setup/assertion reads outside domain transactions.
- New upstream `utils/episodes/f_join.previous_transcript` decodes outside transactions; the existing owner handles no-answer conservatively, so no C2 runner edit is needed. Its main-owned fingerprint is preserved.
- The two strict decoder adapters only delegate to the codec. The codec's own post-commit swap decodes outside a transaction. Its pointer decoder enforces memo-only access whenever the generic marker is set.
- Public chat uses its existing bounded inline decoder and excludes pointer docs; there is no lake fetch. List/detail/MCP/export/search-hydration/notification readers flow through the shared conversation preparation seams and need no per-surface implementation edits.
- Pre-transaction decorator writes upload before publication. Sync/speaker/live transaction encodes return inline and defer a revision-checked swap; live `in_progress` docs are skipped by the swap. Open-loop sibling-field encoding remains inline.

## Known gaps

- Full-unit green is not claimed: the unchanged main Parakeet timeout test remains red, including its isolated rerun. This is reported to the lead; no external ask or contact was made.

- Docker image smoke is waived by fix-r1.md because Docker is unavailable. Runtime source and third-party closure both passed in the final preflight.
- Listen lifecycle, privacy and People writer loopback emulator contracts were rerun in round 2 and passed; all emulators stopped. The offline HTTP harness was not started because local Docker is unavailable. Hermetic reader/domain tests are not a provider-backed or deployed round trip.
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

Hermetic/local verification only; GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before every command. No production access or calls to api.omi.me; no customer data, push, PR or deploy. Exact commands and phase results are in .agent-artifacts/pgf/c2-result.md.

After the final rebase, 625 tests passed across 14 files, covering the C2 core, overlapping episode code, new upstream episode/pusher tests, People inventory and monitoring. Earlier focused runs passed 280 C2/terminal tests, 66 episode caller tests, 114 desktop tests, 70 memory/feedback tests, 7 focus tests (12 slow cases deselected), 6 memory-product tests and 5 sample-transaction tests. Full type checking reported 0 errors; post-rebase episodes.py checking also reported 0 errors (381 warnings). Owned loopback checks passed listen lifecycle, 14 privacy tests and 31 People writer checks; every emulator stopped. Runtime source and third-party closure passed. Docker image smoke is waived by fix-r1.md; the Docker offline-stack round trip remains unverified. The local ASGI detail route tests cover pointer 200/404/500 outcomes.

The original 2,677-file CI selection was covered in two phases (1,332 atomic results, then 1,386 files with 41 deliberate repeats), followed by corrective reruns. The initial command was intentionally checkpointed/interrupted (exit 137); the continuation exited 1 with six failing files, all retained in the receipt. Corrections and upstream monitoring repair clear five of those. Soniox's 80ms timing assertion passed its unchanged isolated rerun (16 passed). The current selection adds four upstream files, all covered by the post-rebase run: 2,681 unique files covered, 2,680 exit 0 (including marker-only skips), one unresolved file. test_qualify_parakeet_route::test_stream_timeout_retains_diagnostics reproducibly fails in unchanged main code (33 passed / 1 failed on both runs); this PR does not claim full-unit green.

Final frozen preflight passed **43 checks in 196.87s** on `cac0edb73e7a55d1e2b0d640d5b6753d84dc7995`. Pinned Black 26.5.1 passed all 48 changed backend Python files. Final receipt metadata-only preflight passed **4 checks in 18.27s**.

## Tests

backend/tests/unit/test_transcript_pointer.py: codec round trips, flag-off golden encodings, compressed-byte threshold, no-IO transaction guard, preload retries, decode taxonomy, memo hygiene, consent and deferred CAS.
backend/tests/unit/test_conversation_transcript_offload.py: pointer reader surfaces, actual HTTP detail 200/404/500 outcomes, domain refusals, direct-SDK terminal no-IO guards, oversized transcripts, tombstone races, malformed keys and authority read budgets.


Reader-site audit after rebase: brief §6a rows 1–19 use preload owners; row 20 finalization admission uses the approved contention-runner wrapper. Empty-recording cleanup, voice publication and episode memo/timeline attach are also transactional and migrated. Terminal cosmetic helpers enforce a local memo-only guard. No runner change is needed for non-transactional recovery status, self-heal, agent-capability reads/fingerprints, batch/shadow projections or stuck-backfill; overlay fingerprint reads inherit their owning transaction guard. Shared preparation covers list/detail/MCP/export/search/notifications. The bounded public-chat decoder intentionally excludes pointer docs. The new upstream f_join.previous_transcript read is outside transactions and retains its owner's conservative no-answer policy; no new runner is needed. Emulator-script direct decodes are setup/assertion reads. Fresh-prepared transaction encodes defer offload; protection migration retains existing pointers.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4892 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.
