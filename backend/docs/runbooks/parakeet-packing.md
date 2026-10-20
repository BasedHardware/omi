# Parakeet packing config train

PR C for plan v3 rows 14/28/29/44. Merge is dark: both new service switches
and the demand scaler default off. Prod remains 2 requests / 35% GPU,
min 3 / max 12, down stabilization 900s and one removal per 900s.
This document authorizes no production mutation by a read-only agent.

## What is measured

`parakeet_request_duration_seconds` is HTTP handler duration after multipart
parsing, not GPU service time. V1 includes upload read/write, queue, ASR and
conversion; v2 also includes speaker post-processing. A long backfill request
can therefore inflate the fleet p99 despite low GPU utilization. Scrapes rename
the application endpoint label to `exported_endpoint`; `endpoint` is the scrape
port. Keep this histogram and the delivery/refusal alarms.

`parakeet_service_seconds_per_audio_second{lane}` observes GPU worker batch wall
time / total audio duration, excluding admission queue, upload and v2 speaker
post-processing. Worker-side file decode and result serialization are included.
It is a per-batch service-efficiency distribution, not an end-to-end delivery
histogram or an audio-weighted fleet RTF. Compare at fixed duration/batch shapes.

Queue gauges refresh every 100ms on the service event loop, without requiring
`/batch/metrics` traffic. `parakeet_batch_lane_oldest_pending_seconds{lane}` is
the oldest *locally queued GPU quantum*, excluding running work. Zero means no
local wait; it does not mean an upstream Cloud Tasks queue is empty. Missing
telemetry must remain missing, never `or vector(0)`. Demand HPA uses the existing
active-requests target 2 plus pod queue ages (live .75s, backfill 30s), removing
raw GPU/p99 *scaling inputs*. Requests include admitted HTTP uploads, queued
work, v2 speaker work and open WS streams; they are not GPU occupancy. Existing
window pressure admission and `PARAKEET_WINDOW_MAX_SESSIONS` are unchanged.

## Bounded work and priority

`PARAKEET_PACKING_ENABLED=true` requires `PARAKEET_MAX_INFLIGHT=1`. The GPU
scheduler rejects unknown or >120s backfill quanta even if a caller bypasses
HTTP splitting. Both v1 and v2 historical uploads yield between <=120s chunks.
Only one historical quantum is dispatched at a time; queued live work always
wins. Running GPU kernels cannot be interrupted. V2 retains its original file
for whole-file speaker clustering; chunk-relative timestamps are offset onto
the original file clock, and a short tail is retained. Owned quantum files
remain owned by the GPU batch through caller cancellation.
Files <=120s pass through at their original path and subtype, including v2's
caller-owned files (`owns_file=False`) retained for speaker clustering.

Strict priority is work-conserving on the warm floor. Sustained live pressure
can starve historical work; watch oldest backfill age and upstream fresh/
backfill delivery deadlines (open <=1min, normal p95 <=5min, ceiling <=60min).
If those gates fail, stop expansion and restore dedicated backfill capacity or
reduce admitted backfill, rather than letting historical work jump queued live
requests. This PR does not admit the dedicated record worker onto live GPUs:
that worker still rejects shared-live mode. Stage C does zero ASR.
The older streaming-shaped HTTP caller marks `X-Omi-STT-Surface: live-stream`;
only packing-enabled service pods promote that marker to live priority, so its
dark-merge behavior is unchanged. Modern windows keep their `live-window` marker.

Chunk boundaries can alter hypotheses. Qualification must cover boundary
words/tails, languages, speaker identity and absolute timestamps, not just
speed. No long-input accuracy claim follows from a short public-fixture load
test. A failing cohort retains the existing processing path.

## CUDA graphs

`PARAKEET_EXPLICIT_CUDA_GRAPHS=true` persists `PARAKEET_CUDA_GRAPHS` into NeMo's
decoding config and initializes timestamp computation before first inference.
Runtime-only `disable_cuda_graphs()` can be undone by timestamp initialization.
Keep BF16 and the chart's graph selection false; this is a separate switch
because making eager mode effective can change throughput. Enabling graphs
with a resident RNNT streaming model remains forbidden. Verify the actual
post-inference decoder's `allow_cuda_graphs`, not only environment values.

## Qualification

Use a copied KUBECONFIG in a tier-specific directory and explicit kubectl
context. Select dev-operator only for an isolated dev Parakeet run. Record the
source hashes, base-image digest, production inference/resource settings and
cleanup receipt. Remove the global auth-plugin cache before tier changes.
Never bind Firebase/Firestore credentials or call an application backend.

