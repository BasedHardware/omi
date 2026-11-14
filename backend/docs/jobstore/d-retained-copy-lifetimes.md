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
