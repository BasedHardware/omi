# Provider admission: a day-late upload is still fresh (2026-11-13)

## What was wrong

Provider admission stamped `fresh_capture` with the bar the GPU lane uses: capture ended at most
600 seconds before admission. Since the provider backlog hold (#25204), a provider-route row that
is not stamped fresh does not commit. It cannot commit in plain order either: nearly every
provider owner has older held rows in front of it, and the merge takes an owner's rows in capture
order. So a provider recording that synced more than 10 minutes late was transcribed and then
never delivered.

Measured in production on 2026-11-13 (job metadata, counts only), provider-route units admitted
between 16:37Z and 17:13Z: 1,195. On time: 1,028, of which 275 committed. Late: 167 (14%), of
which 0 committed; 150 of them were transcribed and waiting. By lag: 36 within an hour, 67 between
an hour and a day, 64 over a day.

## Change

`BATCH_PIPELINE_PROVIDER_FRESH_CAPTURE_LAG_SECONDS`, default 86400, read at provider admission
(`utils/batch_pipeline/provider_stt_admission.py`). A provider upload admitted within that lag of
its capture end is stamped fresh and commits ahead of the held backlog like any fresh row. The GPU
lane keeps `FRESH_CAPTURE_LAG_SECONDS` (600).

`omi_batch_pipeline_provider_admissions_total{merge_class, lag}` counts provider admissions by
class (`fresh`, `catch_up`) and lag (`lt10m`, `lt1h`, `lt24h`, `ge24h`). It is counted per
transaction attempt, so a retried admission can count twice.

## What it does not do

- It does not reclassify rows already admitted. The stamp is written once, at admission.
- Uploads more than a day late stay catch-up and wait for the metered release.
- A fresh row is not subject to the catch-up depth hold, so one owner's day-late bulk sync commits
  as fast as its units settle. That is bounded by that owner's upload.

## Other readers of the stamp

For a provider row, `fresh_capture` is read by the merge (`_catch_up`, `_backlog_held`, the
fresh-first probe and its query) and by `projection_hold_policy.quarantines_assignment_conflict`,
which treats a row stamped not-fresh as the `backfill` lane and everything else as `fresh` when it
decides whether a conflict that waits on another writer holds or keeps retrying. That rule is kept
as it was: a provider row stamped fresh with lag over 600 seconds also carries `late_upload: true`,
and the policy treats it as `backfill`. The only other readers are test code
(`testing/pipeline_sim/store.py`, `testing/batch_replay`).

Fresh-first is not a guarantee for every owner: behind a fresh GPU head that is not ready yet, a
fresh provider row waits for that head in capture order. That was already so for on-time rows.

## Off switch

`BATCH_PIPELINE_PROVIDER_FRESH_CAPTURE_LAG_SECONDS=600` on backend-sync restores the shared bar
for new admissions. Rows stamped meanwhile keep their stamp.
