# STOP_PCM and regional derived-cache ramp

The rollout lead owns every apply, via an existing Cloud Run/GKE train. Config
PRs are a sequence, never a batch of flags to merge together. Keep later PRs
draft until the preceding step passes its soak and the lead requests the next
apply. The batch release freeze remains in force; no extra Cloud Run train.
No lifecycle changes, audio deletion, or custody kill-switch changes belong here.

## Sequence and rollback

| Step / checker argument | Config | Prerequisite | Minimum observation after apply |
| --- | --- | --- | --- |
| `stop-5` | STOP_PCM enabled, percent 5 | LIVE+READ clean; custody fix #23656 live; lead accepts measured write baseline | 12h before next step |
| `stop-25` | STOP_PCM percent 25 | stop-5 >=12h, checks pass | 4h before next step |
| `stop-100` | STOP_PCM percent 100 | stop-25 >=4h, checks pass | >=1h attribution before regional |
| `regional-5` | REGIONAL_CACHE enabled, percent 5; BUCKET_AUDIO_DERIVED=omi-audio-derived-uc1 | STOP_PCM 100 measured; bucket exists; all runtime writers can create/read | 12h before next step |
| `regional-100` | REGIONAL_CACHE percent 100 | regional-5 >=12h, checks pass | >=1h plus D+1 billing |

Each commit updates both production chart values, six production runtime
overlay maps, the generated manifest and flag registry. Development stays at
zero. Rebase/recompose the next draft against current main before requesting
merge; train operators must use that checked revision, rather than a live env
patch that the next train overwrites. Both GKE and Cloud Run must read back the
step before its full observation window starts. Lead ruling 6418ac requires
the custody baseline after the 06Z roll's actual DONE plus one hour; no
pre-roll lookback may become this ramp's baseline. First apply remains in the
bundled post-10Z train, outside op2's 05:45 through GKE DONE+1h reservation.

STOP_PCM rollback: percent 0, optionally disable; READ and custody remain on.
Regional rollback: set REGIONAL_CACHE_PERCENT=0 first, then disable
REGIONAL_CACHE, leaving BUCKET_AUDIO_DERIVED set so
dual-list reads still find artifacts written during the canary. Leave all
archived audio, manifests, lifecycle settings and retention unchanged.

## Per-step evidence check

Run the same read-only checker with the argument in the table for **each** step:

```bash
python3 backend/scripts/check_audio_storage_ramp.py stop-5 /path/to/aggregate-receipt.json
```

The checker validates an operator receipt; it does not fetch live state, grant
an apply, or establish the truth of supplied measurements. Collect only
aggregates and flag/release identities, through ro-prod; no user IDs, audio,
secret values or workload exports. Save linked raw aggregate outputs with the
train record. Missing in-cluster metrics require operator evidence, not zero.
Use the receipt shape in `tests/unit/test_audio_storage_ramp_gate.py:receipt_for`
as a **synthetic schema example**, never as live acceptance evidence.

Receipt fields:

- `previous_step`, `previous_applied_at`, `applied_at`: UTC timestamps; apply
  means every receiving surface has the new state. `baseline` precedes stop-5.
- Except for stop-5, include the complete `previous_receipt`. It must pass its
  own gates recursively, have the same prior apply timestamp, cover the full
  required 12h/4h/1h soak, and end within one hour before the next apply. A
  failed prior quality result cannot be replaced with a claimed step name.
- `lead_apply_ref`, `baseline_acceptance_ref`, `cohort_attribution_ref`: bus or
  report references. Attribution compares similar traffic and cohort shares;
  PCM avoidance counts **verified skipped batches**, not bytes or all writes.
- `before` and `after`: `start`, `end`, `private_write_per_hour`,
  `pcm_writes_avoided_per_hour`, `regional_write_per_hour`. Use >=1h windows;
  after begins only once all surfaces serve the new flags. End within 1h of check.
