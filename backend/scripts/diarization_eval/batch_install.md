# Batch diarizer prerequisites and lead-only installation

This is an opt-in production release. No command here has been applied by this PR.
The standard embedding release and all backend cutover flags remain unchanged.
Read-only inspection on 2026-10-14 found prometheus-adapter v0.12.0 (chart 4.14.2)
serving both custom/external metrics APIs from the in-cluster Prometheus server.
The stack is kube-prometheus-stack 75.15.1. No batch queue rule exists live yet.

## Dedicated capacity

OpenTofu in `infrastructure/opentofu/README.md` owns WIF/IAM/state only and
explicitly excludes GKE. There is no node-pool IaC owner in this repo. The lead
must create an isolated L4 pool; do not modify `diarizer-pool`. The observed GKE
network is `omi-prod-vpc-1`; existing L4 nodes use COS_CONTAINERD, GKE_METADATA,
and the default node service account. The following mirrors that identity/scopes,
not a new IAM grant. Quota and zonal L4 availability are lead prerequisites.

```bash
gcloud container node-pools create diarizer-batch-pool \
  --project based-hardware --cluster prod-omi-gke --region us-central1 \
  --node-locations us-central1-b --machine-type g2-standard-8 \
  --accelerator type=nvidia-l4,count=1,gpu-driver-version=default \
  --image-type COS_CONTAINERD --workload-metadata GKE_METADATA \
  --service-account 208440318997-compute@developer.gserviceaccount.com \
  --scopes gke-default --num-nodes 1 --enable-autoscaling \
  --total-min-nodes 1 --total-max-nodes 18 \
  --node-labels service=diarizer-batch,env=prod \
  --node-taints omi.ai/diarizer-batch=true:NoSchedule,nvidia.com/gpu=present:NoSchedule \
  --enable-autorepair --enable-autoupgrade
```

The batch overlay pins `cloud.google.com/gke-nodepool=diarizer-batch-pool`, replaces
the inherited embedding affinity with **null** (empty maps merge in Helm), and
tolerates the dedicated taint. Existing GPU pods do not tolerate that batch taint.
One replica is the David-only floor, with an HPA ceiling of eighteen. After cohort
qualification, raise the pool's total minimum and `autoscaling.minReplicas` to six
in a reviewed values change; preserve max eighteen. Full-rollout provisional sizing
is 89 GPU-h/day at 45% of 6,300 audio-h/day (range 12–50%), measured on a shared L4
with a 40% CUDA memory cap. See `capacity.md` for limits of that measurement.

## Metric prerequisites

GMP `PodMonitoring` is disabled for this overlay: the live adapter does not query
GMP. The production Prometheus values add a direct `diarizer-batch-metrics` pod
scrape with namespace and pod labels. The custom adapter rule exports
`omi_diarization_v2_queue_depth` per pod, using max by the requested resource
labels; HPA consumes it as a Pods/AverageValue=1 metric. It counts running plus
admitted waiting/upload work. Missing samples remain missing, never fabricated zero.

Lead: reconcile the monitoring releases at their observed chart versions, including
all existing rules/values. First run the owning adapter drift review tool,
`backend/scripts/diff_prod_adapter.py`, so unrelated live/source drift is reviewed;
these commands are not permission to overwrite unreviewed monitoring differences.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  -n prod-omi-monitoring upgrade prod-omi-kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack --version 75.15.1 \
  -f backend/charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml \
  --atomic --wait --timeout 15m
helm --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  -n prod-omi-monitoring upgrade prod-omi-prometheus-adapter \
  prometheus-community/prometheus-adapter --version 4.14.2 \
  -f backend/charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  --atomic --wait --timeout 10m
```

## Image and serving prerequisites

The registry now enables built-image imports for `main` and `batch_main` under
`python -I`, explicitly inserts `/app`, and forbids pretrained model loading.
It also exercises real CPU tensors through raw PCM and WAV decoding with
TorchCodec imports, torchaudio file loading and external decoder processes blocked.
Missing copied first-party modules fail the probe; #21437's installed-dependency
exclusion cannot hide this failure. The existing `gcp_diarizer.yml` runs this probe
before image publication. Models still warm during startup before TCP readiness.

The pyannote import warning about TorchCodec/libavutil concerns its optional file
decoder. `/v2/diarization` accepts mono 16kHz PCM16 or WAV; WAV decoding uses stdlib
`wave`, then NumPy/Torch CPU tensors. Both the pipeline and centroid extraction
receive waveform dictionaries, not file paths. No FFmpeg/TorchCodec is needed by
this v2 decode path. The standard embedding file path is outside this claim.

Local Docker was unavailable: the actual GPU-image probe was not run locally.
Focused tests stage sources with the canonical Docker COPY resolver, execute the
same isolated import/probe with only native/model dependencies stubbed, and
mutation-test removal of the copied turn module. A new built image must pass the
registered real probe before the lead installs it.

After this PR is merged by the lead, use the existing prod `gcp_diarizer.yml` on
main to build, probe and publish the immutable image through GitHub Actions.
It deploys the standard release; the separate batch install below is manual.
Use that run's exact image digest, not `latest`, an unmerged branch or the old
13ae594 image (which does not include the new smoke helper).

Reserve a **new** internal IP; Cloud Run cannot resolve ClusterIP service DNS.

```bash
gcloud compute addresses create prod-diarizer-batch-ilb-ip-address \
  --project based-hardware --region us-central1 \
  --address-type INTERNAL --subnet omi-deepgram-gke-us-central1-prod-vpc-1-subnet-1
