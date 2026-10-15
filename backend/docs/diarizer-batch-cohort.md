# Shared Gateway batch cohort ramp

Lead owns merges, deployments and ramp decisions. The checked-in production binding selects complete stage C: 1% authoritative including sync/backfill, plus David. Stage D (5%) remains prepared in the stage JSON; expansion requires explicitly selecting that complete stage in the shared overlay and pusher chart.
Deployment and further long-audio qualification remain lead-owned.
The reserved prod Gateway is `172.16.160.20`; reservation is not serving readiness.
Follow [Gateway installation and route probes](../charts/internal-gateway/README.md)
before deploying callers. The pyannote adapter appends `/v2/diarization`, yielding
`http://172.16.160.20/diarizer-batch/v2/diarization`.

## Stages (data only)

Exact complete env sets are in [`diarization-cohort-stages.json`](../../config/diarization-cohort-stages.json).
All stages retain these values on backend, backend-sync, backend-sync-backfill and pusher:

```text
HOSTED_DIARIZATION_API_URL=http://172.16.160.20/diarizer-batch
TRANSCRIPTION_FINAL_PASS_DIARIZER=pyannote_shadow
TRANSCRIPTION_FINAL_PASS_BACKEND=pyannote
TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST=vi7SA9ckQCe4ccobWNxlbdcNdC23
TRANSCRIPTION_SHADOW_ENABLED=true
TRANSCRIPTION_SHADOW_KILL_SWITCH=false
TRANSCRIPTION_SHADOW_UID_ALLOWLIST=vi7SA9ckQCe4ccobWNxlbdcNdC23
```

Combine those constants with the following exact values (all strings):

| Stage | FINAL_PASS_PERCENT | SHADOW_PERCENT | FINAL_PASS_AUTHORITATIVE | FINAL_PASS_SYNC_ENABLED | SHADOW_DAILY_AUDIO_HOURS |
| --- | ---: | ---: | --- | --- | ---: |
| A David shadow / sync legacy | 0 | 0 | false | false | 1 |
| B David authoritative including sync | 0 | 0 | true | true | 1 |
| C 1% authoritative + David | 1 | 1 | true | true | 80 |
| D 5% authoritative + David | 5 | 5 | true | true | 400 |

Column names abbreviate the `TRANSCRIPTION_` prefix. Edit only the single
`<<: &batch_cohort {...}` line in `deploy/runtime_env/prod.overlay.yaml`; the three
Cloud Run hosts inherit that exact mapping. Recompose with
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, copy the selected
stage's literal values to pusher's prod chart env, and run preflight. The co-host
gate accepts only a complete reviewed stage; mixed percentages or scope drift fail.
Redeploy pusher, backend, backend-sync and backend-sync-backfill through their
owning workflows. Verify the effective values agree on all four before starting
the observation window. Integration, dev and backend-listen remain excluded.
Rollback restores the complete B mapping on all four hosts, including backfill:
both percentages 0, daily shadow budget 1 h, authoritative=true and sync=true.
Complete A additionally sets authoritative=false and sync=false; retaining C
percentages or its daily budget is neither complete A nor complete B.

Never exceed 5% in this plan. Wait at least 12 hours of data at D before proposing
any expansion; hold each earlier stage until all gates below have enough samples.
An empty series is not a passing gate. Lead records sample counts, baseline,
p95 values and acceptance decision before advancing.

## Why David starts at B

Lead observed David's offline uploads on `lane=backfill`, processed by
backend-sync-backfill. Pusher shadow admission never sees those recordings.
The sync final pass has no shadow mode: `sync_enabled_for` gates a direct speaker
assignment replacement, with legacy identification on failure. Setting only
AUTHORITATIVE=false does not stop sync; SYNC_ENABLED must also be false.
David approved authoritative stage B. Lead-supplied hand labels measured pyannote
94% versus production 37% per word; this PR does not rerun that quality evaluation.

`POST /v2/sync-jobs/run` → `_run_sync_job_body` →
`_run_full_pipeline_background_async(sync_lane=backfill)` → `process_segment` →
`run_sync_final_pass` uses the same code/image for fresh and historical lanes.
`deploy-backend-stack` passes `backend_sync_backfill_env_vars` into
`sync-backfill-lifecycle`'s ENV_OVERLAY; `render_cloud_run_clone_env` preserves all
names except its explicit removal list, which contains no cohort names. No action
allowlist change is needed. A renderer/clone regression test covers every binding.

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
Metrics have no UID labels. For offline David, require `event=sync_final_pass`
outcomes and scoped review of persisted speaker assignments against the hand
labels. Shadow-only owner/remap metrics and v2 receipts do not cover this sync
path; missing samples are not acceptance evidence. Check manual owner/person
assignments, clocks, translations and source references on the actual sync output.

## Capacity and limits

[Stage C aggregate measurements and provisional capacity model](diarizer-batch-stagec-load.md)
qualify the combined sync/pusher planning assumptions and document the remaining
long-audio measurement gap.

