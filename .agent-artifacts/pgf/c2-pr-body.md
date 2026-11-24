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

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4938 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.

Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 3549 -> 3551 | Wrap the existing admission owner in the transcript preload boundary without changing lead2 queue state.
Line-Count-Exception: backend/database/users.py | 2516 -> 2517 | Preserve the voice publication transaction and move its runner to the shared preload boundary.
Line-Count-Exception: backend/utils/sync/assignment.py | 1527 -> 1536 | Validate lake-pointer availability at the existing transaction load boundary before candidate or canonical selection.

Scope provenance: C1-result.md Review disposition assigned tombstones, decompression bounds and authority-read budgeting to C2; those inherited library changes remain in this branch. The inherited .github dead-code allowlist removal follows its own instruction to remove the entry when C2 adds its first caller; round 3 makes no .github edits. Round 3 extends scope only to config/object_lake.py admission and the existing cohort test setup, as required by fix-r2.md. Deep verification returns False for destroyed keys and raises SpaceKeyUnavailable for temporarily unavailable keys; shallow verification checks metadata only. C3 must account for both the 32-reference and 64-MiB operation ceilings before backfill.

## Merge-owner review fixes

B1: normal encoding and backfill share an explicit visibility/deletion/privacy policy: private or unknown visibility, deleted rows and locked rows remain inline. Partial writes use the authoritative stored policy, so a stale shared payload cannot override current private state. Lifecycle decorators prepare inline; the accepted transaction runs all lifecycle and recurring-voice filters before requesting an upload through the existing preupload/replay boundary. Deleted/stale/missing-owner refusals and create-if-absent collisions therefore upload nothing before their guards. Regressions exercise the decorated writers and verify privacy filtering precedes every upload.

B2: runtime write admission is closed outside local/offline even with a real bucket and KMS key. Both the runtime-env and deploy validators independently refuse a positive write percent or enabled master flag. A TODO keeps the fence in place until per-object DEKs are implemented. This supersedes the earlier dev-first ramp wording: deployed writes remain blocked pending per-object DEKs as well as C4 wipe qualification.