BATCH_IP=$(gcloud compute addresses describe prod-diarizer-batch-ilb-ip-address \
  --project based-hardware --region us-central1 --format='value(address)')
```

Create DNS A `diarizer-batch.omi.me` pointing to `$BATCH_IP` in the owning DNS
provider. Public NS lookup returned `dns1.registrar-servers.com` and
`dns2.registrar-servers.com`; GCP RO could not list managed zones. Add a DNS-only
A record with host `diarizer-batch`, value `$BATCH_IP` in the authoritative omi.me
zone, then verify resolution from both caller routes.
Keep the existing `diarizer.omi.me` and its reserved IP unchanged. The separate
internal GCE ingress routes only v2 diarization and health, with its own BackendConfig
900s timeout. Existing backend/pusher VPC routing must reach the new private IP.

The chart supports a validated digest, which takes precedence over tag. Pin the
successful image build's published `sha256:<64 lowercase hex>` digest:

```bash
# Set BATCH_IMAGE_DIGEST to the successful GitHub run's published image digest.
: "${BATCH_IMAGE_DIGEST:?required published sha256 digest}"
helm --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  -n prod-omi-backend upgrade --install prod-omi-diarizer-batch backend/charts/diarizer \
  -f backend/charts/diarizer/prod_omi_diarizer_values.yaml \
  -f backend/charts/diarizer/prod_omi_diarizer_batch_values.yaml \
  --set-string image.tag= --set-string image.digest="$BATCH_IMAGE_DIGEST" --atomic --wait --timeout 15m
kubectl --context gke_based-hardware_us-central1_prod-omi-gke -n prod-omi-backend \
  rollout status deployment/prod-omi-diarizer-batch --timeout=900s
kubectl --context gke_based-hardware_us-central1_prod-omi-gke get --raw \
  '/apis/custom.metrics.k8s.io/v1beta1/namespaces/prod-omi-backend/pods/*/omi_diarization_v2_queue_depth?labelSelector=app.kubernetes.io%2Finstance%3Dprod-omi-diarizer-batch'
```

Before cohort enablement require: one Ready pod on the dedicated pool; the ingress
address equals the new reservation; adapter values describe that pod with a fresh
queue sample (zero idle is valid); HPA has no FailedGetPodsMetric; `/health` resolves
and responds from both GKE pusher and the actual Cloud Run VPC route. Use health or
public synthetic audio only for pre-cohort probes, never production user APIs/data.
No metric visibility or network reachability is claimed before installation.

## Separate David-only commit

The prerequisite PR changes no backend/pusher enablement. A separate unmerged
cohort commit binds **backend**, **backend-sync** and **pusher** to:

```text
HOSTED_DIARIZATION_API_URL=http://diarizer-batch.omi.me:80
TRANSCRIPTION_FINAL_PASS_DIARIZER=pyannote_shadow
TRANSCRIPTION_FINAL_PASS_BACKEND=pyannote
TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST=vi7SA9ckQCe4ccobWNxlbdcNdC23
TRANSCRIPTION_FINAL_PASS_PERCENT=0
TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE=false
TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=false
```

Shadow admission remains David-only: `TRANSCRIPTION_SHADOW_ENABLED=true`,
`TRANSCRIPTION_SHADOW_KILL_SWITCH=false`, the same `TRANSCRIPTION_SHADOW_UID_ALLOWLIST`,
`TRANSCRIPTION_SHADOW_PERCENT=0`, and `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS=1`.
Cloud Run declarations live under `prod.cloud_run.services.{backend,backend-sync}.env`
in the generated `backend/deploy/runtime_env.yaml` (edit authoritative
`backend/deploy/runtime_env/prod.overlay.yaml` and run the composer); pusher must match both `prod.gke.pusher.env`
in that manifest and `backend/charts/pusher/prod_omi_pusher_values.yaml`.
Render/validate through the existing runtime-env tools, then use the owning backend
and pusher deployment workflows. Do not use ad hoc live env updates. Keep the cohort
commit out of main until all install/metric/routing gates above pass.

Rollback order: disable cohort admission/select legacy first; retain the endpoint
until in-flight shadow work drains; roll back the batch release digest or uninstall
that release only. Revert just the new adapter rule/scrape while preserving other
monitoring rules; remove the new node pool/IP/DNS only after verifying no users.
No embedding node, release, ingress, IP or speaker history is mutated by rollback.
