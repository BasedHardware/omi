# Batch serving privacy attempts and partial-ramp admission reads

Serving reconciliation, each recording-drain tick, and each projection follow-up
now own a bounded batch privacy attempt, as GPU worker attempts already do.
With `bpp_generation_memo` enabled, the first check per client/owner/source-ID set
walks live authority; subsequent transactions read only the privacy token. Each
transaction still reads that token, retaining the existing conflict fence and
server-revision protection against token replay. Failure, timeout and cancellation
close the attempt; the next tick starts cold.

Partial-ramp admission memoizes only owners already excluded by intrinsic load
or an uncertifiable/saturated snapshot, for 60 seconds (maximum 1,024 entries,
scoped by client, stage and owner). Hits return unavailable, never stale counts;
light owners and incoming audio always require fresh evaluation. A drained owner
can remain on legacy admission for at most 60 seconds. Existing durable ownership
checks still precede load evaluation. This memo does nothing outside partial ramps
and does not change existing accepted work.

Production backend-integration serving gauges refresh at most once per 60 seconds
(previously the 30-second code default), below the guard's 120-second blind window.
Other services keep their existing refresh settings. Generated runtime env is
composed from the production overlay.

Handoff estimate: about 30–45M reads/day saved at current volume, mostly integration
`batch_pipeline_privacy:read` and `batch_pipeline_store:oldest`; excluded-owner memo
savings apply only during partial ramps. After deployment, use
`FSR_CALLER_WINDOW=1h python3 avo/firestore-reads/measure.py --hours 1` from the workspace with `ro-prod`, compare
those service/caller rows over complete pre/post hours at similar batch throughput,
and check `batch_ramp:read_owner_load` on backend-sync during a partial ramp.
