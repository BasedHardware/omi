# v3 size quarantine and alias slim (SCA-2918)

Under `afab9560`, 12 owners stayed parked on `document_too_large`. The transcript cap engaged, but
the oversize documents were ones it does not measure:

- finished derived rows near 1 MiB from recording-alias `legacy_ids` (up to 128 per file);
- transcript-heavy rows that predate the cap;
- source recordings already at the limit.

`_oldest_pending` re-seeded the same recording every backoff, so one closure froze each owner's
backlog.

- `CONVERSATIONS_V3_SIZE_QUARANTINE` (default on): a one-seed pass Firestore rejects for size
  records that seed in the builder lease's `v3_size_quarantine` (at most 64). Live loads seed past it,
  and the next seed runs on the following wake.
- `CONVERSATIONS_V3_ALIAS_SLIM` (default on): recording aliases stop copying `legacy_ids`.

Rollback: set either switch off on the builder runners. Readback: owners parked on
`document_too_large` among owners with pending rows older than 1 h fall to 0. Their pending rows
fall to the quarantined ids, which are the repair list.
