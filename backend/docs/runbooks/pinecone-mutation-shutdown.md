# Pinecone mutation shutdown

Every admitted mutation is tracked in the serving process, including migration
copy tickets. On SIGTERM a chained server signal handler schedules settlement
immediately, before Uvicorn waits for active requests. The handler does no IO
and does not lock the registry. The lifespan shutdown retries the drain.
Shutdown closes local admission, allows up to three seconds for provider calls
to finish and settle normally, then marks only remaining live tickets `uncertain`.
Repeated drains share the first deadline rather than restarting the grace.
An admission racing shutdown settles before returning to its provider caller.
Provider interruption (`KeyboardInterrupt`/`SystemExit`) also settles uncertainty
before re-raising. Finish writes retry transient Firestore `Unauthenticated`,
`Unavailable` (`ServiceUnavailable`), `DeadlineExceeded` and `Aborted` errors up
to three attempts on fresh transactions, with 50 ms then 100 ms pauses. The
idempotent transaction tolerates a committed write whose response was lost.
An unrecovered finish failure attempts uncertain settlement using the original
ticket; it never retries the provider or allocates a replacement token.
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
* The dedicated `utils.sync.worker_runtime` parent does not mutate Pinecone;
  its isolated `utils.sync.worker_job` child runs the pipeline and awaits actual
  settlement before normal `os._exit`, within the parent's existing work deadline.
  It does not use the five-second lifespan wait, because no grace remains after
  `os._exit`. Lease loss, work deadline and forced process-group SIGKILL
  retain the existing fencing protocol and cannot run a shutdown hook.
* Standalone Python jobs (including `modal/x_connector_sync_job.py` and
  `modal/job.py`) and operator scripts do not use those lifespans and have no
  shutdown drain hook. Their shared mutation callers still settle
  catchable provider interruptions and finish-write failures. No process signal
  handler or operator behavior is changed for those standalone entrypoints.

The drain runs before other application cleanup consumes the shutdown grace.
It offloads synchronous Firestore settlement to a lazy dedicated worker with one
queued retry slot, independent of the shared DB and default asyncio executors.
Queued settlement survives a bounded-wait timeout or caller cancellation. The lifespan waits
at most five seconds, leaving time for audio/client cleanup; settlement may
continue in its worker during the remaining platform grace. The three-second
provider grace leaves two seconds within that wait for settlement and seven
seconds before Cloud Run's [ten-second SIGTERM deadline](https://docs.cloud.google.com/run/docs/container-contract#instance-shutdown).
The server's longer Uvicorn timeout does not extend the platform deadline.
Firestore RPC latency and platform
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
  `outcome=grace_deadline` counts drain passes with tickets still live at the
  deadline; `attempted` is the number of candidates, including races with finish.
* `event=pinecone_mutation_finish outcome=settlement_failed`: a finish could not
  settle after its eligible retries and is attempting uncertain settlement.
  `outcome=uncertain_settlement_failed` means that fallback also failed.

No labels contain an owner, route, vector, operation ID or error payload.
Global pending/uncertain backlog still requires a counts-only journal census.

## Existing backlog

This change does not modify existing stuck operations. Do not bulk-finish them:
finish asserts acknowledgement. Recovery needs a separately authorized operator
decision and receipts tied to the original scope and provider requests under
`reconcile_mutation`; operation age, counts, or an unrelated probe do not prove
settlement. No provider retry, re-drive, reconcile or deletion is performed at shutdown.
