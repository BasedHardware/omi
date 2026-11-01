# WQ21 — batch privacy generation memo: BLOCKED, no implementation

Date: 2026-10-27. Branch: `lane/firestore-reads-wq21-bpp-gen`.
Inspected base: `f10cbeb12c0e467a2a244502509b0d87e78ff4c5`.

## Disposition

Taking the brief's explicit correctness stop: **I have not established a complete,
atomic writer fence and am not delivering a partial memo.** Production source,
`KNOWN_LEVERS`, registry/contracts, and all `FIRESTORE_READ_LEVERS` values are
unchanged. `bpp_generation_memo` is not registered or implemented. This commit
contains the investigation and hermetic evidence only; it is not a deployable
read-reduction candidate. The loop should grade this lane BLOCKED, not SUPPORTED.

No PR, push, deployment, GCP read/write, or service configuration change was
performed. GCP tier: none. `backend-sync` and `backend-sync-backfill` were not
modified or contacted. Their production writer revisions were not verified.

## What I found

`assert_batch_write_allowed` reads, in order:

1. `account_deletions/{uid}`: existence and normalized `wipe_status`; only
   `cancelled` and `billing_failed` permit access when a marker exists.
2. `users/{uid}`: existence, `data_protection_level`, `migration_status`, and
   `private_cloud_sync_enabled` for batch-live records.
3. `batch_pipeline_privacy/{sha256(uid)}`: `generation`, `blocked`, `purging`.
4. For each distinct source and each redirect target:
   `users/{uid}/deleted_conversations/{cid}` existence, then
   `users/{uid}/conversations/{cid}` existence, `deleted`, `sync_merged_into`,
   `record_lane_owner`, `uses_custom_stt`, `private_cloud_sync_enabled`.

Redirect cycles, missing redirect targets, ID validation, and the distinct-document
budget also affect the answer. A new conversation ID cannot inherit another ID's
answer just because the UID/generation match.

The existing `generation` is an **admission/erasure epoch** recorded in work items
and compared to `expected_generation`. `advance_privacy_generation` also sets
`purging=True` and preserves blocking. Calling it for every conversation mutation
would change job validity and admission semantics. A cache invalidation counter
must be separate from this epoch, even if stored on the same privacy document.

The real WQ12 scope is one Firestore transaction callback attempt, not the sync
job/task attempt. `FirestoreStore.run` constructs a fresh view on every callback;
`ProjectionSession.prepare` resets the memo. `batch_artifact_authorize` separately
opens a transaction and supplies no memo. Cross-transaction reuse requires a new
scope and an actual transactional generation read on every reused decision.

`snapshots=` additionally exports full user/conversation rows. Callers in
`utils/batch_pipeline/retention.py` and `utils/enrichment/custody.py` consume those
rows. A counter covering only privacy fields cannot authorize reusing unrelated
row fields. A future implementation must either fence all exported row changes
or keep these snapshot consumers on live reads.

## Writer enumeration from current source

These are verified writer families requiring coverage, **not a claim of proven
writer closure**. No new writer was fenced in this lane.

