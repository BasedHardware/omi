# Pinecone mutation shutdown

Every admitted mutation is tracked in the serving process, including migration
copy tickets. Shutdown closes local admission and marks live tickets `uncertain`.
An admission racing shutdown settles before returning to its provider caller.
Provider interruption (`KeyboardInterrupt`/`SystemExit`) also settles uncertainty
before re-raising. A failed finish write attempts uncertain settlement using the
original ticket; it never retries the provider or allocates a replacement token.
Failed uncertain writes retain the durable pending marker and local registration
so another drain attempt can retry settlement.

`uncertain` is not provider acknowledgement. It releases the active pending slot
but continues to block migration, cutover and account-purge verification until
the existing evidence-based reconciliation protocol proves final state. A late
provider acknowledgement cannot clear a ticket already marked uncertain.

## Process coverage

* Backend, backend-sync, backend-sync-backfill, backend-integration and GKE
  backend-listen use `main:app` and drain from its FastAPI shutdown event.
* Pusher uses `pusher.main:app` and drains from its lifespan shutdown.
* Cloud Tasks jobs running on those services share the same process hook.
* The dedicated `utils.sync.worker_runtime` idle pull worker does not execute
  pipelines or mutate Pinecone and needs no mutation hook.
* Standalone Python jobs and operator scripts do not use those lifespans and
  have no shutdown drain hook. Their shared mutation callers still settle
  catchable provider interruptions and finish-write failures. No process signal
  handler or operator behavior is changed here.

The drain runs before other application cleanup consumes the shutdown grace.
It performs synchronous Firestore settlement on the existing DB executor; it
does not wait for provider calls to finish. Firestore RPC latency and platform
shutdown grace still bound what can persist. SIGKILL, OOM, a blocked event loop
that never reaches lifespan shutdown, or exhaustion of platform grace can leave
pending records. Admission commit acknowledgement loss also remains a gap:
provider IO has not started, but the process may lack the returned ticket.
This is prevention for graceful shutdown and catchable failures, not recovery
of arbitrary process death.

## Signals

* `omi_pinecone_mutations_inflight`: process-local reservations and pending
  tickets, including failed uncertain settlements. This is not a durable global
  backlog gauge and resets when the process dies.
* `omi_pinecone_mutation_uncertain_marks_total`: successful calls to uncertain
  settlement (including idempotent calls), not unresolved journal cardinality.
* `omi_pinecone_mutation_drain_errors_total`: failed drain settlement calls.
* `event=pinecone_mutation_drain`: aggregate attempted and settled counts only.

No labels contain an owner, route, vector, operation ID or error payload.
Global pending/uncertain backlog still requires a counts-only journal census.

## Existing backlog

This change does not modify existing stuck operations. Do not bulk-finish them:
finish asserts acknowledgement. Recovery needs a separately authorized operator
decision and receipts tied to the original scope and provider requests under
`reconcile_mutation`; operation age, counts, or an unrelated probe do not prove
settlement. No retry, re-drive, reconcile or deletion is performed at shutdown.
