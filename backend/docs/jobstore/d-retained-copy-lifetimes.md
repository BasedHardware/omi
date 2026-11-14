# Original record lifetime and erasure census

Source readiness remains false. Migration 0014 and `jobstore.retained_copies`
implement the first destructive phase, not a final erasure certificate or a
new retention policy. A1–A9 authorize dark source only. Legal holds never close
P. No runtime factory selects this adapter.

## Actual entrypoints

Account erasure reaches `user_data_deletion.purge_user_subtree` and then
`batch_pipeline_purge.purge_batch_owner`. Protection changes in `users` also
call `purge_batch_owner`. Conversation erasure reaches the resumable
`batch_pipeline_conversation_purge.purge_conversation` through
`conversation_batch_purge_jobs.RunProgress`.

Both purge functions now accept an explicit retained-copy adapter. Account
purge requires its existing destructive-unit authority; its F-generation
advance rechecks that unit and the hold inside the same FS transaction.
Conversation purge uses the existing progress unit. The adapter requires an
already terminal deleted PC or purging/erased P, a matching PG queue epoch,
and a drained effect registry. It never creates a close in response to a hold.
The production account P-to-purging/drain coordinator and runtime injection
remain unimplemented. Passing the adapter without these prerequisites refuses.

The old shadow-only purge cannot erase originals or acknowledge completion
through this binding: after retiring private copies the adapter raises
`RetainedCopiesPending`. The original production functions behave as before
when no adapter is installed. This default-off behavior is not qualification
of the old mode-dependent purge.

## Copy census and lifetime

| Copy | Original authority/lifetime | This phase |
|---|---|---|
| Per-unit source audio and result objects | Original source/object policy and each explicit custody deadline; no replacement TTL | Original references stay in PG; real generation/session erasure proof missing |
| PG units, attempts and immutable effect IDs | Original admission/attempt; outstanding destructive custody | Protected from deletion for inventoried recordings; no attempt is transferred after restore |
| PG handoff intent/admission/completion/receipt hash | Original recording/sibling census | Retained as original custodian |
| PG recording/custody/grouped outbox | Original recording and per-unit custody | Protected from deletion for inventoried recordings |
| PG mutation journal | Original namespace committed prefix and source identities | Owner journal updates/deletes refused while the census is unresolved; no gaps, scrubbing or fabricated replay certificate |
| FS private jobs/results/cursor | Original recording, ordered siblings and exact original custody deadlines | Real transactional deletion under hold/unit token, queue authority/epoch and original deletion intent |
| FS original intent/completion/receipt/intake | Original capture repair and recording lifetime | Exact paths retained in the census; not deleted by this phase |
| Legacy/cold FS, replay pages and late sinks | Original source family and conditional sink authority | Outstanding, no absence claim or reverse-open certificate |
| New PG census itself | Original recording's unresolved erasure obligation | Immutable per-record paths/deadlines, no independent TTL; final cleanup requires remaining proofs and is not implemented |

The adapter enumerates at most ten original recordings per owner invocation and
refuses an oversized page before deletion. Conversation matching includes the
original immutable paid admission targets discovered through real redirect
walks, even when the canonical target is absent from the original intent list. Production paging, unsupported
cohorts/shared-state census and final per-record cleanup are gates. Every
private transaction has at most 257 deletes for 128 siblings, below the existing
400-write erasure bound. Each attempt reads its actual hold, gate token, queue
authority, deletion intent and private documents. The existing read budget is
a planning bound; expected production volume remains zero.

## Unknown outcomes and takeover

Persist the immutable PG census before any private FS delete. A single FS
transaction rechecks the real legal hold and destructive-unit token, so a new
hold or takeover conflicts with an old erasing transaction. Terminal P/PC
cannot reopen. All PG slots and owner guards end before the FS RPC. A failed
or missing FS COMMIT reply leaves the census and every original reference
intact. A successor repeats the same derived private paths. Missing private
copies are an idempotent replay; no copy is reconstructed.

Only after the FS transaction returns does a short PG transaction mark
`private_erased`. Losing that COMMIT response still retains originals and is
replayable. SQL guards prevent deleting the original custodian, its attempts,
recording/custody/outbox or journal while the census remains unresolved.
Neither `private_erased` nor an elapsed deadline releases original custody.

Tests call the actual account/conversation purge entrypoints with real emulator
and private PG transactions. Abrupt subprocess exits cover before/after private
FS COMMIT and before/after PG progress COMMIT; injected lost FS replies and changed
unit tokens prove replay/refusal. An abandoned FS read transaction can outlive
one unchanged bounded acquisition chain; at most twelve test deliveries model
redelivery without changing production deadlines or retries.

