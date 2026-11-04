# Streaming GPU retirement

Retire the shared streaming Parakeet GPU service after the
fleet-off caller train. `STT_GPU_FLEET_OFF=true` selects Modulate then Soniox
for residual live sessions, Modulate for prerecorded/PTT, and local ONNX for
file VAD. Dedicated batch workers load their own models and keep running.
Preserve hosted VAD, both diarizers, LID, reservations, all audio/PVCs, the
shared Gateway and every dev load balancer. Lead ruling 17ce24 (2026-11-04):
LID stays this pass; VAD and its pools stay untouched while its actual endpoint
dependency remains unproven. Do not pass `--lid-dependency-cleared`.

## Lead order and gates

Only the rollout lead applies charts or runs teardown. Source declarations and
tests do not prove serving state. The ordinary production Parakeet chart
now forces zero replicas and removes its HPA and dedicated ingress, so applying
it before callers drain is unsafe.

1. Before chart retirement, capture the warm baseline with the read-only form:

   ```bash
   python3 backend/scripts/retire_streaming_gpu.py --snapshot
   ```

   The lane captured positive replicas, HPAs, floors and ingress rollback specs
   in the default backup directory before any production changes. Re-runs do
   not replace that original baseline with zeros. Preserve Helm revisions and
   serving image digests in the lead's operator record too.

2. Finish the fleet-off caller train. Inspect `status.traffic` and each serving
   Cloud Run revision's image digest/source identity and fleet-off flag, plus all ready GKE
   listen/pusher pods and canaries. Soniox/Modulate key bindings, vendor credits
   and concurrency, and the batch hard-3 gates must be healthy. Disable stale
   boot-probe/redrive jobs before rerunning an old image. No production account
   data or secret payload is needed for these checks.

3. Measure 15 minutes after the last old caller drains. Require zero shared
   Parakeet HTTP/LID/stream requests through gateway and direct
   routes. Missing metrics mean unknown. Remove host/session scale-up wakes,
   including the lead's scheduled `parakeet-minmax.sh 6` wake, before zero.

4. Preserve LID and VAD capacity. Batch admission calls
   `record_language.classify_probe` and `batch_language.resolve_language`, which
   can call `language_gate.self_detect`. An explicitly configured
   `HOSTED_LID_API_URL` is used even during fleet-off. The production Cloud Run
   binding is secret-backed, so its actual endpoint is not established by a
   read-only revision inspection. The lead's approved Parakeet-only pool list
   below excludes VAD/LID capacity; stop if an LID pod occupies a target pool.
   Before any later VAD/LID retirement, prove that binding is empty or belongs
   to an independent retained LID service; preserve any GPU it needs. The
   dedicated worker has no hosted VAD/LID binding and its strict VAD is local;
   legacy file VAD bypasses hosted VAD while fleet-off is true. Those facts
   alone do not prove the secret-backed admission LID target.

5. Merge this PR with `parakeetSuspended=true`, then deploy the guard chart at
   that exact reviewed SHA once, with its production values. Do not deploy the
   intervening cap-assert fix alone: that would let a blind trip restore 12.
   Verify suspension, no HPA patch permission, no floors.json, and no active
   guard Job (deadline 240 seconds). Never raise a cap to satisfy the guard.
   Independent batch monitoring/state remain intact. Keep the guard state.

6. Apply the reviewed Parakeet chart and its off overlay, preserving the
   serving image tag. Both prod and bare chart defaults set `fleetRetired=true`:
   deployments stay at zero, HPAs and dedicated ingresses are omitted even with
   stale positive replica/HPA/ingress overrides, and optional Japanese streaming
   stays at zero. Dev and the CPU LID release explicitly opt out. Do not apply
   the VAD chart or its off overlay in this pass.

7. Review the offline plan, then execute under the approved `prod-operator` tier:

   ```bash
   python3 backend/scripts/retire_streaming_gpu.py
   python3 backend/scripts/retire_streaming_gpu.py --apply --caller-drain-approved --host-writers-retired --borrowed-pools-reviewed --backup-dir /Volumes/Ephemeral/scratch/teardown-1104/rollback
   ```

   The default executes no commands. Apply requires explicit lead gates,
   positive saved rollback replicas, fully rolled callers, guard suspension and
   removed HPA write permission. Each operation prints before/after state and a
   rollback instruction. A batch/diarizer/unknown pod, persistent/host audio
   volume, or repurposed pool label stops the operation. Every non-DaemonSet pod
   must leave target pools before capacity is changed.

   The pool allowlist is only `parakeet-pool`, `parakeet-pool-b`, `parakeet-pool-v2`.
   Lead ruling 2026-11-04 04:14Z: retain pool objects,
   set autoscaling min=max=0, resize to zero, and verify zero registered nodes.
   Preserve total-vs-per-zone autoscaling scope. If GKE refuses 0/0, stop and
   report it; never substitute a positive maximum or delete a pool. A deletion
   follow-up needs a new decision after 24 clean hours at zero. Production batch
   borrowing is disabled; re-enabling the old pools requires a new ruling.
   [GKE autoscaling API](https://docs.cloud.google.com/kubernetes-engine/docs/reference/rest/v1beta1/projects.locations.clusters.nodePools#NodePoolAutoscaling).

   The tool also deletes the two dormant legacy Deepgram HPAs after checking its
   deployments remain zero. Its ingress is removed only with a complete 24-hour
   zero-request metric window for every attached forwarding rule. Missing,
   partial or nonzero data preserves that ingress and prints a lead follow-up.
   The query ends three minutes behind the current minute for telemetry delay;
   its exact window is written in the receipt. Inspect it read-only with:

   ```bash
   python3 backend/scripts/retire_streaming_gpu.py --check-legacy-traffic
   ```

   Verify GKE reclaims the retired dedicated ingress forwarding rules/backends
   before claiming all LB savings. Do not delete the Vertex reservation, dev
   LBs, PVCs, audio, or any batch/diarizer capacity. The legacy engine/NLLB pools
   remain outside this fixed capacity allowlist and require lead disposition.

## Recovery and routing

Keep vendors as fallback if batch trips. Restoring the old GPU path requires a
separate lead decision: restore the saved pool autoscaling bounds, apply warm
charts with `fleetRetired=false,maintenanceMode=false`, and restore positive
replicas/HPA settings. Wait for node and model readiness before changing caller
routing. Reacquisition during an L4 stockout has no bounded recovery time.
Restore floors/write permission only after that decision and readiness check.

`utils/batch_pipeline/route_selection.py:decide` handles batch saturation by
choosing the next healthy primary vendor (Modulate). Soniox is vendor failover
through `provider_stt.py:_vendor_words`; paid-once/health/spend gates can hold a
unit durably rather than running a vendor immediately. The `GPU` route means the
dedicated batch worker, whose chart pins `BATCH_PIPELINE_POOL_KIND=dedicated_batch`.
`config/stt_provider_policy.py:provider_is_enabled` denies shared Parakeet for
every serving surface during fleet-off. Direct prerecorded calls redirect to
Modulate. Dedicated LID is a separate dependency, as described above.

Keep `VAD_GATE_MODE=active`: the streaming gate is local Silero ONNX. Turning it
off can increase vendor audio and does not save hosted VAD GPU capacity.
