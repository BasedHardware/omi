# Streaming GPU retirement

Production configuration declares `STT_GPU_FLEET_OFF=true`; merging the activation
change authorizes rollout and must wait for the lead's G0-G3 cost and readiness gates.
This source declaration is not evidence of serving state. The Parakeet guard stays
unsuspended until the lead completes the caller rollout and drain below. The switch selects Modulate, then Soniox, for managed live sessions (Modulate is a vendor,
not a fleet GPU, and costs about half of Soniox live), Modulate for prerecorded and PTT work, local ONNX for file VAD, and the existing vendor language probe unless `HOSTED_LID_API_URL` supplies a
separately qualified language-ID service. An unavailable dedicated LID service
returns to the vendor probe, never the retired shared endpoint.
It denies Parakeet in static selection, the cost router, default fallback,
idle failback and direct prerecorded calls. Existing sessions drain during the
normal rollout. Custom user-funded STT follows its existing path.

The dedicated batch worker loads its own Parakeet/pyannote models and stays up.
`diarizer-batch` stays up. **The embedding diarizer also stays up:** speech-profile
enrollment, saved-person matching, speaker learning and batch voice evidence
still call `/v2/embedding`. Soniox speaker ordinals do not replace embeddings;
the batch diarizer app does not expose that endpoint. Turning that GPU off
requires a separately reviewed replacement or an explicit product ruling.

## Lead execution order

Only the rollout lead executes these steps. Run from the reviewed product
worktree after its PR is merged. Preserve serving image digests and Helm revision
numbers before changing anything. Do not change node pools or storage here.

Capture these non-secret capacity values before retirement and retain them in
the operator record. They must be positive; if a value is missing or already
zero, stop and recover the last approved warm baseline instead of guessing.

```bash
GPUFLEET_PARAKEET_ROLLBACK_MIN=$(kubectl -n prod-omi-backend get hpa prod-omi-parakeet -o jsonpath='{.spec.minReplicas}')
GPUFLEET_PARAKEET_ROLLBACK_REPLICAS=$(kubectl -n prod-omi-backend get deployment prod-omi-parakeet -o jsonpath='{.spec.replicas}')
GPUFLEET_VAD_ROLLBACK_MIN=$(kubectl -n prod-omi-backend get hpa prod-omi-vad -o jsonpath='{.spec.minReplicas}')
GPUFLEET_VAD_ROLLBACK_REPLICAS=$(kubectl -n prod-omi-backend get deployment prod-omi-vad -o jsonpath='{.spec.replicas}')
```

Require batch admission and `SERVER_BATCH_ONLY_MOBILE_PERCENT=100` to be
serving first, then measure residual vendor demand and confirm credits and
concurrency before enabling the retirement route. A later batch rollback
retains vendor routing and must be budgeted for the full streaming fallback.
The lead owns qualification and activation for all traffic, with a review by
2026-11-03 12:00Z. If the economic or vendor-readiness gates have not passed by
then, report the blocker instead of silently leaving a dormant rollout.
This temporary default-off stage protects against increased vendor spend:
if batch trips to zero and full pre-flip streaming volume returns, retiring
the GPUs increases the modeled bill. That is the fallback stress case. In the
expected post-flip case, eligible live traffic goes to dedicated batch and
only excluded residual managed streaming uses the vendors (Modulate first,
Soniox as its failover); qualify that residual
instead of pricing all former Parakeet live traffic as Soniox.
The minimum economic test is that avoided allocated GPU cost exceeds added
Modulate and Soniox live spend plus legacy Modulate spend, including
idle nodes retained by pool minimums. A smaller warm floor also needs measured
peak throughput and latency qualification; average audio-hours do not prove it.

1. After lead approval, change `STT_GPU_FLEET_OFF` to true in the production
   runtime overlay and the listen/pusher production chart values, regenerate
   `backend/deploy/runtime_env.yaml`, and review that single activation change.
   Rollback before it serves: retain false. Do not suspend the guard yet.
   Deploy the reviewed image/config to Cloud Run, listen and pusher with the
   canonical rollout train, first using its dry-run. Verify the actual serving
   Cloud Run revisions and every ready GKE pod receive `STT_GPU_FLEET_OFF=true`
   and the Soniox/Modulate key *bindings* exist; never print key values. Update
   or disable reruns of dormant `boot-probe` and `op1-batch-redrive-epoch3` jobs
   before they can run an old image against the retired endpoints. The old
   notifications job's VAD binding must also be cleared before its next run.
   Rollback: keep GPUs warm, redeploy the previous image/config. After zero,
   restore capacity first (step 5) and only then restore routing.

