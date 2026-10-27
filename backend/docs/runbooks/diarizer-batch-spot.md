# Batch diarizer: Spot T4 burst, warm on-demand fallback

Owner: rollout lead. This is an apply packet, **not an applied change**. The
author used `ro-prod` for infrastructure, aggregate metrics, catalog and billing
reads. Node-pool creation and the Helm upgrades require the lead's approved
fleet-change window and GKE write identity. Do not change `batch-pipeline-pool`,
its Spot sibling, Parakeet, embedding, IAM, or cohort admission.

## Measured baseline (2026-10-27 04:35–04:42 UTC)

`prod-omi-gke` is regional in `us-central1`. `diarizer-batch-pool` is
`n1-standard-8`, 30 GiB, one T4, 100 GiB `pd-balanced`, `COS_CONTAINERD`,
`GKE_METADATA`, autorepair/autoupgrade, a/b/c/f locations and `ANY` allocation.
Autoscaler bounds are **total min 1 / max 18**, not per-zone. Three Ready batch
replicas each request 2 CPU / 6 GiB / one GPU; HPA bounds are 1–18. A fourth
registered node with no allocatable GPU disappeared during inspection. This is
not a reason to change the already-approved node shape or throughput target.

The preceding 24-hour GPU duty-cycle query returned 146 hourly observations
across 75 churned pod series: sample-weighted mean 7.43%, largest hourly mean
32.5%. These are utilization samples, not concurrency or spare-throughput proof.
CPU allocatable-utilization averaged 5.92% across 133 hourly node observations;
the instantaneous node CPU sample was 2–4%. T4 is offered in a/b/c/f and regional
preemptible-T4 quota was 16, usage 0. **Neither quota nor an accelerator listing
proves Spot stock.** Only a Ready Spot node and warmed served image do that.

Three settled billing-export days attributed by node resource name or
`goog-k8s-node-pool-name=diarizer-batch-pool`:

| UTC day | Gross USD | Credits USD | Net USD | T4 hours |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-23 | 72.63 | -1.45 | 71.18 | 101.59 |
| 2026-10-24 | 60.11 | -1.72 | 58.39 | 83.83 |
| 2026-10-25 | 44.60 | -1.26 | 43.34 | 62.21 |

This averages 3.44 T4 nodes and $57.64/day net (about $1,753/month at 730 hours).
It is a declining, variable baseline. Resource-attributed credits do not prove
that a project-wide commitment payment can be avoided.

Cloud Billing Catalog API, Compute Engine `6F81-5844-456A`, USD, `us-central1`:

| Component | On-demand hourly USD | Spot hourly USD | SKU (on-demand / Spot) |
| --- | ---: | ---: | --- |
| T4 | 0.35 | 0.2085 | `88B8-C3ED-03F0` / `1A25-07A3-AB6D` |
| N1 CPU, per vCPU | 0.031611 | 0.01544 | `2E27-4F75-95CD` / `D498-1ECA-87C1` |
| N1 RAM, per GiB | 0.004237 | 0.002069 | `6C71-E844-38BC` / `5451-0A15-0123` |

The node is $0.729998/h on-demand vs $0.39409/h Spot, plus the same $10/month
disk. One displaced node saves **$245/month list-equivalent**; 3 nodes →
1 on-demand + 2 Spot is about **$490/month**, not an assured $800. At the
three-day average and unchanged total node-hours, retaining one on-demand node
projects about $598/month list-equivalent. Billing rates/credits differ; confirm
net savings after apply. No vendor changes occur, so STT/LLM/API spend is unchanged.
Raw receipts and query: workspace `data/run-2026-10-27-spotdiar/`.

## Scheduling and availability contract

1. Keep `diarizer-batch-pool` on-demand, total min 1 / max 18. Do not replace it
   in place or shrink its fallback ceiling during this rollout.
2. Add `diarizer-batch-pool-spot`, same T4/node shape, zones, service/env labels,
   GPU and batch taints; total min 0 / max 16, `ANY`. This cap fits the observed
   Spot T4 quota. No autoscaler or priority changes to other pools.
3. The **same Helm release** renders `prod-omi-diarizer-batch-fallback`, fixed
   one replica and pinned to the on-demand pool with `gke-provisioning=standard`.
   Its complete runtime spec is derived from the primary Deployment; only its
   name, instance selector, replicas and placement differ. Normal batch workflow
   upgrades therefore roll both Deployments to the same digest automatically.
   It reuses the primary ServiceAccount and has no separate release, HPA,
   Service, Ingress, BackendConfig or HTTPRoute to drift or collide.
   The renderer rejects a primary maximum plus the fixed warm replica above
   `warmFallback.maxTotalReplicas=18`; remove the drained warm Deployment before
   restoring a primary maximum of18.
