# Diarizer-batch public shadow qualification

Owner: cl2-deploy, after lead2's go. This document authorizes no deployment.
Install a separate release; never upgrade the production release with canary
values. Do not change clients, the ILB/Gateway, production PodMonitoring or HPA.
The existing batch HPA max **5** is a precondition (PR #24970).

## Artifact and access prerequisites

Use merged main containing this change. Record source SHA/tree, build run ID,
OCI digest and runtime imageID, corpus hash, start/end UTC and operator in the
dated qualification receipt. The candidate must be the **main-built digest**
that will later be promoted, with the image smoke gate passed. Record pinned
model revisions from replay provenance. Replay needs a separately approved
main-built `gcr.io/based-hardware/backend@sha256:…` CPU image providing the
shipping client, httpx, soundfile, google-cloud-storage and prometheus-client.
The renderer mounts this checkout's benchmark/replay scripts, so their source
SHA must also be recorded. Preflight those imports in the CPU image before
installing; there are no pip installs at Job runtime.

**Workflow limitation:** `gcp_diarizer.yml` currently builds and immediately
deploys its selected release. Its `image_digest` input supports only
batch-pipeline-worker. Do not dispatch a prod build to obtain a candidate, and
do not rebuild an already qualified candidate for promotion. A build-only /
shadow target and diarizer-batch digest-promotion input are **David-gated
follow-ups**; this PR deliberately changes no `.github/` files. An already
approved main-built artifact can be used if its immutable provenance is known.
The eventual prod workflow uses GitHub's `prod` environment and shared
prod-train lock; its required reviewer gate applies. An equivalent authorized
shadow Helm writer must join that lock. Do not bypass the environment gate
with a local human login. If the authorized writer cannot create a release,
ConfigMap or Job, stop and request the specific IAM/RBAC grant from David;
this PR grants nothing. The Job needs **no cloud credentials**, bucket access,
Secret payloads, Kubernetes API token or production data.

All commands below are instructions for the authorized cl2-deploy writer,
after authorization, using its explicit production kubeconfig/context. This
implementation lane must not execute them. Reads on m5 use the ro-prod tier
and `/Volumes/Ephemeral/scratch/cl2-fixnow/k.sh` (not a write-capable session).

## Install and prove isolation before replay

```bash
# Set these from the approved build receipts; do not use tags.
export CANDIDATE_DIGEST='sha256:<64 lowercase hex>'
export REPLAY_CLIENT_IMAGE='gcr.io/based-hardware/backend@sha256:<64 lowercase hex>'
export CTX=gke_based-hardware_us-central1_prod-omi-gke
export NS=prod-omi-backend
export RELEASE=prod-omi-diarizer-batch-canary
export CHART=backend/charts/diarizer
helm template "$RELEASE" "$CHART" -n "$NS" \
  -f "$CHART/prod_omi_diarizer_values.yaml" \
  -f "$CHART/prod_omi_diarizer_batch_values.yaml" \
  -f "$CHART/prod_omi_diarizer_batch_canary_values.yaml" \
  --set-string image.tag= --set-string "image.digest=$CANDIDATE_DIGEST" > shadow.yaml
# Inspect shadow.yaml: one Deployment and ClusterIP Service; no fallback,
# HPA, route, ingress, BackendConfig/NEG or PodMonitoring.
helm --kube-context "$CTX" -n "$NS" install "$RELEASE" "$CHART" \
  -f "$CHART/prod_omi_diarizer_values.yaml" \
  -f "$CHART/prod_omi_diarizer_batch_values.yaml" \
  -f "$CHART/prod_omi_diarizer_batch_canary_values.yaml" \
  --set-string image.tag= --set-string "image.digest=$CANDIDATE_DIGEST" \
  --atomic --wait --timeout 15m
```

Using the read-only wrapper (`k.sh`, default namespace prod-omi-backend):

```bash
K=/Volumes/Ephemeral/scratch/cl2-fixnow/k.sh
"$K" get pod -l app.kubernetes.io/instance=prod-omi-diarizer-batch-canary \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.labels}{" "}{.spec.nodeName}{" "}{.status.containerStatuses[*].imageID}{"\n"}{end}'
"$K" get service prod-omi-diarizer-batch prod-omi-diarizer-batch-gw \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.selector}{"\n"}{end}'
"$K" get endpointslice -l kubernetes.io/service-name=prod-omi-diarizer-batch \
  -o jsonpath='{range .items[*].endpoints[*]}{.targetRef.name}{"\n"}{end}'
"$K" get endpointslice -l kubernetes.io/service-name=prod-omi-diarizer-batch-gw \
  -o jsonpath='{range .items[*].endpoints[*]}{.targetRef.name}{"\n"}{end}'
"$K" get httproute prod-omi-diarizer-batch-gw -o jsonpath='{.spec.rules[*].backendRefs}{"\n"}'
"$K" get hpa prod-omi-diarizer-batch -o jsonpath='{.spec.scaleTargetRef}{" "}{.spec.maxReplicas}{"\n"}'
```

Compare pod names/addresses, not just counts. The canary must be absent from
**both** production EndpointSlices, and the production route must still name
only its existing Service. Check the canary Service's EndpointSlice contains
only its one pod. Check HPA max 5 targets only the production Deployment and
that no canary HPA exists. Abort/tear down if any proof is missing. Live
selectors may still use the old instance selector; chart render tests cover
the current shared route selector as well as Deployment instance isolation.
Candidate spec image must equal the approved digest; validate the runtime
imageID's OCI platform-manifest lineage if it differs from an OCI index digest.

## Public replay and 24-hour soak

Audio is [OpenSLR SLR12 LibriSpeech test-clean](https://www.openslr.org/12/),
CC BY 4.0, from LibriVox public-domain audiobook recordings, prepared by Vassil
Panayotov with Daniel Povey (Panayotov, Chen, Povey, Khudanpur, ICASSP 2015).
The existing `bench_diarizer_batch.py` checks the archive MD5
`32fa31d27d2e1cad72775fee3f4849a9`, reads FLAC only, and concatenates the first
four sorted public speakers in round-robin order, repeating to 120 minutes.
No transcript extraction, user audio, Firestore, GCS staging or API calls to
api.omi.me. Its manifest records attribution, modification and corpus SHA256.

The renderer emits a ConfigMap plus a CPU-only Job with a **fixed canary DNS**,
no target override, no cloud env/secret mounts, no API token, no Job retry,
26-hour hard deadline and one-day post-finish TTL. The replay uses the shipping
client with transport retries blocked, runs the 5/15/30/60/120-minute matrix at
concurrency 1 and 2, then repeats hourly for at least 24 hours after preparation.
Each wave checks queue idle and counters; unexpected traffic/counter resets,
request errors, invalid timings or gate misses stop further work. A client
timeout does not cancel GPU work: never restart/retry a failed Job.

```bash
python3 backend/scripts/render_diarizer_shadow_job.py \
  --client-image "$REPLAY_CLIENT_IMAGE" \
  --target-image "gcr.io/based-hardware/diarizer@$CANDIDATE_DIGEST" > replay.json
# Authorized writer only; first compare target-image with the actual shadow pod.
kubectl --context "$CTX" -n "$NS" apply -f replay.json
```

Read Job status/logs with `k.sh get job diarizer-batch-shadow-replay` and
`k.sh logs job/diarizer-batch-shadow-replay --timestamps`. Preserve JSONL in the
dated receipt before TTL cleanup. Each request records error class/status,
latency (`wall_seconds`), wall/inference RTF, audio duration, counts of
speakers/turns and model provenance; never text, vectors or turns. Summaries
contain outcome counts and numeric gates. The manifest declares the historical
baseline; **there is no baseline call to the production Service**.

Record a full 24-hour window after the new pod is Ready. Poll pod restartCount,
lastState/reason and startup readiness (30 × 10s startupProbe budget), and
preserve bounded status/metric receipts throughout. The Job's success only
means replay gates passed; it is not permission to roll.

DCGM: resolve the canary pod and its node above, then use the existing GMP
query tool under ro-prod. First inspect aggregate series labels for that node
and bind the exact canary pod/namespace labels exposed by the exporter (commonly
`pod`/`namespace`; verify before querying). With `POD` set to that pod:

```promql
max_over_time(DCGM_FI_DEV_FB_USED{namespace="prod-omi-backend",pod="<POD>"}[24h]) / 1024
```

This converts DCGM MiB to GiB. Execute via
`/Users/dazheng/workspace/omi/data/run-2026-11-05-omi-pipeline/tools/gmpq.sh '<query>'`.
Do not replace an absent pod series with zero or a fleet maximum. If only node
labels exist, prove the node/GPU has exactly this one GPU-consuming pod, bind
that node/GPU UUID, and document the attribution. Missing samples or ambiguous
attribution block the VRAM gate. For app memory, replay samples
`omi_diarization_v2_gpu_memory_bytes` every second during waves; DCGM supplies
the independent full-soak peak including idle/startup.

## Acceptance, teardown and later promotion

Historical baseline: cl2-fixnow `out-diarizer-image.md` §3–4, 24h ending
2026-11-09T07:37Z: 96 ok, 0 failed/rejected, mean RTF 0.0589 (rounded gate
reference **0.059**), app peak 1.62 GiB; DCGM 3,044 MiB (about 3.0 GiB).
These are historical production aggregates, not a same-corpus control.

| Gate | Required result |
| --- | --- |
| Errors | 0 failed, rejected/429, timeouts, unexpected requests or counter resets |
| RTF | Mean inference RTF ≤ **0.06785** (0.059 × 1.15); retain each duration/concurrency wave to inspect mix; no historical bucket counts exist for a numeric bucket-parity claim |
| Latency | Record every request's wall latency/RTF, inspect long/concurrent requests; no measured production latency histogram exists |
| VRAM | App sampled peak ≤ 2.0 GiB; DCGM full-window peak ≤ 3.5 GiB; missing data blocks |
| Stability | ≥24h Ready soak; 0 restarts/OOM; model load within startupProbe budget; record unchanged model revisions and numeric output counts |
| Incomplete coverage | Historical configured-host share 25.1%, success 0.07%, snapshot 2026-11-08T14:09Z. Must not worsen, but **unmeasured by this replay** |

`failed_incomplete_coverage` occurs in upstream final-pass audio assembly
before the diarizer call (`utils/conversations/final_pass_batch.py`). It is not
an HTTP diarizer outcome. Public API replay reports share **null**, never zero.
Its synthetic four-speaker population also cannot establish production quality
parity or a configured-host success share. Keep that gate **PENDING** until
lead2 accepts separate aggregate evidence/an approved synthetic final-pass
fixture; this lane must not read account data to fill it. No automated GO
claim is made. Any gate miss: stop replay, preserve receipts and tear down.

After the soak (pass or fail), cl2-deploy tears down **only** this release and
Job/ConfigMap, records end time and verifies no canary endpoints or GPU pod
remain. TTL deletes neither the Helm release nor the ConfigMap:

```bash
kubectl --context "$CTX" -n "$NS" delete job diarizer-batch-shadow-replay --wait=true
kubectl --context "$CTX" -n "$NS" delete configmap diarizer-batch-shadow-replay
helm --kube-context "$CTX" -n "$NS" uninstall prod-omi-diarizer-batch-canary --wait --timeout 10m
```

Only after the gate receipt and a **new lead2 GO**, cl2-deploy promotes the
**same qualified digest**, through the gated prod-train writer. Once the
David-approved digest-promotion workflow exists, it should perform the
equivalent of the following (without canary values), asserting both primary
and warm-fallback runtime imageIDs and unchanged production routing/HPA:

```bash
helm --kube-context "$CTX" -n "$NS" upgrade prod-omi-diarizer-batch "$CHART" \
  -f "$CHART/prod_omi_diarizer_values.yaml" -f "$CHART/prod_omi_diarizer_batch_values.yaml" \
  --set-string image.tag= --set-string "image.digest=$CANDIDATE_DIGEST" \
  --atomic --wait --timeout 15m
```

Rollback uses that same authorized writer/values, replacing the digest with
`sha256:4f327699acb2a9599847456954d2d6aa2f0969ffd1535068cf8584a4a08eec25`
(live spec re-read 2026-11-09T09:45–09:46Z). Recheck live identity before the
change and preserve the actual pre-roll digest if it has changed. Keep 24-hour
post-roll metrics; rollback on the same controlled gates. No embedding-service
roll, client flag flip, traffic split, HPA change or IAM change belongs here.
