# C2 round 3 implementation result

Status: implementation complete; frozen preflight and final codec checks green. Local commits only; no push/PR. Updated 2026-11-07T01:42:26.310538+00:00.
Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean`. Branch: lane/pgf-c2.
Fetched/rebased base: `ebd12975fe6b0baef217313f27ddff6d625b60b7`. Final implementation commit: `afe5caab56a42caadbb0cf4d7e7a0381e1e22eb4`. Backend tree: `e0fae10553edd48c668445550eace3ef8761a24c`, identical before/after rebase. New upstream changes since the broad CI base are only two firmware CI files; no backend source changed.
GCP tier: none. No production access, api.omi.me calls, customer data, push, PR, deploy, new flag admission, anx write or message to David.

## What was built

The inherited C2 implementation supplies the single transcript pointer-or-inline codec, typed missing/shredded/unavailable read states, transaction preload owners across conversation/review/speaker/sync/cleanup/episode paths, reader-surface coverage, C3 backfill CAS, worker dependencies, and listen/pusher documentation.

Round 3 implements all five fix-r2.md items:

1. Every admitted transactional encode above the compressed inline threshold aborts before staging its transcript write, uploads the candidate outside the transaction, then reruns the complete transaction from a fresh source snapshot. Only the exact recomputed logical-source digest may reuse the uploaded pointer. Source identity is computed before randomized grouping-sidecar protection; the reference SHA and decoded memo describe the actual uploaded JSON. Transaction candidate puts cannot seed the read memo and mask cold current-reference reads. Non-JSON/cyclic optional grouping evidence retains its existing drop behavior, with a deterministic source fingerprint that uses no repr/address identity. This applies to live in_progress rows, including transcripts above Firestore's 1 MiB ceiling. Admission-off encoding and oversize failures retain main's behavior. Failed uploads never commit inline data; abandoned blobs belong to C3.
2. Missing/shredded transcripts remove only the transcript signal from raw_conversation_has_content. Photos and durable has_content still prevent empty deletion; retryable read failures continue to abort cleanup. All dicts, including {}, pass strict pointer validation; corrupt fields remain content and cannot authorize deletion.
3. Admission requires configured bucket and release bindings. KMS remains deliberately optional for the specified hermetic FakeKMS mode; absent release defaults to v1. Flag-on/100% without a bucket stays inline and never puts.
4. The decoded operation memo has both a 32-entry/120-second cap and a 64 MiB aggregate budget measured over decoded Python containers and strings. A budget breach raises retryable TranscriptMemoBudgetExceeded (a TranscriptPointerFetchError), and the owning operation clears plaintext in finally. Insertion checks aggregate room before retaining another decoded memo entry.
5. Deep verification is documented/tested: destroyed key -> False; unavailable key -> SpaceKeyUnavailable; shallow verification can return True in either state because it checks metadata/size only. A deep False must never authorize deletion. The production verifier itself was unchanged.

The retry envelope now allows up to 32 read preloads plus 32 candidate uploads and the existing shared three-content-change allowance, with 68 total outer attempts. Each attempted transaction recomputes against its own snapshot; existing SDK contention retries are unchanged. Published candidates do not displace source plaintext from the read memo. The C3 backfill primitive still skips in_progress rows; the live writer uses the preupload path and does not depend on that swap.

## Round 3 file list

- `.agent-artifacts/pgf/c2-result.md` (this receipt)
- `.agent-artifacts/pgf/c2-pr-body.md` (draft metadata)
- `backend/config/object_lake.py`
- `backend/database/conversations.py`
- `backend/database/transcript_pointer.py`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-06-transcript-lake-offload.md`
- `backend/tests/unit/test_conversation_transcript_offload.py`
- `backend/tests/unit/test_object_lake_config.py`
- `backend/tests/unit/test_transcript_pointer.py`

## Scope extensions taken and deviations

