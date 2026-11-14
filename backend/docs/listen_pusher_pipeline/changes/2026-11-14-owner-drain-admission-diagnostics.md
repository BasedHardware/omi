# Owner drain admission attribution (SCA-1960)

The historical readback found 3,846 empty single-step `end` turns in 20 minutes
and enrichment endpoint throughput of 34.4 HTTP 200/min against 60–66/min.
Those uncontrolled workloads do not establish causation. This instrumentation
distinguishes why turns start; it does not repair scheduling or authorize activation.
The [flag contract](../../listen_pusher_pipeline.mdx#batch-projection-drain-admission)
defaults on; `BATCH_PIPELINE_OWNER_DRAIN_ADMISSION_DIAGNOSTICS=0` disables it.
Reviewed revert is the source rollback. Release remains SCA-2072/SCA-2026.

No new storage reads/writes, claims, timers, waits or product state. New state is
local to the projector/owner drain in its serving process. Request origins are
ORed across the locked thread handoff and event-loop coalescing without changing
FIFO order, `again`, productive continuation precedence, privacy or claim fences.

`event=batch_projection action=admission_diagnostics aggregate=<JSON>` is emitted
at most once per 60 seconds on admission completion. It contains a partial-window
`window_ms`, `counts`, and `cells`. No owner, task, row or content identifiers appear.
For shutdown, the stricter no-delay requirement takes precedence over the proposal's
best-effort flush: close clears diagnostics without sink IO or scheduling another
task. The last incomplete window can be lost; this is not a durable census.

Each cell has exclusive `trigger` (`external`, `continuation`, `again`, `retry`),
`origins` bitmask, `positive` (0/1), normalized `stop`, and `executed` (whether the
chain turn began). `n`, `rows`, `steps`, `timing_ms` and `timing_buckets` aggregate
that cell. Origins: unknown=1, discovery-after-assignment=2,
predecessor-replay=4, targeted-wake=8, internal-retry=16. A continuation inherits
its originating sources plus concurrent re-requests; continuation takes precedence
over `again`, as in scheduling. Mixed masks describe one admission, not multiple
independently additive sources. `again`/`positive=0` counts empty replay admissions.

`counts` distinguishes handoff requests/coalescing/overflow and drain requests
(`queued`, `active`, `coalesced`, `deferred`) from completed admissions. Handoff
requests are counted before deduplication; drain requests are counted after it.
Pre-run `claim_held` and `privacy_unchanged` are `executed=false`, distinct from
empty executed turns. Unknown terminal stops become `other`; privacy dispositions
collapse to `blocked_privacy`. Error and cancellation have explicit categories.

At most 1,024 owners retain origin metadata per handoff and pending-drain map;
active metadata is bounded by existing drain concurrency. Overflow retains wakes
and scheduling, reports `handoff_overflow`/`owner_overflow`, and loses attribution
to unknown. Each window has at most 256 cells; `cell_overflow` counts completed
admissions omitted from cells. Thus `sum(cell.n)+cell_overflow=completed`.
Logger failures cannot stop scheduling and increment `sink_failures`; subsequent
windows can include retained counters. Request and outcome totals may cross window
boundaries; reconcile across windows rather than assuming same-window equality.

Admission wall time starts at launch. Executor wait is submission-to-worker-start,
separate from existing claim GET, claim acquisition and `prefetch.take` wait calls.
Per-cell timing buckets count per-admission sums, with exclusive upper bounds
1/10/100/1,000/10,000 ms plus overflow. Missing timings mean that operation did not
run, not a measured zero. Summed durations overlap and are not CPU consumption.
No extra probes are made; context propagates through the existing executor seam.

For a serving readback, record exact source/revision, window and completeness,
aggregate origins/trigger × positive × stop, empty replay rate, turns/row and
admission/claim/prefetch timings. Preserve existing projected rows/min, pending
total, enrichment HTTP 200/min and estimated cost per HTTP 200 (with reset/source
coverage). Current main has `prefetch_wait`; the historical serving source did not.
Historical provenance and queue-attributed enrichment callback execution duration
remain unavailable. The literal fresh-only-owner cohort still needs independent
measurement; fleet percentages and simulator throughput do not replace acceptance.

Verification runs the real scheduler and chain walk with diagnostics off/on,
forcing deterministic step boundaries: identical admission sequence, continuation
classification, persisted rows/order and storage-call counts, including a genuine
wake after exhaustion and a redundant empty replay. Existing fairness, ordering,
claim/privacy and mixed-load simulator contracts remain required. Printed wall-time
samples are local cost observations, not evidence of production throughput recovery.
