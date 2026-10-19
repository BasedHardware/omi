# Shared Gateway batch cohort ramp

Lead owns merges, deployments and ramp decisions. The checked-in production binding holds stage E at 5% authoritative including sync/backfill, plus private cohort members, with stage E's existing budgets. Stage D (5%) was held clean for 3 hours 2 minutes on 2026-10-16, 02:45→05:47Z: queue depth 0, five replicas with 0 restarts, five T4 nodes, and `upstream_error` about 1%. For an E regression, roll back to complete D with the previous budgets.
David's 2026-10-16 decision is to keep a 5% live quality sample: per-~8-second-clip pyannote runs at RTF 0.308 cost about $100/day at 15%, with $700–900/day estimated at 100%, and miss the cost goal.
This per-clip path will be superseded by whole-unit diarization in the batch pipeline.
Deployment and further long-audio qualification remain lead-owned.
The reserved prod Gateway is `172.16.160.20`; reservation is not serving readiness.
Follow [Gateway installation and route probes](../charts/internal-gateway/README.md)
before deploying callers. The pyannote adapter appends `/v2/diarization`, yielding
`http://172.16.160.20/diarizer-batch/v2/diarization`.

Membership is managed through [private rollout cohorts](runbooks/rollout-cohorts.md);
stage data contains only public rollout switches and budgets.

## Stages (data only)

Exact complete env sets are in [`diarization-cohort-stages.json`](../../config/diarization-cohort-stages.json).
All stages retain these values on backend, backend-sync, backend-sync-backfill and pusher:

```text
HOSTED_DIARIZATION_API_URL=http://172.16.160.20/diarizer-batch
TRANSCRIPTION_FINAL_PASS_DIARIZER=pyannote_shadow
TRANSCRIPTION_FINAL_PASS_BACKEND=pyannote
TRANSCRIPTION_SHADOW_ENABLED=true
TRANSCRIPTION_SHADOW_KILL_SWITCH=false
```

Combine those constants with the following exact values (all strings):

| Stage | FINAL_PASS_PERCENT | SHADOW_PERCENT | FINAL_PASS_AUTHORITATIVE | FINAL_PASS_SYNC_ENABLED | SHADOW_DAILY_AUDIO_HOURS | SYNC_HOURLY_AUDIO_HOURS | SYNC_HOURLY_REQUESTS | Hold / readout |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| A David shadow / sync legacy | 0 | 0 | false | false | 1 | 10 | 1,000 | — |
| B David authoritative including sync | 0 | 0 | true | true | 1 | 10 | 1,000 | — |
| C 1% authoritative + David | 1 | 1 | true | true | 80 | 10 | 1,000 | — |
| D 5% authoritative + David | 5 | 5 | true | true | 400 | 50 | 5,000 | 2026-10-16 02:45→05:47Z (3h 2m): queue 0; 5 replicas, 0 restarts; 5 T4 nodes; `upstream_error` ~1% |
| E 5% quality sample + David | 5 | 5 | true | true | 1,200 | 150 | 15,000 | Current hold; stage E budgets retained |

Column names abbreviate the `TRANSCRIPTION_` prefix. Edit only the single
`<<: &batch_cohort {...}` line in `deploy/runtime_env/prod.overlay.yaml`; the three
Cloud Run hosts inherit that exact mapping. Recompose with
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, copy the selected
stage's literal values to pusher's prod chart env, and run preflight. The co-host
gate accepts only a complete reviewed stage; mixed percentages or scope drift fail.
Redeploy pusher, backend, backend-sync and backend-sync-backfill through their
owning workflows. Verify the effective values agree on all four before starting
the observation window. Integration, dev and backend-listen remain excluded.
For an E regression, restore complete D on all four hosts, including backfill:
both percentages 5, daily shadow budget 400 h, sync caps 50 audio-h/5,000 requests,
authoritative=true and sync=true. Keep the private Firestore memberships and every other scalar value.
For a D regression, restore complete C: both percentages 1, daily shadow budget
80 h, sync caps 10 audio-h/1,000 requests, authoritative=true and sync=true.
Complete B is the broader David-only rollback: both percentages 0, daily shadow
budget 1 h, with sync caps 10/1,000 and authoritative=true/sync=true. Complete A
additionally sets authoritative=false and sync=false.

The checked-in production configuration is E (5%). The preceding D hold met the
three-hour minimum with the readout above. An empty series is not a passing gate.
Lead records sample counts, baseline, p95 values and the acceptance decision for
each stage before advancing.

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

## Gates at every stage A, B, C, D, E and later ramps

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
  Require reviewed parity before B and no regression at C/D/E.
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
qualify the combined sync/pusher planning assumptions. The measured long-audio
T4 RTF is about 0.042, or roughly 24 audio-hours per GPU-hour. At E's sync cap
of 150 audio-hours per wall-clock hour, the 15% planning scenario needs about 6.3 T4
GPU-hours per hour, or 9 nodes at 70% planning utilization. The production batch
HPA and T4 pool each have a maximum of 18. The observed D peak was five replicas
at 5%; the prior 15% scenario projected 15 replicas. The HPA scales up by three pods per
60 seconds, leaving one scale-up step of headroom under the current ceiling (18 − 3 = 15).
A 25% stage projects 25 replicas; raise both the diarizer-batch HPA max and T4
pool max, with scale-up headroom, before considering that stage. These are steady
capacity projections, not a burst-capacity or p95 latency bound.

