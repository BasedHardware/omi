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
| Paid provider effect | Existing provider STT runtime remains unchanged | Real FenceTicket REGISTER/START/COMPLETE binding at the corrected SCA-1890 provider boundary, budget reservation/reconciliation, unknown outcome custody |
| Terminal provider result | Handoff-bound `Units.settle` validates durable WorkResult, joins terminal CAS/counter/one recording outbox and `seal_recording` in one transaction; final census matches every immutable original sibling and admission | Real result object publication/lifetime and rejected/quarantined unit recovery adapters |
| Customer conversation assignment | Existing `batch_pipeline_projection.ProjectionStore` / `ProjectionSession` / `conversations.assign_sync_conversation` remain the production authority | Typed immutable completion view that invokes these actual assignment, enrichment, usage and content-ledger transactions with full privacy/epoch checks; generic Handoff callback tests do not qualify it |
| Customer completion receipt / PG ack | Existing Handoff immutable publication and generic receipt/ack protocol only | Concrete grouped projection receipt in the real customer completion transaction, recording/custody/outbox acknowledgement in one PG transaction; unknown COMMIT and purge race proofs |
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
completed, unacknowledged custody until the still-missing concrete customer
projection adapter succeeds. There is no per-unit provider outbox or FS runnable
queue fallback. Transition lanes retain their original FIFO/DRR/head-wait code.
