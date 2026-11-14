# Audio silence census — 2026-11-10

## What and why

The lifecycle observer now reports `omi_audio_silence_census{state,source}`:
unique users with app activity but no recent audio, app activity with audio,
or audio without app activity. The rolling window is 24 hours and sources are
only `omi`, `desktop`, `other`. The intended signal is silence/orphan prevalence,
not recording correctness or custody disposition.

The observation uses recent conversations, stage-qualified batch jobs and
`sync_reprocess_outbox`. It never lists GCS, exports UID labels or writes account
state. Three indexed 300-row pages and candidate `COUNT(1)` checks share a hard
4,000-read ceiling. Full pages and unseen upload-session maps make counts
partial; unclassifiable users are omitted, not counted as silent. Under
saturation, source attribution covers only source-bearing rows actually read;
other candidates fold to `other`. See
`backend/charts/monitoring/lifecycle-alarms.md#audio-silence-census` for exact
metric and partial semantics.

## Runtime and rollback

`AUDIO_SILENCE_CENSUS_ENABLED` is a registered runtime environment `ops_kill`.
Unset is **on**; the literal string `false` disables subsequent observations.
No runtime deployment binding, Cloud Run service or scheduler is added. The
existing batch/pusher metrics refresh supplies a six-hour per-observer cadence.
Rollback sets the flag to `false`; previous gauge values age out and no audio,
admission, capture or repair behavior changes. Remove the emitter after rollback
if the stale gauges themselves must disappear immediately.

## States and exits

- `app_active_no_audio`: exits when batch-job, received-audio, upload-session
  or outbox evidence is found, when app activity ages out, or when evidence is
  incomplete and the user becomes unclassified.
- `app_active_with_audio`: exits when all activity/audio evidence ages out; it
  can become `audio_no_app_activity` when only app activity ages out.
- `audio_no_app_activity`: exits when conversation/batch activity is found or
  the audio evidence ages out.

These are observations only, not persisted lifecycle phases. No alert threshold
is added until a baseline exists.