| Authority | Real writer(s) / source location | Current atomicity and required work |
|---|---|---|
| Conversation deletion intent | `database/conversation_tombstones.py:18` `record_deletion` | Standalone `create` precedes chunk cleanup and conversation-specific batch purge. That purge does not advance the account epoch. Intent and a new invalidation token must commit together, including cleanup failures. |
| Private-cloud consent | `database/users.py:279` → `speaker_auto_enroll.update_privacy`, `database/speaker_auto_enroll.py:172` | Existing transaction updates consent plus the **speaker** privacy version; it does not touch batch privacy. Must also invalidate batch privacy in that transaction. |
| Conversation retraction | `database/speaker_auto_enroll.py:203` `retract_conversation` | Sets `deleted=True` in its own transaction, even without learned people; no batch-generation write. Must fence independently of the later hard delete. |
| Protection/migration start | `database/users.py:1666` `set_data_protection_level`, `:1683` `set_migration_status` | User `set` commits before `purge_batch_owner` advances the epoch. A memo could hit in that gap or after a failed purge. Need atomic source/token writes, preserving the erasure protocol. |
| Migration completion | `database/users.py:1693` `finalize_migration` | Direct user update removes migration state and changes protection, without advancing batch generation. |
| Account marker creation/status | `database/users.py:389–960`: `set_user_deletion_feedback`, `mark_user_deletion_wipe_running`, `_mark_user_deletion_wipe_intent_txn`, `_mark_user_deletion_wipe_started_txn`, `mark_wipe_completed` (in `database/account_deletion_transitions.py`), `record_late_agent_vm_cleanup` (same module), `mark_user_deletion_wipe_failed`, `_mark_user_deletion_billing_failed_txn`, `cancel_user_deletion_wipe`, `_claim_deletion_wipe_txn`, `_claim_deletion_wipe_task_txn` | Mix of standalone merges and transactions. Creation itself can deny, and transitions out of allowed statuses can deny. Each relevant source/token write must be atomic on the customer-data plane. The process-local `cache_writer('deletion_marker_cache')` decorator is not this fence. |
| Conversation creation/upsert/result persistence | `database/conversations.py:1085` `upsert_conversation_with_lifecycle`, `:1187` `persist_processing_result_with_lifecycle`, `:1395` `create_conversation_if_absent_with_lifecycle` | Full/dynamic prepared payloads, transaction `set`, transaction `create`, and standalone `create`. Privacy fields can arrive in model payloads; literal-key grep alone misses these. |
| Generic conversation patch | `database/conversations.py:2034` `update_conversation` | Read/prepare/direct `update`. Callers include `routers/listen/conversations.py:183,568`, which set `uses_custom_stt=True`. Fence the persisted payload atomically, not only these two callers. |
| Record ownership claim | `database/conversations.py:2081` `claim_record_lane_owner` | Direct update with an update-time CAS and a returned new update time. Atomic token addition must preserve the precondition, typed failed-CAS behavior, and response metadata. |
| Batch admission ownership patch | `database/batch_pipeline_intake.py:92` → `database/batch_pipeline_store.py:145–148` `flush` | Buffers `record_lane_owner` patch, then stages it on the customer-data transaction. It bypasses the standalone ownership-claim helper. |
| Sync canonical/donor/ancestor mutation | `utils/sync/assignment.py:277,817–836` | Record-span update; canonical set/update; donor `deleted`/`sync_merged_into`; ancestor redirect patches. All successful branches and dynamically encoded privacy fields need the same atomic token fence. |
| Smart merge donor/survivor/ancestry | `database/smart_merge.py:249` `absorb_conversation`, writes `:375–378` | Separate persistence owner; writes payloads produced by its plan callback. Fencing only sync assignment would miss this path. |
| Hard conversation deletion | `database/conversations.py:2418` `delete_conversation`; `database/recording_sessions.py:249` `tombstone_and_delete_empty_conversation`, transaction delete `:343` | Existence of redirect targets is authority. Empty recording cleanup has a separate transaction delete and does not use the user-intent tombstone writer. |
| Account/subtree wipe | `database/user_data_deletion.py:17` `purge_user_subtree` | Existing protocol blocks/advances before recursive erasure, then removes children and root. Any new token must survive this walk or fail closed when absent; it must not authorize reuse after token deletion/recreation. |
| Privacy epoch and purge state | `database/batch_pipeline_privacy.py:170` `advance_privacy_generation`, `:188` `finish_privacy_purge` | Existing epoch bump is atomic with its own blocked/purging update. Finish changes `purging` without advancing the epoch. Preserve epoch meaning; invalidate the separate cache token as needed. |

Legal holds: `database/legal_holds.py:154` `_place_legal_hold_transaction` writes
`legal_holds/{uid}` after reading the destructive-operation gate and account
marker. **The batch privacy assertion does not read legal holds or that gate.**
Adding legal holds to its allow/deny policy would be a behavior change, not a
semantically identical memo. Existing destructive-operation hold fencing remains
separate. No new hold semantics are proposed here.

Additional scope to settle before claiming closure:

- If full `snapshots` are reused, metadata writers (for example screen-frame
  `set(..., merge=True)` in `database/screen_frames.py:342,373`) and arbitrary
  conversation/user metadata edits also require coverage or live snapshot reads.
- Administrative and staging writes exist: `scripts/staging/replay.py:262,307`
  writes raw user and conversation payloads for restricted pseudo-owners;
  `migrations/001_enhanced_protection_default.py` calls the protection/migration
  helpers. This lane did not establish that every deployed process, old revision,
  or operator uses a future fencing implementation.
- The existing `_client.py` SDK installers cover other contracts. The memory
  change-head hook filters memory collections; the list-projection hook targets
  its projection contract. Neither supplies a batch-privacy token. A new GAPIC
  hook could cover dynamic payloads, but needs its own proof for sync/async
  document writes, transactions, atomic batches, non-atomic `batch_write`, direct
  deletes, preconditions, response-result slicing, write budgets, and composition
  with those existing hooks. I did not implement or certify that alternative.

## Hermetic evidence and measured reads

Reproducer: `WQ21-privacy-audit.py`; captured result: `WQ21-privacy-audit.json`.
Run at repository root:

```sh
backend/.venv/bin/python .agent-brief/WQ21-privacy-audit.py
```