- `backend/config/object_lake.py` is a C1-owned file, but fix-r2.md explicitly requires its admission contract to be corrected. `backend/tests/unit/test_object_lake_config.py` receives only the required test bucket setup; all existing cohort assertions remain intact. This is the only new extension outside the original C2 deliverables.
- The original inline-in-transaction/deferred-drain design and its tests are superseded by fix-r2.md's preupload ruling. C3 retains offload_inline_transcript as an explicit backfill primitive; transaction owners no longer invoke a post-commit drain.
- The bounded retry policy gains one upload attempt per admitted document. The existing three-content-change allowance stays shared, and the hard bound grows from 36 to 68 to account for 32 read+32 upload preparations.
- Earlier approved fix-r1.md scope (cleanup/finalization/sync/voice/episode owners, batch worker KMS, strict test/import fixture migrations and People inventory refresh) remains. The historical round-2 receipt is preserved in Git at `e6bf0f78701219bd2aae61b9733c4b5136651b33:.agent-artifacts/pgf/c2-result.md`.
- Inherited C1 library hardening follows c1-result.md Review disposition assigning tombstones, decompression bounds and authority read budgets to C2. The inherited .github dead-code allowlist removal follows the entry's own instruction to remove it when C2 adds the first caller. No round-3 edits touch .github/, jobstore/, cells/, directory/ or testing/store_fixtures.py. No credentials, workflows or production values were changed.
- Docker image smoke is waived by fix-r1.md (Docker unavailable); runtime source and third-party closure remain required. The Docker offline-stack round trip remains unverified; the real-router ASGI pointer tests supply local HTTP 200/404/500 coverage, without claiming a live stack.
- The no-argument run-unit-ci.sh command in brief-c2.md is obsolete: it requires --all or --changed-files. This round uses the full branch changed-file list. Its own bash test.sh invocation is the selector-driven test.sh run; that identical full set is not run redundantly a second time.

## Complete implementation file list

- `.agent-artifacts/pgf/c2-pr-body.md`
- `.agent-artifacts/pgf/c2-result.md`
- `.github/scripts/dead_code/backend.allowlist.json`
- `backend/config/object_lake.py`
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
- `backend/tests/unit/test_object_lake_config.py`
- `backend/tests/unit/test_pusher_audio_projection.py`
- `backend/tests/unit/test_space_keys.py`
- `backend/tests/unit/test_transcript_pointer.py`
- `backend/tests/unit/test_users_add_sample_transaction.py`
- `backend/utils/other/object_lake.py`
- `backend/utils/other/space_keys.py`
- `backend/utils/person_evidence_backfill.py`
- `backend/utils/sync/assignment.py`

## Verification

