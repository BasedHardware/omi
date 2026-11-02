# Streaming GPU retirement

Production sets `STT_GPU_FLEET_OFF=true` on listen, pusher and all four Cloud Run
roles. This selects Soniox for managed live sessions, Modulate for prerecorded
and PTT work, local ONNX for file VAD, and the existing vendor language probe.
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

1. Deploy the reviewed image/config to Cloud Run, listen and pusher with the
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
   kubectl -n prod-omi-backend get cronjob prod-omi-incluster-guards -o jsonpath='{.spec.suspend}{" active="}{.status.active}{"\n"}'
   ```

   Wait until `.status.active` is empty: suspension does not cancel a running
   Job (its active deadline is 240 seconds). Do not set the floor schedule to
   zero; it only accepts 1..12 and the guard would restore 12 for a dark fleet.
   Rollback: after restoring ready GPU capacity, apply
   `--set parakeetSuspended=false`. This does not suspend the independent batch
   guard or its rollback actuator.

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
   helm upgrade prod-omi-parakeet backend/charts/parakeet -n prod-omi-backend --reuse-values --set maintenanceMode=false --set autoscaling.minReplicas=7 --wait --timeout 30m
   kubectl -n prod-omi-backend scale deployment prod-omi-parakeet --replicas=7
   helm upgrade prod-omi-vad backend/charts/vad -n prod-omi-backend --reuse-values --set maintenanceMode=false --set autoscaling.minReplicas=1 --wait --timeout 15m
   kubectl -n prod-omi-backend scale deployment prod-omi-vad --replicas=2
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

Keep `VAD_GATE_MODE=active`: that streaming gate uses process-local Silero ONNX,
not `prod-omi-vad`. Disabling it can increase vendor audio and does not save the
hosted VAD node. Soniox connection billing also depends on idle-close policy;
do not claim all skipped silence becomes an equivalent Soniox saving.
