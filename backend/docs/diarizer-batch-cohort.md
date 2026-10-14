# Shared Gateway batch cohort ramp

Lead owns merges, deployments and ramp decisions. This change ships stage A only.
The reserved prod Gateway is `172.16.160.20`; reservation is not serving readiness.
Follow [Gateway installation and route probes](../charts/internal-gateway/README.md)
before deploying callers. The pyannote adapter appends `/v2/diarization`, yielding
`http://172.16.160.20/diarizer-batch/v2/diarization`.

## Stages (data only)

Exact complete env sets are in [`diarization-cohort-stages.json`](../../config/diarization-cohort-stages.json).
All stages retain these values on backend, backend-sync and pusher:

```text
HOSTED_DIARIZATION_API_URL=http://172.16.160.20/diarizer-batch
TRANSCRIPTION_FINAL_PASS_DIARIZER=pyannote_shadow
TRANSCRIPTION_FINAL_PASS_BACKEND=pyannote
TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST=vi7SA9ckQCe4ccobWNxlbdcNdC23
TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=false
TRANSCRIPTION_SHADOW_ENABLED=true
TRANSCRIPTION_SHADOW_KILL_SWITCH=false
TRANSCRIPTION_SHADOW_UID_ALLOWLIST=vi7SA9ckQCe4ccobWNxlbdcNdC23
```

Combine those constants with the following exact values (all strings):

| Stage | FINAL_PASS_PERCENT | SHADOW_PERCENT | FINAL_PASS_AUTHORITATIVE | SHADOW_DAILY_AUDIO_HOURS | One-line overlay edit |
| --- | ---: | ---: | --- | ---: | --- |
| A David shadow | 0 | 0 | false | 1 | `&batch_cohort` line: both percentages `"0"`, authoritative `"false"`, hours `"1"` |
| B David authoritative | 0 | 0 | true | 1 | Same line: authoritative `"true"` |
| C 1% authoritative + David | 1 | 1 | true | 80 | Same line: both percentages `"1"`, hours `"80"` |
| D 5% authoritative + David | 5 | 5 | true | 400 | Same line: both percentages `"5"`, hours `"400"` |

Column names abbreviate the `TRANSCRIPTION_` prefix. Edit only the single
`<<: &batch_cohort {...}` line in `deploy/runtime_env/prod.overlay.yaml`; the two
Cloud Run hosts inherit that exact mapping. Recompose with
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, copy the selected
stage's literal values to pusher's prod chart env, and run preflight. The co-host
gate accepts only a complete reviewed stage; mixed percentages or scope drift fail.
Redeploy pusher and backend/backend-sync through their owning workflows, and
verify the rendered and running values agree on all three before starting the
observation window. No backfill, integration, dev or backend-listen cohort expansion.
Sync/WAL promotion remains disabled throughout A–D.

Never exceed 5% in this plan. Wait at least 12 hours of data at D before proposing
any expansion; hold each earlier stage until all gates below have enough samples.
An empty series is not a passing gate. Lead records sample counts, baseline,
p95 values and acceptance decision before advancing.

## Gates at every stage A, B, C and D

- Failure rate: `omi_transcription_final_pass_total` outcomes `failed:service`,
  `failed:timeout`, `failed:sync_audio`; compare failures / all attempts with the
  preceding stage. Also inspect `omi_transcription_shadow_total` outcomes `failed`,
  `timeout`, `partial_audio`, `no_audio`, `skipped_budget` and
  `event=transcription_shadow` logs. Require no unexplained regression or cap loss.
- Latency: p95 of `omi_transcription_final_pass_latency_seconds` and
  `omi_transcription_shadow_latency_seconds`; inspect Gateway 5xx/429, batch queue
  depth `omi_diarization_v2_queue_depth`, GPU saturation and end-to-record latency.
  Hold on growing queues or timeout pressure; mean occupancy is not a burst SLO.
