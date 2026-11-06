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
