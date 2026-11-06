# C2 round 2 implementation result

Status: C2 focused and frozen-tree gates are green; the full CI-shaped unit run remains in progress.
Updated: 2026-11-06T19:20:50.397193+00:00
Repository: BasedHardware/omi. Branch: lane/pgf-c2.
Base after the required fetch/rebase: 4b1c40b5ef03242b82013a64c1dc941728715bab.
Implementation checkpoint: 0b11e281de8935610f57356c62f3177db47d20be.
GCP tier: none. No production/API/customer-data access, push, PR, deploy, or flag expansion.

## What was built

- Single transcript pointer-or-inline codec, typed read outcomes, request/context memo, upload-before-reference writes, and post-commit revision-checked swaps.
- Cold-pointer transaction preloads for processing, review, speaker/voice publication, episodes, live transcript updates, translation, sync assignment, final-pass promotion, finalization admission, privacy scrubs, and empty-recording cleanup.
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
- `backend/pusher/pylock.toml`
- `backend/pusher/requirements.txt`
- `backend/tests/integration/test_recurring_voice_privacy_firestore.py`
- `backend/tests/support/dream_firestore.py`
- `backend/tests/support/firestore_query_driver_registry.py`
- `backend/tests/unit/test_conversation_archive_filter_contract.py`
- `backend/tests/unit/test_conversation_terminal_family.py`
- `backend/tests/unit/test_conversation_transcript_offload.py`
- `backend/tests/unit/test_episode_attach_cost.py`
- `backend/tests/unit/test_episode_attach_review.py`
- `backend/tests/unit/test_live_transcript_merge.py`
- `backend/tests/unit/test_live_transcript_replay.py`
- `backend/tests/unit/test_object_lake.py`
- `backend/tests/unit/test_pusher_audio_projection.py`
- `backend/tests/unit/test_space_keys.py`
- `backend/tests/unit/test_transcript_pointer.py`
- `backend/utils/other/object_lake.py`
- `backend/utils/other/space_keys.py`
- `backend/utils/person_evidence_backfill.py`
- `backend/utils/sync/assignment.py`

The tracked `.agent-artifacts/pgf-result.md` is restored to origin/main (empty branch diff). This lane's report and draft PR body are under `.agent-artifacts/pgf/`. The unrelated app/analysis_options.yaml and app/pubspec.lock edits are preserved; the temporary preflight stash was restored and its exact binary patch hash matched. The task stash was dropped after restoration.

## Deviations and scope extensions taken

All eight corrections in fix-r1.md were implemented under the lead's explicit approval: helpers collection filtering; finalization admission; recording cleanup; sync load validation; bounded retry amendment; batch worker KMS pin/lock; speaker authority/auto-enroll/users publication; episode memo/timeline owners.

Additional necessary test caller migration: test_episode_attach_cost.py and test_episode_attach_review.py inject their existing operational failures through the locally imported run_preloaded_transactional, replacing the retired runner seam. This keeps failure injection scoped to memo operations while timeline transactions use the shared runner normally. Assertions remain unchanged; no compatibility wrapper was added.

No round-2 edits were made under .github/, database/jobstore/, database/cells/, database/directory/, or testing/store_fixtures.py. The pre-existing branch's dead-code allowlist removal and C1 review files are retained, as recorded in the round-1 receipt. No new C1 API changes were required.

The original no-argument run-unit-ci.sh command now requires a mode, so it is run with --changed-files. Its selector requires the full backend suite for database/_client.py. test.sh is executed by that CI runner with the selected list; there is no redundant second all-suite run.

No anx writes or messages were made, per the implementation task's escalation rule. The earlier scope ask is superseded by fix-r1.md and was not used as an approval gate.

## Verification

