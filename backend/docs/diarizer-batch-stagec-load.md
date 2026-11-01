# Stage C aggregate load model (2026-10-14 UTC)

Preparation receipt, not a production qualification or deployment authorization.
Source checkout: current `origin/main` base `909bfd7aa397`; measurements use
`source ~/.local/bin/gcp-agent-env.sh ro-prod`. No recordings, transcripts,
Firestore/account records or stored payloads were read. Only numeric diagnostic
log fields and aggregate time series were reduced; raw log rows were not saved.

## Production benchmark update (2026-10-15)

Lead's public-corpus production receipt has 20 waves / 29 successful requests:
5/15/30/60-minute inference-wall RTF .039/.041/.041/.042 on one T4;
concurrency two serializes. Use .042 for this long-audio planning update, not
.308 from four tiny requests or the later .060 planning assumption. At 5% of
483.298 audio-h/h, demand is 24.165 audio-h/h, 873 candidate calls/h and
1.015 inference-worker-hours/h (3,654 worker-seconds/h). At 70% occupancy,
`ceil(24.165 * .042 / .70) = 2` T4 replicas. The HPA's 1–18 and batch node-pool
maximum 18 cover this estimate, but one warm replica supplies only 16.667
h/h at the target, or 23.810 h/h at saturation; scaling latency still matters.
One serialized worker supplies ~602 calls/h at 70% for this aggregate mix;
request mix/short-sync overhead, CPU time and p95 are not qualified by this arithmetic.

The independent sync bound is 10 audio-h + 1,000 attempts/UTC hour and one
in-flight pass/process, with bounded Redis I/O and legacy output on refusal.
At 5%, estimated sync demand is 5.903 h/h / 808 attempts/h; pusher is 18.262 h/h
/ 64.9 attempts/h. Saturating the sync audio cap plus this pusher estimate is
28.262 h/h, or 1.187 worker-h/h: still two nodes at 70%. Pusher's complete C/D
stages cap selected audio at 80/400 h/day, with two nonblocking slots/process;
these daily limits are not hourly burst guarantees. The batch API admits only
one running + two waiting requests/replica, then returns 429. Overload/failure
keeps legacy output; existing work is not canceled by a client timeout. Limits
bound admitted work, not a p95 SLO; hourly/day boundaries and autoscaler lag
remain ramp gates. Checked-in prod stays B (0%, David-only, pusher 1 h/day);
C is the explicit 1% stage and D is 5%. Earlier estimates below are historical.

## Closed-hour fleet demand

Window: **2026-10-14 16:00–17:00Z** (not the still-open 17:00 hour).

| Surface | Audio-hours per fleet hour | Candidate calls per hour |
| --- | ---: | ---: |
| Sync + backfill (format proxy) | 118.063 | 16,168 successful segments |
| Pusher | 365.235 | 1,298.082 finalization attempts |
| Combined | 483.298 | 17,466.082 |

Sync duration comes from 22,439 provider byte-length diagnostics: Parakeet
19,234 attempts / 325,924.927 seconds; Modulate 3,205 / 99,103.321 seconds.
Assuming the common mono PCM16/16kHz WAV format, use
`max(0, bytes_len - 44) / (sample_rate * 2)`. This is a header-derived estimate,
not decoded audio. The diagnostic sample_rate is a caller default, not a parsed
WAV header. Sync also accepts PCM8/8kHz and other rates; PCM8/8kHz would make
this proxy undercount duration by 4x. The aggregate logs do not establish format
mix, so **118.063 is not an exact measured fleet audio duration**. At the all-PCM8
sensitivity extreme it becomes 472.254 h/h; uncapped 1%/5%/100% node estimates
below become 4/19/369 at the same RTF. It includes 2,582 provider retry diagnostics (18 Parakeet,
2,564 Modulate), so it is **gross provider-work proxy (conservative for retry duplication only)** for
successful final-pass audio. Successful segment logs determine request count,
not new-conversation logs: sync merges otherwise hide substantial workload.
Pusher counters count attempts, including reprocessing; conversation wall span
is the stored-audio proxy, not measured VAD speech or guaranteed stored audio.

Log filters (Cloud Run services backend-sync and backend-sync-backfill only):

