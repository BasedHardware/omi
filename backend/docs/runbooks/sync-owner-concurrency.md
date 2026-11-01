# Bounded owner preparation

Historical jobs still execute serially for each owner. This change pipelines
read-only staged-audio downloads while the active job processes. It does not
authorize concurrent STT, assignment, merge, enrichment or billing.

## Why retain serial execution

`database/sync_backfill_sequencer.py` stores one active job and monotonic epoch
per UID. `claim_next` selects the ordered pending head in its owner transaction;
`begin_job`, `renew_job`, `finish_job` and `redrive_job` fence that identity.
Dispatch retries preserve the epoch; expired running leases advance it. Redis
job locks and durable content-ledger run tokens are additional fences. The
reconciler refuses to replace a run while its Redis lock is present, including
leaves surviving request cancellation.

Assignment is transactionally safe under contention: every intake reads and
writes the per-user assignment index, and follows redirect/recording lineage.
That does not establish that whole jobs with different recording IDs or
distant upload timestamps have disjoint effects. Existing conversation extents
can bridge windows, redirects change targets, source-position coverage reads
prior committed speech, and final enrichment/audio writes occur after intake.
Dispatching four whole jobs would change the order of these effects. A full
concurrent execution design needs conflict sets and fencing through finalization,
proven with Firestore contention and lifecycle acceptance tests.

Preparation leaves every execution fence and ordered selection unchanged. It
snapshots up to K-1 future jobs without claiming or dispatching them, only for
a matching running head/epoch. Later admission can change their order; warming
grants no authority and the next normal claim reselects the head transactionally.

## Controls and bounds

Only `backend-sync-backfill` declares these runtime values:

| Environment value | Default | Meaning |
| --- | --- | --- |
| `SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED` | `on` | Set `off` to stop preparation and ignore cached bytes. |
| `SYNC_BACKFILL_OWNER_CONCURRENCY` | `2` | Head plus speculative prefix, clamped 1–4; invalid values use 1. |
| `SYNC_BACKFILL_OWNER_CONCURRENCY_THRESHOLD` | `8` | Minimum pending backlog before warming, clamped 4–100. |

An owner with fewer pending jobs remains entirely serial. At K=4, up to three
future jobs are warmed sequentially in one storage leaf alongside the head.
There are at most two preparation leaves per instance and one per owner, so
a hot owner cannot occupy both. Each pass attempts at most 20 files, checks an
eight-second scheduling budget between reads, and disables SDK retries with
one-second connection / three-second read timeouts. Socket read timeouts are
not a total wall-clock deadline; a streaming peer can outlive the budget, but
keeps its slot until the actual leaf exits. No slot is expired/reissued under
an unfinished leaf.

The cache holds at most 128 entries / 32 MiB per instance, 8 MiB per owner,
2 MiB per file, with lazy 120-second expiry. A full cache declines new entries
rather than evicting other owners. Release/publication requires the exact
process-local preparation token. Cancellation can leave an I/O leaf alive;
it can populate only this bounded cache and never writes a job's local paths.

Downloads use the existing derived-bucket-first policy and a GCS generation
precondition. Normal execution validates the generation with fresh metadata
before using bytes. Deleted or replaced objects, bucket-priority changes,
cache misses, oversized audio and speculative failures retain the ordinary
download/retry path. Preparation writes no cloud state. Execution still
requires the existing Redis job token and durable ledger binding.

Queue dispatch limits and Cloud Run maxScale are untouched. There are no extra
Cloud Tasks, execution leases, or Cloud Run requests. The original bounded
owner sweeps continue rotating due-owner and pending pages. Kill-switch rollback
does not invalidate epochs or strand in-flight tasks; speculative reads already
started may finish, and cached bytes are ignored.

## Throughput and acceptance

The supplied 4.8 jobs/minute rate implies 76.0 minutes for 365 jobs
(`365 / 4.8`), or 76.04 minutes using 12.5 seconds/job. Ideal independent K=4
execution would be about 19.2 minutes (`ceil(365/4) * 12.5s`), before shared
resource contention and retries. This implementation does not provide that
fourfold speedup.

Let D be average download seconds removed from the critical path and H the
generation-validation overhead. With local cache hit fraction p, drain is
approximately `365 * (12.5 - p*(D-H)) / 60` minutes. Meeting 60 minutes requires
net savings of at least 2.64 seconds/job. Task delivery can go to another
instance, so p is unknown and can be zero; in that case this is bounded extra
storage traffic. The observed oldest age also includes previous delay and
cannot be inferred from burst drain alone. No 60-minute wait guarantee is made.

Use `event=sync_owner_prefetch outcome=prepared` (files/cached) and `outcome=hit`
logs alongside existing job phase timings and waiting-age samples to assess
hit fraction and net benefit after an authorized deployment. If hits are low
or read/memory pressure rises, set the kill switch off. No historical redrive
or capacity change is part of this change.
