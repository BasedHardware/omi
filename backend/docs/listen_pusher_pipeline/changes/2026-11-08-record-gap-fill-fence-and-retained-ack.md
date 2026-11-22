# Gap-fill admission fence and retained-copy ack (option A)

**Admission fence.** The closed-record gap fill now takes the drain's own lease
before it writes. In the claim transaction it sets the `record_pending` job's
`available_at` to `now + FILL_LEASE_SECONDS` (600 s); `due` and the drain's
`claim` skip the row until then, so no admission lists retained audio mid-fill.
A live lease is reported `skipped_busy` and nothing is written. The write stops
on a piece boundary `LEASE_MARGIN_SECONDS` before the lease ends, measured
from before the gates, and each piece upload is bounded inside that margin. A
cancelled request leaves the lease to lapse rather than releasing it under a
storage thread that may still be writing. After the
write, one transaction re-checks privacy and that the job is still
`record_pending` under this exact lease, then releases it to the claim's clock.
If either check fails the outcome is `raced` and the lease is left to whoever
moved the job. A create collision is always `skipped_collision`, even after
earlier pieces landed.

**Option A.** Behind `RECORD_RETAINED_ACK` and `RECORD_RETAINED_ACK_PERCENT`
(both default off), a jobs-missing upload whose fill outcome is `written`,
`skipped_no_gap`, `skipped_no_audio` or `skipped_marker`, with a clean settle,
gets the existing covered 200 if `record_retained_ack.prove` passes. The proof
re-lists `chunks/` and counts only lossless single-chunk `.bin`/`.enc` objects
at 16 kHz in the private-cloud-sync or derived audio bucket, read pinned to the
listed generation. Every WAL sample, decoded once per file (decoding consumes
the upload), must equal the sample at the same capture time in a counted
object, inside `[started_at - 1 s, finished_at + 1 s]`. Privacy is re-checked
after the read. Any other result keeps today's 503. No state is written, so a
retry gets the same answer.

No lifecycle rule can delete a counted object. In the applied rules and in
`deploy/storage-lifecycle/prod.json`, the private bucket's only `chunks/` rules
are a Coldline transition for `.batch.*` and a delete of noncurrent `.opus.enc`
versions; neither suffix is ever counted, and the delete never touches a live
object. The derived bucket has no rules. The batch staging bucket, which
expires objects at 30 days, is never listed or counted.

Counters: `omi_record_gap_fill_total{outcome}` gains `skipped_busy` and `raced`;
`omi_record_retained_ack_total{outcome}` is new. Both pass closed enums through
`reason_label`; logs carry only the 16-hex record key. Coverage is in
`test_record_gap_fill.py`: hermetic, not deployment evidence. See the
[recording pipeline contract](../../listen_pusher_pipeline.mdx).
