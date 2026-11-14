# SCA-1959 review record

This is an incomplete dark implementation. Readiness is false. No merge,
activation, serving acceptance or savings follows from these source receipts.

## First FIX at 28f07cbcb44ac6a8e787ac4956d217faba01a5c5

Studio Luna returned FIX on SCA-1959, comment
`01a1d5ea-75c7-78ac-a976-892736a374b5`, and recorded further defects on parent
SCA-1697, comment `01a1d5ee-a83c-7929-8766-d0ce6e216a8a`. Both concern the same
head. They are the existing first FIX context, not two new review requests.

| Finding | Repair and real local regression |
|---|---|
| Raw SQL can reopen FS or remove registration | 0009 refuses reverse-open while certificates are absent, DELETE/TRUNCATE, namespace rename and forged bootstrap. `test_jobstore_sql_boundary.py` exercises direct SQL and verifies that legacy writes still refuse after each attempted removal. |
| Migration map confused with null | Explicit protobuf null is the only safe migration value. `test_migration_status_only_explicit_null_is_non_narrowing` checks actual Commit interception. |
| Generation/purge write bypasses closure | Classify the hashed privacy-authority document without hashing its key again. `test_generation_purge_writer_closes_actual_hashed_owner_before_commit`; Q10 remains covered by `test_legal_hold_token_rotation_does_not_close_pg_owner`. |
| Redirect target never enters A1 | Discovering a new target restarts A1 before another allowing walk. `test_redirect_target_is_snapshotted_before_retrying_allowing_walk`. |
| Refused admission poisons healthy claims | Persist a refusal hold and release its lease without discarding custody/paid-attempt tokens. `test_closed_and_expired_admissions_do_not_poison_other_owners_claims`. |
| Admission/claim lock inversion | Sorted owner locks precede namespace and row locks; recheck candidates under authority. `test_restore_admission_and_claim_do_not_invert_owner_namespace_locks` forces the disputed interleaving using real PostgreSQL lock observations. |
| Required production integration is incomplete | **Still blocking.** The source checkpoint inventory and cutover harness explicitly enumerate the missing adapters, purge/recovery, reverse certificates and complete crash matrix. Primitive tests cannot discharge this finding. |

The normal primary review verdict and final exact-head privacy/custody second
look have not been obtained for a complete source implementation. No second
review round is requested by this repair checkpoint. The two-round maximum
continues to apply; privacy/custody/data-loss defects remain blocking.

## Lifecycle source continuation

Migration 0010 and `privacy_fence/lifecycle.py` make new close drains durable
in the close transaction, fence stale task acknowledgements, and expose bounded
drain/janitor passes. Abrupt subprocess exits exercise the real close/drain
commit gaps. Tasks bind the close sequence: delayed old tasks cannot retire
post-restore registrations. Retry backoff preserves unresolved GCS capabilities
while allowing other owners' janitor work to proceed.

`Units.readmit` uses a new real-authority admission and preserves original targets
and custody. A paid attempt retains its original admission identity; restoring
the unit cannot adopt that attempt's late result or dispatch it a second time.

These source adapters reduce the lifecycle gap. Production scheduling, the
effect/customer projection adapters, purge/reverse certificates and the complete
matrix remain unfinished. No new review round or merge handoff is requested.

## Ordinary provider source binding

Migration 0011 retains immutable original source metadata. Production
`batch_pipeline_intake.admit` can explicitly inject the typed provider plan;
`ProviderHandoff.deliver` validates it again before admitting Units. The last
terminal unit transaction seals the complete ordered original sibling census.
Lost admission/terminal COMMIT replies replay without duplicated units, counters
or recording outbox work. Real emulator/PG tests include abrupt child exits on
both sides of these commits. Custody remains completed and unacknowledged.

This does not qualify customer projection or paid provider dispatch. See
`d-provider-integration-inventory.md` for the concrete production seams and
remaining cohort adapters. The first P1 remains blocking; no further review
round, merge, runtime activation or savings claim is requested.

## Ordinary customer projection source binding

`ProviderProjection` binds the sealed recording to the actual Projector,
ProjectionStore/Session, conversation assignment, enrichment, usage and content
ledger transactions. Private recording cursors never authorize through a cold
legacy queue. A concrete receipt shares customer completion COMMIT; grouped
SQL acknowledgement rechecks the full original terminal seal and atomically
updates handoff, recording, custody and outbox. Migration 0012 makes isolated
raw-SQL handoff acknowledgement fail at COMMIT.

