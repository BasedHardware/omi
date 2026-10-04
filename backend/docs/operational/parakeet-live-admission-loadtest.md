# Parakeet live admission capacity qualification

## Limits map

Source baseline: `40ce87543b36c34870f704ea1ca53a0ca1e8e312` (2026-10-04).
Line numbers below refer to that baseline. A session is not an active HTTP
request, and a listen process is not a GPU pod.

| Boundary | Current limit / behavior | Source (`backend/` prefix) |
| --- | --- | --- |
| Listen local window leases | `PARAKEET_WINDOW_MAX_SESSIONS`: default 1, prod 16 **per listen process**, not per Parakeet pod. Acquisition is atomic; overflow is session-local. | `utils/stt/parakeet_window.py:236`, `:241`; `charts/backend-listen/prod_omi_backend_listen_values.yaml:457` |
| Window in-flight work | One POST per session; minimum 6 s between POST starts in prod; contexts grow to 24 s. Code default pace is now 15 s, while the prod chart explicitly pins 6 s. | `utils/stt/parakeet_window.py:277`; `utils/stt/window_anchor.py:28`; listen values `:467` |
| Listen shared HTTP capacity | STT semaphore 8, HTTP max connections 8 / keepalive 4 per event loop/process, shared with other STT/ML work. Window's 8 s budget includes waiting for this semaphore. | `utils/http_client.py:392`, `:538`; `utils/stt/parakeet_window.py:1106` |
| Session deadline / buffering | POST wall deadline 8 s; startup first-text rescue 12 s; max empty streak 4; retained PCM `2*context+2*pace` = 60 s with prod settings. Buffer pressure can open the provider circuit. | `utils/stt/parakeet_window.py:298`, `:320`; `utils/stt/window_anchor.py:81` |
| Listen live pressure gate | Busy at **live pending >=4 OR live oldest >=0.75 s**. Pending excludes in-flight GPU work. Backfill pending alone does not mark busy. | `utils/stt/batch_pressure.py:33`, `:131`; `parakeet/batch_engine.py:374` |
| Pressure quorum / pool refusal | Fresh >=max(min replicas, strict majority); prod min replicas 3. Refuse if (busy+unknown)/ready >=0.5; DNS failure or stale telemetry refuses. Poll 5 s, sample TTL 15 s, fetch 1 s, fan-out cap 64. | `utils/stt/batch_pressure.py:29`, `:122`, `:135`, `:187`; listen values `:461` |
| Allocation / eligibility | Configured chain on, UID in allocated bucket (prod 100%), supported language, endpoint configured; excludes custom STT, BYOK, multichannel and PTT. Full local admission skips this leg before construction. | `utils/stt/live_rollout.py:11`, `:15`, `:23`, `:28`; `utils/stt/live_chain.py:879` |
| Provider health / routing | Circuit/half-open probe admission is separate from capacity. Target capacity cooldown 5 s. An acquired POST timeout/5xx or buffer overflow benches the provider; queue_timeout is a capacity failure. No POST retries. | `utils/stt/live_router.py:24`; `utils/stt/streaming.py:154`; `utils/stt/parakeet_window.py:1140` |
| Server HTTP admission | `/v1/transcribe` routes only `X-Omi-STT-Surface: live-window` to live. Unmarked v1 and every v2 request enter backfill. No live HTTP session-count hard cap exists on the GPU pod. Not-ready returns 503. | `parakeet/main.py:205`, `:207`, `:313`, `:365` |
| Server queue | Combined pending queue max 4096, including both lanes; 503 on full. Live deadline starts at route entry: min(8 s, positive finite client timeout header), includes file preparation. Expiry removes only queued work, never preempts running inference. Backfill has no server queue deadline. | `parakeet/main.py:108`, `:216`, `:230`; `parakeet/batch_engine.py:201`, `:267`, `:398` |
| GPU batch assembly | Max batch 32, partial flush timer 2 ms. VRAM budget = `(GPU total*0.8 - model baseline)/max_inflight`; full-attention estimate uses 136.6 bytes*T² with T=duration/0.08. Unknown duration assumes 300 s. Can reduce to one file. | `parakeet/main.py:163`; `parakeet/batch_engine.py:105`, `:155`, `:174`, `:315` |
| Lane scheduling | Live first at each dispatch; one aged backfill item after four live batches if age >=5 s. Running backfill cannot be preempted. Otherwise duration-aware batch selection with aged-item fairness. | `parakeet/batch_engine.py:315`, `:354` |
| GPU dispatch | `PARAKEET_MAX_INFLIGHT` default 2, **prod 1**. Single worker thread; GPU FIFO max 512 work items (also embeddings). Sync submission enqueue wait 5 s, transcription result 120 s / embedding 30 s. | `parakeet/main.py:172`; `charts/parakeet/prod_omi_parakeet_values.yaml:126`; `parakeet/gpu_worker.py:45`, `:100`, `:223`, `:241` |
| Files / attention | Prod max file 3600 s; invalid duration rejected. Prod auto attention switches to local at 300 s, preventing quadratic VRAM growth for long files. Embeddings and diarization can still delay live work. | prod Parakeet values `:106`; `parakeet/gpu_worker.py:473` |
| v2 / I/O executors | Four file-I/O threads and four v2 postprocessing threads. These are concurrency bounds, but their executor waiting queues are not bounded admission. | `parakeet/main.py:105`, `:106`, `:369` |
| Legacy `/v3/stream` | Separate GPU-owner lease cap 25 and 100% allocation; **does not cap windowed v1 HTTP**. One ASR executor thread; receive timeout 30 s re-arms rather than expiring a session. | `parakeet/admission.py:86`; prod Parakeet values `:90`; `parakeet/stream_handler.py:80`; `parakeet/main.py:408` |
| Prerecorded client | Per-call sync HTTP client: connect 10 s/read 120 s/write 30 s/pool 10 s; one retry; v2 with diarization by default, v1 fallback on 404. URL download 100 MiB cap. | `utils/stt/pre_recorded.py:759`, `:819`, `:893`, `:907` |
| Client-facing STT proxy | Separate STT proxy semaphore 4, isolated from the shared STT semaphore. | `utils/http_client.py:396`, `:549` |
| Upstream sync producers | VAD segments <=300 s; per-pipeline groups of five chunks; inline fresh pipelines 16 / backfill 2. Cloud Tasks handlers use Cloud Run container concurrency instead. These producers are bypassed by this probe. | `utils/sync/pipeline.py:195`, `:1677`, `:1906`, `:2651` |
| HPA | Total active v1/v2 requests + legacy streams, **not live sessions**: requestsPerPod 2. GPU target 35. Bounds 3–7; scale up one pod/300 s, down one/600 s with 600 s stabilization. HPA is a scaling signal, not an admission cap. | prod Parakeet values `:203`; `charts/parakeet/templates/hpa.yaml:49`; `charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml:123` |