4. Upgrade `prod-omi-diarizer-batch`: min 1 / max 17, prefer existing Spot nodes
   but allow on-demand spillover. Both Services select the batch-specific route
   label shared by the two Deployments. Embedding and dev lack that label. The
   shared Gateway path remains `/diarizer-batch`, timeout 900s, and balances over
   individual Ready endpoints from both Deployments (no fixed per-group weight).
5. Include the fallback instance in the existing Prometheus scrape job. Its
   queue is observable, while HPA continues to select only its own burst pods.

The warm replica preserves a serving endpoint through **Spot-only loss**; it
does not preserve requests already executing on a preempted GPU or guarantee
full throughput during a stockout. GKE gives Spot Pods at most 15s to terminate;
the batch timeout is 900s. Retry/custody behavior must be qualified before
apply. Do not claim a PDB or PriorityClass can prevent provider preemption.

The warm-Deployment design raises the minimum from one GPU pod to two. At sustained
one-pod demand this costs an extra Spot node (~$298/month list + disk), so the
lead must compare **total** before/after node-hours. Do not book savings just
because Spot nodes exist. Preferred affinity does not drive autoscaler decisions
or migrate existing pods; GKE normally expands the cheaper eligible pool, but
stockouts and already-running on-demand pods can prevent the expected saving.
Use normal safe scale-down, never force an eviction to manufacture savings.
The 18-replica bound is steady state; default rolling updates can request extra
surge GPUs temporarily. Include old, new, warm and Pending capacity in the cost
window; a pool cap is not a promise of capacity or instantaneous rollout.

## Lead apply sequence

Re-fetch main, confirm the reviewed PR SHA is included, and capture current
Helm revisions, digest, replicas/HPA, Ready endpoints, node bounds and billing
baseline. Preserve all live tuning overrides in private local values files;
do not print workload YAML/env or check those files into Git. Use the exact
served digest, never a tag or a newer application build for this infra change.
This repository manages these pools with gcloud/runbooks, not Terraform.

After the lead approves the fleet window, refresh quota, node identity/scopes,
zones and GKE version; compare to the baseline. With that GKE-write identity:

```bash
SPOTDIAR_PROJECT=based-hardware
SPOTDIAR_CLUSTER=prod-omi-gke
SPOTDIAR_REGION=us-central1
SPOTDIAR_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
SPOTDIAR_NAMESPACE=prod-omi-backend
SPOTDIAR_NODE_SA=$(gcloud container node-pools describe diarizer-batch-pool \
  --project="$SPOTDIAR_PROJECT" --cluster="$SPOTDIAR_CLUSTER" \
  --region="$SPOTDIAR_REGION" --format='value(config.serviceAccount)')
test -n "$SPOTDIAR_NODE_SA"
gcloud container node-pools create diarizer-batch-pool-spot \
  --project="$SPOTDIAR_PROJECT" --cluster="$SPOTDIAR_CLUSTER" \
  --region="$SPOTDIAR_REGION" \
  --node-locations=us-central1-a,us-central1-b,us-central1-c,us-central1-f \
  --spot --location-policy=ANY --enable-autoscaling \
  --num-nodes=0 --total-min-nodes=0 --total-max-nodes=16 \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-t4,count=1,gpu-driver-version=default \
  --image-type=COS_CONTAINERD --disk-type=pd-balanced --disk-size=100 \
  --service-account="$SPOTDIAR_NODE_SA" --scopes=cloud-platform,userinfo-email \
  --workload-metadata=GKE_METADATA --enable-autorepair --enable-autoupgrade \
  --node-labels=service=diarizer-batch,env=prod \
  --node-taints=nvidia.com/gpu=present:NoSchedule,omi.ai/diarizer-batch=true:NoSchedule
```

Pool status RUNNING at size zero is not capacity acceptance. Before changing the
serving release, qualify at least one real Ready Spot T4 with the exact image and
public synthetic PCM using an isolated, bounded probe. Confirm driver/GPU
allocatable, scheduling, model warmup and successful diarization; remove only
that probe after recording receipts. A failed stock or image probe stops here.
Prove Spot-loss retries and the shared-endpoint behavior in a non-serving
qualification release first; this author has no authority to run that experiment.

Bootstrap the warm Deployment **inside the existing release**, retaining the
old Service selectors and on-demand primary placement. This first upgrade is
mandatory before any normal batch workflow deploy on the new chart. There is
no new release to install or independently update:

