# 2026-11-14: end-of-recording proof for uploaded audio

## What changed

- New route `POST /v2/sync-capture-end`. The phone states that a recording ended, when its last speech was,
  and how many sealed files are still not accepted. Stored as `capture_end` on the recording-session document.
- `processing_hold.admission` skips the arrival-quiet wait (outcome `end_proof`) when that marker proves the
  recording's speech has fully landed on the row. Everything else about the hold is unchanged.
- The lifecycle ledger gains `end_observed_at` and a `record_end` writer. Server-known ends are typed at the
  instant a finalization intent is accepted: client finalize is `user_initiated`, server recovery is
  `silence_backstop`, a bare capture end stays `unknown`. A known end is never replaced by a weaker one.
- `X-Omi-Upload-Trace` on `/v2/sync-local-files` feeds `omi_sync_seal_to_accept_seconds{gate}`.
- `end_silence_seconds` on the `mobile_batch_admission` status event tells a phone how long without speech
  ends a recording.

## Why

Notes on uploaded audio waited 600 s after the last content arrival because the server could not tell an
ended recording from one with uploads still coming. The phone knows. The uploaded audio does not always land
in the conversation bound to the recording, so the marker lives on the session and is read at admission.

## Clocks

The marker's times are on the phone clock. An upload from a phone whose clock runs ahead of the server is
stored shifted onto the server clock by a per-request offset (production median 171 s, see
`utils/sync/capture_clock.py`), so comparing the two directly would call a complete recording
`content_behind`. The sync writer now passes the shift it applied to assignment, and the hold state keeps it
(`content_clock_offset`) beside the row end it applies to (`content_clock_end`) whenever that arrival sets the
row's end. The proof adds it back, so both sides are on the phone clock and the 5 s tolerance is unchanged.
A row that was never shifted carries neither field. If the row's end no longer matches the recorded one, the
result is `clock_unknown` and the quiet wait applies. No extra read or write: the two numbers ride on the
assignment write that already happens.

## Reads and writes

Per recording: one or two calls, each one transaction with one read and at most one write on the session
document, plus one ledger transaction (one read, one write) when the marker is new. At admission: one read of
the session document per evaluation that would otherwise wait, only for rows carrying a recording session id.

## Kill switch and rollback

`SYNC_UPLOAD_WATERMARK_ENABLED=false` (default on): the route stores nothing, admission reads nothing, phones
get no silence timer. Old clients send nothing and keep today's behaviour.

## Readback

`omi_sync_capture_end_proof_total{result}` share `proven`; `omi_sync_processing_hold_total{outcome="end_proof"}`;
conversations with `late_runs > 0` against their baseline; `home_ready_at - end_at` from the ledger census.