Real object/session destructive-unit COMMIT cancellation barriers, journal/cold
copy erasure, production takeover resolution and final PG/census retirement
remain missing. The generic legal-hold remote helper alone cannot qualify a PG
unknown-COMMIT outcome: a missing prepared operation is not rollback proof, and
DB transport errors must not be classified as definitive erasure outcomes.
The last PG custodian must survive until those units have definitive outcomes.

Migration 0015 also requires the existing exclusive owner lock before census
changes and original custodian deletion (including registered outbox and journal
cleanup). It checks caller ownership rather than acquiring/upgrading in a
trigger. Without this boundary an unlocked deletion could race the first,
uncommitted census. The concurrent real-PG test holds the actual inventory's
L_x, blocks a destructive transaction until census COMMIT, then verifies that
the committed census refuses its deletion. Unregistered legacy outboxes retain
their old path. Sorted multi-owner destructive units and final proofs remain
requirements; this serialization does not grant an erasure certificate.

## Original object and metadata continuation

Migration 0016 and `original_copies.OriginalCopies` extend the explicit actual
account/conversation entrypoint binding. The complete immutable ordinary
terminal seal supplies original audio/result URIs. Every URI must already have
an original positive GCS generation; encrypted or unpinned references refuse
before any object delete. The production retention helper validates configured
owner storage and deletes precisely that generation, outside SQL slots/guards.
Its transport is synthetic in local qualification. Real upload/session C4,
late objects, staging references and cold-copy absence are still unproved.

Only after all original object progress records commit may the original
intent/completion/receipt transaction delete its three exact paths. The original
intake repair context is deliberately excluded from the PG intent, so that
unique FS custodian remains until its full reference adapter is qualified.
This phase neither copies repair context into PG nor discards its references.
That COMMIT reads the actual hold/unit token, queue epoch and deletion intent.
Account erasure also checks the exact F generation returned by the actual
generation advance. Every PG progress operation binds the original terminal
hash and per-record census; account progress also binds P's purge generation.
These are source phase receipts, never a final all-copy certificate.

The new operation table is itself retained per-record custody: immutable
operation ID, recording, owner hash, unit token, original references and payload,
with monotonic prepared-to-committed/cancelled state. It has no TTL and cannot
be deleted or rearmed. Execution and recovery acquire the existing L_x before
the same row lock. Recovery either observes COMMIT or durably cancels a prepared
operation; a paused old executor then refuses. Absence, foreign targets, lock
timeouts and PG transport/COMMIT errors never prove rollback. Psycopg errors
are normalized to unknown transport outcomes for the real legal-hold gate.
The actual conversation progress resolver routes the durable operation target
before acquiring the next unit. Account orchestration/recovery injection remains
a runtime gate.

Gate settlement compares the observed target as well as the token. Otherwise a
slow object proof could clear a newer unknown PG operation under the same unit
token. The real FS/PG regression advances those targets during resolution and
proves the newer request remains held until its own durable cancellation.

Successful phase records let bounded redelivery skip completed original
versions. A replacement generation is never selected by lookup. No successful
phase removes the last PG custodian, attempt/effect metadata, journal or census.
Journal committed prefixes cannot acquire gaps, identities cannot be silently
scrubbed, and no reverse certificate exists without a real conditional sink and
cold-copy proof. Final per-record retirement, original lifetime scheduling,
owner paging, terminal-session and residue scheduling remain unfinished.
Readiness remains false and the first-review P1 remains open; no new review,
activation or savings are requested.

## Conditional cold copies and durable erasure suppression

Migrations 0017/0018 and `cold_sink.ColdSink` bind the actual journal page
reader to actual Firestore transactions for ordinary typed units, recordings,
custody, handoffs and the grouped recording outbox. The outbox's immutable
logical generation is its original paid admission ID. Legacy numeric IDs and
missing generations are refused, not guessed or backfilled. Unsupported shared
budgets/document cohorts also refuse without advancing the checkpoint. Runtime
selection, final parity and cold-to-serving conversion remain absent.
This adapter accepts current-epoch original handoffs only; an older original
handoff cannot be adopted into a later queue epoch. Cross-epoch cohort transfer
still requires its own qualified adapter.

Every cold write first commits an immutable original per-record PG census under
L_x. This protects the last PG custodian even before a privacy purge creates its
separate census. The manifest includes all deterministic cold paths and the
per-record erasure barrier, with the exact original custody deadlines and no new
TTL. The source journal version/payload is checked against its actual PG row.
Cold documents preserve original bodies and compare `(epoch, seq)` inside their
actual COMMIT. Same-version differences refuse; older copies cannot overwrite
newer ones. A fresh actual A1/walk/A2 admission and writing-transaction F token,
privacy walk and namespace authority checks preserve the original paid P/PC
generation/targets. A restored admission cannot adopt the old original.