Every test command uses `python3 .agent-artifacts/pgf-c2-test-env.py`, which removes GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable, service-account/Firebase credential paths and inherited project bindings; it supplies only demo hints and a closed loopback metadata endpoint. Python is backend/.venv (3.11.15). Heavy commands run through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 --`.

Current wrapper: `python3 .agent-artifacts/pgf-c2-test-env.py /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- <payload>`

| Exact payload / command | Result |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py -q` | Initial: 186 passed, 3 failed. Corrected rerun on the final implementation: **190 passed, 0 failed**. The historical-version eviction regression and two unrelated projection-fake failures were corrected. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_episode_attach_cost.py backend/tests/unit/test_episode_attach_review.py -q` | **66 passed, 0 failed**. |
| `env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib bash backend/scripts/run-unit-ci.sh --changed-files "$PWD/.agent-artifacts/pgf/c2-changed-files.txt"` | Environment: 18 passed, 8 optional warnings, 0 failed. Full type check: **0 errors**, 75,445 warnings. `test.sh` is running the selected **2,677 files**; terminal counts pending. PID 81323, command session 32410, log c2-unit-ci.log; 50-minute heartbeat is armed and touched on wakes. |
| `bash test-preflight.sh` (backend/) | **18 passed, 8 optional warnings, 0 failed**. |
| `.venv/bin/python scripts/scan_import_time_side_effects.py` (backend/) | Exit 0. |
| `.venv/bin/python scripts/check_module_stub_pollution.py` (backend/) | Exit 0. |
| `.venv/bin/python scripts/scan_async_blockers.py --dirs routers utils` (backend/) | Exit 0. |
| `make runtime-image-source-closure` | Exit 0, **19 registered images**. |
| `backend/.venv/bin/python backend/scripts/runtime_image_contracts.py check-third-party` | Exit 0; worker KMS gap resolved. Existing open dependency-set exemptions are unchanged. |
| `.venv/bin/python -m pytest tests/integration/test_recurring_voice_privacy_firestore.py -q` (backend/) | **14 skipped** without an emulator/credentials; not counted as a pass. |
| `uv pip compile backend/diarizer/requirements-batch-pipeline.txt --format pylock.toml --python 3.11.15 --python-platform x86_64-unknown-linux-gnu --output-file backend/diarizer/pylock.batch-pipeline.toml` | Exit 0. Only `google-cloud-kms==3.6.0` added; no package changed version or was removed. |
| `bash backend/scripts/update-python-lock.sh` | Exit 0; all six managed locks regenerated with **no Git changes**. No upgrade flag used. |
| `env OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf/c2-pr-body.md" BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | **41 checks passed**, exit 0, frozen clean tree at `0b11e281de8935610f57356c62f3177db47d20be`; 637.81 s. User's app edits were stashed for this command, then restored and hash-verified. |
| `scripts/pr-preflight --suggest` | Ran; required invariant citation: none. |
| `scripts/pr-preflight --lane local --pr-body-file .agent-artifacts/pgf/c2-pr-body.md --metadata-only` | **4 checks passed** before final receipt text updates. Final body validation remains to be refreshed. |
| `uvx --from black==26.5.1 black --line-length 120 --skip-string-normalization <round-2 Python files>` + pinned pre-commit formatter | Passed; every changed Python file was formatted by the pinned hook. The backend venv does not expose a Black executable, so the pinned tool/hook is used. |
| `git diff --check` | Passed. |

The static batch is `.agent-artifacts/pgf/c2-static-checks.py`; its exact commands, working directories, UTC epoch start times, elapsed times and exit codes are in c2-static-receipts.jsonl. Logs remain under `.agent-artifacts/pgf/c2-*.log`. The full suite is the only implementation validation still in flight.

## Known gaps

- Docker image smoke is waived by fix-r1.md because Docker is unavailable. Runtime source and third-party closure remain required.
- The optional Firestore emulator suite was not rerun in round 2. The offline HTTP harness was not started because local Docker is unavailable. Hermetic reader/domain tests are not a provider-backed or deployed round trip.
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

Hermetic local tests only. GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before each command. No production access, API calls or customer data. Exact commands and final counts are recorded in .agent-artifacts/pgf/c2-result.md. Docker is unavailable locally; image smoke is waived by the lead. Runtime source and third-party closure guards are required. The focused codec/domain run passed 190 tests; the two migrated episode caller files passed 66 tests. Full type checking reported 0 errors. Frozen-tree make preflight passed 41 checks, and source plus third-party runtime closure passed. The 2,677-file CI-shaped unit selection remains in progress; 14 privacy integration tests skipped without an emulator. No offline HTTP harness or deployed acceptance is claimed.

## Tests

backend/tests/unit/test_transcript_pointer.py: codec round trips, flag-off golden encodings, compressed-byte threshold, no-IO transaction guard, preload retries, decode taxonomy, memo hygiene, consent and deferred CAS.
backend/tests/unit/test_conversation_transcript_offload.py: pointer reader surfaces, domain refusals, oversized transcripts, tombstone races, malformed keys and authority read budgets.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4892 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.