2. Observe at least 15 minutes after the last old pod/revision drains. Require
   zero shared-Parakeet HTTP/LID/stream requests, zero hosted-VAD requests,
   healthy Soniox transcription and batch hard-3 gates, and healthy vendor
   credits/concurrency. A traffic series that is absent is unknown, not zero.
   Check both internal gateway and direct ClusterIP callers. Rollback: retain
   warm replicas and roll the prior routing. A batch admission rollback to zero
   must still use Soniox live and Modulate legacy; do not couple this switch to
   `batch-pipeline` admission or to the batch safety guard.

3. Suspend the **Parakeet guard only**, retaining its chart and state:

   ```bash
   helm upgrade prod-omi-incluster-guards backend/charts/incluster-guards -n prod-omi-backend --reuse-values --set parakeetSuspended=true --wait --timeout 5m
   kubectl -n prod-omi-backend get cronjob prod-omi-incluster-guards -o jsonpath='{.spec.suspend}{"\n"}{range .status.active[*]}active{"\n"}{end}'
   ```

   Wait until `.status.active` is empty: suspension does not cancel a running
   Job (its active deadline is 240 seconds). Do not set the floor schedule to
   zero; it only accepts 1..12 and the guard would restore 12 for a dark fleet.
   Rollback: after restoring ready GPU capacity, apply
   `--set parakeetSuspended=false`. This does not suspend the independent batch
   guard or its rollback actuator.

   The check prints only the suspended state and an `active` marker for each
   remaining Job. Do not print full active references or workload objects.

4. Apply the VAD and Parakeet off overlays **only after steps 1–3 pass**:

   ```bash
   helm upgrade prod-omi-vad backend/charts/vad -n prod-omi-backend --reuse-values -f backend/charts/vad/prod_omi_vad_off_values.yaml --wait --timeout 10m
   helm upgrade prod-omi-parakeet backend/charts/parakeet -n prod-omi-backend --reuse-values -f backend/charts/parakeet/prod_omi_parakeet_off_values.yaml --wait --timeout 10m
   kubectl -n prod-omi-backend get deployment prod-omi-vad prod-omi-parakeet -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas
   ```

   These retain the HPAs with min 1 and set deployment replicas to zero.
   [Kubernetes implicit maintenance mode](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/#implicit-maintenance-mode-deactivation)
   stops positive-minimum HPAs from reviving explicitly deactivated workloads.
   Do not use `minReplicas: 0`: these pod/resource-metric HPAs are not a
   scale-from-zero design. Rollback: step 5. Deployment zero releases pods;
   savings only realize as nodes leave, and pool minimums can retain idle nodes.

5. Capacity rollback (keep routing on vendors while doing this):

   ```bash
   helm upgrade prod-omi-parakeet backend/charts/parakeet -n prod-omi-backend --reuse-values --set maintenanceMode=false --set autoscaling.minReplicas="${GPUFLEET_PARAKEET_ROLLBACK_MIN:?capture the warm baseline first}" --wait --timeout 30m
   kubectl -n prod-omi-backend scale deployment prod-omi-parakeet --replicas="${GPUFLEET_PARAKEET_ROLLBACK_REPLICAS:?capture the warm baseline first}"
   helm upgrade prod-omi-vad backend/charts/vad -n prod-omi-backend --reuse-values --set maintenanceMode=false --set autoscaling.minReplicas="${GPUFLEET_VAD_ROLLBACK_MIN:?capture the warm baseline first}" --wait --timeout 15m
   kubectl -n prod-omi-backend scale deployment prod-omi-vad --replicas="${GPUFLEET_VAD_ROLLBACK_REPLICAS:?capture the warm baseline first}"
   kubectl -n prod-omi-backend rollout status deployment/prod-omi-parakeet --timeout=30m
   kubectl -n prod-omi-backend rollout status deployment/prod-omi-vad --timeout=15m
   ```

   Explicit scale is required because removing `spec.replicas` alone does not
   reactivate an HPA. Once the pods are Ready, turn `STT_GPU_FLEET_OFF=false` on
   every routing runtime with a reviewed config rollback, then unsuspend the
   Parakeet guard. If a Helm wait fails while at zero, perform the explicit
   scale rather than waiting for an HPA to wake itself. **Node reacquisition
   has no bounded recovery time in the observed L4 stockout**; vendors remain
   the safe rollback route while capacity is unavailable. VAD cold starts
   have historically taken about 4–6 minutes after a node is available.

After zero, keep the off overlays on subsequent GPU-chart upgrades and persist
the intended maintenance/suspended-guard state in the owning production
configuration. A later warm-baseline apply can revive the workloads or floor
writer. Make that persistence change only after the caller rollout and drain
gates pass; it must preserve the ordering above.

Keep `VAD_GATE_MODE=active`: that streaming gate uses process-local Silero ONNX,
not `prod-omi-vad`. Disabling it can increase vendor audio and does not save the
hosted VAD node. Soniox connection billing also depends on idle-close policy;
do not claim all skipped silence becomes an equivalent Soniox saving.