`cold_purge.erase_recording` is bound ahead of private/original erasure in the
actual account/conversation adapter. It inventories the actual owner journal,
refuses unknown cohorts or more than 1000 source rows before deletion, and
checks the original retained-copy manifest. One bounded Firestore transaction
checks hold/unit token, queue epoch and real deletion intent (exact F generation
for account purge), deletes the original cold keys, and commits a durable
per-record suppression barrier through the original source sequence. Covered
delayed puts are definitively acknowledged without recreating data. Neither a
missing destination nor a shadow-mode selector proves erasure. All SQL slots
and owner guards end before this FS I/O. The page checkpoint also CASes its
observed source epoch, so a completed old page cannot advance a newer epoch.

Real child-process exits cover before/after cold-copy and cold-erasure COMMIT.
The emulator retains killed-client read leases: copy redelivery is bounded to
64 deliveries at the unchanged 1.5-second page budget; erasure uses at most 12
deliveries with unchanged unit/SDK deadlines. These are synthetic redelivery
tests, not a new production retry policy or fleet qualification.

The cold census and suppression barrier remain original retained copies. No
journal row, committed prefix, original intake repair context, PG attempt/effect
identity, operation barrier or final per-record custodian is retired. Original
intake/staging/late-session references and C4 still lack definitive proofs.
Destructive PG journal/final cleanup needs its own prepared/committed/cancelled
barriers and complete remote proof before it can execute. Neither successful
cold-copy acknowledgement nor this phase receipt is a final erasure/reverse
certificate. Owner paging, account orchestration, other cohorts, runtime
injection and lifetime/residue scheduling remain gates. Source readiness is
false and no savings are booked.


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

New staging coverage exercises 21 actual emulator/private-PG cases: original
registration and production purge entrypoint; missing/changed unique custody;
raw SQL split-outcome/census/recreation refusal; exact copy mismatch rollback;
unknown operation refusal; cancellation fencing; free pool/owner guards during
FS; lost PG replies; os._exit before/after actual PG DELETE/outcome and FS seal
COMMIT; actual progress target recovery; stale epoch/closed queue handling.
The intake counter observes one read each for actual seal and verify. Killed
FS read leases use at most12 synthetic redeliveries under unchanged deadlines.
Initial new phase fixtures used invalid raw transitions; corrected to the
existing transition API without changing production policy/refusal assertions.


## Ordinary result session source (migration 0020)

The explicit `batch_pipeline_purge.provider_result_artifacts` factory now binds
actual `ArtifactStore.persist_result` to an ordinary typed paid attempt. No
runtime selects it. Audio, native, recovery and pre-unit uploads keep their
existing policy and require separate bindings. The lake adapter and its
settlement authority are unchanged. This is source/local transport evidence,
not remote GCS C4 qualification or a final all-copy certificate.

Before any object bytes, PG reserves the immutable original name, payload hash,
paid admission/attempt and exact unit custody deadline. The actual FS artifact
reference commits with fresh A1/walk/A2, valid matching F token, original P/PC
and namespace authority, under the real Coordinator through SDK COMMIT. It has
no replacement TTL. It contains no unique intake repair context. The SDK then
creates an exact-size `ifGenerationMatch=0` resumable session with retries off.
The session capability is durable only in the GCS effect registry before START;
one full PUT follows START on the same stack. Unknown/prepared outcomes refuse
a second session or PUT. COMPLETE joins original positive generation/reference
publication and capability retirement in SQL; the later paid terminal CAS must
reference that exact published original object. No restored admission adoption.

The actual SDK HTTP adapter uses explicit existing upload socket deadlines,
suppresses sensitive capability exception text, cancels/queries the original
session and calls the production generation-pinned retention deletion path.
A real legal-hold destructive unit is mandatory for cleanup. An open-owner
lease janitor first commits an irreversible `draining` claim under owner X;
this excludes concurrent valid COMPLETE before any storage deletion. No SQL
slot/owner guard crosses FS or storage I/O. A successful COMPLETE that won
first is never deleted by that janitor. Terminal proof joins phase `fenced` and
registry retirement in SQL. Missing generation on finalized or expired/missing
sessions is unresolved; current object metadata is never substituted. A sticky
499 proves cancellation before finalize; sticky 412 is not adopted and does not
authorize deleting a foreign collision. Recovery uses `jobstore-gcs-v1` targets
and the existing observed-target/token CAS; missing operations are not rollback
proof. Holds never close P. Normal false returns never settle an unknown unit.