```bash
: "${SPOTDIAR_IMAGE_DIGEST:?exact currently served sha256 digest}"
helm --kube-context "$SPOTDIAR_CONTEXT" -n "$SPOTDIAR_NAMESPACE" \
  upgrade prod-omi-diarizer-batch backend/charts/diarizer \
  -f backend/charts/diarizer/prod_omi_diarizer_values.yaml \
  -f backend/charts/diarizer/prod_omi_diarizer_batch_values.yaml \
  -f backend/charts/diarizer/prod_omi_diarizer_batch_bootstrap_values.yaml \
  --set-string image.digest="$SPOTDIAR_IMAGE_DIGEST" --atomic --wait --timeout 15m
kubectl --context "$SPOTDIAR_CONTEXT" -n "$SPOTDIAR_NAMESPACE" \
  rollout status deployment/prod-omi-diarizer-batch-fallback --timeout=900s
# Verify BOTH Deployments are Ready on-demand, and synthetic /health and audio
# pass directly on the warm replica. Then omit ONLY the bootstrap overlay:
helm --kube-context "$SPOTDIAR_CONTEXT" -n "$SPOTDIAR_NAMESPACE" \
  upgrade prod-omi-diarizer-batch backend/charts/diarizer \
  -f backend/charts/diarizer/prod_omi_diarizer_values.yaml \
  -f backend/charts/diarizer/prod_omi_diarizer_batch_values.yaml \
  --set-string image.digest="$SPOTDIAR_IMAGE_DIGEST" --atomic --wait --timeout 15m
```

Apply any captured tuning overrides to both commands after the checked-in
values; retain the reviewed scheduling and route labels. Verify both rendered
Deployment images, commands, resources and env references match before apply.
Do not use `--reuse-values`: the second upgrade must remove the temporary
primary nodepool pin and restore the shared Service selector from batch values.
Apply the monitoring scrape delta through the lead's existing monitoring Helm
release (see [batch installation](../../scripts/diarization_eval/batch_install.md));
preserve unrelated monitoring values and chart version.

Before moving more work, require: warm on-demand Ready replica; primary and
fallback Pod IPs both in the existing Gateway Service's Ready EndpointSlices;
accepted/resolved HTTPRoute and healthy backend; fresh queue samples for both
instances; healthy HPA metrics; synthetic success via the actual GKE and Cloud
Run Gateway route. Record primary/fallback image IDs and actual Spot node count.
Run the existing per-pod/route synthetic contract, then watch queue age/depth,
diarization error/timeout rate, endpoint readiness and total node-hours for a
full hour. Stop on lost warm readiness, unavailable endpoints, failed HPA
metrics, request failures or a rising queue that cannot drain on fallback.
Do not resize other GPU pools to pass this gate. A one-pod fallback is an
availability floor; if stockout demand exceeds it, retain on-demand scale-out.
Record billable net costs after export settles before claiming savings.

## Rollback (lead-owned; no node or data deletion)

1. Upgrade the current release with the same reviewed values/digest **plus**
   `--set-string 'nodeSelector.cloud\.google\.com/gke-nodepool=diarizer-batch-pool'`.
   Keep `warmFallback.enabled=true`, the shared selectors, and primary HPA max
   **17**. Use `--atomic --wait --timeout 15m`; verify primary replicas are Ready
   on-demand and queues recover before removing any warm serving capacity.
   The existing on-demand pool remains total min 1 / max 18.
2. Upgrade with the bootstrap overlay again. It retains the on-demand pin and
   HPA max17, but restores instance-only Service selectors. The warm Deployment
   remains running while requests already assigned to it drain. Prove its active
   requests and queue are zero; retain a full request-timeout window if those
   signals are unavailable. At every steady stage, 17 primary + 1 warm fits18.
3. Only after that drain, repeat the bootstrap-overlay upgrade with
   `--set warmFallback.enabled=false --set autoscaling.maxReplicas=18`. Helm
   removes only the drained warm Deployment; there is still one release and
   the primary stays pinned on-demand. Do not restore max18 before this step.

Keep the empty Spot pool at min0; primary placement now excludes it. Do not
blindly roll back to the original Helm revision: its unpinned primary could
scale onto Spot again. No pool, release or customer data deletion is needed.
Revert the fallback scrape inclusion in the next monitoring roll if desired.
Verify replicas, placement, served digest, Gateway health, queue recovery and
costs. No Cloud Run/backend/listen/pusher deploy is part of this change.

References: [GKE Spot behavior](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/spot-vms),
[autoscaler choice](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler),
[Spot pricing](https://cloud.google.com/spot-vms/pricing),
[Billing Catalog API](https://cloud.google.com/billing/v1/how-tos/catalog-api).
