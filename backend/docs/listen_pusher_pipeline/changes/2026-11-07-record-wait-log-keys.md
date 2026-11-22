# Record custody wait and drain retry logs carry a hashed recording key

Log-only change; no status, body, retention or admission behavior changes.

- `event=sync_record_upload outcome=pending` adds `record=<16 hex>`: a prefix of
  the record content hash `sha256("record-v1:{uid}:{cid}")`, which is also the
  intake key `bp_<content>`. Waits raised before the record identity is known
  (owner context mismatch, target unresolved, owner claim raced) log `record=-`.
- `event=batch_live_admission outcome=retry` adds the same `record=<16 hex>`
  key, from the record_pending job's `record_content_id`, so a pending upload
  joins its drain retry reason.
- New `event=sync_record_coverage outcome=unproven cause=<cause>` before an
  `audio_coverage_unproven` wait, with a static cause:
  `wal_audio_outside_record` (WAL audio before or between record units),
  `wal_audio_past_record` (WAL runs past the record's last unit),
  `audio_bytes_differ` (overlapping samples differ), or `record_unit_exhausted`.

Why: on 2026-11-07 record_capture_pending stayed near 2.3k per 15 minutes after
the account-pause fix, about half record_jobs_missing and half
audio_coverage_unproven. Neither line carried any per-recording key, so a read
could not tell one stuck recording retried thousands of times from thousands of
recordings, nor join a pending upload to its drain retry reason, without
row-level reads of user data. The coverage cause separates a phone holding
audio the record lacks from a decode or alignment mismatch. Both keys are
one-way hashes; no uid, conversation id, audio or error text is logged.