The daily cap is already configurable through `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS`
and reserved atomically in shared Redis across shadow workers before provider work. It
charges **all** selected stored audio, even single-speaker triage skips. At the
planning load of 6,300 audio-h/day, C selects ~63 h and D ~315 h; 80/400 h provide
headroom. At D, ~140 multi-speaker audio-h/day × supplied T4 RTF 0.06 is **8.4 GPU-h/day**
(~35% average occupancy). These are planning assumptions, not a T4 load-test receipt.
At the same ~45% multi-speaker share, spending the entire 400 h cap is ~10.8 GPU-h.
Bursts, extra ASR work and retries still require queue/latency gates.
**Sync has an independent admission cap.** Each process admits one final pass without
waiting. Shared Redis atomically reserves at most 10 WAV audio-hours and 1,000 attempts
per UTC hour across backend, sync and backfill. The stage data binds
`TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS=10` and
`TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS=1000` on all four hosts.
The reservation uses the shared bounded Redis factory with 0.5s connect/read
timeouts and closes the client even on timeout. Each retry is charged again; reservations are never refunded. Invalid config,
Redis failure and exhaustion skip before embedding/GPU calls, emit
`event=sync_final_pass outcome=skipped_budget` plus fallback telemetry, and retain
legacy speakers. UTC boundaries can admit twice the hourly allowance in a short
interval; batch admission still bounds each replica to one running plus two queued.
The one-process slot is not a fleet cap; Redis is the fleet authority.
Outcome and speaker-failure logs include `uid_hash=sha256("sync-final-pass:" + uid)`
(full hex), with no UID metric labels. The hash is stable for scoped verification;
no transcript, audio, or stored record read is needed to count outcomes.

 Backfill has its own global speech allowance
(`SYNC_BACKFILL_GLOBAL_DAILY_HOURS`, default 555), not a diarization-specific cap.
The 8.4 GPU-h estimate above covers the original shadow planning load, not combined
shadow plus fresh/backfill sync work. B stays David-only; do not advance C/D until
combined GPU demand, queueing, sync volume and latency are qualified.

The worker and batch API both cap individual calls at **7,200 seconds** (about
230.4 MB PCM16). Keep this bounded limit: longer conversations do not receive
whole-conversation diarization and retain legacy attribution (`failed:too_long`
in v2 metadata). It does not prevent a percentage ramp among eligible calls;
report the excluded duration share rather than claiming coverage of longer audio.
At RTF .06 a two-hour call needs ~432s inference, inside the worker's default
600s deadline and Gateway's 900s timeout, but decoding, ASR and queuing consume
that same worker budget. Hold the ramp if long-call timeouts rise; do not silently
raise limits. Stored-audio opt-in remains required for the shadow worker; sync
reuses its uploaded matching WAV, including when private-cloud storage is disabled.

Cloud Run's process-local shadow task is not durable after request completion;
shipping equal env does not establish Cloud Run shadow completion. Check receipts
per host; a reliable Cloud Run shadow ramp still needs durable dispatch as described
in the shadow runbook. Sync/backfill executes in its existing Cloud Task pipeline;
it does not depend on that process-local shadow task.

## Cohort deploy order and rollback

1. Lead qualifies isolated batch digest, T4 pool, shared Gateway programmed route,
   health and synthetic PCM probes from GKE and Cloud Run per the Gateway runbook.
2. Deploy complete B to backend, backend-sync, backend-sync-backfill and pusher;
   confirm David's actual backfill jobs log `event=sync_final_pass` and inspect output.
3. Hold B for acceptance, then advance C/D only after the gates and combined-load
   qualification. Redeploy all four for each data edit.

### Rollback

An immediate incident stop sets `TRANSCRIPTION_SHADOW_KILL_SWITCH=true` and
`TRANSCRIPTION_FINAL_PASS_DIARIZER=legacy` on all hosts; restore reviewed data
after recovery. Disable callers before removing batch capacity.

The first operational rollback move needs no merge: send each Cloud Run service's
traffic back to its recorded previous ready B revision and roll prod pusher back
to its previous successful B Helm revision. Use the pre-C deployment receipts;
verify these revisions contain complete B before selecting them. Each service has
its own previous revision. The lead/operator runs the following templates with
production project, region and revision placeholders replaced:

```bash
gcloud run services update-traffic backend --to-revisions=<previous-ready-backend-revision>=100 --project=<prod-project> --region=<region>
gcloud run services update-traffic backend-sync --to-revisions=<previous-ready-sync-revision>=100 --project=<prod-project> --region=<region>
gcloud run services update-traffic backend-sync-backfill --to-revisions=<previous-ready-backfill-revision>=100 --project=<prod-project> --region=<region>
helm -n prod-omi-backend rollback prod-omi-pusher <previous-successful-B-helm-revision> --wait --timeout=160m
```

Verify 100% traffic on the selected ready Cloud Run revisions and the restored
pusher rollout. In-flight work may finish on the old instances. The configuration
revert follows this operational rollback so a later deploy cannot re-enable C:

1. Restore **complete B** in the `&batch_cohort` anchor of
   `backend/deploy/runtime_env/prod.overlay.yaml` and in
   `backend/charts/pusher/prod_omi_pusher_values.yaml`: set
   `TRANSCRIPTION_FINAL_PASS_PERCENT=0`, `TRANSCRIPTION_SHADOW_PERCENT=0` and
   `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS=1`; keep
   `TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE=true` and
   `TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=true`. Keep David's allowlists and the
   hourly sync caps (10 audio-h / 1,000 attempts) unchanged. Recompose with
   `backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, review/merge
   the revert, then redeploy backend, backend-sync and backend-sync-backfill via
   `gcp_backend.yml` (`environment=prod`, `deploy_targets=cloud-run-only`), and
   pusher via `gcp_backend_pusher.yml` (`environment=prod`, `service=pusher`,
   qualified immutable digest). Both deployment paths are required. Verify the
   complete B values agree across all four hosts. This restores David-only
   authoritative final passes, including sync.
2. If legacy sync and no live promotion are required, select **complete A**
   instead: both percentages 0 and daily shadow budget 1, **plus**
   `TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE=false` and
   `TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=false` in both sources. Recompose and
   redeploy all four through the same workflows. This retains David-only shadow;
   changing only the two flags while leaving C's percentages/budget is insufficient.

Existing promoted records are not rewritten by rollback. Keep Gateway and
embedding routes for the independent caller migration.
