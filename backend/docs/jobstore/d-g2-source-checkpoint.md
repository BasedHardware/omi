# SCA-1959 dark source checkpoint

This branch is **incomplete**. It is not an enforcement, migration, cutover,
reverse certificate, staging-sizing receipt, serving acceptance or savings claim.
Source delivery books $0. Continue all fixes on `sca-1697-d-g2-dark`; no second D writer.

Base: `f3902ec5435809d95ac7c15f6be7e9f056564d3d` (current origin/main at checkout).
G2 authority: Revision 3, SHA-256
`1d9ea5dd8aae66d067e6d52c562ee3404429709e1f501d7958a96039e307b7b6`.
The design's illustrative migration 0006 maps to actual 0006; 0007 adds D/W4,
0008 adds immutable handoffs, and 0009 closes raw-SQL authority bypasses.
No old migration was edited. No staging, production, IAM, provisioning or runtime
configuration was touched. Runtime SQL grants are an operator-rendered source
file, never executed remotely by the harness.

## Implemented surface

- G2 schema, monotonic/terminal/protocol/immutable-effect triggers, explicit owner
  shared/exclusive locks and post-lock reads. Runtime-role grants are separate.
- A1/walk/A2 admission using the real Firestore CustomerData walk, token mint,
  immutable admissions, redirect target generations, work check, detector,
  close/change settlement, START/COMPLETE, bounded drain passes and janitor mode.
- Conservative narrowing classifier and an explicitly injected Commit seam,
  including bulk's existing route through Commit. No environment enables it.
  G writes join their exact sequences and precondition in the original Commit.
  Transaction/transform Commits never silently retry internally. A lost PG ack
  after a successful FS Commit stays pending for reconciliation instead of
  encouraging a duplicate caller transform.
- C1 ledger observers re-read deletion/privacy authority in their committing FS
  transaction; conversation purge erases the ledger under its destructive unit.
- Optional PostgresStore fence injection fails closed without a persisted
  admission. Existing production defaults retain the live walk. The real-client
  walk now uses a begun transaction. All-backend qualification uses the real
  customer adapter instead of the simulator previously hiding that bug.
- Typed corrected W4 `units`/`recordings`/`budgets` schema, explicit fresh/backlog
  shares, terminal CAS/counter and one armed projection row per recording;
  unknown paid outcomes hold instead of sending twice. Class/owner_turn policy
  and partial wait are explicit caller inputs, not silently selected here.
- D epoch CAS, committed-prefix allocator/journal, database fencing of registered
  PG namespaces (including old-image writes), copier stop/checkpoint primitives.
  Reverse-open refuses without the missing reverse-certificate integration.
- Continuation adds migration 0008 immutable handoff rows, FS admission intents,
  idempotent epoch-fenced PG mutation callbacks, immutable completion publication,
  customer-transaction projection receipts and PG acknowledgement. The existing
  admission function can explicitly inject the ordinary GPU intent adapter;
  original-capture repair lineage remains in the existing FS intake receipt and
  never enters PG custody. Outstanding intents/receipts have no automatic expiry.
  Canonical fingerprints normalize timestamps to UTC and sort object keys.
- Explicit FS authority binding fences Store transactions, direct Commit/CAS and
  BulkWriter RPCs. Bulk authority context survives SDK executor threads, deferred
  flushes and retries; thread exceptions surface at flush instead of looking like
  success. Unknown queue tables/subcollections and changed bindings refuse.
  Imports/default constructors do not bind or enable any new path.
- First FIX repair: SQL itself now refuses all reverse-open edges while the
  certificate path is absent; DELETE/TRUNCATE and namespace renames cannot erase
  registration, and bootstrap cannot forge an authoritative epoch/history.
  Runtime grant source also revokes DELETE/TRUNCATE. This is refusal, not an
  implemented reverse certificate or permission to reopen FS.
- Classifier distinguishes an explicit protobuf null from migration maps and
  closes the actual hashed owner for generation/blocked/purging authority writes.
  Token-only rotation does not recursively close P; Q10 legal holds still do not
  close P. Redirect targets discovered by W trigger a new A1 snapshot/walk.
- Typed claim discovers bounded candidates without row/namespace locks, locks
  owners in sorted order first, then acquires authority and rechecks each locked
  row (SKIP LOCKED). Admission/heartbeat/settlement use the same owner-before-
  namespace order. Refused candidates get a durable hold and lease release;
  healthy owners in the same batch can commit, while paid-attempt tokens survive.
  This does not implement the missing production restore/re-admission runner.