```text
timestamp >= "2026-10-14T16:00:00Z" AND timestamp < "2026-10-14T17:00:00Z"
(textPayload =~ "(parakeet|modulate|deepgram)_prerecorded_from_bytes bytes_len=" OR
 jsonPayload.message =~ "(parakeet|modulate|deepgram)_prerecorded_from_bytes bytes_len=")
# Aggregate bytes_len, sample_rate and retry attempt; discard every row.
(textPayload : "event=sync_transcription_segment outcome=success" OR
 jsonPayload.message : "event=sync_transcription_segment outcome=success")
# Count timestamps only. Both reads finished below their 50,000/20,000 row limits.
```

PromQL at `time=2026-10-14T17:00:00Z`:

```promql
sum(increase(omi_capture_finalized_total{job="pusher-metrics"}[1h]))
sum(increase(omi_capture_finalized_seconds_total{job="pusher-metrics",span="conversation"}[1h])) / 3600
```

Use Kubernetes **GET** service proxy:
`/api/v1/namespaces/prod-omi-monitoring/services/http:prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/query`.
The ro-prod identity cannot port-forward; no privilege escalation is needed.
`omi_sync_lane_speech_ms_total` was absent at inspection; a zero/absent series
cannot establish zero sync load. `omi_conversation_shape` logs only bound new
records and are not the full segment/audio workload.

## Batch measurements and provisional extrapolation

At approximately 17:35Z, the batch job exposed **4** completed inferences,
**8.32875** audio seconds and RTF sum **1.2307242245**, giving mean request
RTF **0.307681**. Histogram counts: <=.05:1, <=.1:2, <=.5:3, <=1:4.
These are seconds-long samples; they do **not** qualify long-recording throughput.
There is no batch request-latency or inference-seconds histogram/counter in this
revision. Exact per-request latency/GPU seconds therefore cannot be recovered
from these unpaired aggregate sums. `RTF * duration` below is an explicitly
estimated inference wall-time proxy for GPU occupancy, not measured GPU busy time.

```promql
omi_diarization_v2_rtf_count{job="diarizer-batch-metrics"}
omi_diarization_v2_rtf_sum{job="diarizer-batch-metrics"}
omi_diarization_v2_rtf_bucket{job="diarizer-batch-metrics"}
omi_diarization_v2_audio_seconds_total{job="diarizer-batch-metrics"}
```

Assume uniform volume sampling by UID and every candidate reaches batch (no
single-speaker triage, opt-in, duration exclusion or budget reduction). This
conservative *eligibility* scenario still has unqualified RTF and cohort skew:
a UID percentage is not a deterministic audio percentage. David's allowlisted
load and retries consume the same sync cap, but his incremental volume cannot
be isolated from the pre-hash aggregate logs.

| Selected percent | Requests/hour | GPU seconds/hour, estimated | T4 nodes at 70% target |
| --- | ---: | ---: | ---: |
| 1 | 174.66 | 5,353 | 3 |
| 5 | 873.30 | 26,766 | 11 |
| 100 | 17,466.08 | 535,326 | 213 |

Formula: `GPU seconds/hour = 483.298 * 3600 * fraction * 0.307681`;
`nodes = ceil(GPU seconds/hour / (3600 * .70))`.
The implied mix is 99.61 audio seconds/request, 30.65 inference seconds/request,
117.46 requests/replica-hour at full occupancy, or **82.22 at 70%**.
This mix differs sharply by surface: sync ~26.29s audio/request versus pusher
~1,012.9s. Do not apply seconds-long probe latency directly to long pusher calls.

Live GETs verified `diarizer-batch-pool`: `n1-standard-8`, one T4 per node,
autoscaler total minimum **1**, maximum **18**; deployment currently **1** replica.
Each replica reserves one GPU and the API's single executor/GPU lock serializes
inference. Admission capacity three means **one running plus two queued**, not
three parallel GPU calls. Capacity is not a queue/timeout SLO; the current floor
of one is below this provisional 1% estimate. **100% exceeds the pool ceiling.**
Hold deployment qualification until representative long-audio timing, p95 client
latency, queue/refusal pressure and cohort audio skew have real samples. No
node/pool/HPA change is part of this PR.

## Why the sync cap is suitable for a 5% preparation

One process-local slot refuses immediately. Shared atomic Redis reservations
admit at most **10 audio-hours and 1,000 attempts per UTC hour**, across all
sync hosts, ahead of embeddings and provider work. The measured 5% sync scenario
is **5.90 audio-hours and 808.4 calls/hour**, within both defaults under the PCM16 format assumption. At the all-PCM8
sensitivity extreme, 5% sync is 23.61 h/h: the audio cap sheds excess work into
legacy instead of attempting an unsafe full ramp. Pusher retains
its existing daily shadow budget; it does not consume the new sync budget.

