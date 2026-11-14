# SCA-1959 dark source checkpoint

This branch is **incomplete**. It is not an enforcement, migration, cutover,
reverse certificate, staging-sizing receipt, serving acceptance or savings claim.
Source delivery books $0. Continue all fixes on `sca-1697-d-g2-dark`; no second D writer.

Original base: `f3902ec5435809d95ac7c15f6be7e9f056564d3d` (origin/main at checkout).
Current main `e2c4d62a05ba9f8e45ef0473234902b2d7e48487` was merged without
history rewriting to resolve overlapping collection-budget registrations; both
the existing fresh-guard budget and D projection budget are retained.
G2 authority: Revision 3, SHA-256
`1d9ea5dd8aae66d067e6d52c562ee3404429709e1f501d7958a96039e307b7b6`.
The design's illustrative migration 0006 maps to actual 0006; 0007 adds D/W4,
0008 adds immutable handoffs, 0009 closes raw-SQL authority bypasses, and 0010
adds transactional close-drain tasks and paid-attempt admission binding.
0011 binds original typed provider source metadata and terminal sealing.
0012 enforces grouped typed acknowledgement at SQL COMMIT.
0013 binds the original paid effect and grouped terminal COMPLETE.
No old migration was edited. No staging, production, IAM, provisioning or runtime
configuration was touched. Runtime SQL grants are an operator-rendered source
file, never executed remotely by the harness.

The ordinary provider admission/terminal continuation is inventoried in
`d-provider-integration-inventory.md`. It binds the real upload transaction to
typed Units and seals full-recording completion atomically. An explicitly
injected recording view now invokes the real customer assignment/usage/ledger
transactions with a same-transaction receipt and grouped PG acknowledgement.
The actual paid POST seam also accepts the explicit original-attempt FenceTicket.
Production runners, retained-copy cleanup/purge, object publication and full paid
cohort/funding qualification remain gates. This
reduces the first P1's admission/completion gap without closing that P1.

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
- Lifecycle continuation: every new close inserts its scoped drain task in the
  close transaction. Bounded claim/drain/ack passes survive a lost wake, abrupt
  process exit and lease takeover. Tasks are deleted after completion; no new
  indefinite registry/coordination retention is introduced. Old close tasks only
  retire registrations with an earlier change sequence, so they cannot delete
  effects created after restore. Registered rows are visited before live started
  rows; janitor retry backoff prevents a stuck GCS owner monopolizing discovery.
- Explicit typed-unit re-admission uses the production CustomerData walk and
  A1/A2, preserves every original target and original custody, and mints a new
  admission. Unresolved paid attempts keep their token in a vendor hold. Their
  immutable attempt-admission identity prevents a late result from being adopted
  after restore. These are callable source adapters, not installed schedulers.

## Missing integration (blocks completion/readiness)

1. All FS queue writer entry points must install the explicit authority binding.
   The handoff protocol and ordinary GPU FS intent adapter now execute locally,
   but production Scheduler/runtime selection and remaining cohort adapters are
   not installed. Ordinary typed provider admission, terminal sealing, customer
   ProjectionStore and original-attempt POST adapters execute locally through
   concrete production seams. Native/partial/coalesced/recovery adapters still
   refuse; callback tests cannot qualify those cohorts. Terminal custody cleanup needs the accepted per-record retention
   manifest; no new indefinite terminal lifetime is authorized. Unknown
   shared/control/GPU owner bindings fail closed in the registered PG namespace.
2. The ordinary original-vendor provider POST seam binds a real FenceTicket;
   production runner/funding/failover qualification, vector/push/outbox/GCS
   adapters, H-25 dispatch lint and the real C4 terminal-session adapter remain
   unwired. The
   registry test's synthetic sink is not evidence that a real sink rejects bytes.
3. Mode-independent account/conversation purge across retained copies, journal
   and cold FS, purge-generation chunk binding, destructive-unit lost-COMMIT
   resolution and hold/takeover custody remain incomplete. Legal holds never
   close P (Q10); no alternate privacy policy is proposed here.
4. Conditional FS reverse sink, complete tombstone/expiry replay, all-field parity
   checksums and final source-fenced reverse certificates are missing. No automatic
   fallback, rollback env flip or reverse-open edge is permitted by this source.
5. Production scheduling/binding for the new durable close-drain/lease-janitor
   passes and typed restore API; residue cadence; production
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

`tests/integration/test_privacy_lifecycle_postgres.py` adds abrupt subprocess
exit before close COMMIT, after close/before wake, after drain claim, after
registry retirement/before ack and after ack. The restarted runner observes
durable SQL and takes over expired leases; a stale runner cannot ack a successor.
It also checks post-restore/other-conversation effects survive old tasks, both
pool slots and the exclusive owner guard remain available during sink I/O,
registry terminal lifecycles, janitor fairness, real-authority restore, and
refusal of pre-restore paid results. GCS terminal proof is still synthetic:
these tests do not qualify a real session adapter or the complete wipe path.

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
| 16a | Typed readmit API tested with real walk; production backoff/restore sweep scheduling still missing |
| 16b | test_g2_16b_restore_cannot_adopt_pre_restore_effect; typed attempt-admission refusal in test_restore_mints_new_admission_and_never_adopts_old_paid_result |
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
| 36 | test_close_drain_does_not_hold_pool_or_exclusive_lock_during_gcs_io (real SQL locks/pool, synthetic sink; complete production drain still missing) |

## P21-P25 inventory