All checks are launched through `python3 .agent-artifacts/pgf-c2-test-env.py`, which unsets GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable, customer-service-account paths and inherited project bindings before execution. Only demo/loopback bindings are supplied. Python is backend/.venv (3.11.15). Heavy work goes through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 --` (7200 for queued long checks). The subprocess receipt runner has hard command deadlines and kills only its owned process groups.

Commands below are the exact inner invocations, always behind the credential scrubber above and, for heavy runs, omi-heavy. Paths beginning `$PWD` are expanded to this worktree; cwd is repo root unless explicitly stated.

- `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py -q`: initial **220 passed / 2 failed** (obsolete deferred-output expectations); tests migrated to committed-pointer behavior required by fix-r2.
- `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py backend/tests/unit/test_object_lake_config.py -q`: intermediate **231 passed**. Follow-up first run **227 passed / 4 failed**, exposing transaction candidate uploads masking cold current-reference reads. Fixed cache behavior; no existing assertions weakened. **Final: 243 passed / 0 failed**, 16.47 s (`c2-r3-final-focused-v2.log`).
- New red cleanup probe: **3 failed / 3 passed**; randomized-grouping retry probe: **3 failed / 6 deselected**. Both reproduced actual defects, were added to the permanent focused suite, and now pass. A scratch candidate prototype initially had **5 failed / 7 passed** from invalid double-reveal assertions; corrected the test to compare protected uploaded JSON using the raw decoder, and revealed fields using the verified decoder. This prototype did not mutate production source.
- `env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/scripts/run-unit-ci.sh --changed-files "$PWD/.agent-artifacts/pgf/c2-r3-branch-files.txt"`: **exit 1**; all **2,681 selected files** attempted, **2,679 file exits 0 / 2 exits 1**, including marker-only files; 4590.97 s. Full type-check phase: **0 errors / 75,544 warnings**. Two unchanged live-provider files had four timing assertions fail: recovery-matrix delivery-expired/replay-send-stalled (2), provider-pairs slow-consumer two-second waits (2). Their 15 test/direct-provider subjects match tested main byte-for-byte (`c2-r3-stt-failure-identity.json`); this is identity evidence, not a fresh execution on main. Parakeet's previous-round failure did not recur.
- `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-r3-stt-rerun.txt" BACKEND_PYTEST_WORKERS=1 DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh`: **exit 0; 134 passed / 3 slow deselected**. Recovery 103 passed/3 deselected; provider pairs 31 passed. This isolated recovery does not change the original full-CI exit status.
- `env BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf/c2-r3-postfix-tests.txt" BACKEND_PYTEST_WORKERS=4 DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/test.sh`: **exit 0; 2,410 passed across 58 related encoder/grouping/cleanup/caller files**, after all codec fixes. Rebase preserved this backend tree exactly. The full CI contract already invokes the required selector-driven test.sh internally.
- Frozen `scripts/pr-preflight --suggest`, `env OMI_PR_BODY_FILE=.agent-artifacts/pgf/c2-pr-body.md BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight`, and `scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/c2-pr-body.md --metadata-only`: **all passed**: suggest exit 0; make **43 checks in 110.16 s** (process 110.6 s); metadata **4 checks in 5.73 s**. Frozen HEAD was `b937e5183f5274c2e6e3c78ccb526ae077a203d5`, with the final source tree above. Later changes are receipt/body only. The make gate includes ordinary full PR-body validation; metadata-only validates later receipt edits without repeating the full gate.

Additional exact command receipts (all executed this round; JSON receipts retain full argv and wall times):