At the measured RTF proxy, saturating the sync cap alongside the observed 5%
pusher audio rate is 8.696 GPU-hours/hour, or **13 nodes at 70%**. Two hourly
sync buckets bursting across a boundary give approximately **17 nodes**, below
18, assuming the same pusher rate and RTF. This is not a hard GPU-time guarantee:
RTF deterioration, long-call timeouts and pusher bursts still require the gates.
The hard guarantee is bounded admitted audio/attempts and bounded per-process
concurrency, with immediate legacy output on refusal or Redis failure. Budgets
are not refunded; retries cannot evade them. Every stage keeps these sync caps.

Rollback uses complete A from the stage JSON: authoritative=false, sync=false,
percentages zero, daily shadow cap one; recompose and redeploy all four hosts.
Existing promoted records are not rewritten. Lead owns that action.

## Long-audio qualification preparation (2026-10-15)

The 3/11/213 estimate remains an unqualified short-input extrapolation. No long
batch probe, corpus upload, cluster mutation or deployment was executed by the
author. The bounded Redis correction is in #21546, commit `12456bd18a34`:
`create_bounded_redis_client(0.5)`, a real nonresponding TCP peer test, and
`acquire(blocking=False)`. The harness is a separate preparation PR.

### Public corpus and method

`scripts/bench_diarizer_batch.py --prepare DIR` fetches only the official
[OpenSLR LibriSpeech test-clean archive](https://www.openslr.org/12/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), checking its
[published MD5](https://openslr.trmal.net/resources/12/md5sum.txt).
Attribution: Vassil Panayotov, Daniel Povey, Guoguo Chen, Sanjeev Khudanpur.
It decodes FLAC only, never corpus transcripts; four stable speaker IDs alternate
in clip order. Clips repeat to fill precisely 120 minutes. The manifest includes
source/archive checksum, attribution, modifications, per-clip speaker/time
references, and PCM SHA256. Each shorter input is a prefix of the same PCM.
This is a reproducible multi-speaker concatenation, with **no overlap or natural
conversation acoustics**; also qualify AMI overlap/room audio before asserting
conversation quality. Do not infer DER from the speaker-count diagnostic.

One 230,400,000-byte mono PCM16/16kHz object plus its manifest is sufficient.
The author prepares local artifacts; **lead** uploads them once into an existing
bucket whose existing probe identity can read the synthetic prefix. No IAM or
account-data changes are implied. The probe downloads those two exact objects
without listing buckets or accessing the internet and verifies provenance/hash.

The matrix uses the same `HttpDiarizer('pyannote')` as the final pass, including
raw PCM, endpoint suffix, backend validation, 5s connect cap, and deadline.
Defaults: three repeats, 600s shipping read deadline. Each wave has one or two
simultaneous requests to **one pod IP**, bypassing Gateway load balancing only
for per-replica capacity measurement. It refuses a nonempty initial queue and
aborts on error/429/timeout: cancellation does not cancel the server GPU job.
Abort is not evidence of server idleness; lead waits for queue zero before rerun.
Do not restart/delete the target to clear a probe. Repeat through the Gateway
separately to qualify its 900s limit; a larger diagnostic client timeout does not
change either deployed limit. No timeout increase or production tuning is part
of this preparation.

Receipts include client wall/RTF, server audio/inference seconds/RTF, wave
audio-hours/hour, status/error class, counts and model provenance; never turns,
vectors or text. Optional model fields preserve the server's existing timing
metadata without changing the client transport. Client-minus-inference includes
upload, queue, decoding and response overhead; it is **not isolated queue time**.
DCGM samples `DCGM_FI_DEV_GPU_UTIL` once/second, filtered by exact `Hostname`;
missing/blocked/mismatched exporter is `unavailable`, not zero utilization.
These are utilization samples, not measured CUDA kernel seconds. Other traffic
on the node can contaminate them; compare exact target/node and queue counters.

| Audio minutes | C=1 wall / infer RTF / p95 | C=2 wave h/h / p95 | GPU mean / samples | Outcome |
| ---: | --- | --- | --- | --- |
| 5 | to be measured | to be measured | to be measured | NOT RUN |
| 15 | to be measured | to be measured | to be measured | NOT RUN |
| 30 | to be measured | to be measured | to be measured | NOT RUN |
| 60 | to be measured | to be measured | to be measured | NOT RUN |
| 120 | to be measured | to be measured | to be measured | NOT RUN |

Three repeats are an initial smoke sample, not a credible tail-latency estimate.
Use `--repeats 10` for follow-up and report sample count with empirical p95. Fit
server seconds `a + b * audio_seconds` on successful C=1 inputs; report intercept,
long-input slope and per-duration residuals, not the mean of tiny-input RTFs.
Use aggregate wave completed audio/wall time for throughput. C=2 has one running
and one queued request; it cannot double inference concurrency in this revision.
For fleet sizing use measured sustained audio-hours/replica-hour times 70%,
request mix/timeout failures, and cohort audio skew. Recompute at 1%, 5%, 100%
and compare max18; do not promote past5% from this unfilled table.

### Exact lead-owned probe commands

Run from the reviewed benchmark checkout. These commands create a temporary
probe/ConfigMap and synthetic objects; **lead executes them**, using the lead's
existing authorized identity. Author production reads remain ro-prod only.
`BENCH_BUCKET` and `BENCH_SA` must name an existing approved artifact bucket and
Kubernetes identity already permitted to read it; no secrets/env are copied.

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/bench_diarizer_batch.py \
  --prepare /Volumes/Ephemeral/scratch/diarizer-bench-public-corpus
BENCH_SHA=$(git rev-parse HEAD)
: "${BENCH_BUCKET:?existing approved synthetic artifact bucket}"
: "${BENCH_SA:?existing approved probe KSA with artifact-read access}"
BENCH_PREFIX="gs://$BENCH_BUCKET/synthetic/diarizer-bench/$BENCH_SHA"
gcloud storage cp /Volumes/Ephemeral/scratch/diarizer-bench-public-corpus/corpus.pcm \
  /Volumes/Ephemeral/scratch/diarizer-bench-public-corpus/manifest.json "$BENCH_PREFIX/"
BENCH_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
BENCH_NS=prod-omi-backend
BENCH_ID="diarizer-bench-${BENCH_SHA:0:12}-$(date -u +%H%M%S)"
BENCH_DIR=$(mktemp -d)
# Select a ready batch replica from this deployment; save metadata, never env.
kubectl --context="$BENCH_CONTEXT" -n "$BENCH_NS" get pods -o json | python3 -c '
import json,sys
pods=json.load(sys.stdin)["items"]
print(json.dumps({"items":[{"metadata":{k:p["metadata"][k] for k in
    ("name","uid","ownerReferences","deletionTimestamp") if k in p["metadata"]},
    "spec":{"nodeName":p["spec"].get("nodeName")},
    "status":{k:p["status"][k] for k in ("podIP","containerStatuses") if k in p["status"]}}
    for p in pods]}))' > "$BENCH_DIR/pods.json"
python3 - "$BENCH_DIR/pods.json" > "$BENCH_DIR/target.json" <<'PY'
import json, sys
pods = json.load(open(sys.argv[1]))['items']
pods = [p for p in pods if any(o['name'].startswith('prod-omi-diarizer-batch-')
        for o in p['metadata'].get('ownerReferences', []))
        and all(s['ready'] for s in p['status'].get('containerStatuses', []))
        and p['status'].get('podIP') and not p['metadata'].get('deletionTimestamp')]
assert pods, 'No ready batch replica'
p = sorted(pods, key=lambda p: p['metadata']['name'])[0]
image = p['status']['containerStatuses'][0]['imageID'].removeprefix('docker-pullable://')
assert '@sha256:' in image, 'Require served target digest'
print(json.dumps(dict(pod=p['metadata']['name'], uid=p['metadata']['uid'],
    ip=p['status']['podIP'], node=p['spec']['nodeName'], image=image)))
PY
# Served backend-listen image includes HttpDiarizer + backend runtime dependencies.
BENCH_IMAGE=$(kubectl --context="$BENCH_CONTEXT" -n "$BENCH_NS" get pods \
  -l app.kubernetes.io/name=backend-listen --field-selector=status.phase=Running \
  -o 'jsonpath={.items[0].status.containerStatuses[0].imageID}')
BENCH_IMAGE=${BENCH_IMAGE#docker-pullable://}
case "$BENCH_IMAGE" in *@sha256:*) ;; *) echo 'Require served client digest'; exit 1;; esac
kubectl --context="$BENCH_CONTEXT" -n "$BENCH_NS" create configmap "$BENCH_ID" \
  --from-file=bench_diarizer_batch.py=backend/scripts/bench_diarizer_batch.py \
  --from-file=diarization.py=backend/models/diarization.py
# Optional: set BENCH_DCGM_URL to http://<exporter-on-target-node-pod-IP>:9400/metrics.
# Metadata-only discovery: get monitoring pods, select exporter on target.node.
# Leave empty if exporter/route absent; the receipt explicitly says unavailable.
BENCH_DCGM_URL=${BENCH_DCGM_URL:-}
python3 - "$BENCH_ID" "$BENCH_IMAGE" "$BENCH_SA" "$BENCH_PREFIX" \
  "$BENCH_DIR/target.json" "$BENCH_DCGM_URL" > "$BENCH_DIR/pod.json" <<'PY'
import json, sys
name, image, sa, prefix, target_file, dcgm = sys.argv[1:]
t = json.load(open(target_file))
args = ['-c', "import runpy;runpy.run_path('/probe/bench_diarizer_batch.py',run_name='__main__')",
    '--gcs-prefix', prefix, '--corpus', '/data', '--base', 'http://' + t['ip'] + ':8080',
    '--target-image', t['image'], '--client-image', image, '--dcgm-node', t['node'],
    '--timeout', '600', '--repeats', '3']
if dcgm: args += ['--dcgm-url', dcgm]
print(json.dumps({'apiVersion': 'v1', 'spec': {
    'restartPolicy': 'Never', 'activeDeadlineSeconds': 21600, 'serviceAccountName': sa,
    'securityContext': {'fsGroup': 10001},
    'containers': [{'name': name, 'image': image, 'workingDir': '/app',
        'command': ['python'], 'args': args, 'env': [{'name': 'PYTHONPATH', 'value': '/app'}],
        'resources': {'requests': {'cpu': '250m', 'memory': '1Gi'},
                      'limits': {'cpu': '2', 'memory': '3Gi'}},
        'volumeMounts': [{'name': 'probe', 'mountPath': '/probe', 'readOnly': True},
            {'name': 'probe', 'mountPath': '/app/models/diarization.py',
             'subPath': 'diarization.py', 'readOnly': True},
            {'name': 'data', 'mountPath': '/data'}]}],
    'volumes': [{'name': 'probe', 'configMap': {'name': name}},
                {'name': 'data', 'emptyDir': {'sizeLimit': '1Gi'}}]}}))
PY
# Keep target metadata and JSONL with the run receipt; no workload changes.
kubectl --context="$BENCH_CONTEXT" -n "$BENCH_NS" run "$BENCH_ID" \
  --image="$BENCH_IMAGE" --restart=Never --attach=true --rm --quiet \
  --pod-running-timeout=2m --overrides="$(cat "$BENCH_DIR/pod.json")" \
  > "$BENCH_DIR/results.jsonl"
BENCH_STATUS=$?
kubectl --context="$BENCH_CONTEXT" -n "$BENCH_NS" delete configmap "$BENCH_ID"
cat "$BENCH_DIR/results.jsonl"
test "$BENCH_STATUS" -eq 0
```

Confirm the chart's container port (`8080` above) and target UID/image before and
after the run; a rollout/competing traffic invalidates isolation. The reviewed
optional-timing model is mounted into the **probe only** because the served
image predates this harness. The serving service/model/image is unchanged.
The probe KSA needs synthetic-object read access only. No `envFrom`, production
runtime secrets, Hugging Face keys, Firestore access or extra GPU are needed.
To test the Gateway, regenerate only probe args `--base` as
`http://172.16.160.20/diarizer-batch`; record replica count, because that run no
longer establishes one-replica concurrency. Check aborting queues before rerun.

### Where time goes: source, not measured component shares

`diarizer/batch_main.py:lifespan` initializes WeSpeaker v2 and Community-1 before
readiness. Model load is startup-only, not steady-state request inference.
`api_v2.py` admits/upload-buffers then queues a single executor; decoding happens
before `final_pass.py:infer` starts its timer. The timer includes GPU_LOCK wait,
pipeline, exclusive/overlap reconstruction and canonical centroids. It is wall
time, not synchronized CUDA-event GPU time. No stage durations are exposed.

Pinned [pyannote.audio 4.0.3 SpeakerDiarization source](https://github.com/pyannote/pyannote-audio/blob/4.0.3/src/pyannote/audio/pipelines/speaker_diarization.py)
performs overlapping-window segmentation (speech/overlap activity, not a separate
Omi VAD endpoint), batched internal embeddings, clustering, and reconstruction.
The [clustering implementation](https://github.com/pyannote/pyannote-audio/blob/4.0.3/src/pyannote/audio/pipelines/clustering.py)
uses NumPy/SciPy-style CPU operations; moving it to CPU is not a new optimization.
Omi then makes up to three separate whole-window WeSpeaker calls per speaker
(0.5–10s overlap-free clips) for canonical centroids. Interval cutting, exclusive
turns, overlap detection, vector normalization/weighted mean, PCM conversion and
JSON serialization are CPU work. All inference work currently holds GPU_LOCK,
including CPU work. Profile total pipeline and post-centroid phase separately,
then use pyannote hooks around segmentation/embeddings/clustering with explicit
CUDA synchronization only in a diagnostic image; hooks alone include asynchronous
launch effects. Such an instrumented image requires a separate lead deployment.

### Ranked levers and conditional 100% cost

No speedup below is measured or a vendor promise. Planning baseline **long-input
RTF=0.060**, 70% effective utilization, one replica/node; replace with the table.
Whole-node budget inputs: T4/n1-standard-8 **$0.73/h** (including $0.35 GPU),
L4/g2-standard-8 **$0.854/h**. Refresh region/contract pricing before procurement:
[Google GPU/node pricing](https://cloud.google.com/products/compute/pricing/accelerator-optimized),
[general-purpose CPU/RAM pricing](https://cloud.google.com/products/compute/pricing/general-purpose).
These rounded on-demand planning inputs omit disk, networking, GKE fees, floors,
negotiated discounts and other product costs.

For 100% rollout, incremental diarizer cost per worn hour is
`f * node_hour_price * RTF / .70`, where `f=processed_audio_hours/worn_hours`
(including repeats). Table uses **f=1**; for f=.5 halve it. Total product cost
is `B + this`, where B is separately measured ASR/storage/backend/LLM cost per
worn hour. B and f are not established by these fleet aggregates. Thus there is
no defensible absolute total-product projection or claim that $0.05–0.08 is met.
Baseline diarization alone is $0.063/worn-hour; the short-input RTF.308 proxy
would be $0.321. Gains overlap and **must not be multiplied together**.

| Priority / lever | Hypothesized whole-request RTF multiplier | Incremental $/worn-hour at 100%, f=1 | Risk / experiment |
| --- | ---: | ---: | --- |
| 1. Larger internal embedding batch (+ segmentation batch sweep) | .65–.90 | .041–.056 | Moderate: T4 16GiB OOM; sweep existing model defaults, peak VRAM, DER |
| 2. fp16/autocast for neural inference | .50–.80 | .031–.050 | Moderate/high: numeric/centroid drift; compare turns, DER and owner-match parity |
| 3. L4 instead of T4 | .50–.80 | .037–.059 (L4 price) | Moderate: measured hardware crossover, quota/floor cost; no assumed 2x speed |
| 4. Batch Omi post-centroid segments | .90–1.00 | .056–.063 | Low/moderate: variable-length masking; only <=3 clips/speaker, likely small long-input gain |
| 5. Window/chunk step and size | .60–.90 | .038–.056 | High: fewer overlapping windows change embeddings, speaker count/boundaries; recalibrate DER |
| 6. ONNX/TensorRT neural submodels | .40–.70 | .025–.044 | High: export/masks/dynamic shapes, engine compatibility, parity; not entire clustering pipeline |
| 7. CPU clustering / release GPU lock during CPU phases | .90–1.00 | .056–.063 | Already CPU; lock split needs bounded staging and concurrency/memory tests |
| 8. Pin pyannote/model versions | 1.00 | .063 | Already 4.0.3 + Community-1/WeSpeaker revisions pinned; reproducibility, no direct gain |

T4→L4 is cheaper only if `RTF_L4/RTF_T4 < .73/.854 = .855` at equal utilization.
At hypothetical T4 RTF.06 the fleet requires 1/3/42 nodes at1/5/100%; L4 RTF.03
requires1/2/21. Both100% scenarios exceed max18. To fit18 at the PCM16 fleet
proxy needs RTF <= `18*.70/483.298 = .0261`, regardless of chip price. To meet
$0.08 total/worn-hour at f=1, T4 .06 leaves B <= $0.0174; L4 .03 leaves
B <= $0.0434. Neither B nor long RTF has been measured. Qualification requires
timeouts/queue pressure, sustained throughput, quality parity and a billing
budget together before scaling past5%.
