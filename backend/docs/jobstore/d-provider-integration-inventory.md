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
| Customer conversation assignment | `jobstore.provider_projection.ProviderProjection` provides a private recording view to the actual `ProjectionStore` / `ProjectionSession` / `conversations.assign_sync_conversation`, enrichment, usage and content ledger transactions | Actual assignment call and private Store.run/ProjectionStore.run/publication now scope CommitCoordinator through SDK COMMIT. Production runner, other writers, unsupported recovery cohorts, per-record lifetime/cleanup and mode-independent purge qualification remain required |
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