`backend/scripts/qualify_parakeet_packing.py` runs inside the standalone GPU
image, on public fixture audio only. It starts a local ASR server, compares
packing off/on at 2 simultaneous requests, then probes 3. Forty synchronized
waves per step use 24s live windows and 120s backfill, minimum 3s cadence.
That 40-wave table measures mixed-load delivery and DCGM at the tested request
density. Its backfill inputs fit one quantum: it is not splitter, boundary-word
or speaker evidence. The separate 360s historical probe exercises splitting
with six overlapping live requests; its nonempty v2 response and last segment
end of 359.84s support yielding and time coverage only. Diarization was disabled,
so boundary-word, language and speaker-quality parity remain canary gates.
Receipts retain only shapes, response success, timing and node-matched DCGM.
Use an owned 1Hz DCGM exporter: the managed 30s exporter can alias bursts.
Run with `nice -n 19`; never overlap this qualification with local tests or
preflight. Require pooled delivery p95 <3s, no refusals/empty successes, real
nonzero DCGM in the final loaded sample, plus live-first/progress acceptance.
Never increase admission from 2/35 merely because an average GPU is low.

## Daily train and rollback

Two open blockers (swarm review 2026-10-18, still present 2026-10-20):

- **Caller timeout (blocks step 3).** A packed >120s file is N serial quanta,
  each waiting behind any queued live work, then whole-file v2 diarization, all
  inside one HTTP response. The production pre-recorded client reads for 120s
  (`_PARAKEET_TIMEOUT` in `utils/stt/pre_recorded.py`), retries the whole file
  once, and completed quanta are not checkpointed. Before any caller reaches a
  packing pod, either its read timeout covers worst-case quanta plus v2
  diarization, or completed quanta are checkpointed. The 360s probe uses its
  own client and is not evidence for this.
- **Queue-age signal (blocks step 4).** The demand HPA takes each pod's max
  queue age and then averages it across pods (`Pods`/`AverageValue`). On the
  min3 floor, one pod at 60s backfill age and two at 0 read 20s, under the 30s
  target. Before `autoscaling.demand.enabled=true`, use a fleet-max (External)
  signal, or show in dev that one hot pod scales.

1. Merge dark, then deploy the immutable image through the normal Parakeet
   workflow. Preserve every existing caller, HPA limit and floor. Capture the
   actual served digest and route probes for /v1, /v2, /v3 and health.
2. Install additive queue-age adapter rules plus the separately reviewed #21673
   GPU scope fix. `diff_prod_adapter.py` permits only the exact new rules and
   rejects changed/duplicate versions. Verify custom-metric discovery and each
   ready pod's samples; retain the prior Helm release for rollback.
3. Test explicit CUDA selection separately, then packing on a dedicated GPU
   canary receiving <=5% of eligible work. A pod's traffic share is not its
   replica fraction: measure caller routing. At least 3h and a busy period at
   <=5%, then expand only if delivery, quality, refusals and queue deadlines
   hold. No caller-routing canary is installed by this PR.
   Deploy the marker-producing backend/listen/pusher image before including
   older streaming-shaped HTTP callers in that canary; otherwise restrict it
   to modern windows which already send `live-window`. An old unmarked caller
   cannot be distinguished from historical v1 work by the GPU service.
4. After the whole serving fleet exposes fresh queue gauges, enable
   `autoscaling.demand.enabled=true` with max12, min3, requests2 and *existing*
   900s behavior first. Compare recommendations with the old HPA off-line.
   Missing samples block promotion. Do not run competing HPAs on one Deployment.
5. On a later train apply `packing_hpa_values.yaml` over the environment values:
   min3/max12, down stabilization300s, one pod per120s. Up cadence remains one
   per60s. The measured 24h request trough is ~3.04 total at01Z; three warm pods
   provide conservative headroom at target2 and preserve A2+B1 physical floors.
   Require a 24h diurnal receipt before another change. Restore prior behavior
   and `demand.enabled=false` to roll back; requests2/GPU35/p99=3 then return.
6. Keep max12 until measured peak mixed-work delivery qualifies a smaller cap.
   A higher density is a **separate config change** only after both admission
   gates pass. The unreferenced `packing_density_values.yaml` overlay contains
   the separate target3/35 step; [dev receipts](../operational/parakeet-packing-qualification-2026-10-16.json)
   support qualification on the deployed immutable artifact before its canary.
   Floor below3 needs independent resilience/freshness evidence;
   none is proposed here. Pool renaming yields $0 and is not in this train.

Watch live/pooled POST p95<3s, first/progress text, 503/queue-timeout/refusal rate,
ASR failures/empty successes, boundary/language quality, live and backfill queue
age, pending GPU pods, ready/desired replicas, DCGM/VRAM and fatal CUDA/OOMs.
Rollback on sustained live p95>=3s, increased refusals or any quality/coverage
regression; do not wait for the 3h bake. Disable packing to restore old dispatch
and file handling; let the <=120s running quantum finish. Disable explicit CUDA
selection only through the normal immutable-image/config rollback.

Savings count only after accelerator-SKU billed node-hours fall at the same
workload scope. Price each removed L4 at ~$0.61044/node-h ($14.65/24h), not a
reduction in desired pods. Record D+1/D+3 pool hours including stranded nodes,
credits/commitments and burst recovery. Admission, scaler, floor and pool
consolidation share one savings line and must never be added together.
