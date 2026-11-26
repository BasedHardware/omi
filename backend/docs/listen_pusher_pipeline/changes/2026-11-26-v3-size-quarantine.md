# v3 size quarantine and alias slim (SCA-2918)

Under `afab9560`, 12 owners stayed parked on `document_too_large`. The transcript cap engaged, but
the oversize documents were ones it doesn't measure:

- finished derived rows near 1 MiB from recording-alias `legacy_ids` (up to 128 per file);
- transcript-heavy rows that predate the cap;
- source recordings already at the limit.

`_oldest_pending` re-seeded the same recording every backoff, so one closure froze each owner's
backlog.

- `CONVERSATIONS_V3_SIZE_QUARANTINE` (default on): a one-seed pass Firestore rejects for size records
  every pending recording it loaded in the builder lease's `v3_size_quarantine` (all or nothing, at most
  64), so seeds sharing that closure are set aside together. Closures still load quarantined rows, so
  claims are never filtered. Live seeding, the pass chain and the sweep skip them. The next independent
  seed runs on the following wake.
- `CONVERSATIONS_V3_ALIAS_SLIM` (default on): recording aliases, including retained ones, stop carrying
  `legacy_ids`.

Rollback: set either switch off on the builder runners.

Readback, as two numbers that are never added together:
- **owners recovering:** parked `document_too_large` owners whose park cleared and whose
  non-quarantined pending rows older than 1 h are draining;
- **work quarantined:** ids in `v3_size_quarantine`, owners holding any, and owners whose list is full.
  Quarantined work stays unrepaired until the oversize document is fixed.