- `bash test-preflight.sh` (cwd backend): **exit 0**, 27.27 s; log `c2-r3-environment.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python scripts/scan_import_time_side_effects.py` (cwd backend): **exit 0**, 31.25 s; log `c2-r3-import-purity.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python scripts/check_module_stub_pollution.py` (cwd backend): **exit 0**, 69.34 s; log `c2-r3-stub-pollution.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils` (cwd backend): **exit 124**, 180.03 s; log `c2-r3-async-blockers.log`.
- `make runtime-image-source-closure` (cwd repo root): **exit 0**, 587.24 s; log `c2-r3-source-closure.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python backend/scripts/runtime_image_contracts.py check-third-party` (cwd repo root): **exit 0**, 214.59 s; log `c2-r3-dependency-closure.log`.
- `bash backend/scripts/update-python-lock.sh` (cwd repo root): **exit 0**, 3.21 s; log `c2-r3-locks.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python -m pytest tests/unit/test_object_lake_config.py -q` (cwd backend): **exit 0**, 5.88 s; log `c2-r3-config-contract.log`.
- `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH=/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend npm run test:listen-lifecycle:emulator -- --config /Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/.agent-artifacts/pgf/c2-r3-firebase.json` (cwd repo root): **exit 0**, 24.83 s; log `c2-r3-listen-emulator.log`.
- `env -u FIREBASE_TOKEN -u GOOGLE_OAUTH_ACCESS_TOKEN CI=1 FIREBASE_CLI_DISABLE_TELEMETRY=1 PYTHONPATH=/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend firebase emulators:exec --only firestore --project demo-batch-pipeline-d --config /Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/.agent-artifacts/pgf/c2-r3-firebase.json 'backend/.venv/bin/python -m pytest backend/tests/integration/test_recurring_voice_privacy_firestore.py -q'` (cwd repo root): **exit 0**, 27.41 s; log `c2-r3-privacy-emulator.log`.
- `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean/backend/.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils` (cwd backend): **exit 0**, 147.84 s; log `c2-r3-async-blockers-retry.log`.
- `uvx --from black==26.5.1 black --check --line-length 120 --skip-string-normalization backend/config/object_lake.py backend/database/_client.py backend/database/conversation_finalization_jobs.py backend/database/conversation_terminal_title.py backend/database/conversations.py backend/database/episode_attach_memo.py backend/database/episode_timeline.py backend/database/episodes.py backend/database/helpers.py backend/database/owner_confirmation.py backend/database/recording_sessions.py backend/database/recurring_voice_privacy.py backend/database/review_changes.py backend/database/review_overlay_merge.py backend/database/review_transcript_changes.py backend/database/smart_merge.py backend/database/speaker_assignment_effects.py backend/database/speaker_auto_enroll.py backend/database/speaker_learning_jobs.py backend/database/speaker_profile_authority.py backend/database/speaker_resolution_updates.py backend/database/sync_assignment.py backend/database/transcript_pointer.py backend/database/users.py backend/tests/integration/test_recurring_voice_privacy_firestore.py backend/tests/support/dream_firestore.py backend/tests/support/firestore_query_driver_registry.py backend/tests/unit/memory_import_isolation.py backend/tests/unit/test_conversation_archive_filter_contract.py backend/tests/unit/test_conversation_terminal_family.py backend/tests/unit/test_conversation_transcript_offload.py backend/tests/unit/test_desktop_migration.py backend/tests/unit/test_episode_attach_cost.py backend/tests/unit/test_episode_attach_review.py backend/tests/unit/test_focus_sessions_adversarial_challenge.py backend/tests/unit/test_focus_sessions_read_boundary.py backend/tests/unit/test_focus_sessions_stress_harness.py backend/tests/unit/test_live_transcript_merge.py backend/tests/unit/test_live_transcript_replay.py backend/tests/unit/test_memory_product_error_sanitization.py backend/tests/unit/test_object_lake.py backend/tests/unit/test_object_lake_config.py backend/tests/unit/test_pusher_audio_projection.py backend/tests/unit/test_space_keys.py backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_users_add_sample_transaction.py backend/utils/other/object_lake.py backend/utils/other/space_keys.py backend/utils/person_evidence_backfill.py backend/utils/sync/assignment.py` (cwd repo root): **exit 0**, 1.81 s; log `c2-r3-black.log`.

Final checks after frozen preflight:

- `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python database/transcript_pointer.py` (cwd backend): **exit 0**, 1.02 s; log `c2-r3-final-codec-types.log`.
- `uvx --from black==26.5.1 black --check --line-length 120 --skip-string-normalization backend/config/object_lake.py backend/database/_client.py backend/database/conversation_finalization_jobs.py backend/database/conversation_terminal_title.py backend/database/conversations.py backend/database/episode_attach_memo.py backend/database/episode_timeline.py backend/database/episodes.py backend/database/helpers.py backend/database/owner_confirmation.py backend/database/recording_sessions.py backend/database/recurring_voice_privacy.py backend/database/review_changes.py backend/database/review_overlay_merge.py backend/database/review_transcript_changes.py backend/database/smart_merge.py backend/database/speaker_assignment_effects.py backend/database/speaker_auto_enroll.py backend/database/speaker_learning_jobs.py backend/database/speaker_profile_authority.py backend/database/speaker_resolution_updates.py backend/database/sync_assignment.py backend/database/transcript_pointer.py backend/database/users.py backend/tests/integration/test_recurring_voice_privacy_firestore.py backend/tests/support/dream_firestore.py backend/tests/support/firestore_query_driver_registry.py backend/tests/unit/memory_import_isolation.py backend/tests/unit/test_conversation_archive_filter_contract.py backend/tests/unit/test_conversation_terminal_family.py backend/tests/unit/test_conversation_transcript_offload.py backend/tests/unit/test_desktop_migration.py backend/tests/unit/test_episode_attach_cost.py backend/tests/unit/test_episode_attach_review.py backend/tests/unit/test_focus_sessions_adversarial_challenge.py backend/tests/unit/test_focus_sessions_read_boundary.py backend/tests/unit/test_focus_sessions_stress_harness.py backend/tests/unit/test_live_transcript_merge.py backend/tests/unit/test_live_transcript_replay.py backend/tests/unit/test_memory_product_error_sanitization.py backend/tests/unit/test_object_lake.py backend/tests/unit/test_object_lake_config.py backend/tests/unit/test_pusher_audio_projection.py backend/tests/unit/test_space_keys.py backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_users_add_sample_transaction.py backend/utils/other/object_lake.py backend/utils/other/space_keys.py backend/utils/person_evidence_backfill.py backend/utils/sync/assignment.py` (cwd repo root): **exit 0**, 0.52 s; log `c2-r3-final-black.log`.