The reported refusal near three active HTTP requests is an observed operating
point, not a coded `3` cap. More slots on listen do not necessarily create more
GPU work: one session spends most of its time accumulating speech. The pool
gate reacts to queued requests and telemetry coverage, while the HPA reacts to
active HTTP work (which includes backfill/diarization).

## Method and receipts

Run `backend/scripts/parakeet_live_loadtest.py` only against a loopback dev pod
port-forward. It validates the hashes of the checked-in LibriSpeech CC-BY-4.0
and synthetic Portuguese release fixtures, repeats their PCM to create bounded
contexts, and emits no transcript content. Live uses v1 with the live header and
8 s timeout; batch uses v2 with diarization enabled. Each live session has one
POST in flight, 6 s start spacing, and a repeating 6/12/18/24 s context profile.
Batch duration bands are 30/60/120/240 s at 30/20/40/10% by count. Its rate is
the larger of 177k/day/3 pods (0.683 RPS) and live RPS*16/84.

This is a direct ASR/queue/diarization capacity test. It does not prove WER,
listen admission, VAD behavior, sentence-held delivery, fallback reliability,
or the end-to-end first-text SLO. First-text qualification must retain the
production first-VAD-to-delivered-text histogram gate below 30 s.

POST percentiles use client measurements including port-forward overhead and
failures. Lane queue and inference percentiles are interpolated from cumulative
Prometheus histogram **deltas per step**, not a cumulative run quantile. DCGM
must cover each measured interval; missing telemetry is not a pass. Raw
content-free receipts live under the task worktree's ignored `.local/` directory.

## Results (2026-10-04 UTC)

