# 2026-11-16: a sealed live record proves its own end

## What changed

- `utils.sync.capture_end.seal_proof` (pure) and `sealed` (kill switch + metric): a completed `batch_live_v1`
  row with a closed record barrier and a projected record transcript, and no notes yet, is proven ended.
- `database.capture_end.proven` asks the seal first, with no read, then the phone marker as before. Both
  hold admissions that already pass `end_proven` (enrichment callback, legacy sync pipeline) get it.
- Complete-record notes scheduling in projection passes the same proof to `processing_hold.admission`
  (`RECORD_NOTES_EAGER_ENABLED`, still off in prod), so a sealed record's completion is due now.
- `CaptureEndProofOutcome.SEALED` (`omi_sync_capture_end_proof_total{result="sealed"}`).

## Why

Prod, 2026-11-16, one user's batch-owned mobile recordings: the record's own transcript lands about 1.5 to
5 minutes after the seal, but a phone or pendant copy (`sync_vad`) that merges into the live target restarts the
600 s arrival-quiet clock. Live recordings send no `/v2/sync-capture-end` marker (their recording-session documents
carry no `capture_end`), so admission always fell back to the quiet rule. One 34-second recording: sealed 03:17:45,
transcribed 03:22:52, notes 04:08:27; its outbox row's last deferral was `quiet_wait`. Four recordings that night
went from audio end to notes in 6.7, 14.7, 29.7 and 30.4 minutes.

## Scope

The seal proves the server's capture ended. It says nothing about a pendant copy still uploading, so it covers the
first notes only. Content that lands after notes starts a normal hold epoch: quiet wait, then at most
`MAX_LATE_RUNS` (1) automatic re-run if the change is material; unchanged and immaterial rules are unchanged. Pure
sync uploads and `batch_sync_v1` records keep the quiet rule.

Not changed: the 120 s first-summary deadline on per-unit projection marks, live-episode member-notes deferral,
and a sync mark that lands after the record's own mark (it still schedules its wake at +quiet; the proof applies
at the next claim, as for the phone marker).

## Kill switch and rollback

`SYNC_UPLOAD_WATERMARK_ENABLED=false` turns off both the phone marker and the seal proof. No data migration.

## Readback

`omi_sync_capture_end_proof_total{result="sealed"}`; `omi_sync_processing_hold_total{outcome="end_proof"}`;
`noted.at - transcribed.at` in `users/{uid}/pipeline_ledger` for `batch_live_v1` rows; `late_runs > 0` share.
