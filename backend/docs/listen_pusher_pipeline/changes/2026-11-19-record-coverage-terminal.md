# A final record's unproven WAL gets a terminal keep-local answer

Contract: "named safety WALs and recording-session WALs" in
[`../../listen_pusher_pipeline.mdx`](../../listen_pusher_pipeline.mdx).

## Why

On 2026-11-19 backend-sync answered about 10,200 `POST /v2/sync-local-files`
requests per 10 minutes with 503 `record_capture_pending` (unsampled request
log, 07:42–07:52Z). About 94% were `audio_coverage_unproven`, spread over about
2,350 distinct recordings in one hour. Every one of those recordings was
`completed` and `record_audio_closed`; 83% were sealed and 70% had not been
resealed for 6 hours or more. Some started 30 days earlier.

`_covered` in `utils/batch_pipeline/live_upload.py` is a pure function of the
WAL bytes, the record's job list (`intakes/bp_<content>.segment_ids`) and those
jobs' pinned artifacts. Once a record is sealed and no longer changing, the same
WAL gets the same negative on every retry, yet the answer stayed the retryable
503. The 2026-11-11 coverage memo only skips recomputing that negative; it
returns the same 503, so the phone kept retrying every 30 seconds and the app
showed uploads waiting indefinitely. About 65% of the negatives are
`audio_bytes_differ` (independently decoded Opus against the record's PCM), the
rest `wal_audio_past_record` / `wal_audio_outside_record`.

## What

When coverage is unproven (a fresh negative or a memo hit) and the record is
final, the upload gets HTTP 400:

```json
{"code": "record_capture_unprovable", "detail": "...keep the local copy", "retryable": false}
```

Final means: `record_audio_closed`, not `record_audio_partial`, no
`record_upload_sessions`, no `record_seal_refused_at`, not deleted, and both
`finished_at` and `record_sealed_at` at least `COVERAGE_FINAL_AFTER_SECONDS`
(6 h) old. The known paths that add units to a record (a reconnect reopening
it, a late producer session, a partial continuation, a seal or reseal moving
`record_sealed_at`) all clear one of those conditions and restart the clock. If
an unknown path changed units later anyway, the phone's daily re-offer would
still pick up the new proof within seven days. Anything else, including
coverage-check errors and unreadable clocks, keeps the 503.

The sync route's provenance read (`PROVENANCE_FIELDS`) now also projects those
record markers, so the router sees them without another document read.

## Shipped clients

- Current builds treat 400 as a definitive refusal: the WAL is kept, marked
  refused (no user attention, no Retry), and re-offered at most once a day for
  seven days. A later proof is still accepted on one of those attempts.
- Mid-October builds mark the WAL rejected and keep it.
- Builds from before mid-October raise a generic upload error and keep the WAL
  pending under their retry budget.

No shipped build deletes or releases audio on a 400; only a 200 or a completed
202 does. Unknown `code` values map to the closed `server_refused` token.

## Telemetry and rollback

- Log: `event=sync_record_upload outcome=terminal reason=audio_coverage_unproven record=<16 hex> path=coverage memo=<hit|miss|off>`.
- Counter: `omi_pipeline_record_coverage_terminal_total{memo}`.
- Readback: the unsampled request-log 503 count for `POST /v2/sync-local-files`
  on backend-sync (the `omi_pipeline_upload_admission_503` log metric) falls,
  with a matching transient rise in 400s that decays as phones stop re-offering.
- Rollback: `SYNC_RECORD_COVERAGE_TERMINAL=false` restores the 503 for every
  unproven WAL. Refused WALs stay on the phone.