One NVIDIA L4, current-main image `40ce875`, prod-equivalent ASR env/resources,
`PARAKEET_MAX_INFLIGHT=1`, one Uvicorn process. Dev HPA was pinned to one pod.
The original dev RNNT-stream configuration was temporarily replaced for parity;
it is restored after the test. The deployment was updated by the successful
[development workflow](https://github.com/BasedHardware/omi/actions/runs/37195897675).
No backend/listen, Firestore, user audio, or production HTTP endpoint was used.

Three minutes per step, followed by draining requests. These seven steps used
closed HTTP connections, a conservative tunnel-overhead case. POST includes
8 s timeouts. Queue/inference values are histogram estimates. GPU columns are
DCGM mean/maximum percentages.

| Live sessions | POST p50 / p95 / p99 (s) | Live / backfill queue p95 (s) | Inference p95 (s) | GPU mean / max (%) | Backfill completed RPS | Live errors / count |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 2 | 1.30 / 2.78 / 3.14 | 0.50 / 0.44 | 0.62 | 27.4 / 100 | 0.679 | 0 / 60 |
| 4 | 1.27 / 2.76 / 3.67 | 0.64 / 0.44 | 0.50 | 19.8 / 100 | 0.675 | 0 / 120 |
| 6 | 1.30 / 2.88 / 3.83 | 0.71 / 0.81 | 0.49 | 16.3 / 36 | 0.677 | 0 / 180 |
| 8 | 1.35 / 2.79 / 3.23 | 0.77 / 0.92 | 0.49 | 40.3 / 100 | 0.677 | 0 / 240 |
| 12 | 1.48 / 3.04 / 5.00 | 0.66 / 0.94 | 0.47 | 11.4 / 26 | 0.659 | 0 / 360 |
| 16 | 3.69 / 8.00 / 8.01 | 3.86 / 7.42 | 1.00 | 21.3 / 100 | 0.663 | 32 / 462 |
| 24 | 1.99 / 4.09 / 5.68 | 1.85 / 2.89 | 0.81 | 57.3 / 100 | 0.759 | 0 / 720 |

All steps had zero GPU OOMs/fatal CUDA errors and zero backfill HTTP errors.
At 16 sessions, 32 live requests timed out, backfill POST p95 reached 41.30 s,
and minimum free GPU memory dropped to 6.6 GiB. At 24, larger live batching
improved throughput, but client p95 still missed 3 s. This non-monotonic result
excludes 16 and 24 from a reliable admission recommendation.

DCGM had 182–187 scrape samples per step but only 3–6 value changes. GPU peaks
hit 100%; averages are coarse, cached collector measurements and cannot locate
subsecond saturation. Queue/POST behavior provides stronger capacity evidence.
The test cannot support a claim that GPU utilization alone permits 24 sessions.

Server-side live POST p95 for the seven steps was respectively 0.56, 0.87,
0.92, 1.47, 1.52, 5.45, and 2.39 s (Prometheus histogram estimates).
Transport overhead accounts for part of the difference from client latency.

### Connection-reuse confirmation

The same three-minute mixed load with up to eight reusable HTTP connections:

| Live sessions | POST p50 / p95 / p99 (s) | Live / backfill queue p95 (s) | Inference p95 (s) | GPU mean / max (%) | Backfill RPS | Live errors |
| ---: | --- | --- | ---: | --- | ---: | ---: |
| 8 | 0.82 / 1.84 / 2.57 | 0.64 / 0.74 | 0.48 | 6.7 / 36 | 0.680 | 0 |
| 12 | 0.95 / 4.78 / 6.13 | 0.76 / 1.40 | 0.47 | 1.2 / 8 | 0.682 | 0 |

Eight passed again; 12 missed client p95 despite server POST p95 1.36 s.
Transport/upload/scheduling effects therefore remain part of the observed
capacity boundary. There were no telemetry gaps or GPU errors in these repeats.
Do not infer a GPU-only ceiling from a port-forward test.

## Proposed settings and cost

Plan conservatively for **eight continuously paced live sessions per L4** with
the tested batch floor. This is a capacity budget, not a newly introduced hard
GPU-session lease. Keep listen's local lease cap at 16: it belongs to a listen
process and cannot enforce per-GPU ownership through a load-balanced service.
Use the existing fleet pressure admission mechanism:

| Setting | Current | Draft recommendation |
| --- | ---: | ---: |
| Listen process window leases | 16 | 16 |
| Busy pod: live pending requests | 4 | 8 |
| Busy pod: oldest live queue age | 0.75 s | 1.5 s |
| Busy plus unknown pool refusal | 50% | 50% |
| Fresh replica minimum | 3 | 3 |
| HPA active HTTP requests per pod | 2 | 3 |
| HPA GPU target | 35% | 45% |
| HPA min / max | 3 / 7 | 3 / 7 |
| Scale up | +1 / 300 s | +1 / 60 s |
| Scale down / stabilization | -1 / 600 s; 600 s | unchanged |

The age bound is deliberately below the 3 s POST target and 8 s wall budget;
it still catches the failed step's multi-second backlog. Pending counts are
not session counts. The HPA request target includes diarization/backfill waiting
and is intentionally lower than queued-live refusal. GPU/HTTP targets are a
conservative proposed operating point, not an experimentally optimized HPA.
Keep the single GPU dispatch, maximum batch 32, and live/backfill fairness.
Contract tests exercise the checked-in prod settings at the busy boundaries,
unknown-pod quorum, rendered HPA targets, and runtime/Helm parity.

Prod reads were aggregate Prometheus only, under `ro-prod` (cutoff approximately
2026-10-04 11:30 UTC). The requested `scratchpad/q.sh` was absent; equivalent
explicit-context Prometheus service-proxy queries were used. Last-day live
requests were about 322k and prerecorded requests 116k: 74% live, versus the
supplied 84% profile. The probe deliberately used the higher 177k/day batch
floor across three pods. Seven-day peak five-minute live rate was 16.66 RPS;
it represents about 100 six-second-paced live session equivalents fleet-wide.
Thus three pods cannot absorb every continuously voiced peak at eight sessions
per pod: retain max seven and provider fallback. Do not promise three nodes
at every peak.

Counterfactual desired pods per minute = clamp(3, 7,
max(ceil((total active HTTP + legacy streams) / 3),
ceil(current replicas * fleet GPU percent / 45))). Applying this to observed
aggregates yielded 3.12 pods over 24 h and 3.26 over seven days, with peaks at
seven. This omits HPA tolerance/stabilization, cold start, node retention,
changed admission and correlated peaks. It is a planning model, not a forecast.

At 730 h/month and $0.613/node-hour:

| Scenario | Mean nodes | Node-hours/month | GPU node cost/month |
| --- | ---: | ---: | ---: |
| Supplied baseline | 5 | 3,650 | $2,237 |
| Planning allowance for lag/retention | 3.4–3.7 | 2,482–2,701 | $1,521–1,656 |
| Three-node floor only | 3 | 2,190 | $1,342 |

Expected planning saving versus five nodes: **$581–716/month**; floor-only
maximum $895/month. Each removed average node saves $447/month. Actual observed
node averages were 5.27 over 24 h and 3.83 over seven days; savings relative to
that seven-day baseline are only about $56–190/month at the planning allowance.
This covers GPU nodes only and excludes fallback-provider costs.

## Risks and acceptance before a production change

- **L4 stockout / zone failure:** retain floor three and max seven across the
  existing two-zone pools (ceilings four plus three). Existing soft zone spread
  cannot guarantee stock availability or a particular placement during outage.
- **Scale-up lag:** +1/minute still trails a burst and needs node provisioning;
  keep fallback and conservative pressure/POST guards. Higher admission changes
  the load distribution used by the cost model.
- **Cold start:** this dev parity rollout took about 3m37s to become ready with
  a cached image; an uncached node/image/model can take longer. Lowering warm
  floor below three is excluded.
- **Long recordings / diarization / synchronized speech:** non-preemptible
  backfill and embeddings can create queues despite low mean GPU. The fixture
  duration mix and three-minute steps are bounded evidence, not a soak test or
  a test of the rare 300–3600 s recordings.
- **First-text delivery:** directly measured ASR text is not first delivered
  listen text. Separately authorize a production bake retaining <30 s first
  text, live POST p95 <3 s, queue age/refusal/error/fallback rates, and backfill
  completion/audio throughput. Revert targets to 2/35 and pressure to 4/0.75
  if these regress. No production rollout is part of this draft.
