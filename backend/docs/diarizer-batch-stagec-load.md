# Stage C aggregate load model (2026-10-14 UTC)

Preparation receipt, not a production qualification or deployment authorization.
Source checkout: current `origin/main` base `909bfd7aa397`; measurements use
`source ~/.local/bin/gcp-agent-env.sh ro-prod`. No recordings, transcripts,
Firestore/account records or stored payloads were read. Only numeric diagnostic
log fields and aggregate time series were reduced; raw log rows were not saved.

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
textPayload =~ "(parakeet|modulate|deepgram)_prerecorded_from_bytes bytes_len="
# Aggregate bytes_len, sample_rate and retry attempt; discard every row.
textPayload : "event=sync_transcription_segment outcome=success"
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
