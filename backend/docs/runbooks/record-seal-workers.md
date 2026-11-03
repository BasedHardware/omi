# CPU record seal workers

`record-seal-worker` seals completed, unclosed `record_pending` obligations before
normal batch admission. It uses the existing repair image, KSA and pods.list Role,
and launches the unchanged `record_seal_repair_job.py --row` subprocess, 270s per
attempt. GPU workers, admission scheduling, pusher and proof rules are unchanged.

One slot per CPU pod; 1–16 replicas. Each pod requests 62m/128Mi and limits
250m/512Mi. Sixteen slots preserve repair's 4CPU/8Gi aggregate limit (request CPU
rounds down from 62.5m to Kubernetes' 1m precision). Memory/throughput at sixteen
slots need staging qualification; an OOM is a failed attempt with an expiring
claim, never permission to bypass retained-tail or privacy proof.

## Discovery and claims

The new composite indexes on `batch_pipeline_{prod,dev}_jobs` are state,
record_snapshot.finished_at, document name. Deploy readiness must report READY
before this image takes over. Keyset pages of 64 pending jobs use a frozen finish
horizon; completed passes wrap, so inserted or refused old rows are revisited.
Missing snapshot timestamps and missing registrations remain the sweeper's job.

Only `seal_claim` metadata is added to existing obligations: token, expires_at,
retry_after. Acquisition transactionally rechecks the job and conversation, then
sets a 360s expiry, without changing scheduler state or available_at. No renewals
invalidate the planner's exact job snapshot during a walk. A reclaim changes
the exact job and invalidates an old plan; apply always rechecks the row and
privacy. Claim ownership is for avoiding wasted walks, not seal authority.
Concurrent cron walks are still possible during overlap; only one apply seals.

After a completed attempt, reap the child, release only the matching token and back off one hour.
This applies to refusals, budget expiry and ambiguous results; no proof class is
redriven or force-closed. Partial rows stay out of seal debt. SIGTERM reaps the
process group and leaves the short claim to expire without refusal backoff;
abrupt pod death also relies on the expiry. Inherited
270s child IO cancellation and the parent's deadline remain unchanged.

## Metrics and deployment order

Apply the Prometheus scrape job and adapter rule in this PR before HPA cutover.
The local Prometheus scrape is required in addition to managed PodMonitoring.
Each worker samples all pending pages, reading only conversation seal metadata,
including active/backoff debt. Publish count and oldest age only after a complete
pass. This is a paginated observation, not a transactionally consistent census.
Freshness uses the pass START; partial/failed/long passes never fabricate zero.
If a complete pass takes over 60s, the HPA metric is unavailable; investigate
sampler latency and pending volume before retiring the cron.

- External `omi_record_seal_backlog`: max across fresh replicated global samples;
  AverageValue 4 rows/slot, minimum 1, maximum 16. Missing metric blocks scale-down.
- `omi_record_seal_oldest_age_seconds`, `omi_record_seal_refreshed_at_seconds`:
  debt age and sample freshness, including chronic privacy/upload refusals.
- `sum(rate(omi_record_seal_sealed_total[1m])) * 60`: seals per minute; select one
  scrape job if the collector receives duplicates.
- `histogram_quantile(0.95, sum by (le)
  (rate(omi_record_seal_age_seconds_bucket[1h])))`: successful seals' p95 age.
  Also inspect oldest debt/refusal counts so an unsealed chronic tail cannot be
  hidden by this success histogram. Metrics have only static release/namespace
  and closed-set disposition labels; never user IDs, paths or provider messages.

## Evening ramp and rollback

Lead/infracost owns deployment and staging; this change performs neither.
Populate `recordSealWorker.serverFlags` with the current serving policy, as for
`recordSealRepair.serverFlags`; with the switch on, an absent/invalid map exits
the pod before `/metrics` serves, so it crash-loops and never reports Ready.
Refresh both maps together while the cron overlaps. Runtime worker switch is ON
by default, but no live flag change is implied by this chart.

1. Verify index READY, CPU packing/memory, fresh adapter metric and forced-death
   reclaim in staging. Keep all existing seal proof tests green.
2. Deploy workers ON and explicitly set `recordSealRepair.suspend=false` for one
   evening peak. The checked-in default is suspended, so this override is required
   on the first rollout. Watch exact transaction rechecks during overlap.
3. After the overlap, set suspend=true. Run one bounded catch-up sweeper over
   chronic classes with existing proof/privacy policy; no redrive is included.
4. Gate: seal-age p95 below 30min throughout one evening peak, no manual worker
   adjustments. Check unfinished age too. Lead owns expansion and the peak gate;
   remove the retained cron in a later PR only after a recorded passing peak.

Rollback in one Helm values change: `recordSealWorker.runtimeEnabled=false` and
`recordSealRepair.suspend=false`. The new Deployment idles and its old pods reap
children during replacement; repair resumes at its existing cadence. Never delete
the cron or its RBAC in the first rollout. The hourly sweeper remains the net.
The worker reuses `RECORD_SEAL_REPAIR_ENABLED` in its own pod and row child;
`recordSealWorker.runtimeEnabled` controls that pod independently of the cron's
`recordSealRepair.runtimeEnabled`. No additional runtime flag or budget exception.
Malformed job identities advance the discovery cursor and increment
`omi_record_seal_invalid_jobs_total`; investigate that count through a scoped
operator query. Startup/tick failures emit only aggregate status, never exceptions
or provider bodies, while private dependency diagnostics stay suppressed.
