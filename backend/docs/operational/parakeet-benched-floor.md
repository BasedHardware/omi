# Shared Parakeet floor while live is benched

Owner: rollout lead; apply/restore: op1. Decision: 2026-10-28 lead ruling
`7c7114`. Restore this override when [pkwin2 #23863](https://github.com/BasedHardware/omi/pull/23863)
is deployed. If that remains blocked, the lead reviews it by 2026-10-29 10:00 UTC
and records a new dated promise on `card:floors10-gpu-listen-floor-decision-1028`.

The shared service still serves legacy `/v2/transcribe` batch work. Four warm
replicas replace the previous eight-replica floor while live Parakeet is benched.
The ceiling remains 12, admission targets remain two active requests per pod
and 35% GPU utilization, and the existing safety guard remains enabled. This is
not clearance to re-ramp live traffic or the dedicated batch pipeline.

## Apply (operator only)

Before **every Parakeet Helm apply**, including restoration below, inspect the
exact live HPA's external metric names:

```bash
kubectl --context=gke_based-hardware_us-central1_prod-omi-gke \
  -n prod-omi-backend get hpa prod-omi-parakeet \
  -o jsonpath='{.spec.metrics[*].external.metric.name}{"\n"}'
```

If `parakeet_request_latency_p99` is present, the guard has an active rollback:
**defer the Parakeet workflow/chart apply** until the guard's own consecutive
clean-window recovery removes that metric. Keep its 12-replica floor and full
rollback metrics intact; neither the four-replica apply nor eight-replica
restoration may overwrite them. Do not clear the marker manually. Recheck at
the Helm apply boundary, not only before the image build; if a rollback appears
while the workflow is building, stop that run before its Helm step. If the
operator cannot ensure this precondition, hold the apply. A floor of 12 alone
is not the marker: the normal time-of-day schedule can also request 12.

If #23863 is already deployed, skip the four-replica reduction and follow the
restoration instructions instead, under the same active-rollback precondition.

1. Deploy `backend/charts/incluster-guards/prod_omi_incluster_guards_values.yaml`
   through `gcp_incluster_guards.yml` first. Confirm the installed script
   ConfigMap's `floors.json` contains 24 fours and the guard still observes
   usable signals. It must retain its trip rollback; do not disable it.
2. Deploy the Parakeet chart through `gcp_parakeet.yml`. The prod overlay has
   `autoscaling.minReplicas: 4`, `maxReplicas: 12`. This workflow also builds/pins
   a source-SHA image; review that image rollout before dispatching. On Oct 28
   the live HPA scale-up policy was 1 pod/60s while the existing source specifies
   4 pods/15s: the workflow will reconcile that pre-existing drift as well.
   Image or HPA-policy changes reset the guard's 15-minute arming identity;
   observe a full new-state lookback before accepting the reduced floor as
   guarded. If that warmup exposure is unacceptable, hold the apply for a
   floor-only operator path instead of assuming the workflow keeps the image.
   Do not bypass a deferred or blind guard.
3. Use an approved GKE operator identity for the following **pool autoscaler
   edits**, never the report's `ro-prod` identity. These are separate from the
   Helm workflows and are not applied by merging this change:

   ```bash
   gcloud container node-pools update parakeet-pool \
     --project based-hardware --cluster prod-omi-gke --region us-central1 \
     --enable-autoscaling --min-nodes=0 --max-nodes=4
   gcloud container node-pools update parakeet-pool-b \
     --project based-hardware --cluster prod-omi-gke --region us-central1 \
     --enable-autoscaling --min-nodes=0 --max-nodes=3
   ```

   `parakeet-pool-v2` already has total min 0/max 10 and needs no edit. Preserve
   all maxima. The HPA supplies four warm pods, so zero pool minima do not mean
   zero serving replicas. Let normal drain and cluster autoscaling reclaim idle
   nodes; do not resize pools down, evict busy pods, or delete nodes manually.
4. Verify exact-context HPA min/max 4/12, desired and ready replicas, current
   guard verdict/freshness, shared v1/v2 latency and queue age, and actual nodes
   after scale-down. A guard trip may intentionally restore 12 and the latency
   metric. The existing down budget is one pod per 900 seconds plus 900 seconds
   stabilization, so reduction from eight can take about an hour plus node drain.
   Observe one full new-state lookback before treating a guard as armed.

Dedicated batch L4 workers stay at three; T4 diarizer-batch stays HPA/pool 1–18;
listen stays HPA 30–60 with zero CPU-pool minima. Do not count those pools as
interchangeable GPU capacity or pre-allocate capacity above 16.

## Restore or roll back

Restore Parakeet `autoscaling.minReplicas: 8` and remove the production
`floorSchedule.hours` override so it inherits the prior schedule below. Reapply
both charts through their owning workflows. Restore the first pool's min to 2
and the `-b` pool's min to 1 using the commands above with those minima; keep
their maxima 4 and 3 and v2 total min/max 0/10. Confirm the current UTC hour's
scheduled floor and readiness; the schedule, rather than the static eight,
becomes the normal floor writer again. Preserve any active safety rollback
until its existing clean-window recovery permits the schedule to resume.
In particular, defer the Parakeet chart restoration while
`parakeet_request_latency_p99` is present; reapplying a minimum of eight is also
a reduction from the guard's twelve and is not a way to clear the incident.

Prior UTC-hour schedule (indexes 0–23):

```text
[10,10,10,10,10,8,8,8,8,8,10,10,12,12,11,11,11,11,10,10,9,9,8,8]
```
