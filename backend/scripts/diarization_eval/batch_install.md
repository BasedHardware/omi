# Batch diarizer prerequisites and lead-only installation

This is an opt-in production release. No command here has been applied by this PR.
The standard embedding release and all backend cutover flags remain unchanged.
Read-only inspection on 2026-10-14 found prometheus-adapter v0.12.0 (chart 4.14.2)
serving both custom/external metrics APIs from the in-cluster Prometheus server.
The stack is kube-prometheus-stack 75.15.1. No batch queue rule exists live yet.

## Dedicated capacity

Production batch already runs on the isolated T4 `diarizer-batch-pool`.
Do not recreate it from the earlier L4 capacity recipe or modify the embedding
`diarizer-pool`. The batch overlay pins that node-pool label, replaces inherited
embedding affinity with **null**, and tolerates its dedicated batch/GPU taints.
The lead verifies current node readiness, accelerator type, quota and capacity
before upgrading the separate `prod-omi-diarizer-batch` release.

One replica is the David-only floor. At the supplied T4 RTF .06, the 5% plan's
~140 multi-speaker audio-h/day requires ~8.4 GPU-h/day; this is planning arithmetic,
not a new T4 qualification. Do not apply the six-L4 full-rollout floor from the
historical `capacity.md` receipt to this ≤5% T4 ramp. Queue/latency and ≥12h at 5%
gate any further expansion; see [cohort stages](../../docs/diarizer-batch-cohort.md).

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

Use the **shared internal Gateway**, not a batch-only IP, DNS record or Ingress.
Follow [Gateway prerequisites, installation and route qualification](../../charts/internal-gateway/README.md)
with the environment-specific context and reserved `${ML_ENV}-ml-gateway-ilb-ip`.
Prod's reserved address is `172.16.160.20`; reservation alone is not route readiness.
The batch overlay disables Ingress and enables the `/diarizer-batch` HTTPRoute.
The Gateway rewrites the prefix to `/`; its backend timeout is 900 seconds.
Verify the programmed Gateway address and accepted/resolved route, native `/health`,
synthetic PCM contract and reachability from GKE pusher and actual Cloud Run VPC.
Do not create a batch hostname or substitute ClusterIP DNS for Cloud Run callers.
Keep legacy embedding addresses untouched until its separate caller migration.

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

Before cohort enablement require: one Ready pod on the dedicated pool; the programmed
shared Gateway address equals its reservation; adapter values describe that pod with a fresh
queue sample (zero idle is valid); HPA has no FailedGetPodsMetric; `/health` resolves
and responds from both GKE pusher and the actual Cloud Run VPC route. Use health or
public synthetic audio only for pre-cohort probes, never production user APIs/data.
No metric visibility or network reachability is claimed before installation.

## Separate David-only commit

The prerequisite chart changes alone do not enable backend/pusher admission.
The runtime-env cohort commit binds **backend**, **backend-sync** and **pusher** to:

```text
HOSTED_DIARIZATION_API_URL=http://172.16.160.20/diarizer-batch
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
deployment gated until all install/metric/routing checks above pass. Exact A–D
stages, observation gates and independent rollback are in the cohort runbook.

Rollback order: disable cohort admission/select legacy first; retain the endpoint
until in-flight shadow work drains; roll back the batch release digest or uninstall
that release only. Revert just the new adapter rule/scrape while preserving other
monitoring rules. Remove batch capacity only after verifying no users; retain the
shared Gateway and address while any NLLB, VAD, embedding or other route uses them.
No embedding node, release, ingress, IP or speaker history is mutated by rollback.