| Case | Evidence / missing proof |
|---|---|
| P21 | 2s locks and post-lock reads tested; full measured guard/pool bounds with process kill/lost COMMIT missing |
| P22 | Unknown owner binding fails closed; sorted any-owner destructive retirement/restart proof missing |
| P23 | Mode-independent cold-copy erasure / retained-target manifest missing |
| P24 | Real production ledger transaction refuses late admission/completion observers after account/conversation deletion; real conversation purge deletes ledger. Process-kill/lost-COMMIT variants missing |
| P25 | Unaffected-conversation START/COMPLETE behavior tested; long-stall custody/latency qualification missing |

The first FIX and its repair are recorded in `d-g2-review-log.md`. A complete
implementation has not obtained the final exact-head primary review and Luna
privacy/custody second look. This continuation requests neither another round
nor merge.

## Ordinary paid effect and customer writer scope

Migration 0013 preserves the original provider effect identity through registry
retirement and rejects isolated terminal result settlement at SQL COMMIT.
`ProviderHandoff.fence_ticket` binds REGISTER/START/COMPLETE to the original
paid admission and immutable typed source. The actual provider STT seam invokes
START after the existing allowance observation and before its single POST.
COMPLETE joins Units terminal custody/counter/outbox/full seal; missing replies
never authorize a second send. Synthetic tests replace only the paid network
and exercise the real FS/SQL boundaries, including abrupt process exits before
and after START and terminal COMMIT. The A3 late-transmission residual remains.

Customer publication, private mutations and actual production assignment calls
now scope CommitCoordinator through SDK COMMIT. Full conversation replacements
use Rev3's post-image predicate; masked authority writes retain conservative
ownership/redirect/consent treatment. Ordinary successful projection and real
narrowing classifier/commit tests cover this source change. Other production
writer/runner/cohort bindings remain uninstalled. Original result publication,
per-record retained-copy cleanup/purge, GCS/reverse certificates, scheduling and
the complete matrix/fleet/budget qualification still block the first P1.
No new review round, merge, activation or savings claim is requested.


## Retained-copy erasure first phase

Migration 0014 persists an immutable original-record census and keeps the last
PG custodian while any copy family remains unresolved. The actual account and
resumable conversation erasure entrypoints accept the explicit dark adapter.
Real FS transactions retire private jobs/results/cursors under the existing
legal-hold/unit token, queue epoch and deletion intent; unknown responses and
process exits replay the original census. No SQL slot/owner guard spans FS I/O.
Original deadlines are copied exactly, with no new TTL or lifetime extension.

This phase deliberately stops legacy erasure before original metadata removal
or completion acknowledgement. Original objects, attempts, handoffs, grouped
recording/custody/outbox, journal and cold copies still need their real remote
proofs and final per-record retirement. Account P-to-purging/drain orchestration,
production paging/injection and remote PG destructive-unit cancellation barriers
remain gates. See `d-retained-copy-lifetimes.md`; private retirement alone does
not close P23, A4/A9 qualification or the first-review P1. No review/activation
or savings are requested.

Exact ea9884 CI also exposed the new writer-scope interface breaking structural
legacy stores and the missing private-publication inventory entry. The repair
uses the explicit class protocol when installed and a no-op only when absent;
an installed scope failure still propagates. The actual provider coordinator
binding remains mandatory. The lifecycle inventory now records the real
private publication, preserving its existing field/state assertions.

Migration 0015 requires the existing exclusive owner lock before census
changes and original custodian deletion. A real concurrent first-census/delete
test proves serialization and post-lock refusal; triggers never acquire or
upgrade a guard. Unregistered legacy outboxes retain their existing path.

## Original object and metadata source continuation

Migration 0016 retains immutable per-record destructive-operation barriers.
Actual account/conversation purge binding now uses the production retention
helper for original generation-pinned audio/results, then the real FS
intent/completion/receipt deletion transaction. Original intake repair context,
whose unique references are excluded from PG intent, stays retained. The PG custodian
and journal remain protected. Real PG lost-COMMIT and subprocess-exit tests
exercise prepared/committed/cancelled recovery and actual conversation gate
takeover. Unknown/missing outcomes never return False as a settled operation.
Account metadata also checks the exact original F and P purge generations.

GCS transport is synthetic, not real terminal-session/C4 qualification. See
`d-retained-copy-lifetimes.md` for the new retained operation census, exact
original lifetime obligations and remaining late/cold/journal proof. Final
per-record retirement, real reverse sink/certificates, runtime account recovery,
scheduling/paging and full matrix/fleet/budget qualification remain missing.
The first P1 stays open, readiness stays false, and no new review round, merge,
activation or savings are requested.

### Ordinary typed conditional cold sink continuation

Migrations 0017/0018 bind a concrete conditional Firestore cold destination to
the actual journal reader. The grouped outbox uses immutable original admission
generation instead of numeric PG identity. Original source rows/bodies are
verified; cold transactions compare epoch/sequence and recheck actual privacy,
token and queue authority. Original per-record PG custody is persisted before
the first cold write, with exact deadlines and no new TTL.

The actual erasure entrypoint now performs mode-independent cold deletion and
commits a per-record durable suppression barrier. Delayed covered source pages
cannot recreate erased data. Lost replies/process exits preserve replay and
original PG custody. Source checkpoints additionally CAS the observed epoch.
Unsupported cohorts/generations, shared budget rows and oversized owner journal
censuses refuse. No runtime factory selects this source.

See `d-retained-copy-lifetimes.md` for retained cold census/barrier lifetimes
and real COMMIT crash coverage. Journal rows/prefixes and final PG custodians
are still retained: intake/staging/late object proofs, real C4, full reverse
conversion/parity, destructive PG final barriers, all cohorts, runtime
orchestration/paging/scheduling and full matrix/fleet/budget qualification remain
open. This is not a final reverse/erasure certificate. Readiness remains false,
the first P1 remains open, and no new review, activation or savings are claimed.
