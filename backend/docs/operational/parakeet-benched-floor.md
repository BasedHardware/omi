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

## Apply through the guard's atomic floor writer (operator only)

**Do not dispatch `gcp_parakeet.yml` or run a Parakeet Helm upgrade for this
floor operation.** That workflow rolls an image and can overwrite an active
guard rollback after an operator's last check. The Parakeet chart's static
minimum remains eight; the guard's existing schedule writer applies four to
the live HPA without an image or HPA-policy reconcile. Avoid an unrelated
Parakeet Helm/image deployment during this floor operation.

1. Confirm #23863 is not already deployed; if it is, skip the reduction and use
   the restoration below. Lead also clears the source-pin merge slot first.
2. Deploy `backend/charts/incluster-guards/prod_omi_incluster_guards_values.yaml`
   through `gcp_incluster_guards.yml` only. Confirm the installed script
   ConfigMap's `floors.json` contains 24 fours, the guard is enabled, and its
   readings are fresh. Do not disable or manually bypass the writer.
3. Let the scheduled guard Job apply the HPA floor. Its `apply_floor_schedule`
   checks `rolled_back(spec)` and defers while the external metric
   `parakeet_request_latency_p99` is present. Lowering also requires one full
   15-minute lookback under the current identity and a usable current reading.
   The write uses a JSON patch that **tests the whole observed `/spec` before
   replacing `/spec/minReplicas`**: a concurrent guard rollback or HPA policy
   edit makes that patch fail instead of overwriting it. Any identity change
   from the guard upgrade starts a new lookback; wait for it. No static Helm
   minimum or operator patch may clear the rollback marker or its floor of 12.
4. Verify the guard reports `floor_schedule` applied (or explicitly deferred),
   then read the exact-context HPA min/max, desired and ready replicas, shared
   v1/v2 latency and queue age. A legitimate rollback remains at 12 until its
   own consecutive clean-window recovery clears it; a floor of 12 alone is
   not a rollback marker because the normal schedule can also request 12.
   The existing down budget is one pod per 900 seconds plus 900 seconds
   stabilization, so eight to four takes about an hour plus node drain. Do not
   accept a pending/deferred floor as an applied saving.
5. Use an approved GKE operator identity for these separate **pool autoscaler
   edits**, never the report's `ro-prod` identity. Merging the PR and deploying
   the guard chart do not apply them:

   ```bash
   gcloud container node-pools update parakeet-pool \
     --project based-hardware --cluster prod-omi-gke --region us-central1 \
     --enable-autoscaling --min-nodes=0 --max-nodes=4
   gcloud container node-pools update parakeet-pool-b \
     --project based-hardware --cluster prod-omi-gke --region us-central1 \
     --enable-autoscaling --min-nodes=0 --max-nodes=3
   ```

   `parakeet-pool-v2` already has total min 0/max 10 and needs no edit. Preserve
   all maxima. The HPA supplies the serving pods, so zero pool minima do not
   mean zero replicas. Let normal drain and cluster autoscaling reclaim idle
   nodes; do not resize pools down, evict busy pods, or delete nodes manually.

Dedicated batch L4 workers stay at three; T4 diarizer-batch stays HPA/pool 1–18;
listen stays HPA 30–60 with zero CPU-pool minima. Do not count those pools as
interchangeable GPU capacity or pre-allocate capacity above 16.

## Restore through the same atomic writer

Remove the prod `floorSchedule.hours` override so it inherits the prior
schedule below; the Parakeet chart minimum already remains eight. Deploy
only the guard chart through `gcp_incluster_guards.yml`; **do not dispatch the
Parakeet Helm/image workflow for restoration**. Let the existing schedule writer
restore the current UTC hour's prior floor using the same `/spec` test patch.
It defers while `parakeet_request_latency_p99` is present, so a restore to eight
cannot erase an active twelve-replica rollback. Preserve that rollback until the
guard's own clean-window recovery clears it; no manual marker removal.

Restore the first pool's min to 2 and the `-b` pool's min to 1 using the commands
above with those minima; keep maxima 4 and 3 and v2 total min/max 0/10. Verify
the scheduled floor, readiness and actual nodes. The schedule, rather than the
static eight in source, remains the live floor writer. Any later normal
Parakeet image/HPA deployment is a separately reviewed operator action.

Prior UTC-hour schedule (indexes 0–23):

```text
[10,10,10,10,10,8,8,8,8,8,10,10,12,12,11,11,11,11,10,10,9,9,8,8]
```