## Missing integration (blocks completion/readiness)

1. All FS queue writer entry points must install the explicit authority binding.
   The handoff protocol and ordinary GPU FS intent adapter now execute locally,
   but the production Scheduler/typed admission, terminal-result sealing and
   grouped existing ProjectionStore adapters are not wired. Callback tests are
   not evidence that the complete production customer projection is qualified.
   Native/partial/provider/coalesced admissions explicitly refuse the generic
   adapter. Terminal custody cleanup needs the accepted per-record retention
   manifest; no new indefinite terminal lifetime is authorized. Unknown
   shared/control/GPU owner bindings fail closed in the registered PG namespace.
2. Production provider/vector/push/outbox/GCS FenceTicket adapters, H-25 dispatch
   lint and the real C4 sticky terminal-session adapter remain unwired. The
   registry test's synthetic sink is not evidence that a real sink rejects bytes.
3. Mode-independent account/conversation purge across retained copies, journal
   and cold FS, purge-generation chunk binding, destructive-unit lost-COMMIT
   resolution and hold/takeover custody remain incomplete. Legal holds never
   close P (Q10); no alternate privacy policy is proposed here.
4. Conditional FS reverse sink, complete tombstone/expiry replay, all-field parity
   checksums and final source-fenced reverse certificates are missing. No automatic
   fallback, rollback env flip or reverse-open edge is permitted by this source.
5. Durable close-drain, restore, residue cadence and janitor runners; production
   no-account-label metrics; final admission class/owner_turn and budget reservation
   chunk policy; complete crash/kill/restart harness remain missing.
6. Guard/handoff read budgets are dark sentinels (expected production 0, budget 1/day),
   not a serving forecast. Q15 volume/conflict/reconciliation measurements and a
   replacement reviewed daily budget block activation.
7. Full G2 §5.2/P21-P25 and production/emulator update_time equivalence are NOT
   established. Emulator v1.22 rejects stale update_time with FailedPrecondition
   and stale exists=false with AlreadyExists; the source treats guard conflicts
   as retryable. No production test is authorized or claimed.

A3 remains accepted: a worker paused after committed START can send arbitrarily
late, including after deletion. COMPLETE refuses its result. Vector residue after
the final pass may persist; push/provider transmissions cannot be recalled.
A4 is per-record: fence/change rows survive; registry rows and sink capabilities
are deleted on terminal outcomes; residue has its five-pass lifecycle. A9 keeps
deferred jobs through grace and purge retries with no invented outage bound.

## FS writer binding inventory (not an activation certificate)

`FirestoreAuthority.writers()` is an explicit process/call scope. Every writer
below must bind it when a runtime is eventually selected; raw client acquisition
alone is not proof that its later RPC is fenced. A selected FirestoreStore reads
authority in its mutation transaction and binds the complete run, including its
post-commit reseed. An unbound existing process remains dark/legacy. The missing
factory must refuse mixed/uninventoried writers before opening PG authority.

| Writer family | Source entry points and bound coverage |
|---|---|
| Ring, leases, merge, heartbeats | `batch_pipeline_store.FirestoreStore.run`; Commit guard, no FIFO/DRR/head-wait algorithm replacement |
| Direct pull-claim CAS/frontier reseed | `batch_pipeline_store` direct create/update; Commit update_time guard when explicitly scoped |
| Projection/session/release/coalescing receipts | `batch_pipeline_projection`, `batch_pipeline_projection_session`, `batch_pipeline_projection_release`, `batch_pipeline_coalescing_completion`; PG projection-view/group adapters still missing |
| Coalescing reservation/quotas | `batch_pipeline_coalescing`; caller must bind direct transactions; generic intent adapter refuses this cohort |
| Native seals/restores/partial repair | `record_seal_repair`, `record_seal_sweeper`, partial/record admission; cohort-specific PG reservation adapter missing |
| Retention/quarantine/purge | `retention`, `batch_pipeline_quarantine_recovery`, `batch_pipeline_purge`; binding alone cannot replace mode-independent retained-copy/legal-hold purge |
| Bulk and direct transport | SDK Commit and BatchWrite wrapper; BulkWriter binds construction/enqueue/flush context and preserves it in worker threads |

Tests in `tests/integration/test_jobstore_handoff.py` cover rollback before PG
admission/result commit, lost-response replay after successful commits, immutable
SQL/FS completion, customer effect plus receipt atomicity, forged/missing receipt,
independent FS/PG closes, privacy deletion before projection, paused direct writer,
deferred/threaded bulk and original ledger+intent admission. They use local real
FS/PG; process-kill/restart and complete grouped projection remain gaps.

