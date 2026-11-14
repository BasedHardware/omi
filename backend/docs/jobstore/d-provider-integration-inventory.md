# Dark typed provider integration inventory

Source readiness remains false. This inventory follows actual production entry
points; it grants no serving, provider spend, retention or activation authority.
The first review's production-binding P1 remains open.

| Boundary | Existing production entry / concrete dark binding | Remaining requirement |
|---|---|---|
| Ordinary upload admission | `database.batch_pipeline_intake.admit` explicitly accepts Handoff + complete `provider_plan`; `IntentStore` keeps original customer ledger/intake and stages the immutable provider plan in the same FS transaction | Runtime selection/default-off rollout gate and final fresh/class/owner rotation policy; no implicit defaults |
| Durable PG ingress | `jobstore.provider_handoff.ProviderHandoff.deliver` validates actual WorkItem, policy, route, complete projection binding, owner/targets, schedule and packet budget, then joins Units admission to the handoff transaction | Production runner/backoff and original staging reference custody adapters |
| Native, partial, coalesced uploads | Existing production intake and `utils.batch_pipeline.provider_stt_admission` keep their existing behavior | Typed reservation, group/source census, funding and projection adapters; typed intent injection explicitly refuses these cohorts |
| Scheduler / provider claim | `jobstore.units.Units.claim` uses explicit fresh/backlog shares, owner rotation and paid-attempt admission binding | Production scheduler/provider process adapter and accepted fleet/budget workload; bounded typed workload is not an RC2 certificate |
| Paid provider effect | Explicit `ProviderHandoff.fence_ticket` registers the original typed attempt; `provider_stt.transcribe_async` invokes START after existing allowance reservation and before its one paid POST. Ticket COMPLETE joins actual Units terminal/counter/outbox/seal COMMIT | Production runner and funding/budget qualification, failover/recovery cohort adapters, original result-object publication/lifetime and unknown result-object outcome reconciliation; old transition stage remains unchanged |
| Terminal provider result | Handoff-bound `Units.settle` validates durable WorkResult, joins terminal CAS/counter/one recording outbox and `seal_recording` in one transaction; final census matches every immutable original sibling and admission | Real result object publication/lifetime and rejected/quarantined unit recovery adapters |
| Customer conversation assignment | `jobstore.provider_projection.ProviderProjection` provides a private recording view to the actual `ProjectionStore` / `ProjectionSession` / `conversations.assign_sync_conversation`, enrichment, usage and content ledger transactions | Actual assignment, bridge/playback/completion follow-ups and private Store.run/ProjectionStore.run/publication now scope CommitCoordinator through SDK COMMIT. Production runner, other writers, unsupported recovery cohorts, per-record lifetime/cleanup and mode-independent purge qualification remain required |
| Customer completion receipt / PG ack | Private view publication is atomic; one typed receipt joins the actual customer completion transaction. Recording/custody/outbox/handoff acknowledgement shares one SQL transaction, with deferred SQL constraint 0012 | Full production runner and destructive-unit/purge races remain gates; generic export/project/ack APIs explicitly refuse the typed cohort |
| Original capture repair context | Original FS intake keeps repair lineage; it is excluded from PG intent | Preserve its existing per-record lifetime and include original + retained copies in purge census; no new automatic TTL for unresolved custody |
| Purge / restore | G2 close/drain tasks and Units.readmit primitives exist | Mode-independent retained-copy destructive-unit manifest, terminal restore/re-admission scheduling, unknown COMMIT/takeover proof; admission restoration must not adopt an old paid attempt |
| Reverse copy | Authority fencing and committed-prefix primitives exist | Actual conditional reverse sink, final parity certificate and certified reverse-open transaction; raw SQL currently refuses reopening |

Tests in `tests/integration/test_jobstore_provider_handoff.py` use the real
ordinary-upload admission transaction, isolated Firestore emulator and private
PostgreSQL. They prove source admission/terminal custody replay and abrupt child
exit on both sides of the actual PG admission and terminal commits. They neither
invoke a paid provider nor substitute a callback for customer projection.

A provider plan reserves the complete bounded metadata envelope before source
acknowledgement. It records caller-supplied class, rotation and original custody
deadline; none becomes a new retention grant. Settled recordings retain their
completed, unacknowledged custody until the explicitly injected concrete customer
projection adapter and grouped acknowledgement succeed. There is no per-unit provider outbox or FS runnable
queue fallback. Transition lanes retain their original FIFO/DRR/head-wait code.

The ordinary successful-result view now runs the actual Projector path without
creating FS runnable queue rows. Its cursor belongs to one recording; it never
uses a cold legacy erased-chain lookup to authorize ordering. Every write reads
real FS authority and a valid matching F token. G2 4.9 benign self-rotations use
fresh A1/walk/A2 E1 admission, while the original paid admission must still pass
unchanged P/PC generations and change sequence. Restore cannot adopt old results.

The cursor publishes an exact retained-copy manifest with original per-unit
custody deadlines, original intake and all new private metadata refs. It does
not arm the legacy live-queue TTL or extend original object lifetimes. Unknown
PG acknowledgement retains unresolved metadata. Production per-record cleanup
and mode-independent purge of every listed copy remain unimplemented gates;
this manifest alone is not an erasure certificate.

