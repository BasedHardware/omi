## What changed and why

Oversized transcript_segments can be stored as an encrypted object-lake pointer inside the existing field. The shared codec resolves pointers for backend, listen, pusher, MCP, export and search; migrated transaction owners use a content-addressed preload/retry boundary and revision-checked post-commit swaps. Deleted-owner key tombstones prevent rekeying, malformed key rows remain retryable, transcript decompression is bounded to 32 MiB, and key-document authority reads are budgeted (one per unwrap, two per put).

Writes remain default-off/0 admission. O1: OBJECT_LAKE_WRITE_ENABLED stays off in prod until C4's wipe-coverage test is green. Ramp is dev-first via OBJECT_LAKE_WRITE_PERCENT; C1's registry retains ramp metadata and ownership. No new env binding, dependency upgrade, schema migration or index is introduced; space_keys already exists and retains content-free destruction tombstones.

C3 reuses offload_inline_transcript for backfill and owns legacy re-encryption, orphan janitor and registry/receipt. C4 owns account-wipe integration, quiescing in-flight puts, prefix purge and key destruction last (preserving tombstones). B/W2 syncs pointer field changes as content-free doc changes. A6 ports the seam unchanged. Public-chat's bounded decoder excludes pointer docs; existing long shared conversations need a later product decision before backfill.

C2 also covers finalization admission, empty-recording cleanup, sync canonical/candidate admission, voice publication, and episode memo/timeline transactions. Preloads allow up to 32 distinct documents plus three content-change retries (36 total attempts). The batch worker pins KMS to match the backend runtime; existing locked versions are preserved.

## Product invariants affected

none

## How it was verified

Hermetic/local verification only; GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before every command. No production access, API calls, customer data, push, PR or deploy. Exact commands and phase results are in .agent-artifacts/pgf/c2-result.md.

After the final rebase, 625 tests passed across 14 files, covering the C2 core, overlapping episode code, new upstream episode/pusher tests, People inventory and monitoring. Earlier focused runs passed 280 C2/terminal tests, 66 episode caller tests, 114 desktop tests, 70 memory/feedback tests, 7 focus tests (12 slow cases deselected), 6 memory-product tests and 5 sample-transaction tests. Full type checking reported 0 errors. Owned loopback checks passed listen lifecycle, 14 privacy tests and 31 People writer checks; every emulator stopped. Runtime source and third-party closure passed. Docker image smoke is waived by fix-r1.md; the Docker offline-stack round trip remains unverified. The local ASGI detail route tests cover pointer 200/404/500 outcomes.

The original 2,677-file CI selection was covered in two phases (1,332 atomic results, then 1,386 files with 41 deliberate repeats), followed by corrective reruns. The initial command was intentionally checkpointed/interrupted (exit 137); the continuation exited 1 with six failing files, all retained in the receipt. Corrections and upstream monitoring repair clear five of those. Soniox's 80ms timing assertion passed its unchanged isolated rerun (16 passed). The current selection adds four upstream files, all covered by the post-rebase run: 2,681 unique files covered, 2,680 exit 0 (including marker-only skips), one unresolved file. test_qualify_parakeet_route::test_stream_timeout_retains_diagnostics reproducibly fails in unchanged main code (33 passed / 1 failed on both runs); this PR does not claim full-unit green.

Final frozen preflight: pending. Metadata-only receipt validation follows its completion.

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