Benign F self-rotations require fresh E1 A1/walk/A2 admission (G2 4.9), while the
original paid admission remains unchanged and must still pass its P/PC fence.
Original generations/change sequence cannot be adopted after restore. New
retained metadata has an exact source-deadline/ref manifest, no legacy queue TTL
and no grant to extend original object lifetimes. Its full cleanup/purge runner
is still required. Process-exit tests exercise both sides of real customer and
PG acknowledgement commits, including bounded redelivery after abandoned FS
server read leases. Existing deadline/retry policies remain unchanged.

This reduces the first P1; it does not close production dispatch/cohort, purge,
reverse certificate, runtime scheduling, fleet/budget or full matrix gaps. No
new review round, merge, activation or savings claim is requested.

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


Original staging custody and destructive PG artifact-copy units (0019)

The actual account/conversation adapter now joins real production artifact
registration, original FS intake verification and a bounded staging census.
The intake's repair context remains solely in the original FS document: PG
retains only its path/fingerprint, never a reconstructed or copied repair
context. Original artifact URIs, existing cleanup/expiry/write-pending values
and original typed per-record deadlines are sealed, not extended. All unpinned
and late-upload references stay in their original staging rows and in immutable
reference custody. No current GCS generation lookup substitutes for the original
upload version, and no terminal-session or all-copy absence is inferred.

Migration0019 protects registered artifact mutations with an already-held owner
X lock, then the namespace row lock. The trigger acquires no owner guard.
Immutable per-record census/key rows resolve old artifact journal identities.
A prepared operation binds the original unit token, source, census hash, queue
epoch and account purge generation. Actual artifact-mirror DELETEs, their new
journal entries and committed outcome share one SQL transaction; deferred
constraints reject split DELETE/ack or an ack with known copies outstanding.
Recovery locks the same owner and operation row, then observes committed or
persists cancelled. Missing rows, transport/COMMIT errors and lease expiry
cannot prove rollback. A paused old executor refuses a cancelled operation.
Closed queue phases admit only this bound destructive DELETE, never new work.

The adapter seals actual original FS custody under hold/unit-token, queue epoch
and real deletion intent before SQL mutation, and verifies it again before the
remote unit. No SQL slot/owner guard spans FS or GCS I/O. Exact account F
generation and original paid admission remain authoritative. The real progress
resolver routes staging operation targets before allowing another unit.

Order is now private/original phases, staging seal/census, cold erase,
destructive PG artifact-copy COMMIT, then cold erase covering the actual new
DELETE journal versions. This supersedes the earlier cold-first ordering:
artifact keys need the original staging census to resolve. All copies remain
reachable through their original PG custodian throughout. Conditional cold
handling acknowledges only definitively suppressed artifact versions; a live
artifact reverse conversion still refuses. Cold key cap399/journal cap1000,
owner cap10 and staging cap128 refuse oversized inputs pending paging.

These are redundant PG artifact-mirror deletions, not final custody retirement.
The original intake, original FS staging/upload capabilities, typed PG
handoff/attempt/effect/recording/custody/outbox, journal prefix, reference census
and operation barriers stay retained. No journal gaps, identity scrubbing, TTL,
final erasure/reverse certificate or runtime selection is introduced. Real C4,
late terminal-session proof, final destructive journal/typed PG cleanup,
account orchestration, recovery injection, paging and scheduling remain gates.
The broad first-review P1 remains open; readiness is false, no savings booked.


## Ordinary result session source (migration 0020)

The same first FIX remains open. Migration 0020 binds actual ordinary typed
`ArtifactStore.persist_result` to durable original session custody, START/one PUT,
COMPLETE publication/registry retirement and an exclusive drain claim that
excludes late COMPLETE. Actual legal-hold units and observed-target recovery are
required. Local resumable process-exit evidence does not qualify remote C4.
See `d-g2-source-checkpoint.md` for the source contract and
`d-retained-copy-lifetimes.md` for outstanding original custody. Audio/native/
recovery sessions, reverse conversion of this new journal family and final
custody retirement remain missing; readiness=false. No additional review or
activation requested, no savings booked.