Abrupt subprocess exit tests cover before/after the real customer completion
and grouped PG acknowledgement commits. A killed FS read transaction can keep
server locks until its lease expires. One delivery may exhaust the unchanged
bounded contention policy; tested redelivery preserves source custody and does
not rerun paid work or double-charge usage. No new server deadline, retry count
or production scheduling policy is selected by the adapter.

The ordinary typed provider effect keeps an immutable `provider_effect_id` on
its unit (migration 0013), even after the transient registry row retires. A
lost START reply cannot mint a second send. A result reference, recording
counter, grouped terminal seal, outbox and registry retirement share COMPLETE's
SQL COMMIT; a deferred constraint rejects isolated result settlement while the
effect remains unresolved. START rechecks the real FS token/authority before
its short SQL transaction. No pool slot or owner guard spans provider I/O.
The accepted A3 arbitrary delay after START remains; lease expiry never grants a
second START and never by itself discards an otherwise authorized completion.
No new vendor failover route, retry, class, owner-turn, budget or TTL policy is
selected. Existing allowance observation is preserved; it is not a new budget
authority or a fleet certificate. Result object upload is still a separate,
unqualified real GCS/lifetime/custody adapter.

The customer role now binds Coordinator through the actual assignment call and
all private projection mutation COMMITs, resetting ContextVar state on exit.
Rev3's full-replacement post-image classifier is distinct from masked authority
updates: ordinary non-live sync conversations with false cloud consent do not
close themselves. Masked ownership/redirect/consent changes remain conservative;
full live-record replacements still close because user consent is not proven
by that conversation write. This does not install the coordinator on other
production writers, dispatch a runner or reopen an admission after narrowing.


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

`batch_pipeline_purge.provider_result_artifacts` explicitly composes the actual
ordinary result ArtifactStore with `ProviderUpload`, `ResultUploadRows`,
`GCSTransport` and `GCSSink`. No serving factory selects it. Legacy upload policy
and the lake authority are unchanged. Durable original name/hash/deadline precede
FS reference registration and exact-size create-only session creation; registry
START precedes one full PUT; publication and registry retirement share SQL COMMIT.
The later paid terminal transition requires that exact original result URI.

A real legal-hold unit is mandatory for destructive drain. The original namespace
epoch/FS authority are checked; the durable draining claim excludes late COMPLETE.
No SQL guard spans remote I/O. The real conversation resolver routes
`jobstore-gcs-v1` before another destructive unit; original account orchestration
and runtime injection remain missing. See the source checkpoint for terminal
status/generation rules. The new original session journal family intentionally
refuses cold conversion pending its own adapter. Local transport tests are not
remote C4 proof; remaining cohorts/all-copy/final-custody gates stay open.

Budgeted result reads also use the typed original paid source/P/PC/epoch checks,
fresh real A1/walk/A2 and matching valid F token. They retain the existing
single-attempt read-only object-authorizing snapshot and caller read deadline;
all admission FS RPCs honour that same deadline. The legacy reader remains
unchanged for unbound stores. Added restored-admission/epoch cases first failed
against the inherited legacy callback; the real binding now refuses before any
object bytes. Original source is rechecked after I/O. No retry/deadline policy
or original paid admission was weakened or replaced.

Published ordinary results now join actual retained-copy account/conversation
purge independently of the paid terminal seal. Exact original upload row/hash,
deadline and generation bind object absence and original artifact-reference
progress. Production orchestration/runtime selection, nonpublished and other
upload cohorts, remote C4, cold conversion of session journal and final typed
PG/journal custody retirement remain gates; readiness=false.


### Original upload conditional cold cohort (0023)

`queue_provider_uploads` journal rows now use the actual conditional ColdSink
and mode-independent ColdPurge. A separate immutable `queue_upload_cold_custody`
extension records each cold key's original paid admission, attempt, object
identity/hash and exact original deadline. Existing original/cold manifests
remain byte-for-byte unchanged. The extension commits under owner X before
any remote write; SQL rejects mutations/deletion, mismatched source and missing
owner guards. It references the original upload and base cold custodian.

Replay checks the actual journal row/body, original sibling membership,
immutable paid source and allowed upload phase history. No session capability
is copied. Actual fresh A1/walk/A2, original P/PC and matching F token/namespace
epoch still fence the writing transaction. Original paid admissions cannot be
adopted after restore. SQL slots and owner guards end before SDK I/O.

Purge inventories these keys even if copying never ran. Existing real hold,
destructive-unit token, deletion intent/account F generation, namespace epoch
and suppression-through-sequence checks cover their actual FS deletion COMMIT.
Unknown/newer upload destinations refuse; delayed covered puts acknowledge
without resurrection. The existing committed prefix and original upload,
attempt/effect, typed PG records, intake repair context and all censuses remain
retained. This is cold-copy phase proof, not remote C4, a final all-copy/parity
certificate, a cold-to-serving conversion or destructive final PG permission.
No runtime installs the adapter, TTL is not extended and no new policy chosen.
The broad first-review P1 remains open and source readiness remains false.