New PG `queue_provider_uploads` is original per-record custody, not disposable
mirror state: immutable original deadline/name/hash/admission/attempt and
original effect ID, positive generation when known, no independent expiry.
Its FK and mutation constraints retain the original typed unit/handoff and
refuse identity scrubbing or final deletion. Its journal entries contain no
session URL. The current cold converter refuses this new family without
advancing the journal checkpoint. These unresolved originals, the unique FS
intake/staging and original references remain retained; no journal gaps or
final certificate is fabricated. A crash between empty-session creation and
registry registration leaves a prepared original reservation, no authorized
bytes and no automatic retry; reconciliation remains a liveness gate.

The local disk-backed resumable fixture now retains finalized session metadata
across process exit, allowing tests of the actual adapter's original generation
handling. This does not establish the remote terminal-status/absence contract.
Actual GCS qualification, complete upload cohorts, original lifetime scheduling,
account drain/runtime recovery injection, all-copy proof and final destructive
PG/journal barriers remain missing. Broad first-review P1 and readiness=false
remain unchanged; no new review, activation or savings follows.

Budgeted result reads also use the typed original paid source/P/PC/epoch checks,
fresh real A1/walk/A2 and matching valid F token. They retain the existing
single-attempt read-only object-authorizing snapshot and caller read deadline;
all admission FS RPCs honour that same deadline. The legacy reader remains
unchanged for unbound stores. Added restored-admission/epoch cases first failed
against the inherited legacy callback; the real binding now refuses before any
object bytes. Original source is rechecked after I/O. No retry/deadline policy
or original paid admission was weakened or replaced.

The terminal-session destructive unit treats any original-generation delete or
absence-probe SDK failure as unresolved, including raw deadline and 412 errors.
A generic per-request error classification cannot settle this whole multi-step
proof or clear its gate. Only terminal-session plus original-version absence
returns normally; the registry and last original custodian stay retained.

## Published originals before paid terminal COMMIT (0021)

The actual account/conversation retained-copy adapter now enumerates immutable
`queue_provider_uploads` custody independently of the recording terminal seal.
A successful original result publication can precede a discarded or crashed paid
terminal COMMIT; the upload row and its exact original deadline remain the source,
not an inferred result URI from a missing terminal unit. No original manifest is
rewritten and no unique intake repair context is copied or removed.

`PublishedCopies` verifies the original artifact reference under real hold/unit
token, namespace epoch and deletion intent (exact advanced F generation for an
account). It uses the production retention path to delete only the published
positive original generation, then probes that same generation for absence.
Any delete/probe error is unknown ConnectionError and pins the actual remote gate.
No SQL pool slot or owner guard spans storage/FS I/O. A committed immutable
`published_object` operation receipt is required before reference deletion; its
own FS COMMIT rechecks authority. `published_reference` progress then commits
through the existing prepared/committed/cancelled operation barrier and recovery
route. The operation binds the complete immutable upload fingerprint and URI;
it never borrows a restored admission or treats source absence as rollback.
The published lease janitor remains unchanged and never erases a winning COMPLETE.

Upload rows, original deadlines, typed PG source/attempt/effect identities,
reference census and journal remain retained. These are original-phase receipts,
not a terminal-session/all-copy certificate or authority for final destructive PG
cleanup. Nonpublished session custody refuses this phase pending its drain and
full lifecycle adapter. Unique intake/staging/late audio capabilities, real remote
C4, new journal-family cold conversion, final journal/custody barriers, production
account orchestration, paging and scheduling remain gates. Readiness stays false.

One artifact point read per actual verification/deletion transaction attempt is
a planning bound; the uncontended two-phase path performs three such reads.
Production remains unselected (0 expected/day, existing sentinel1/day). No new
TTL, funding or fleet budget policy; retries/redeliveries count separately.

Published-original selection also requires the deleted conversation to belong to
the original intent/paid target census. Reference comparison uses the full
original source-derived document, so an unexpected retained reference cannot be
silently discarded. The absence probe refuses dispatch after the unit deadline
and clamps its socket timeouts to the remaining deadline without SDK retries.

Main integration: main's `0006_transactional_fresh_gate.sql` now occupies version6.
The unmerged dark migrations formerly0006–0021 are resequenced to0007–0022,
with every SQL body/checksum preserved byte for byte. Main0006 remains unchanged.
Earlier section numbers describe their original delivery; the published-original
purpose expansion is now0022. These source changes were exercised only through
disposable local fixture clusters in this task, not deployed migrations. Existing
applied-checksum refusal remains unchanged; no live migration/rewrite is performed.