The daily cap is already configurable through `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS`
and reserved atomically in shared Redis across shadow workers before provider work. It
charges **all** selected stored audio, even single-speaker triage skips. At the
planning load of 6,300 audio-h/day, C selects ~63 h and both D and the current E hold select ~315 h;
the prior 15% scenario selected ~945 h; 80/400/1,200 h provide headroom. At that prior
scenario, ~426 multi-speaker audio-h/day × measured T4 RTF 0.042 is about **17.9 GPU-h/day**;
the current 5% hold is about **6 GPU-h/day**. At the same ~45% multi-speaker share,
spending the entire 1,200 h cap is about **22.7 GPU-h/day**. These are planning
assumptions, not a T4 load-test receipt.
Bursts, extra ASR work and retries still require queue/latency gates.
**Sync has an independent admission cap.** Each process admits one final pass without
waiting. Shared Redis atomically reserves at most 150 WAV audio-hours and 15,000 attempts
per UTC hour across backend, sync and backfill at E. Stage D used 50 audio-hours and
5,000 attempts; the stage data binds E's
`TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS=150` and
`TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS=15000` on all four hosts.
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
The shadow GPU-h estimate above covers the shadow planning load, not combined
shadow plus fresh/backfill sync work. Stage E retains David's allowlist. The D
hold recorded above met the three-hour clean-window gate; continue to assess
combined GPU demand, queueing, sync volume and latency during E.

The worker and batch API both cap individual calls at **7,200 seconds** (about
230.4 MB PCM16). Keep this bounded limit: longer conversations do not receive
whole-conversation diarization and retain legacy attribution (`failed:too_long`
in v2 metadata). It does not prevent a percentage ramp among eligible calls;
report the excluded duration share rather than claiming coverage of longer audio.
At RTF .042 a two-hour call needs ~302s inference, inside the worker's default
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
3. Hold B for acceptance, then advance through C and D only after the gates and
   combined-load qualification. Keep E at 5% for the live quality sample; further
   per-clip percentage increases require a new cost decision. Redeploy all four for
   each data edit.

### Rollback

An immediate incident stop sets `TRANSCRIPTION_SHADOW_KILL_SWITCH=true` and
`TRANSCRIPTION_FINAL_PASS_DIARIZER=legacy` on all hosts; restore reviewed data
after recovery. Disable callers before removing batch capacity.

For an E regression, the first operational rollback move needs no merge: send each
Cloud Run service's traffic back to its recorded previous ready D revision and
roll prod pusher back to its previous successful D Helm revision. Use the pre-E
deployment receipts; verify these revisions contain complete D before selecting
them. Each service has its own previous revision. The lead/operator runs the following templates with
production project, region and revision placeholders replaced:

```bash
gcloud run services update-traffic backend --to-revisions=<previous-ready-backend-revision>=100 --project=<prod-project> --region=<region>
gcloud run services update-traffic backend-sync --to-revisions=<previous-ready-sync-revision>=100 --project=<prod-project> --region=<region>
gcloud run services update-traffic backend-sync-backfill --to-revisions=<previous-ready-backfill-revision>=100 --project=<prod-project> --region=<region>
helm -n prod-omi-backend rollback prod-omi-pusher <previous-successful-D-helm-revision> --wait --timeout=160m
```

Verify 100% traffic on the selected ready Cloud Run revisions and the restored
pusher rollout. In-flight work may finish on the old instances. The configuration
revert follows this operational rollback so a later deploy cannot re-enable E:

1. Restore **complete D** in the `&batch_cohort` anchor of
   `backend/deploy/runtime_env/prod.overlay.yaml` and in
   `backend/charts/pusher/prod_omi_pusher_values.yaml`: set
   `TRANSCRIPTION_FINAL_PASS_PERCENT=5`, `TRANSCRIPTION_SHADOW_PERCENT=5` and
   `TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS=400`; keep
   `TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE=true` and
   `TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=true`. Keep David's allowlists and set
   the previous hourly sync caps to 50 audio-h / 5,000 attempts. Recompose with
   `backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, review/merge
   the revert, then redeploy backend, backend-sync and backend-sync-backfill via
   `gcp_backend.yml` (`environment=prod`, `deploy_targets=cloud-run-only`), and
   pusher via `gcp_backend_pusher.yml` (`environment=prod`, `service=pusher`,
   qualified immutable digest). Both deployment paths are required. Verify the
   complete D values agree across all four hosts.
2. To roll back further to **complete C**, set both percentages to 1, daily shadow
   budget to 80, and sync caps to 10 audio-h / 1,000 attempts, keeping the
   authoritative and sync flags true. Recompose and redeploy all four hosts.
3. To roll back further to David-only, select **complete B**: both percentages 0,
   daily shadow budget 1, sync caps 10/1,000, authoritative=true and sync=true.
   Recompose and redeploy all four through the same workflows.
4. If legacy sync and no live promotion are required, select **complete A**
   instead: both percentages 0 and daily shadow budget 1, **plus**
   `TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE=false` and
   `TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED=false` in both sources. Recompose and
   redeploy all four through the same workflows. This retains David-only shadow;
   changing only the two flags while leaving E's percentages/budget is insufficient.

Existing promoted records are not rewritten by rollback. Keep Gateway and
embedding routes for the independent caller migration.