- Agreement: `omi_transcription_final_pass_agreement` and
  `omi_transcription_shadow_word_distance{outcome="ok"}`; inspect scalar v2 results
  and hold on unexplained drift. Agreement with legacy is not ground truth.
- Owner parity: `omi_transcription_shadow_owner_delta_ratio{outcome="ok"}`
  (zero is parity), plus `live_owner_seconds` / `pass_owner_seconds` in comparisons.
  Require reviewed parity before B and no regression at C/D.
- Remap: `omi_transcription_shadow_remap_success_rate{outcome="ok"}` and
  `omi_transcription_shadow_remap_safe_total{outcome="ok",safe="false"}`.
  Promotion requires full mapping, safe annotations and current revision;
  inspect rejected promotions, manual speaker assignments, translations and source
  references. Unsafe candidates must retain the original record.
- Language: out-of-profile / determined segments from
  `omi_stt_output_language_segments_total{conformance="out_of_profile"}` divided by
  the sum of `in_profile` and `out_of_profile` (exclude `undetermined`), with
  `live_stt_language_summary` logs. Match provider/profile/arm and baseline window.
  This is existing live telemetry, not a new batch-language accuracy measure.

Histograms expose `_bucket`, `_sum`, `_count`. See
[shadow PromQL and scalar-result semantics](transcription-shadow.md).
Metrics have no UID labels; use scoped scalar receipts for David's acceptance.

## Capacity and limits

The daily cap is already configurable through `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS`
and reserved atomically in shared Redis across hosts, before provider work. It
charges **all** selected stored audio, even single-speaker triage skips. At the
planning load of 6,300 audio-h/day, C selects ~63 h and D ~315 h; 80/400 h provide
headroom. At D, ~140 multi-speaker audio-h/day × supplied T4 RTF 0.06 is **8.4 GPU-h/day**
(~35% average occupancy). These are planning assumptions, not a T4 load-test receipt.
At the same ~45% multi-speaker share, spending the entire 400 h cap is ~10.8 GPU-h.
Bursts, extra ASR work and retries still require queue/latency gates.

The worker and batch API both cap individual calls at **7,200 seconds** (about
230.4 MB PCM16). Keep this bounded limit: longer conversations do not receive
whole-conversation diarization and retain legacy attribution (`failed:too_long`
in v2 metadata). It does not prevent a percentage ramp among eligible calls;
report the excluded duration share rather than claiming coverage of longer audio.
At RTF .06 a two-hour call needs ~432s inference, inside the worker's default
600s deadline and Gateway's 900s timeout, but decoding, ASR and queuing consume
that same worker budget. Hold the ramp if long-call timeouts rise; do not silently
raise limits. Stored-audio opt-in remains required.

Cloud Run's process-local shadow task is not durable after request completion;
shipping equal env does not establish Cloud Run shadow completion. Check receipts
per host; a reliable Cloud Run shadow ramp still needs durable dispatch as described
in the shadow runbook. Sync remains false, avoiding additional unbudgeted sync work.

## Cohort deploy order and rollback

1. Lead qualifies isolated batch digest, T4 pool, shared Gateway programmed route,
   health and synthetic PCM probes from GKE and Cloud Run per the Gateway runbook.
2. Deploy A bindings to all three hosts; confirm effective env and David receipts.
3. Advance A → B → C → D only after the gates; redeploy all three for each data edit.
4. Roll back the cohort commit alone and redeploy pusher/backend/backend-sync, or
   return the overlay/chart to stage A to stop promotion while retaining shadow.
   An incident stop sets `TRANSCRIPTION_SHADOW_KILL_SWITCH=true` and
   `TRANSCRIPTION_FINAL_PASS_DIARIZER=legacy` on all hosts; restore reviewed data
   after recovery. Disable callers before removing batch capacity. Existing
   promoted records are not rewritten by rollback. Keep Gateway and embedding
   routes for the independent caller migration.