Final codec types: **0 errors / 258 warnings**. Final Black: **50 files unchanged**. Frozen preflight also reran backend import-purity and test module-isolation guards successfully.

Result counts for the additional checks: environment **18 passed / 8 optional warnings / 0 failed**; configuration **9 passed**; source closure **19 registered images passed**; third-party closure passed; all six locks regenerated with **no Git changes**; listen lifecycle passed; privacy integration **14 passed**; all three configured loopback emulator ports checked closed. Import-purity, stub-isolation and async scans passed. Async's first agent-imposed 180-second deadline exited 124; the 900-second retry passed in 147.84 seconds. Black 26.5.1 checked all **50 changed backend Python files**; the final follow-up source was rechecked successfully after frozen preflight. Heavy/test processes and emulators are stopped before handoff. Docker image smoke remains explicitly waived by fix-r1; Docker offline-stack round trip unverified.

Decode grep rerun: `.agent-artifacts/pgf/c2-r3-decode-sites.txt`. The previous full site classification remains valid; round 3 changes the shared encode/retry mechanism and content helper, introducing no new decode callers. Brief rows 1-19 retain preload owners, row 20 uses the approved finalization contention wrapper, and the direct terminal cosmetic helpers keep their local no-IO guard. Nontransactional recovery, agent-capability, projection and F-join callers need no runner changes; public-chat remains inline-only. Encode-only audit: `.agent-artifacts/pgf/c2-r3-encode-sites.txt`; all transcript-bearing transaction owners use the upload/preload boundary. The voice_profiles encoder updates only manual_speaker_assignments, and transcript_files uses an id-less encoding solely to measure inline bytes, so neither can enter offload or needs a runner change.

## Known gaps and handoffs

- Production writes stay off under O1 until C4 wipe coverage passes. No migration or index is required.
- C3 owns backfill/re-encryption, orphan cleanup and registry/receipt, and must account for the 32-reference and 64-MiB operation ceilings before ramping backfill. Absent-pointer list rows can shorten pages without the rule-discard skip cap; aliases of the preload runner remain a mechanical audit follow-up from Flash review. C4 owns quiescing puts, prefix purge and key destruction last. B/W2 carries pointer field changes as content-free document changes. A6 ports the seam after C2.
- Existing public shared long conversations become ineligible for bounded public-chat reads when backfilled; product treatment remains outside C2.
- Full CI originally exited 1 for the two timing-sensitive live-provider files; both isolated reruns passed. No green aggregate full-CI claim. The final focused and 58-file source/caller selections passed after all fixes.
- The tracked `.agent-artifacts/pgf-result.md` remains untouched. Existing app/analysis_options.yaml and app/pubspec.lock edits remain uncommitted; their pre/post-rebase binary patches match SHA-256 `24ea1309984dd69b44cb9c08cd0d6ad04f121eeb768f7d66d2bb2314ab39f0ee`.

Final receipt/body metadata revalidation: `scripts/pr-preflight --pr-body-file .agent-artifacts/pgf/c2-pr-body.md --metadata-only` -> **4 checks passed in 4.64 s**, process exit 0. App edits were again restored to the exact same patch. Only receipt text changed after this validation.

