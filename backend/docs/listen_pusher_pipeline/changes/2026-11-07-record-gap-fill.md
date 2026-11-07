# Closed records with a missing retained tail are filled from the owner's WAL (dark)

Ships with `RECORD_GAP_FILL=off` and `RECORD_GAP_FILL_PERCENT=0`: no behavior
changes until both are set. Responses never change: the upload still gets the
503 `record_capture_pending` until the record admits, and the WAL is released
only by the existing byte-exact `_covered` proof on a later upload.

Why: about 300 closed recordings were in a circular wait on 2026-11-07. Their
retained audio under `chunks/{uid}/{cid}/` was empty or stopped before
`finished_at`, so admission refused every 60 s (`retained capture not durable
yet` / `retained capture tail not durable yet`, ~16.2k retries in 52 minutes,
the same records each minute) and the obligation has no TTL. The owner's phone
still held the audio, but its upload reached `record_jobs_missing` and kept
the WAL. Nothing ever wrote the missing span to the server.

What: in `registered_record_response`'s `if not jobs:` branch,
`utils/batch_pipeline/record_gap_fill.fill_closed_record_gap` writes the WAL
audio for the missing span as new retained objects, and the drain's next
normal pass admits the record. Admission, `validate_record_tail`, barriers, the
drain and projection are unchanged.

Gates (all required): switch and uid cohort; owner context (checked earlier in
the function: same uid path, source and capture device); no record jobs;
`require_record_audio_barrier` passes and the row is not partial, deleted,
discarded or sync-disabled; finished, and the row unwritten, for at least 300 s
(`CLOSED_MIN_SECONDS`); a (record, WAL) Redis marker for 600 s (a Redis error
counts as no marker); admission's own retained walk ends more than 0.1 s before
`finished_at`; the `check_privacy` fence.

Written: the decoded WAL PCM inside `[retained end, finished_at + 1 s]`, or from
`started_at - 1 s` when nothing is retained; at most 3600 s per request, in
objects of at most 300 s. Each object is lossless PCM16 at
`chunks/{uid}/{cid}/{start:.6f}.bin` (`.enc` for enhanced protection), with
span metadata and `source=phone_wal`, `rendition=gap-fill-v1`, `record=` and
`wal=` hash prefixes. The write is create-only with no overwrite fallback.

Who wins a key or a frame: every other `chunks/` writer uses 3-decimal names,
so no writer can address a gap-fill object and a fill never addresses theirs.
A late pusher write after a fill creates its own object; the fill object's
bytes and generation never change. In admission's walk the object listed first
owns overlapping frames: a later-starting pusher object only adds frames past
the fill; one starting at the same instant lists first, so retained server
audio stays authoritative for the frames it carries. A fill never starts
before the retained end, so it never overlaps retained audio at write time.

Not durable vs not yet visible: GCS object listing is strongly consistent, the
fill waits 300 s after the last row write, and the stuck records were refused
on every retry for the full window, so the refusal is a missing tail, not
listing lag.

Telemetry: `event=sync_record_gap_fill outcome=<written|skipped_gate|skipped_recent|skipped_marker|skipped_retained|skipped_no_gap|skipped_no_audio|skipped_collision|failed> record=<16 hex> seconds_bucket=<0-10|10-60|60-600|600+>`
and `omi_record_gap_fill_total{outcome}`. No uid, conversation id, audio or
error text is logged.

Ramp: 1, 10, 50, 100 percent, at least 30 minutes per step, with lead2's go at
each. Stop on `conflicting retained audio overlap` retries for filled records,
a rise in admission errors, or a `_covered` failure after a fill for the same
`record=` key. Rollback is `RECORD_GAP_FILL=off`; the tagged objects stay and
are ordinary retained audio for that record (never deleted, per the raw-audio
rule).

Not in this change: admitted records whose WAL holds audio the record lacks or
does not match (`audio_coverage_unproven`, phase 2).