## Repeatable local commands

Use Python 3.11 and the checked-in platform lock. Start only a loopback emulator:

```bash
PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH" OMI_REQUIRE_STORE_BACKENDS=all \
 firebase emulators:exec --config tests/integration/firebase-list-projection.json \
 --only firestore --project demo-omi-isolated-tests \
 '.venv/bin/python -m testing.jobstore_cutover --scenario all --seed 7 --receipt cutover.json'
```

`all` runs real primitive/C1 tests, emits counts and **exits 1 while missing
integration remains**. A successful primitive suite cannot turn it green.

The corrected typed workload is independently executable with the same emulator:

```bash
.venv/bin/python -m testing.jobstore_cutover --scenario corrected-w4 --seed 7 \
 --owners 200 --jobs 10 --pool 2 --seconds 120 --receipt w4.json
```

This measures the typed index/admission/terminal accounting surface with explicit
synthetic class/rotation and partial_wait=60. It is NOT the complete accepted
SCA-1690 fleet/budget/RC2 workload and is NOT a staging sizing receipt. `ready`
stays false until the missing source/integration is resolved and exact-head tests
are remotely accessible. The historical jobstore_contention command still tests
the document scheduler and must never be described as end-state W4 sizing.

## G2 §5.2 test-to-invariant inventory

All entries are primitive evidence or explicit gaps. None is an end-to-end
qualification of an activated cohort. Tests below live in
`tests/integration/test_privacy_fence_postgres.py` unless otherwise stated.

| Row | Evidence or exact gap |
|---|---|
| 1 | test_close_between_a1_a2_cannot_reopen (A1/A2 primitive only) |
| 2 | test_full_production_admission_walk_and_detector (real CustomerData) |
| 3 | test_close_waits_for_work_commit_and_reads_after_lock |
| 4 | test_admission_close_restore_changes_fingerprint |
| 5 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 6 | test_close_drain_registry_lifecycle_and_accepted_late_send (unstarted) |
| 6a | test_close_drain_registry_lifecycle_and_accepted_late_send (provider registry; accepted A3 residual) |
| 6b | test_close_drain_registry_lifecycle_and_accepted_late_send (vector/push registry; accepted A3 residual) |
| 6c | test_gcs_custody_retained_until_terminal_and_absent (synthetic sink ONLY; real C4 adapter missing) |
| 6d | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 6e | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 7 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 8 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 9 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 10 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 11 | test_real_guard_update_time_and_exact_sequence_kill |
| 12 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 12a | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 13 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 14 | test_admission_close_restore_changes_fingerprint (PG primitive; restore job runner missing) |
| 15 | test_close_between_a1_a2_cannot_reopen |
| 15a | test_g2_15a_15b_concurrent_guard_versions_never_settle_by_high_water |
| 15b | test_real_guard_update_time_and_exact_sequence_kill |
| 16 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 16a | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 16b | test_g2_16b_restore_cannot_adopt_pre_restore_effect |
| 17 | test_g2_17_seed_race_does_not_upgrade_shared_lock |
| 18 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 19 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 20 | test_unrelated_conversation_close_blocks_start_but_not_complete |
| 21 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 22 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 23 | test_erased_owner_never_reopens |
| 24 | test_r14_legacy_marker_denies_admission_and_never_discovers_a_wipe (no live watch read) |
| 25 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 26 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 27 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 27a | test_protocol_barrier_and_explicit_exclusive_lock |
| 27b | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 28 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 29 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 30 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 31 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 32 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 33 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 34 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |
| 35 | test_clock_backward_and_expired_admission_refused |
| 36 | MISSING: end-to-end scenario/integration not implemented; all-scenario receipt remains failed |

## P21-P25 inventory

| Case | Evidence / missing proof |
|---|---|
| P21 | 2s locks and post-lock reads tested; full measured guard/pool bounds with process kill/lost COMMIT missing |
| P22 | Unknown owner binding fails closed; sorted any-owner destructive retirement/restart proof missing |
| P23 | Mode-independent cold-copy erasure / retained-target manifest missing |
| P24 | Real production ledger transaction refuses late admission/completion observers after account/conversation deletion; real conversation purge deletes ledger. Process-kill/lost-COMMIT variants missing |
| P25 | Unaffected-conversation START/COMPLETE behavior tested; long-stall custody/latency qualification missing |

Exact-head independent review and Luna privacy/custody second look have not
started. This checkpoint does not consume a review round or request merge.
