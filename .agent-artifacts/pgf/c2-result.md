# C2 round 3 implementation result

Status: implementation committed; verification in progress. Updated 2026-11-06T23:29:25.054625+00:00.
Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean`. Branch: lane/pgf-c2.
Fetched/rebased base: `34125ccd5fbd6c47885d23abe70e9a1448b7515e`; rebase reported already up to date.
GCP tier: none. No production access, api.omi.me calls, customer data, push, PR, deploy, new flag admission, anx write or message to David.

## What was built

The inherited C2 implementation supplies the single transcript pointer-or-inline codec, typed missing/shredded/unavailable read states, transaction preload owners across conversation/review/speaker/sync/cleanup/episode paths, reader-surface coverage, C3 backfill CAS, worker dependencies, and listen/pusher documentation.

Round 3 implements all five fix-r2.md items:

1. Every admitted transactional encode above the compressed inline threshold aborts before staging its transcript write, uploads the candidate outside the transaction, then reruns the complete transaction from a fresh source snapshot. Only the exact recomputed digest may reuse the uploaded pointer. This applies to live in_progress rows, including transcripts above Firestore's 1 MiB ceiling. Admission-off encoding and oversize failures retain main's behavior. Failed uploads never commit inline data; abandoned blobs belong to C3.
2. Missing/shredded transcripts remove only the transcript signal from raw_conversation_has_content. Photos and durable has_content still prevent empty deletion; retryable read failures continue to abort cleanup.
3. Admission requires configured bucket and release bindings. KMS remains deliberately optional for the specified hermetic FakeKMS mode; absent release defaults to v1. Flag-on/100% without a bucket stays inline and never puts.
4. The decoded operation memo has both a 32-entry/120-second cap and a 64 MiB aggregate budget measured over decoded Python containers and strings. A budget breach raises retryable TranscriptMemoBudgetExceeded (a TranscriptPointerFetchError), and the owning operation clears plaintext in finally. Encode checks room before making its memo copy.
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

Initial focused command: `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py -q` -> **220 passed / 2 failed**. The failures were old tests asserting a deferred drain and inline output; both were migrated to assert the committed pointer and decoded translation/identity under the new ruling.

Corrected focused command: `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py backend/tests/unit/test_object_lake_config.py -q` -> **231 passed / 0 failed** in 67.84 seconds.

Environment validation: **18 passed, 8 optional warnings, 0 failed**. Import-time side effects and module-stub pollution scans exited 0. The first async scan hit its agent-imposed 180-second deadline (exit 124), so a 900-second retry is queued; the historical receipt took 346 seconds for this full-tree scanner.

Current run receipts are `.agent-artifacts/pgf/c2-r3-static-receipts.jsonl`, `c2-r3-command-receipts.jsonl`, and `c2-r3-*.log`. Final counts and exact commands will replace this in-progress entry.

Decode grep rerun: `.agent-artifacts/pgf/c2-r3-decode-sites.txt`. The previous full site classification remains valid; round 3 changes the shared encode/retry mechanism and content helper, introducing no new decode callers. Brief rows 1-19 retain preload owners, row 20 uses the approved finalization contention wrapper, and the direct terminal cosmetic helpers keep their local no-IO guard. Nontransactional recovery, agent-capability, projection and F-join callers need no runner changes; public-chat remains inline-only.

## Known gaps and handoffs

- Production writes stay off under O1 until C4 wipe coverage passes. No migration or index is required.
- C3 owns backfill/re-encryption, orphan cleanup and registry/receipt, and must account for the 32-reference and 64-MiB operation ceilings before ramping backfill. C4 owns quiescing puts, prefix purge and key destruction last. B/W2 carries pointer field changes as content-free document changes. A6 ports the seam after C2.
- Existing public shared long conversations become ineligible for bounded public-chat reads when backfilled; product treatment remains outside C2.
- Historical round-2 full selection had one unchanged-main Parakeet timing failure. Current full-CI status will be recorded after its run; no current green full-suite claim is made yet.
- The tracked `.agent-artifacts/pgf-result.md` remains untouched. Existing app/analysis_options.yaml and app/pubspec.lock edits remain uncommitted; their pre/post-rebase binary patches match SHA-256 `24ea1309984dd69b44cb9c08cd0d6ad04f121eeb768f7d66d2bb2314ab39f0ee`.

## Local commits

- `33877eeb59d` feat(storage): close incomplete lake admission and retain independent content
- `741b4e1dd24` feat(storage): preupload transactional transcript candidates with bounded memory
- `cd44123aae7` test(storage): verify committed pointers after transactional reencoding

## Draft PR body

## What changed and why

Oversized transcript_segments can be stored as an encrypted object-lake pointer inside the existing field. The shared codec resolves pointers for backend, listen, pusher, MCP, export and search; migrated transaction owners use a content-addressed preload/retry boundary and snapshot-recomputed candidate uploads before transaction replay. C3 backfill retains its update-time CAS swap. Deleted-owner key tombstones prevent rekeying, malformed key rows remain retryable, transcript decompression is bounded to 32 MiB, and key-document authority reads are budgeted (one per unwrap, two per put).

Writes remain default-off/0 admission. O1: OBJECT_LAKE_WRITE_ENABLED stays off in prod until C4's wipe-coverage test is green. Ramp is dev-first via OBJECT_LAKE_WRITE_PERCENT; C1's registry retains ramp metadata and ownership. No new env binding, dependency upgrade, schema migration or index is introduced; space_keys already exists and retains content-free destruction tombstones.

C3 reuses offload_inline_transcript for backfill and owns legacy re-encryption, orphan janitor and registry/receipt. C4 owns account-wipe integration, quiescing in-flight puts, prefix purge and key destruction last (preserving tombstones). B/W2 syncs pointer field changes as content-free doc changes. A6 ports the seam unchanged. Public-chat's bounded decoder excludes pointer docs; existing long shared conversations need a later product decision before backfill.

C2 also covers finalization admission, empty-recording cleanup, sync canonical/candidate admission, voice publication, and episode memo/timeline transactions. The boundary allows 32 distinct read preloads and 32 candidate uploads plus three shared content-change retries (68 total attempts). The decoded memo is capped at 32 entries and 64 MiB of decoded Python objects, with a typed retryable byte-budget failure. Oversized live in_progress writes publish pointers before crossing Firestore's 1 MiB ceiling; retries recompute candidates from fresh transactional snapshots. Missing/shredded transcripts preserve photos and durable has_content markers during empty cleanup. Missing bucket/release bindings close admission; unset KMS intentionally selects offline FakeKMS. The batch worker pins KMS to match the backend runtime; existing locked versions are preserved.

## Product invariants affected

none

## How it was verified

Hermetic/local verification only; GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before every command. No production access or calls to api.omi.me; no customer data, push, PR or deploy. Exact commands and phase results are in .agent-artifacts/pgf/c2-result.md.

After the final rebase, 625 tests passed across 14 files, covering the C2 core, overlapping episode code, new upstream episode/pusher tests, People inventory and monitoring. Earlier focused runs passed 280 C2/terminal tests, 66 episode caller tests, 114 desktop tests, 70 memory/feedback tests, 7 focus tests (12 slow cases deselected), 6 memory-product tests and 5 sample-transaction tests. Full type checking reported 0 errors; post-rebase episodes.py checking also reported 0 errors (381 warnings). Owned loopback checks passed listen lifecycle, 14 privacy tests and 31 People writer checks; every emulator stopped. Runtime source and third-party closure passed. Docker image smoke is waived by fix-r1.md; the Docker offline-stack round trip remains unverified. The local ASGI detail route tests cover pointer 200/404/500 outcomes.

The original 2,677-file CI selection was covered in two phases (1,332 atomic results, then 1,386 files with 41 deliberate repeats), followed by corrective reruns. The initial command was intentionally checkpointed/interrupted (exit 137); the continuation exited 1 with six failing files, all retained in the receipt. Corrections and upstream monitoring repair clear five of those. Soniox's 80ms timing assertion passed its unchanged isolated rerun (16 passed). The current selection adds four upstream files, all covered by the post-rebase run: 2,681 unique files covered, 2,680 exit 0 (including marker-only skips), one unresolved file. test_qualify_parakeet_route::test_stream_timeout_retains_diagnostics reproducibly fails in unchanged main code (33 passed / 1 failed on both runs); this PR does not claim full-unit green.

Final frozen preflight passed **43 checks in 196.87s** on `cac0edb73e7a55d1e2b0d640d5b6753d84dc7995`. Pinned Black 26.5.1 passed all 48 changed backend Python files. Final receipt metadata-only preflight passed **4 checks in 18.27s**.

## Tests

backend/tests/unit/test_transcript_pointer.py: codec round trips, flag-off golden encodings, compressed-byte threshold, no-IO transaction guard, preload/upload retry limits, decode taxonomy, aggregate memo byte budget, consent and C3 backfill CAS.
backend/tests/unit/test_conversation_transcript_offload.py: pointer reader surfaces, actual HTTP detail 200/404/500 outcomes, domain refusals, direct-SDK terminal no-IO guards, live transcripts above 1 MiB, source changes during candidate upload, photo-bearing cleanup, destroyed/unavailable deep-verifier key outcomes, tombstone races, malformed keys and authority read budgets.


Reader-site audit after rebase: brief §6a rows 1–19 use preload owners; row 20 finalization admission uses the approved contention-runner wrapper. Empty-recording cleanup, voice publication and episode memo/timeline attach are also transactional and migrated. Terminal cosmetic helpers enforce a local memo-only guard. No runner change is needed for non-transactional recovery status, self-heal, agent-capability reads/fingerprints, batch/shadow projections or stuck-backfill; overlay fingerprint reads inherit their owning transaction guard. Shared preparation covers list/detail/MCP/export/search/notifications. The bounded public-chat decoder intentionally excludes pointer docs. The new upstream f_join.previous_transcript read is outside transactions and retains its owner's conservative no-answer policy; no new runner is needed. Emulator-script direct decodes are setup/assertion reads. Fresh-prepared admitted transaction encodes upload before replay; protection migration retains existing pointers.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4894 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.

Scope provenance: C1-result.md Review disposition assigned tombstones, decompression bounds and authority-read budgeting to C2; those inherited library changes remain in this branch. The inherited .github dead-code allowlist removal follows its own instruction to remove the entry when C2 adds its first caller; round 3 makes no .github edits. Round 3 extends scope only to config/object_lake.py admission and the existing cohort test setup, as required by fix-r2.md. Deep verification returns False for destroyed keys and raises SpaceKeyUnavailable for temporarily unavailable keys; shallow verification checks metadata only. C3 must account for both the 32-reference and 64-MiB operation ceilings before backfill.