## Workspace preservation

Only the original two app files are left dirty. Frozen gate preservation object: `626f815882e621e6c3809b55af4c88dfd457caf9`. Restored app patch SHA-256: `24ea1309984dd69b44cb9c08cd0d6ad04f121eeb768f7d66d2bb2314ab39f0ee`. The tracked `.agent-artifacts/pgf-result.md` has no diff. Owned command process groups and configured loopback emulators have stopped. The heartbeat is stopped before handoff.

## Cleanup incident for the lead

I mistakenly sent SIGTERM to heartbeat PID `45829` while identifying the timer by command and an assumed parent, rather than verifying this lane's ancestry first. It belonged to Codex PID `40642`, cwd `/Volumes/Ephemeral/scratch/worktrees/omi-rollout-tools`, heartbeat key `pg-short`. Its receipt records `event=killed`, signal 15, at Unix time `1794015769.576229` (`~/.cache/agent-heartbeat/pg-short.45829:1794006964054994000.json`). That lane's Codex work process remains running; I did not stop a work process or alter its files. **Lead follow-up: ensure that lane re-arms its heartbeat.** I did not contact David or another lane.

This lane's actual Codex parent is `46005`; I verified its heartbeat PID `93397` against both parent and exact command before stopping it. Its owned tool session exited 143 as expected. No C2 test, emulator, gate or waiter remains running. This incident changes no implementation or verification result.

## Local commits

- `b937e5183f5` test(storage): record complete round three regression results (frozen gate HEAD)
- `afe5caab56a` feat(storage): bind transcript retries before randomized protection
- `65df9cecc8f` test(storage): record round three implementation and focused verification
- `af90ea383a4` test(storage): verify committed pointers after transactional reencoding
- `73c23ca55c4` feat(storage): preupload transactional transcript candidates with bounded memory
- `67840d9145a` feat(storage): close incomplete lake admission and retain independent content

## Draft PR body

## What changed and why

Long transcript_segments can be stored as encrypted object-lake pointers inside the existing field, through one codec shared by backend, listen, pusher, MCP, export and search. API responses still contain segment lists. Small or unadmitted transcripts retain the existing encoding.

Admitted transactional writes upload candidates outside Firestore, then replay the entire transaction and recompute the logical source digest before randomized grouping protection, from a fresh snapshot before publishing a pointer. The pointer hash and decoded memo always describe the actual uploaded JSON; transaction candidate puts cannot mask cold reads of existing pointers. This lets live in_progress transcripts cross Firestore's 1 MiB ceiling without an oversized inline commit. The boundary permits 32 read preloads plus 32 candidate uploads and three shared content changes (68 outer attempts). Its plaintext memo has a 32-entry/120-second cap and a 64 MiB decoded-object budget; budget failures are typed and retryable.

Transport/key availability errors abort reads and decisions; absent blobs are deleted transcripts and destroyed keys retain a distinct shredded state. Missing/shredded transcripts preserve photos and durable has_content signals during empty-recording cleanup. Malformed dictionaries, including empty ones, remain unreadable content and cannot authorize empty deletion. Missing bucket/release bindings close write admission; unset KMS deliberately selects the existing offline FakeKMS. Deep object verification returns False for destroyed keys and raises SpaceKeyUnavailable for unavailable keys; shallow verification checks metadata only.

O1: OBJECT_LAKE_WRITE_ENABLED stays off in prod until C4's wipe-coverage test is green. Ramp is dev-first via OBJECT_LAKE_WRITE_PERCENT and C1's existing registry plan. This PR adds no env binding, dependency upgrade, schema migration or index. The pusher and batch worker carry the required KMS dependency; existing lock versions are preserved.

C3 reuses offload_inline_transcript for revision-checked backfill and owns legacy re-encryption, orphan GC and registry/receipt; it must account for the memo ceilings before ramping backfill. C4 owns quiescing puts, prefix purge and key destruction last, preserving tombstones. B/W2 carries pointer changes as content-free doc changes. A6 ports the seam after C2. Public-chat's bounded decoder excludes pointer docs; treatment of existing long shared conversations remains a product decision before backfill.

