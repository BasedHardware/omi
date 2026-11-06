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