- The baseline must end within 1h before apply and start after
  `custody_roll_completed_at` plus 1h. `before.evidence_ref` names its actual
  aggregate measurement. `accepted_baseline` repeats that exact `start`, `end`
  and `evidence_ref` so an older accepted firehose window cannot be substituted.
- `after.custody.listen` and `.pusher`: window deltas `commits`, `failures`,
  `would_drop`, and `evidence_ref`. Query each service's counters independently,
  including restarts; do not substitute Cloud Run's zero custody counters.
- Listen failures/would_drop stay zero. Include `before.custody.pusher` with
  the same reset-aware fields as after, from the matched post-roll window.
  Both pusher windows split failures into `projection_transient`,
  `commit_failures` (all commit-stage reasons), and `other_failures` (everything
  else); split would_drop into `queue_would_drop` and `other_would_drop`.
  The parts must sum to totals. Each part's hourly rate must not rise from the
  matched baseline, including commit failures even when projection errors fall.
  Long-soak deltas are divided by their window duration. This implements lead
  6418ac; existing recoverable pressure is neither zeroed nor an automatic trip.
- `serving`: all six surface names from the checker, each a list of every
  traffic-receiving revision/image. Each record has `release_sha`,
  `image_digest`, `share_percent` (sum 100), `ready`, and `effective_env`.
  Cloud Run uses `status.traffic` and those revisions' release identity, never
  the newest service spec. GKE uses ready pods/images and effective flags,
  including all running images during a roll. Omitted default-on custody must
  be verified from the exact image source before recording effective `true`.
- `quality`: batch_stt, shadow_wer, speech_redrive, playback, audio_merge,
  decode_failed; each has `passed` plus a linked `evidence_ref`. Require flat
  success/quality and errors, with decode_failed near zero; no unmeasured pass.
- Regional steps additionally need `iam` and `dual_list`, each with `passed`
  and `evidence_ref`. IAM evidence covers all runtime writer identities and
  effective create/read access, not merely a bucket binding. Non-admitted
  owners' dual-list calls must stay flat; use aggregate cohort evidence.

GCS metric: `storage.googleapis.com/api/request_count`, `gcs_bucket`,
`response_code=OK`, bucket `omi-private-cloud-sync`, method `WriteObject`.
Sum disjoint deltas; never sum cumulative snapshots. Also record ListObjects
for private-sync/syncing-local and WriteObject on omi-audio-derived-uc1.
PCM metric: `omi_audio_archive_pcm_writes_avoided_total`; use reset-aware
window increases, split by serving service. Custody: corresponding
`omi_audio_custody_{commits,failures,would_drop}_total` counters on listen/pusher.

The historical 120–140k WriteObject/h target was an estimate. #23656 deployed
2026-10-26 03:38Z; the latest full hour at 2026-10-27 04:22Z was ~302k/h, down
from 1.345M/h before the roll. The old target is **not passed**. A lead baseline
ruling is required before stop-5; do not rewrite that finding as acceptance.
Lead ruling 658331 accepted ~302k/h, then 6418ac required a fresh post-06Z-roll
matched-hour custody baseline. The pre-roll 03:44–04:44Z pusher snapshot had
projection/transient ~1477, commit/other ~3, queue would_drop ~196; it is
context, not the new step's acceptance baseline.

## Savings reporting

After every step, post the observed write/avoidance/replication changes and
monthly estimate to plans-cost with its report reference. Label a modeled
write delta separately from realized savings. October 25 billing measured
multi-region Standard Class A at $9/M requests. A comparable reduction of
`D` writes/hour models `D * 24 * 30 * 9 / 1e6` dollars/month, but LIST requests,
replication and traffic also change: the gross delta is not causal net saving.
Confirm net savings with complete D+1 billing by bucket/SKU, including added
regional charges; do not extrapolate an incompletely exported day. Until a
step is live and measured, realized ramp savings are $0. The separate #23632
lifecycle freeze remains in force (earliest hard-delete 2026-10-29); this
runbook grants no lifecycle or deletion authority.