It blocks outbound network, uses synthetic IDs and the existing strict document
transaction fixture, and invokes real production privacy/writer functions.
It does not model Firestore snapshot isolation, contention or rollback, and is
an investigation artifact rather than a regression expectation to preserve.

For **three actual writers**, a live check first returns generation 7, then the
writer commits a privacy change, the generation remains 7, and a fresh live
check correctly denies:

| Writer exercised | Generation before → after | Fresh live denial |
|---|---|---|
| `speaker_auto_enroll.update_privacy` | 7 → 7 | `recording_privacy_changed` |
| `speaker_auto_enroll.retract_conversation` | 7 → 7 | `conversation_deleted` |
| `conversation_tombstones.record_deletion` | 7 → 7 | `conversation_deleted` |

The tombstone reproducer stops at an intentionally failed external-cleanup
boundary, after durable intent. These are counterexamples to **reusing the
existing epoch as a cache token**, not claims that today's live privacy guard
returns stale results. It denies correctly.

Measured document-get counts for 20 checks of the same owner/source:

| Existing path | Privacy reads |
|---|---:|
| WQ12 off, one transaction | 100 |
| WQ12 on, one transaction | 5 |
| WQ12 on, 20 separate transactions | 100 |
| This lane, before → after | 100 → 100 for separate transactions; no implementation |

The existing real-admission WQ12 test also passes: 20 distinct conversations
cost 124 total reads off versus 67 on (24 unrelated reads plus 100 versus 43
privacy reads). This does not measure this lane or prove fleet savings.

A fully fenced memo reusing the same owner/source across 20 transactions could
theoretically cost 5 + 19 = 24 reads if a separate token field lives on the
already-read privacy document, or 6 + 19 = 25 with a new token document. Those
are arithmetic targets, **not measurements or a delivered effect**. Actual
implemented savings in this lane: **zero**. Candidate hit/miss/mismatch and
bump-on-write regression tests: **NOT IMPLEMENTED**, because no candidate ships.

## Verification

Each suite ran in its own pytest process via `omi-heavy`, using this worktree's
`backend/.venv`:

```sh
cd backend
.venv/bin/python -m pytest -q tests/unit/test_fsr_wq12_batch_privacy.py
.venv/bin/python -m pytest -q tests/unit/test_batch_pipeline_privacy.py
.venv/bin/python -m pytest -q tests/unit/test_conversation_tombstones.py
.venv/bin/python -m pytest -q tests/unit/test_speaker_auto_enroll.py
```

Results: **43 + 14 + 13 + 83 = 153 passed**. The last suite emitted five
dependency deprecation warnings. Raw local log:
`/Volumes/Ephemeral/scratch/wq21-focused.log`.

Hermetic reproducer: **PASS**, including all read-count and writer-counterexample
assertions. No runtime lever values are changed by it; its WQ12 measurement
patches the imported gate in memory.

`make preflight`: **PASS**, 13 selected checks in 11.08s, with these three
investigation artifacts staged. Ran via `omi-heavy`, with `VIRTUAL_ENV` and
`PATH` selecting this worktree's `backend/.venv`. Log:
`/Volumes/Ephemeral/scratch/wq21-preflight.log`. PR metadata was unavailable
because no PR exists; the local gate passed without it.
No emulator contention test, service canary, production measurement, or fleet
writer rollout was performed.

## Required next work before a candidate can be enabled

1. Choose a separate invalidation token and establish complete writer ownership,
   including both merge engines, consent/protection/account markers, ownership
   claims, hard deletes and dynamic payloads. Select explicit atomic writer
   migration or a fully tested shared commit hook.
2. Preserve existing admission epoch, deletion intent durability, CAS metadata,
   transaction read-before-write ordering and legal-hold behavior.
3. Make the memo task-attempt scoped, owner/plane/source aware, and resettable on
   job retry. Revalidate the token **inside each authorizing transaction**. Never
   cache failed/partial reads; missing/malformed/blocked token means live checks.
   Keep full-row snapshot consumers live unless the token covers all their data.
4. Implement writer coverage, cross-request invalidation, token mismatch fallback,
   missing token, transaction retry, new source/redirect, read failure, and exact
   off-path tests. Measure the actual sync call path, not just a memo helper.
5. Register only `bpp_generation_memo`, default 0, with contracts. Keep runtime
   lever configuration unchanged. Require all relevant writer services and
   maintenance producers to run the fence before any separate enablement/ramp.

No deadline or enablement promise is made by this blocked investigation.

## ANX outcome

Recorded via `anx-participant` on `card:loop-firestore-reads` as
`event:179b5b44-ab51-4ba0-9268-30542d66d8cc`. The note explicitly reports
BLOCKED, zero savings, no implementation/registration, local-only commit,
153 passing tests, and 13 passing preflight checks. It does not finish or
change the loop card or create a new promise.