## Product invariants affected

none

## How it was verified

Hermetic/local checks only; GCP tier: none. Every test command unsets GOOGLE_APPLICATION_CREDENTIALS, CLOUDSDK_* and inherited customer-service-account bindings. No production/customer-data access, api.omi.me calls, push, PR or deploy. Exact commands, source identities and individual receipts are in .agent-artifacts/pgf/c2-result.md.

Final focused verification: **243 tests passed**, including all five round-3 review requirements. Full type checking reported **0 errors** (75,544 warnings). Loopback checks passed listen lifecycle and **14 privacy tests**; all owned emulator ports were verified closed. Runtime source closure passed all **19 registered images**, third-party closure passed, all six locks regenerated without Git changes, and Black 26.5.1 passed all **50 changed backend Python files**. Import-purity, test-isolation and async-blocker scans passed; the async scan's first 180-second agent deadline was insufficient, and its 900-second retry passed.

The full CI contract ran all **2,681 files**: **2,679 exited 0 / 2 exited 1**. The two unchanged live-provider files then passed in the same guarded runner with one worker: **134 passed / 3 slow cases deselected**. The earlier Parakeet failure did not recur. After the final codec/cleanup corrections, **2,410 tests passed across 58 related source/caller files**, in addition to the 243 focused tests. This reports cumulative coverage and isolated recovery of the timing failures, not a green exit from the original full-CI command. Rebase changed only two upstream firmware-CI files; the backend tree was byte-identical before/after. Frozen preflight passed all **43 checks in 110.16 s** on `b937e5183f5274c2e6e3c78ccb526ae077a203d5`; metadata validation passed **4 checks**. Final codec type checking passed **0 errors / 258 warnings**, and pinned Black rechecked all 50 changed backend Python files. Existing app edits were temporarily shelved for the gate and restored byte-for-byte. Docker image smoke is waived by fix-r1.md. The Docker offline-stack round trip remains unverified; real-router ASGI tests exercise pointer detail reads with 200/404/500 outcomes.

## Tests

backend/tests/unit/test_transcript_pointer.py pins round trips, flag-off golden encodings, compressed-byte thresholds, missing bindings, no lake IO inside transaction bodies, bounded read/upload retries, failed-upload non-commit, decode states, aggregate memo bytes, consent and C3 CAS.

backend/tests/unit/test_conversation_transcript_offload.py covers the transaction owners and reader surfaces, live writes above 1 MiB, source changes during upload, randomized grouping sidecars, exact memo/blob equality, invalid optional sidecars, kill-switch rechecks, photo/has_content retention, malformed-pointer cleanup, and destroyed/unavailable verifier keys. backend/tests/unit/test_object_lake_config.py retains the deterministic cohort contract with a configured bucket.

Decode/encode audits were rerun. Brief rows 1-19 use preload owners; finalization admission uses the approved contention wrapper; terminal cosmetics enforce a local no-IO guard. Recovery, agent-capability, projection and F-join reads are nontransactional. The voice_profiles encode is receipt-only, and transcript_files uses an id-less inline size measurement; neither can offload. Protection migration retains existing pointers. No reader is left relying on inline-only decoding except deliberately bounded public chat.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4895 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.

Scope provenance: C1-result.md Review disposition assigned tombstones, decompression bounds and authority-read budgeting to C2; those inherited library changes remain in this branch. The inherited .github dead-code allowlist removal follows its own instruction to remove the entry when C2 adds its first caller; round 3 makes no .github edits. Round 3 extends scope only to config/object_lake.py admission and the existing cohort test setup, as required by fix-r2.md. Deep verification returns False for destroyed keys and raises SpaceKeyUnavailable for temporarily unavailable keys; shallow verification checks metadata only. C3 must account for both the 32-reference and 64-MiB operation ceilings before backfill.
