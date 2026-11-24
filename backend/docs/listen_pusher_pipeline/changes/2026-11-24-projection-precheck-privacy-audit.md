# Audit enforced projection precheck hits

The [batch projection lifecycle](../../listen_pusher_pipeline.mdx) can take a speculative Redis allow for an unassigned projection. Assignment, replay, exports and downstream effects use their existing authority checks. Acknowledged Firestore authority commits invalidate the speculative evidence after commit.

After a successful precheck transaction, sample its enforced hit and submit a fresh read-only Firestore walk to the optional read-cache executor. The executor has two workers and zero queue. Each audit gets up to two seconds and 32 point reads inside the evidence deadline. Audit results do not affect the precheck result. Shadow comparisons remain a separate pre-canary signal.

Both enforcement and the audit sampler default to zero. Set the sampler to 50 for a 0.5% audit fraction or 100 for the maximum 1%. For expansion require evaluated audits by Cloud Run namespace and projection precheck route. Zero evaluations is NO_DATA. An evaluated beyond-window disagreement trips the enforcement inverse. Failed and dropped audits are separate counters. Charge audit Firestore reads from origin `job:projection_tokenless_audit` to the measured cost of the rollout. SCA-3508 tracks review, the six-hour pre-canary shadow, and the integration canary.
