# Record custody wait and drain retry logs carry a hashed recording key

Log-only change; no status, body, retention or admission behavior changes.

- `event=sync_record_upload outcome=pending` adds `record=<16 hex>`: a prefix of
  the record content hash `sha256("record-v1:{uid}:{cid}")`, which is also the
  intake key `bp_<content>`. Waits raised before the record identity is known
  (owner context mismatch, target unresolved, owner claim raced) log `record=-`.
- `event=batch_live_admission outcome=retry` adds `segment=<16 hex>`: a prefix
  of the record_pending segment id, itself a content hash.

Why: on 2026-11-07 record_capture_pending stayed near 2.3k per 15 minutes after
the account-pause fix, about half record_jobs_missing and half
audio_coverage_unproven. Neither line carried any per-recording key, so a read
could not tell one stuck recording retried thousands of times from thousands of
recordings, nor join a pending upload to its drain retry reason, without
row-level reads of user data. Both keys are one-way hashes; no uid,
conversation id, audio or error text is logged.
